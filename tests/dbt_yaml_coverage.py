#!/usr/bin/env python3
"""Exercise configs/dbt-yaml-coverage.py.

The rule under test: a parsed dbt manifest contains every model of every
installed package, and only THIS project's models may be audited. A package
that ships models -- elementary, dbt_artifacts, dbt_project_evaluator -- must
be invisible here.

The obvious wrong fix is to filter on the file path (`models/edr/`), which
works until a package uses a different folder. The manifest already records
`package_name` per node and the root project in `metadata.project_name`, so
that is what this asserts.

Equally important: the filter must not turn the gate into a rubber stamp.
Half of these cases exist to prove a real problem in the project's OWN models
still fails.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "configs" / "dbt-yaml-coverage.py"


def load():
    spec = importlib.util.spec_from_file_location("cov", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def model(name, *, pkg, path, documented=True, tested=True,
          contract=False, columns=True, fqn=None):
    node = {
        "resource_type": "model",
        "name": name,
        "package_name": pkg,
        "original_file_path": path,
        "fqn": fqn or [pkg, name],
        "config": {"contract": {"enforced": contract}},
    }
    if documented:
        node["patch_path"] = f"{pkg}://models/schema.yml"
        node["description"] = f"The {name} model."
        node["columns"] = (
            {"id": {"description": "Primary key."}} if columns else {}
        )
    return node


def manifest(models, *, project="polaris", tested_uids=()):
    nodes = {}
    for uid, node in models.items():
        nodes[uid] = node
    for i, uid in enumerate(tested_uids):
        nodes[f"test.{project}.t{i}"] = {
            "resource_type": "test",
            "attached_node": uid,
            "depends_on": {"nodes": [uid]},
        }
    doc = {"metadata": {"project_name": project} if project else {}, "nodes": nodes}
    return doc


def run(cov, doc, mart_path="marts"):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(doc, fh)
        p = Path(fh.name)
    try:
        return cov.check(p, mart_path)
    finally:
        p.unlink()


def main() -> int:
    cov = load()
    cases = []

    # 1. The polaris case: clean own models, filthy package models.
    own = "model.polaris.stg_charges"
    pkg = "model.elementary.alerts_dbt_tests"
    doc = manifest(
        {
            own: model("stg_charges", pkg="polaris", path="models/staging/stg_charges.sql"),
            pkg: model("alerts_dbt_tests", pkg="elementary",
                       path="models/edr/alerts/alerts_dbt_tests.sql",
                       documented=False, tested=False),
        },
        tested_uids=[own],
    )
    cases.append(("package models are invisible", run(cov, doc), 0))

    # 2. A package using a folder name that looks like the project's own.
    #    Proves the filter is package_name, not a path heuristic.
    doc = manifest(
        {
            own: model("stg_charges", pkg="polaris", path="models/staging/stg_charges.sql"),
            "model.dbt_artifacts.x": model("x", pkg="dbt_artifacts",
                                           path="models/staging/x.sql",
                                           documented=False, tested=False),
        },
        tested_uids=[own],
    )
    cases.append(("package under a familiar path is still invisible", run(cov, doc), 0))

    # --- the gate must still bite on this project's own models ---------------

    doc = manifest({own: model("stg_charges", pkg="polaris",
                               path="models/staging/stg_charges.sql",
                               documented=False)})
    cases.append(("own model with no YAML still fails", run(cov, doc), 1))

    doc = manifest({own: model("stg_charges", pkg="polaris",
                               path="models/staging/stg_charges.sql")})
    cases.append(("own model with no tests still fails", run(cov, doc), 1))

    doc = manifest({own: model("stg_charges", pkg="polaris",
                               path="models/staging/stg_charges.sql",
                               columns=False)}, tested_uids=[own])
    cases.append(("own model declaring no columns still fails", run(cov, doc), 1))

    mart = "model.polaris.dim_customer"
    doc = manifest({mart: model("dim_customer", pkg="polaris",
                                path="models/marts/core/dim_customer.sql",
                                fqn=["polaris", "marts", "core", "dim_customer"],
                                contract=False)}, tested_uids=[mart])
    cases.append(("own mart without a contract still fails", run(cov, doc), 1))

    # --- refusing to guess ---------------------------------------------------

    doc = manifest({own: model("stg_charges", pkg="polaris",
                               path="models/staging/stg_charges.sql")},
                   project=None, tested_uids=[own])
    out = run(cov, doc)
    ok = len(out) == 1 and "project_name" in out[0]
    cases.append(("no project_name -> refuses rather than guesses", out, 1 if ok else -1))

    doc = manifest({pkg: model("alerts_dbt_tests", pkg="elementary",
                               path="models/edr/a.sql", documented=False)})
    out = run(cov, doc)
    ok = len(out) == 1 and "installed packages" in out[0]
    cases.append(("only package models -> says so, does not pass silently",
                  out, 1 if ok else -1))

    failures = []
    for name, got, want in cases:
        good = len(got) == want if want >= 0 else False
        print(f"    [{'ok' if good else 'FAIL'}] {name}: {len(got)} failure(s)")
        if not good:
            failures.append(name)
            for g in got[:3]:
                print(f"           {g}")

    if failures:
        print(f"\nFAIL: {len(failures)} case(s)")
        return 1
    print(f"\nOK: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
