#!/usr/bin/env python3
"""The runner setup cannot quietly lose its safety properties.

    python3 tests/runner_setup.py

Three things make a self-hosted runner safe here, and all three fail SILENTLY --
the runner keeps working, jobs keep passing, and the property is gone:

  --ephemeral   dropped, and every job inherits the last one's checkout and tokens
  runner group  widened, and a public repo's fork PR runs on our network
  disk timer    removed, and the box dies in a fortnight

None of them produce an error when they go missing, which is exactly why they
are asserted here rather than trusted to a runbook.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "runners"
DOC = ROOT / "docs/self-hosted-runners.md"
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


def code_only(text: str) -> str:
    """Strip comments before asserting on a script.

    Every one of these scripts explains in a comment why its flag matters, so a
    naive substring check passes on the comment while the flag itself is gone.
    Removing `--ephemeral` from the command survived this suite for exactly that
    reason: the paragraph above it still said the word.
    """
    return "\n".join(
        l for l in text.split("\n") if not l.lstrip().startswith("#")
    )


run = code_only((R / "run-ephemeral.sh").read_text())
unit = code_only((R / "actions-runner.service").read_text())
tmpl_raw = (R / "actions-runner@.service").read_text()
tmpl = code_only(tmpl_raw)
disk = code_only((R / "reclaim-disk.sh").read_text())
timer = (R / "reclaim-disk.timer").read_text()
doc = DOC.read_text()

# --- ephemeral ------------------------------------------------------------
check("the runner registers as --ephemeral", "--ephemeral" in run,
      "without it one registration serves every job and the isolation is gone")
check("it re-registers per job rather than reusing a token",
      "registration-token" in run and "./run.sh" in run)
check("systemd restarts it, because exiting after a job is SUCCESS",
      "Restart=always" in unit,
      "without this the runner exits after one job and never comes back")

# --- the group is the control that keeps public repos out ------------------
check("the runner joins a named group, not the default",
      "--runnergroup" in run and "RUNNER_GROUP" in run,
      "the default group is every repository, including the public ones")
check("the group is required, not defaulted",
      re.search(r'\$\{RUNNER_GROUP:\?', run) is not None,
      "a defaulted group would silently fall back to something wider")

# --- disk -----------------------------------------------------------------
check("a disk reclaim timer exists", "OnCalendar=hourly" in timer)
# The escalation itself -- which tier deletes what, and never under a running
# job -- is driven for real by tests/reclaim_disk.py. These only pin the shape.
check("reclaim escalates rather than nuking every time",
      "DISK_WARN_PCT" in disk and "DISK_CRIT_PCT" in disk,
      "a warm cache saves real time on a slow uplink; drop it only when the disk is the problem")
check("it FAILS when the disk is still full after cleaning",
      "exit 1" in disk,
      "a silent failure here surfaces later as unrelated-looking job failures")
check("...and does not dress that up as a GitHub annotation",
      "::error::" not in disk and "::warning::" not in disk,
      "reclaim-disk runs under systemd, where `::error::` is a literal string in a "
      "journal nobody reads. That is how it failed every hour for six weeks unseen")
check("reclaim finds every runner by directory, not from RUNNER_DIR",
      "actions-runner-*" in disk and "RUNNER_DIR" not in disk,
      "the env file still names the old single-runner directory; reading it is "
      "how the previous version cleaned nothing for six weeks")
# The script refuses to follow links -- tests/reclaim_disk.py plants them and
# watches. This is the second wall: root deleting in job-writable directories,
# with everything outside /opt read-only to it should the first ever give.
for name in ("reclaim-disk.service", "actions-runner-revive.service"):
    u = code_only((R / name).read_text())
    exe = re.search(r"^ExecStart=(\S+)", u, re.M)
    check(f"{name} runs as root a script only root can write",
          exe is not None and "User=" not in u and not exe.group(1).startswith("/opt/"),
          "the runner user owns /opt/actions-runner; a root script there is a root "
          "shell for anything that runs as that user")
reclaim_unit = code_only((R / "reclaim-disk.service").read_text())
check("reclaim runs as root in a sandbox where only /opt can be written",
      re.search(r"^ProtectSystem=strict$", reclaim_unit, re.M) is not None
      and re.search(r"^ReadWritePaths=/opt$", reclaim_unit, re.M) is not None,
      "it deletes inside directories every job can write; one followed link "
      "outside /opt must hit a read-only filesystem, not the machine")

# --- a runner that is not ready waits; it does not exit -------------------
check("run-ephemeral.sh waits for readiness instead of exiting",
      "wait-until-ready.sh" in run and "check-throughput.sh" not in run,
      "every exit counts toward StartLimitBurst; twenty refusals stop the runner for good")
revive = (R / "actions-runner-revive.timer").read_text()
check("a revive timer gives failed runners another chance",
      "OnUnitActiveSec" in revive and "OnBootSec" in revive and "timers.target" in revive,
      "StartLimitBurst stops a runner for good; on 2026-11-10 nobody came for eight days")
check("the unit points no runner at a shared tool cache",
      "RUNNER_TOOL_CACHE" not in tmpl and "AGENT_TOOLSDIRECTORY" not in tmpl
      and "hostedtoolcache" not in tmpl,
      "setup-uv cannot be redirected once the runner fixes the directory: the day "
      "uv 0.12.21 shipped, every Python job failed writing to the shared one")

# --- the rules are written where somebody will read them -------------------
for phrase, why in [
    ("Never a public repository", "rule one"),
    ("Ephemeral, always", "rule two"),
    ("pull_request_target", "rule three"),
]:
    check(f"the runbook states: {phrase}", phrase in doc, why)

check("the runbook says container builds stay off this box",
      "Container jobs stay on GitHub-hosted" in doc,
      "100 GB and image layers do not coexist")

# --- credentials ----------------------------------------------------------
apptok = code_only((R / "app-token.py").read_text())

check("the App path is preferred over a PAT",
      "APP_PRIVATE_KEY_PATH" in run and "app-token.py" in run,
      "a PAT on disk IS the credential, and it belongs to a person")
check("a PAT still works, but warns",
      "::warning::" in run and "GH_TOKEN" in run,
      "blocking the fallback outright strands anyone mid-setup")
check("with no credential at all it refuses rather than guessing",
      "exit 1" in run)
check("the JWT is short-lived",
      '"exp": now + 540' in apptok,
      "a long-lived assertion is a long-lived credential")
check("clock skew is absorbed",
      '"iat": now - 60' in apptok,
      "a fast clock makes every token 'issued in the future' and rejected")
check("errors never echo the JWT or the key path",
      "Never print the JWT" in (R / "app-token.py").read_text(),
      "service logs are easier to read than /etc")

# --- and the units must not run it as root ---------------------------------
check("the service does not run as root",
      "User=runner" in unit and "User=root" not in unit)


# --- ten runners, and the four ways that went wrong ------------------------
#
# Every one of these was found by watching ten instances crash-loop against
# GitHub, not by reading the unit. They share a shape: the runner keeps
# restarting, systemd reports `active`, and nothing registers.
check("the template exists at all", tmpl_raw != "",
      "one runner is a queue of one -- 14 jobs took 28 minutes")
check("each instance gets its own directory",
      "/opt/actions-runner-%i" in tmpl,
      "config.sh writes one registration and _work per directory")
check("RUNNER_DIR is set through /usr/bin/env, not Environment=",
      "/usr/bin/env" in tmpl and "Environment=RUNNER_DIR" not in tmpl,
      "EnvironmentFile wins over Environment=, so the systemd way silently "
      "loses to /etc/actions-runner.env and every instance crash-loops")
check("HOME is per instance",
      "HOME=/opt/actions-runner-%i" in tmpl,
      "a shared ~/.cache/uv gives 'Could not acquire lock' on every Python job")
check("PATH carries pipx's bin directory",
      "/opt/actions-runner-%i/.local/bin" in tmpl,
      "else `pipx install semgrep` succeeds and `semgrep` is not found")
check("pip is allowed to install on a PEP 668 system",
      "PIP_BREAK_SYSTEM_PACKAGES=1" in tmpl,
      "gitops-ci does a bare `pip install pyyaml`; Ubuntu 24.04 refuses it")
check("a persistent failure stops instead of hammering GitHub",
      "StartLimitBurst" in tmpl,
      "ten instances retrying every 5s is a self-inflicted denial of service")
check("the template keeps the hardening the single unit had",
      all(x in tmpl for x in ("User=runner", "ProtectSystem=strict",
                              "NoNewPrivileges=true")),
      "a template is a rewrite, and a rewrite is where hardening is dropped")

# --- the ephemeral loop survives an unclean kill ---------------------------
check("stale local registration is cleared before configuring",
      "rm -f .runner" in run,
      "a runner killed mid-job leaves .runner, and config.sh then refuses "
      "with 'already configured' forever")
check("the runner name is stable per instance, not per process",
      "$$" not in run.split("--name")[1].split("\\")[0],
      "clearing .credentials means it cannot deregister itself, so a PID-based "
      "name orphans a registration every job -- 39 in one afternoon")

# --- the runbook records what the numbers actually were --------------------
check("the runbook says bandwidth is the constraint, not CPU",
      "do not buy more cores" in doc.lower(),
      "the next person will resize the VM again otherwise")
check("the runbook lists the packages the workflows assume",
      all(x in doc for x in ("libpq-dev", "pipx", "python3-dev")),
      "each absence fails somewhere other than the install")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print(f"\nOK: the silent-failure properties are asserted")
