#!/usr/bin/env python3
"""Findings are grouped by what it takes to fix, and unknown means "needs review".

    python3 tests/semgrep_report.py

Semgrep reprints each rule's full description once per occurrence.
The first client repo we adopted came back as 782 log lines
reading like 33 separate problems; it was 8 rules. The fixture here is modelled
on that run.

THE ASSERTION THAT MATTERS is the default. The `MECHANICAL` list is curated --
it claims "a script can fix this", which is not in Semgrep's output and is the
one part of this that can go stale. It must go stale in the SAFE direction: a
rule nobody has classified is reported as needing a human, never as a quick win.
Mislabelling review work as mechanical sends somebody to run a script over a
problem that needed reading.

Summary and annotations are asserted SEPARATELY and never concatenated. They
have opposite jobs -- the summary names a rule once with a count, the
annotations name it once per line -- so a test that reads them as one stream
cannot tell "collapsed" from "repeated". The first version of this file did
exactly that and failed for the wrong reason.

The script under test is EXTRACTED FROM THE WORKFLOW, not a copy kept beside it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/security-baseline.yml"
FIXTURE = ROOT / "tests/fixtures/semgrep-adopted-repo.json"
MARKER = "DATUM_SEMGREP_REPORT"
FAILURES: list[str] = []


def extract(dest: Path) -> Path:
    src = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(rf"<<'{MARKER}'\n(.*?)\n\s*{MARKER}", src, re.S)
    if not m:
        sys.exit(f"FAIL: no {MARKER} heredoc in {WORKFLOW.name} — was the step renamed?")
    body = "\n".join(l[10:] if l.startswith(" " * 10) else l
                     for l in m.group(1).split("\n"))
    out = dest / "report.py"
    out.write_text(body)
    return out


def run(results: list[dict] | None = None) -> tuple[int, str, str]:
    """Returns (exit code, job summary, annotation stream). Kept apart on purpose."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        doc = {"results": results if results is not None
               else json.loads(FIXTURE.read_text())["results"], "errors": []}
        j = d / "semgrep.json"
        j.write_text(json.dumps(doc))
        summary = d / "summary.md"
        r = subprocess.run(
            [sys.executable, str(extract(d))],
            env={**os.environ, "SEMGREP_JSON": str(j),
                 "GITHUB_STEP_SUMMARY": str(summary)},
            capture_output=True, text=True)
        if r.returncode not in (0, 1):
            sys.exit(f"FAIL: the report crashed (exit {r.returncode}):\n{r.stderr}")
        return r.returncode, (summary.read_text() if summary.exists() else ""), r.stdout


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


def finding(check_id: str, fix: str | None = None) -> dict:
    r = {"check_id": check_id, "path": "a.py", "start": {"line": 1},
         "extra": {"message": "m", "severity": "ERROR", "metadata": {}}}
    if fix:
        r["extra"]["fix"] = fix
    return r


MUTABLE_TAG = ("yaml.github-actions.security.github-actions-mutable-action-tag"
               ".github-actions-mutable-action-tag")

# --- the default is the whole point ---------------------------------------
_, md, ann = run([finding("some.rule.nobody.has.ever.classified")])
check("an unclassified rule is 'needs review', not a quick win",
      "Needs a decision" in md and "Mechanical" not in md and "one command" not in md,
      "a stale curated list must fail safe, not send someone to run a script")
check("...and its annotation says so too", "[needs review]" in ann, ann[:120])

# --- the two buckets that DO come from the data ---------------------------
_, md, ann = run([finding("dockerfile.security.missing-user.missing-user",
                          fix="USER nonroot")])
check("a Semgrep autofix is reported as one command",
      "Fixable with one command" in md and "--autofix" in md, md[-200:])

_, md, ann = run([finding(MUTABLE_TAG)])
check("a curated mechanical rule says how, not just that",
      "commit SHA" in md and "Mechanical" in md, md[-200:])

# --- fix instructions must not leak across buckets ------------------------
_, md, _ = run([finding(MUTABLE_TAG, fix="uses: foo@abc")])
check("a fix from Semgrep beats the curated guess",
      "Fixable with one command" in md and "Mechanical" not in md,
      "if Semgrep can do it, don't send a human to do it by hand")

# --- grouping, on the real shape ------------------------------------------
code, md, ann = run()
check("the headline counts rules, not just findings",
      "18 findings across 8 rules" in md, md[:200])
check("worst-first: the decisions come before the quick wins",
      md.index("Needs a decision") < md.index("Fixable with one command"))
check("the summary names a rule ONCE, with its hit count",
      md.count("`secrets-in-config-file`") == 1 and re.search(
          r"`secrets-in-config-file` \| 4 \|", md) is not None,
      f"named {md.count('`secrets-in-config-file`')}x; the point is not "
      "reprinting a rule per hit")
row = next((l for l in md.splitlines() if "`secrets-in-config-file`" in l), "")
check("...and lists the files it hit, deduplicated",
      row.count("k8s/clickhouse.yaml") == 1 and row.count("k8s/dagster.yaml") == 1
      and "ingress" not in row,
      f"4 hits in 2 files should read as 2 files, once each: {row}")
check("it says how many rules avoid reading code entirely",
      "2 of 8 rules can be fixed without reading the code" in md, md[-300:])

# --- annotations ----------------------------------------------------------
check("every finding gets an annotation on its own line",
      ann.count("::error file=") == 18, str(ann.count("::error file=")))
check("the annotations DO repeat per hit — that is their job",
      ann.count("title=secrets-in-config-file") == 4,
      str(ann.count("title=secrets-in-config-file")))
lines = [l for l in ann.splitlines() if l.startswith("::error file=")]
buckets = [re.search(r"\[(.+?)\]::", l).group(1) for l in lines]
check("needs-review annotations come first, for GitHub's ~10 display slots",
      buckets == sorted(buckets, key=["needs review", "mechanical",
                                      "one command"].index),
      " -> ".join(dict.fromkeys(buckets)))
check("every annotation carries a file and a line GitHub can anchor to",
      all(re.match(r"::error file=\S+,line=\d+,title=", l) for l in lines))

# --- exit codes -----------------------------------------------------------
check("findings fail the job", code == 1, f"exit {code}")
code, md, ann = run([])
check("no findings passes, and says nothing about buckets",
      code == 0 and "no findings" in ann and "Needs a decision" not in md,
      f"exit {code}: {md[:80]}")

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print(f"\nOK: grouped by fixability, unknown fails safe ({len(lines)} annotations ordered)")
