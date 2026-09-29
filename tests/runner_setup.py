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
check("reclaim escalates rather than nuking every time",
      "until=24h" in disk and "--volumes" in disk,
      "always dropping every image makes each build cold for no reason")
check("it FAILS when the disk is still full after a full prune",
      "::error::" in disk and "exit 1" in disk,
      "a silent failure here surfaces later as unrelated-looking job failures")

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
