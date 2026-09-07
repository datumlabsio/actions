#!/usr/bin/env python3
"""The audit reports where we stand, not only what is broken.

    python3 tests/conformance_report.py

An issue tracker answers "what is broken". It cannot answer "where do we stand",
because a conformant repository files nothing and is therefore indistinguishable
from one nobody has ever looked at.

That distinction is the entire rollout question. **1 of 59 and 40 of 59 look
identical in an issue list.** The audit already checked all seven §12 items on
every repository and threw the passes away; this asserts it keeps them.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ca", Path(__file__).resolve().parent / "conformance_audit.py")
ca = importlib.util.module_from_spec(spec)
sys.modules["ca"] = ca
spec.loader.exec_module(ca)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'ok' if ok else 'FAIL'}] {name}{'' if ok else f' — {detail}'}")
    if not ok:
        FAILURES.append(name)


def rep(name, archetype="application", owner="datum-core", failed=()):
    r = ca.Report(repo=name, archetype=archetype, owner_team=owner)
    for f in failed:
        r.fail(f, "why")
    return r


# --- the passes must survive ----------------------------------------------
clean = rep("datumlabsio/polaris", "monorepo", "datum-core", [])
out = ca.summarise([clean])
check("a conformant repo appears in the report", "polaris" in out,
      "if only failures appear, the report cannot show coverage")
check("the headline counts conformant repos", "1 of 1" in out, out[:120])

# --- internal and external are distinguished -------------------------------
out = ca.summarise([clean, rep("client-org/their-app", failed=[ca.SECURITY])])
check("internal and external are counted separately",
      "1 internal, 1 external" in out, out[:200])

# --- worst first, because a name-sorted table buries the point -------------
rows = ca.summarise([
    rep("datumlabsio/aaa", failed=[]),
    rep("datumlabsio/zzz", failed=[ca.SECURITY, ca.PROTECTION]),
]).split("\n")
body = [l for l in rows if l.startswith("| `")]
check("the most broken repo is first, not the alphabetical one",
      "zzz" in body[0], body[0] if body else "<no rows>")

# --- every check gets a column --------------------------------------------
out = ca.summarise([clean])
for _, label in ca.CHECK_COLUMNS:
    pass
header = [l for l in out.split("\n") if l.startswith("| Repo")][0]
check(f"all {len(ca.CHECK_COLUMNS)} checks have a column",
      all(k in header for k, _ in ca.CHECK_COLUMNS), header)

# --- a failed check must not read as "not checked" -------------------------
check("the report says a dash means FAILED, not untested",
      "failed check, not an untested one" in ca.summarise([clean]),
      "a blank cell reads as 'we did not look', which is the opposite of true")

# --- the ownership gap is called out separately ----------------------------
out = ca.summarise([rep("datumlabsio/x", owner=""), clean])
check("repos with no owning team are named",
      "no owning team" in out and "datumlabsio/x" in out,
      "a CODEOWNERS naming a team without write is silently ignored by GitHub")
out = ca.summarise([clean])
check("...and that section is absent when everything is owned",
      "no owning team" not in out, "an always-present warning is furniture")

# --- and it must not claim more than it checks -----------------------------
check("the report says what it cannot see",
      "does not re-run what the repo's own CI decides" in ca.summarise([clean]),
      "a full row of ok must not read as 'this repo is correct'")

# --- degenerate input ------------------------------------------------------
check("no repositories is not a crash", "No repositories audited" in ca.summarise([]))

if FAILURES:
    print(f"\nFAIL: {len(FAILURES)}: {', '.join(FAILURES)}")
    sys.exit(1)
print(f"\nOK: the report shows coverage, not just failures")
