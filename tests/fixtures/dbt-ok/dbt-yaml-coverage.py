# datum-config: dbt-yaml-coverage v1
# Vendored from datumlabsio/actions/configs/dbt-yaml-coverage.py. Bump it, do
# not edit it.
"""Enforce the YAML discipline in `blocks/dbt.md` §2 against a parsed manifest.

The rules, and where they come from:

  1. Every model has a YAML entry at all           (dbt.md §2)
  2. Every model has a description                 (dbt.md §2)
  3. Every declared column has a description       (dbt.md §2)
  4. Every model has at least one test             (dbt.md §2)
  5. Every mart model enforces a contract          (dbt.md §2, DPS §4)

Run it after `dbt parse`, which writes target/manifest.json.

Locally:
    dbt parse
    python dbt-yaml-coverage.py --manifest target/manifest.json

What this cannot check: whether every column that actually exists in the
warehouse is documented. That needs catalog.json from `dbt docs generate`,
which needs a live connection. This checks every column the YAML declares.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def collect_tested_models(nodes: dict) -> set[str]:
    """Model unique_ids that have at least one test pointing at them."""
    tested: set[str] = set()
    for node in nodes.values():
        if node.get("resource_type") != "test":
            continue
        # Newer manifests name the model directly; older ones only carry the
        # dependency edge. Read both so this works across dbt versions.
        attached = node.get("attached_node")
        if attached:
            tested.add(attached)
        for dep in node.get("depends_on", {}).get("nodes", []):
            if dep.startswith("model."):
                tested.add(dep)
    return tested


def is_mart(node: dict, mart_path: str) -> bool:
    fqn = node.get("fqn") or []
    return mart_path in fqn


def check(manifest_path: Path, mart_path: str) -> list[str]:
    with manifest_path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    nodes = manifest.get("nodes", {})
    tested = collect_tested_models(nodes)
    failures: list[str] = []

    models = {
        uid: node
        for uid, node in nodes.items()
        if node.get("resource_type") == "model"
    }
    if not models:
        return ["No models found in the manifest. Did `dbt parse` run?"]

    for uid, node in sorted(models.items()):
        name = node.get("name", uid)
        where = node.get("original_file_path", "?")

        if not node.get("patch_path"):
            failures.append(
                f"{where}: model '{name}' has no YAML entry. "
                "A model without YAML is not merged (dbt.md §2)."
            )
            # Everything below would just repeat this; move on.
            continue

        if not (node.get("description") or "").strip():
            failures.append(f"{where}: model '{name}' has no description.")

        columns = node.get("columns") or {}
        if not columns:
            failures.append(
                f"{where}: model '{name}' declares no columns in YAML."
            )
        for col_name, col in sorted(columns.items()):
            if not (col.get("description") or "").strip():
                failures.append(
                    f"{where}: column '{name}.{col_name}' has no description."
                )

        if uid not in tested:
            failures.append(
                f"{where}: model '{name}' has no tests (dbt.md §2)."
            )

        if is_mart(node, mart_path):
            contract = (node.get("config") or {}).get("contract") or {}
            if not contract.get("enforced"):
                failures.append(
                    f"{where}: mart model '{name}' does not enforce a contract. "
                    "Marts declare their contract fields (dbt.md §2, DPS §4)."
                )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="target/manifest.json")
    parser.add_argument(
        "--mart-path",
        default="marts",
        help="Path segment identifying mart models. Default: marts",
    )
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.is_file():
        print(f"::error::{manifest} not found. Run `dbt parse` first.")
        return 1

    failures = check(manifest, args.mart_path)
    if failures:
        print("::error::dbt YAML coverage failed:")
        for f in failures:
            print(f"  {f}")
        print(f"\n{len(failures)} problem(s).")
        return 1

    print("dbt YAML coverage: every model documented, tested, and contracted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
