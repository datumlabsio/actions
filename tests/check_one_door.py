#!/usr/bin/env python3
"""Exercise configs/check_one_door.py.

The rule under test: an exposure depends on MARTS and nothing else. The refusals
are the point -- a dashboard wired straight to a source or a staging model is
exactly the failure DAS §2 exists to stop, and it must not pass here.

`marts` is matched against the node's fqn, not its file path string, so a repo
that nests marts deeper still resolves. Exposures and models from installed
packages are out of scope, as elsewhere.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "configs" / "check_one_door.py"


def load():
    spec = importlib.util.spec_from_file_location("onedoor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def node(name, *, zone, pkg="fixture"):
    return {"resource_type": "model", "name": name, "package_name": pkg,
            "fqn": [pkg, zone, name]}


NODES = {
    "model.fixture.fct_orders": node("fct_orders", zone="marts"),
    "model.fixture.stg_orders": node("stg_orders", zone="staging"),
    "model.fixture.int_orders": node("int_orders", zone="intermediate"),
    "model.elementary.alerts": node("alerts", zone="edr", pkg="elementary"),
}


def manifest(deps, *, pkg="fixture", project="fixture"):
    return {
        "metadata": {"project_name": project},
        "nodes": NODES,
        "exposures": {
            "exposure.fixture.e": {
                "name": "orders_review",
                "package_name": pkg,
                "depends_on": {"nodes": deps},
            }
        },
    }


def main() -> int:
    gate = load()
    cases = []

    def check(name, deps, want, **kw):
        cases.append((name, gate.audit(manifest(deps, **kw), "marts"), want))

    # --- passes ---------------------------------------------------------------
    check("a mart-only exposure passes", ["model.fixture.fct_orders"], 0)
    check("an installed package's model is not this project's door",
          ["model.fixture.fct_orders", "model.elementary.alerts"], 0)
    check("an installed package's exposure is invisible",
          ["model.fixture.stg_orders"], 0, pkg="elementary")

    # --- refusals: the half that matters --------------------------------------
    check("reading staging fails", ["model.fixture.stg_orders"], 1)
    check("reading intermediate fails", ["model.fixture.int_orders"], 1)
    check("reading a source directly fails", ["source.fixture.raw.orders"], 1)
    check("one mart plus one staging model still fails",
          ["model.fixture.fct_orders", "model.fixture.stg_orders"], 1)
    check("declaring nothing fails -- an exposure must name what it reads", [], 1)

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
