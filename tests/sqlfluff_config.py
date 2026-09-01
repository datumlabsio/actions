#!/usr/bin/env python3
"""The vendored .sqlfluff must not autofix code into breaking.

`sqlfluff fix` REWRITES SOURCE. A rule that misfires here does not report a
false positive -- it edits the file and the damage ships. Two exemptions exist
for that reason, and both are narrow enough that the rules still bite:

  CP03  ClickHouse function names are case-sensitive and camelCase
        (toDateTime, toStartOfMonth). Lowercasing them produces a name that is
        not a function, and CI on DuckDB never runs those models, so it reaches
        production silently. Setting dialect = clickhouse does NOT help -- CP03
        applies its policy regardless of dialect, which is why this is a regex
        exemption rather than a dialect change.

  RF04  `month` is the idiomatic column on a monthly fact table.

Half these cases exist to prove the exemptions did not disable the rules.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "configs" / ".sqlfluff"

CASES = [
    # (name, sql, rule, should_be_flagged)
    ("ClickHouse toDateTime is left alone",
     "select toDateTime(a) as b from t", "CP03", False),
    ("ClickHouse toStartOfMonth is left alone",
     "select toStartOfMonth(a) as b from t", "CP03", False),
    ("COUNT is still flagged",
     "select COUNT(*) as n from t", "CP03", True),
    ("Sum is still flagged",
     "select Sum(a) as n from t", "CP03", True),
    ("a camelCase name that is not to* is still flagged",
     "select myHelper(a) as b from t", "CP03", True),
    ("month is left alone",
     "select t.a as month from t", "RF04", False),
    ("year is still flagged",
     "select t.a as year from t", "RF04", True),
]


def main() -> int:
    if not shutil.which("sqlfluff"):
        try:
            import sqlfluff  # noqa: F401
        except ImportError:
            print("SKIP: sqlfluff not installed")
            return 0

    text = CONFIG.read_text()
    # The shipped config templates through dbt, which needs a real project.
    # Only the rule settings are under test, so swap the templater.
    text = text.replace("templater = dbt", "templater = raw")

    failures = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / ".sqlfluff").write_text(text)
        for name, sql, rule, want_flagged in CASES:
            f = d / "m.sql"
            f.write_text(sql + "\n")
            out = subprocess.run(
                [sys.executable, "-m", "sqlfluff", "lint", str(f)],
                capture_output=True, text=True, cwd=d,
            ).stdout
            flagged = rule in out
            ok = flagged == want_flagged
            verb = "flagged" if flagged else "clean"
            print(f"    [{'ok' if ok else 'FAIL'}] {name}: {rule} {verb}")
            if not ok:
                failures.append(name)

    if failures:
        print(f"\nFAIL: {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print(f"\nOK: {len(CASES)} cases — both exemptions are scoped, neither rule is disabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
