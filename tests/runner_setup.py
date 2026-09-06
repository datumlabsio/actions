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

# --- and the units must not run it as root ---------------------------------
check("the service does not run as root",
      "User=runner" in unit and "User=root" not in unit)

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print(f"\nOK: the three silent-failure properties are asserted")
