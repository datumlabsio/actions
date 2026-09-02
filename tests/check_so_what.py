#!/usr/bin/env python3
"""Exercise configs/check_so_what.py.

The rule under test: an exposure declares a DECISION that is a FORK, a WHO and a
WHEN. The interesting half is the refusals -- a gate that only ever passes is not
a gate. "Revenue visibility" is the canonical topic-not-a-decision, and it must
fail; an arrow and the word "whether" must both read as forks, because that is
how people actually write them.

Exposures from installed packages are invisible here, the same scoping
dbt_yaml_coverage.py applies to models.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "configs" / "check_so_what.py"

GOOD = ("DECISION: whether to hold the SLA or tighten it to next-day. "
        "WHO: the operations lead. WHEN: at the weekly review.")


def load():
    spec = importlib.util.spec_from_file_location("sowhat", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def exposure(description=GOOD, *, pkg="fixture", email="o@datumlabs.io"):
    return {
        "name": "orders_review",
        "package_name": pkg,
        "description": description,
        "owner": {"name": "Owner", "email": email} if email else {"name": "Owner"},
        "depends_on": {"nodes": ["model.fixture.fct_orders"]},
    }


def manifest(exp, project="fixture"):
    return {"metadata": {"project_name": project}, "exposures": {"exposure.fixture.e": exp}}


def main() -> int:
    gate = load()
    cases = []

    def check(name, exp, want, project="fixture"):
        bad = gate.audit(manifest(exp, project))
        cases.append((name, bad, want))

    # --- passes ---------------------------------------------------------------
    check("a real decision fork passes", exposure(), 0)
    check("an arrow reads as a fork",
          exposure("DECISION: revenue 20% under plan -> hiring pause. "
                   "WHO: CEO, CFO. WHEN: 1st business day."), 0)

    # --- refusals: the half that matters --------------------------------------
    check("a topic with no fork fails",
          exposure("DECISION: revenue visibility. WHO: CEO. WHEN: monthly."), 1)
    check("no DECISION fails",
          exposure("WHO: the ops lead. WHEN: weekly."), 1)
    check("no WHO fails",
          exposure("DECISION: hold or tighten the SLA. WHEN: weekly."), 1)
    check("no WHEN fails",
          exposure("DECISION: hold or tighten the SLA. WHO: the ops lead."), 1)
    check("an unowned dashboard fails", exposure(email=None), 1)
    check("an empty description fails everything at once", exposure(""), 1)

    # --- scoping --------------------------------------------------------------
    check("an installed package's exposure is invisible",
          exposure("DECISION: nothing.", pkg="elementary"), 0)

    failures = []
    for name, got, want in cases:
        good = len(got) == want
        print(f"    [{'ok' if good else 'FAIL'}] {name}: {len(got)} failing exposure(s)")
        if not good:
            failures.append(name)
            for entry in got[:3]:
                print(f"           {entry}")

    if failures:
        print(f"\nFAIL: {len(failures)} case(s)")
        return 1
    print(f"\nOK: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
