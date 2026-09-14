#!/usr/bin/env python3
"""A conflicted update must not look like a clean one.

    python3 tests/scaffold_update_conflicts.py

Two bugs, both of which produced a GREEN run and the wrong outcome -- the exact
shape this standard exists to stop.

1.  The conflict guard counted `.rej` files. Copier has not written those by
    default since v9; it writes INLINE `<<<<<<<` markers. So every conflicting
    update was reported clean, and dl-assessment-platform pushed a datum-ci.yml
    containing `<<<<<<< before updating` with the run green.

2.  `gh pr view <branch>` matches CLOSED and MERGED pull requests. On a branch
    force-pushed every week, the first run after a bump is merged finds the
    MERGED pull request and edits it -- rewriting the record of what was
    actually merged -- then reports "updated the open pull request", while the
    real update sits on a branch with no pull request at all.
    dl-assessment-platform#483 was merged carrying one tag and retitled to
    another by a later run.

The detector is exercised against real conflicted text rather than only
grepped for, because a regex that matches nothing passes quietly forever.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / ".github/workflows/scaffold-update.yml"
FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {what}")
    if not ok:
        FAILURES.append(what)


def step(job: dict, prefix: str) -> dict:
    for s in job["steps"]:
        if s.get("name", "").startswith(prefix):
            return s
    sys.exit(f"FAIL: no step starting {prefix!r} -- renamed?")


def main() -> int:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = wf["jobs"]["update"]
    render = step(job, "Run copier update")["run"]
    opener = step(job, "Open or update the pull request")

    print("inline markers are detected, not just .rej")
    check("conflicts=" in render, "a conflicts count is computed")
    check("<<<<<<<" in render and ">>>>>>>" in render,
          "it looks for the markers copier actually writes")
    check("rejects=" in render, ".rej files are still counted too")
    check("outputs.conflicts" in str(opener.get("env", {})),
          "the count reaches the pull request step")

    print("\nand the detector really detects")
    # Pull the grep out of the step and run it over a fixture, so this asserts
    # behaviour rather than the presence of a string.
    m = re.search(r"grep -rlE '([^']+)'", render)
    check(m is not None, "the grep pattern can be extracted")
    if m:
        pattern = m.group(1)
        with tempfile.TemporaryDirectory() as d:
            conflicted = Path(d) / "datum-ci.yml"
            conflicted.write_text(
                "jobs:\n"
                "<<<<<<< before updating\n"
                "  uses: x@v1.5.0\n"
                "=======\n"
                "  uses: x@v1.6.0\n"
                ">>>>>>> after updating\n"
            )
            clean = Path(d) / "clean.yml"
            # A file that merely MENTIONS the markers, as this test does, and a
            # markdown heading underline -- neither is a conflict.
            clean.write_text("# talks about <<<<<<< in prose\n"
                             "Title\n=======\n")
            r = subprocess.run(["grep", "-rlE", pattern, "."],
                               cwd=d, capture_output=True, text=True)
            hits = set(r.stdout.split())
            check("./datum-ci.yml" in hits, "a genuinely conflicted file is found")
            check("./clean.yml" not in hits,
                  "a markdown underline and prose are NOT flagged")

    print("\nthe run says so out loud")
    check("::warning::" in render, "a conflicted render raises a warning")

    print("\nand the pull request is unmissable")
    body = opener["run"]
    check("[!CAUTION]" in body, "the body carries a CAUTION admonition")
    check("Do not merge this as-is" in body, "it says not to merge it")
    check("CONFLICTED" in body,
          "the TITLE carries it -- a bump is merged from the list, not the body")

    print("\nonly an OPEN pull request is updated")
    # Comments stripped WHOLE. The comment explaining why `gh pr view` was
    # removed contains the words `gh pr view`, and a naive substring check
    # fails on the very explanation of the fix.
    code = "\n".join(
        ln for ln in body.split("\n") if not ln.lstrip().startswith("#")
    )
    check("gh pr view" not in code,
          "`gh pr view <branch>` is gone from the code -- it matches merged ones")
    check("--state open" in code, "the lookup is restricted to open")
    check(re.search(r"gh pr edit\s+\"?\$\{?open_pr\}?\"?", code) is not None,
          "the edit targets the number the open lookup returned")

    print("\nthe shell parses")
    for s in job["steps"]:
        if "run" not in s:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(s["run"])
            path = f.name
        r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        check(r.returncode == 0, f"{s['name']!r}: {r.stderr.strip()[:50]}")
        os.unlink(path)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
