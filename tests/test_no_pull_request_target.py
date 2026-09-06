#!/usr/bin/env python3
"""The ban catches the real thing, and does not cry wolf.

    python3 tests/test_no_pull_request_target.py

A check that flags its own documentation gets deleted by the third person who
hits it. Half of these cases exist to prove it does not.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / ".github/workflows/workflows-ci.yml"
MARKER = "PRT_CHECK"
FAILURES: list[str] = []


def extract(dest: Path) -> Path:
    """The script under test is EXTRACTED FROM THE WORKFLOW, not a copy.

    A reusable workflow only checks out the CALLER's repository, so the check
    has to be inlined rather than shipped as a file -- and a second copy kept
    beside it for testing would drift, silently, into testing something the
    workflow does not run.
    """
    src = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(rf"<<'{MARKER}'\n(.*?)\n\s*{MARKER}", src, re.S)
    if not m:
        sys.exit(f"FAIL: no {MARKER} heredoc in {WORKFLOW.name} -- was the step renamed?")
    body = "\n".join(
        ln[10:] if ln.startswith(" " * 10) else ln for ln in m.group(1).split("\n")
    )
    out = dest / "check.py"
    out.write_text(body)
    return out


def run(files: dict[str, str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        wf = root / ".github/workflows"
        wf.mkdir(parents=True)
        for name, body in files.items():
            (wf / name).write_text(body)
        check = extract(root)
        r = subprocess.run([sys.executable, str(check)], cwd=root,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


# --- it must catch the real shapes ---------------------------------------
code, out = run({"bad.yml": "on: pull_request_target\njobs:\n  a:\n    runs-on: ubuntu-latest\n"})
check("catches the inline form", code == 1, out[:120])

code, out = run({"bad.yml": "on:\n  pull_request_target:\n    types: [opened]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"})
check("catches the block form", code == 1, out[:120])

code, out = run({"bad.yml": "on:\n  push:\n  pull_request_target:\njobs:\n  a:\n    runs-on: ubuntu-latest\n"})
check("catches it alongside another trigger", code == 1, out[:120])

code, out = run({"ok.yml": "on: pull_request\n", "bad.yml": "on: pull_request_target\n"})
check("catches it in one file among several", code == 1, out[:120])

# --- and must NOT cry wolf ------------------------------------------------
code, out = run({"ok.yml": "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest\n"})
check("a normal pull_request workflow passes", code == 0, out[:120])

code, out = run({"doc.yml": "# never use pull_request_target here\non: pull_request\n"})
check("a comment ABOVE the on: block passes", code == 0,
      "the check flags its own documentation, which is how it gets deleted")

# The one that matters: a comment INSIDE the `on:` block. The case above sits
# outside it and passes even with comment-stripping removed, so it proved
# nothing -- a mutation deleting the strip survived the suite.
code, out = run({"doc.yml": "on:\n  # pull_request_target is banned here, see workflows-ci\n  pull_request:\n    types: [opened]\n"})
check("a comment INSIDE the on: block passes", code == 0,
      "warning about the trigger, inside on:, must not itself fail the check")

code, out = run({"doc.yml": "on: pull_request\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo 'pull_request_target is banned'\n"})
check("prose in a run step passes", code == 0, out[:120])

code, out = run({"ok.yml": "on:\n  pull_request:\n    types: [opened]\n\njobs:\n  a:\n    runs-on: ubuntu-latest\n    # pull_request_target would be wrong here\n"})
check("a trailing comment after the on: block passes", code == 0, out[:120])

# --- it must say what to do instead ---------------------------------------
code, out = run({"bad.yml": "on: pull_request_target\n"})
check("the failure explains the alternative", "workflow_run" in out,
      "an error with no way forward gets worked around, not fixed")

# --- and survive a repository with no workflows ----------------------------
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    r = subprocess.run([sys.executable, str(extract(root))], cwd=root,
                       capture_output=True, text=True)
    check("a repo with no workflows is not an error", r.returncode == 0, r.stdout)

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nOK: catches every form, and does not flag prose about it")
