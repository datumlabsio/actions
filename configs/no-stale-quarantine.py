#!/usr/bin/env python3
# datum-config: no-stale-quarantine v1
# Vendored from datumlabsio/actions/configs/no-stale-quarantine.py. Bump it, do
# not edit it.
"""DES §11: a test disabled for flakiness carries an owner and a date.

    A test that fails at random MUST be disabled the same day, with an owner
    and a date to fix or delete it. Random failures teach people to ignore
    red builds.

§12 lists this as CI-enforced. Nothing enforced it, so a quarantined test could
sit disabled forever — which is the failure the rule exists to prevent, arrived
at slowly instead of quickly.

The annotation §11 does not specify a syntax for, so this is the one it reads:

    quarantined(@owner, YYYY-MM-DD): why

on the same line as the skip, or within two lines of it.

    @pytest.mark.skip(reason="quarantined(@humayun-1, 2026-09-03): flaky under xdist")
    it.skip("renders", ...)  // quarantined(@humayun-1, 2026-09-03): timing-dependent

WHAT IS AND IS NOT A QUARANTINE, which is the whole reason this does not cry
wolf. An unconditional skip means "this test is disabled and nobody is looking
at it" — that is a quarantine and needs an owner. A CONDITIONAL skip means
"this test does not apply here", which is a legitimate permanent statement about
the environment, not a deferral. So skipif, importorskip and their equivalents
are exempt; skip and xfail are not.

A gate that flags every platform guard gets switched off in a week.

Usage:  no_stale_quarantine.py PATH [PATH ...]
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

# Unconditional disables: nobody is watching these.
QUARANTINE = re.compile(
    r"""
      @pytest\.mark\.(?:skip|xfail)\b(?!if)   # decorator form
    | \bpytest\.(?:skip|xfail)\s*\(           # imperative form
    | (?:^|[^.\w])(?:it|test|describe)\.(?:skip|failing|todo)\s*\(
    | (?:^|[^.\w])x(?:it|test|describe)\s*\(  # xit / xdescribe
    """,
    re.VERBOSE,
)

# Conditional or environmental: legitimate, permanent, not a deferral.
EXEMPT = re.compile(
    r"""
      @pytest\.mark\.skipif\b
    | \bpytest\.importorskip\b
    | \bskipif\s*\(
    | \.skipIf\s*\(
    | \.runIf\s*\(
    """,
    re.VERBOSE,
)

ANNOTATION = re.compile(
    r"quarantined\(\s*(?P<owner>@[A-Za-z0-9][A-Za-z0-9._-]*)\s*,\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s*\)"
)

SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# This file documents the patterns it searches for, so it matches itself. Same
# reason no_literal_env_values.py carries an allowlist: a checker that flags its
# own examples fails the day its example date passes, which is a confusing way
# to learn nothing is wrong.
SELF = Path(__file__).name

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "coverage",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
}

WINDOW = 2  # lines either side an annotation may sit on


def files(roots: list[str]):
    for root in roots:
        p = Path(root)
        if p.is_file():
            if p.name != SELF:
                yield p
            continue
        for f in p.rglob("*"):
            if f.suffix in SUFFIXES and f.name != SELF and not (set(f.parts) & SKIP_DIRS):
                yield f


def main(argv: list[str]) -> int:
    roots = argv[1:] or ["."]
    today = dt.date.today()
    problems: list[str] = []
    found = 0

    for f in sorted(files(roots)):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for n, line in enumerate(lines):
            if EXEMPT.search(line) or not QUARANTINE.search(line):
                continue
            found += 1

            lo, hi = max(0, n - WINDOW), min(len(lines), n + WINDOW + 1)
            m = None
            for cand in lines[lo:hi]:
                m = ANNOTATION.search(cand)
                if m:
                    break

            where = f"{f}:{n + 1}"
            if not m:
                problems.append(
                    f"{where}: disabled test with no owner or date. DES §11 "
                    f"requires both. Add: quarantined(@owner, YYYY-MM-DD): why"
                )
                continue

            try:
                due = dt.date.fromisoformat(m.group("date"))
            except ValueError:
                problems.append(f"{where}: '{m.group('date')}' is not a real date (YYYY-MM-DD).")
                continue

            if due < today:
                overdue = (today - due).days
                problems.append(
                    f"{where}: quarantine expired {overdue} day(s) ago "
                    f"({due.isoformat()}, owner {m.group('owner')}). "
                    f"Fix the test, delete it, or agree a new date — do not extend it silently."
                )

    if problems:
        print(f"{len(problems)} stale or unowned quarantine(s) (DES §11):\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print(
            "\nA disabled test nobody owns is a test that never comes back. "
            "That is what §11 is for.",
            file=sys.stderr,
        )
        return 1

    print(
        f"No stale or unowned quarantines. {found} disabled test(s) checked, all owned and in date."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
