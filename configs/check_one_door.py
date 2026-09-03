# datum-config: check-one-door v1
# Vendored from datumlabsio/actions/configs/check_one_door.py. Bump it, do not
# edit it.
"""Enforce the one door up in DAS §2 against a parsed manifest.

The rule: dashboards, metrics and alerts read MARTS -- never raw, never staging,
never intermediate. A dashboard that reaches past the marts bypasses every test,
contract and documented definition that makes a number worth trusting, and it
breaks silently the next time a staging column is renamed.

This checks the DECLARED graph: every exposure's `depends_on` must resolve to a
mart model in this project. That is the half CI can prove from the repo alone --
no BI credentials, no network, no extra dependency.

Only THIS project's exposures are audited, the same way dbt-yaml-coverage.py
scopes its models.

Run it after `dbt parse`, which writes target/manifest.json.

Locally:
    dbt parse
    python check_one_door.py --manifest target/manifest.json --mart-path marts

What this cannot check: SQL an analyst types straight into the BI tool, which
never appears in the manifest. That half is enforced in the warehouse -- the BI
service account is granted select on the mart schema only (DES §4). The check
and the grant are belt and suspenders; neither replaces the other.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def classify(dep: str, nodes: dict, mart_path: str, project: str | None) -> str | None:
    """Why this dependency is not a mart, or None when it is not ours to judge."""
    if dep.startswith("source."):
        return "reads a source directly"
    if not dep.startswith("model."):
        return None  # metrics, seeds and the like are not a door up
    node = nodes.get(dep)
    if node is None:
        return None  # not in this manifest at all
    # A model shipped by an installed package (elementary and friends) is not
    # this project's door up, and blocks/dbt.md §4 puts Elementary in every
    # install -- flagging its models would make the gate cry wolf.
    if project is not None and node.get("package_name") != project:
        return None
    if mart_path in (node.get("fqn") or []):
        return None
    return f"reads {node.get('name', dep)}, which is not a mart"


def audit(manifest: dict, mart_path: str) -> list[tuple[str, list[str]]]:
    project = (manifest.get("metadata") or {}).get("project_name")
    # Refusing rather than guessing. Without project_name this project's exposures
    # cannot be told apart from an installed package's, and the package filter
    # below would then discard EVERY exposure -- reporting "all 0 exposure(s)"
    # and exiting 0 on a manifest it never read. dbt-yaml-coverage.py refuses on
    # the same input; these gates are opt-in, so the repo that hits this is one
    # that switched them on and believes it is covered.
    if not project:
        return [
            (
                "<manifest>",
                [
                    "manifest has no `metadata.project_name`, so this project's "
                    "exposures cannot be told apart from an installed package's. "
                    "Refusing to audit exposures that may not be yours."
                ],
            )
        ]

    nodes = manifest.get("nodes", {})
    bad: list[tuple[str, list[str]]] = []
    for exposure in manifest.get("exposures", {}).values():
        if exposure.get("package_name") != project:
            continue
        problems = [
            reason
            for dep in exposure.get("depends_on", {}).get("nodes", [])
            if (reason := classify(dep, nodes, mart_path, project)) is not None
        ]
        if not exposure.get("depends_on", {}).get("nodes"):
            problems.append("declares no depends_on -- an exposure must name what it reads")
        if problems:
            bad.append((exposure.get("name", "?"), sorted(set(problems))))
    return sorted(bad)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=Path("target/manifest.json"))
    parser.add_argument(
        "--mart-path",
        default="marts",
        help="Path segment identifying mart models, as in dbt-yaml-coverage.py.",
    )
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"::error::{args.manifest} not found. Run `dbt parse` first.", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text())
    project = manifest.get("metadata", {}).get("project_name")
    total = len(
        [e for e in manifest.get("exposures", {}).values() if e.get("package_name") == project]
    )
    bad = audit(manifest, args.mart_path)

    for name, problems in bad:
        for problem in problems:
            print(f"::error::exposure {name}: {problem}")

    if bad:
        print(
            f"one door up: {len(bad)} of {total} exposure(s) reach past the marts.",
            file=sys.stderr,
        )
        return 1

    print(f"one door up: all {total} exposure(s) read marts only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
