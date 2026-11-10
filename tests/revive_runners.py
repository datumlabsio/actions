#!/usr/bin/env python3
"""A runner systemd gave up on gets another chance; one stopped on purpose
does not.

    python3 tests/revive_runners.py

StartLimitBurst stops a runner that keeps failing -- for good, until a person
runs reset-failed. On 2026-11-10 that person had not come for eight days.
revive-runners.sh runs every fifteen minutes and gives FAILED units one more
round. INACTIVE units are somebody's deliberate `systemctl stop`, and are left
alone; so is anything that only looks like a runner directory.

`systemctl` is stubbed on PATH and records every call.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "runners/revive-runners.sh"
FAILURES: list[str] = []

# runner 2 failed, 3 was stopped on purpose, 1 and 10 are fine.
SYSTEMCTL = r'''#!/usr/bin/env bash
echo "$*" >> "$CALLS"
if [ "$1" = is-failed ]; then
  case "$2" in
    actions-runner@2.service)  echo failed;   exit 0 ;;
    actions-runner@3.service)  echo inactive; exit 1 ;;
    *)                         echo active;   exit 1 ;;
  esac
fi
'''


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' -- {detail}'}")
    if not ok:
        FAILURES.append(name)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    root, stubs = tmp / "opt", tmp / "stubs"
    for n in ("1", "2", "3", "10"):
        (root / f"actions-runner-{n}").mkdir(parents=True)
        (root / f"actions-runner-{n}" / "run-ephemeral.sh").write_text("#!/bin/sh\n")
    (root / "actions-runner-9").mkdir()        # no run-ephemeral.sh: not a runner
    stubs.mkdir()
    (stubs / "systemctl").write_text(SYSTEMCTL)
    (stubs / "systemctl").chmod(0o755)
    calls = tmp / "calls"

    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}",
                            "RUNNER_ROOT": str(root), "CALLS": str(calls)})
    log = calls.read_text().splitlines() if calls.exists() else []

check("exits 0", p.returncode == 0, p.stderr)
check("the failed runner is reset and started",
      "reset-failed actions-runner@2.service" in log
      and "start --no-block actions-runner@2.service" in log, "\n".join(log))
check("a runner stopped on purpose is left stopped",
      not any("actions-runner@3.service" in c and not c.startswith("is-failed") for c in log),
      "\n".join(log))
check("healthy runners are only looked at, never restarted",
      not any(c.startswith(("start", "reset-failed")) and ("@1." in c or "@10." in c) for c in log))
check("a directory without run-ephemeral.sh is not a runner",
      not any("actions-runner@9" in c for c in log))
check("--no-block: one slow unit cannot hold up the rest",
      all("--no-block" in c for c in log if c.startswith("start")))

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: failed runners get another chance; stopped ones stay stopped")
