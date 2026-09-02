# datum-config: check-so-what v1
# Vendored from datumlabsio/actions/configs/check_so_what.py. Bump it, do not
# edit it.
"""Enforce the so-what gate in DAS §1 against a parsed manifest.

The rule: a dashboard is a decision surface, or it is not built. Every exposure
description must name three things:

  1. DECISION -- and it must be a FORK, not a topic
  2. WHO      -- the reader
  3. WHEN     -- the moment

"Revenue visibility" is a topic: nothing a person does changes depending on what
it shows. A fork names the alternatives -- "revenue 20% under plan -> hiring
pause" -- and a dashboard that cannot state one is a dashboard nobody needs. The
argument is worth having once, at declaration time, in a pull request.

Only THIS project's exposures are audited. A package that ships exposures is
invisible here, the same way dbt-yaml-coverage.py scopes its models.

Run it after `dbt parse`, which writes target/manifest.json.

Locally:
    dbt parse
    python check_so_what.py --manifest target/manifest.json

What this cannot check: whether the decision is real. A person still has to mean
it. This checks that somebody was made to write it down, and that a reviewer saw
it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LABELS = ("DECISION", "WHO", "WHEN")

# A DECISION must offer a choice. An arrow ("under plan -> hiring pause") reads
# as one; so do the words people actually write. Listed, not inferred, so a
# reviewer can see exactly what counts.
FORK_TOKENS = (
    "->",
    "→",
    "whether",
    " vs ",
    " vs.",
    " versus ",
    " or ",
    "either ",
    "go/no-go",
    "yes/no",
)


def segments(description: str) -> dict[str, str]:
    """Split a description into its DECISION / WHO / WHEN chunks."""
    text = " ".join((description or "").split())
    positions = [
        (label, match.start())
        for label in LABELS
        for match in re.finditer(rf"\b{label}\s*:", text)
    ]
    positions.sort(key=lambda pair: pair[1])
    found: dict[str, str] = {}
    for index, (label, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        found[label] = re.sub(rf"^{label}\s*:", "", text[start:end]).strip(" .;-")
    return found


def failures(exposure: dict) -> list[str]:
    """Every reason this exposure does not pass the gate."""
    problems: list[str] = []
    parts = segments(exposure.get("description", ""))
    for label in LABELS:
        if not parts.get(label):
            problems.append(f"no {label}: stated")
    decision = (parts.get("DECISION") or "").lower()
    if decision and not any(token in decision for token in FORK_TOKENS):
        problems.append("DECISION names a topic, not a fork between options")
    owner = exposure.get("owner") or {}
    if not owner.get("email"):
        problems.append("no owner email -- an unowned dashboard is not a decision surface")
    return problems


def audit(manifest: dict) -> list[tuple[str, list[str]]]:
    project = manifest.get("metadata", {}).get("project_name")
    bad: list[tuple[str, list[str]]] = []
    for exposure in manifest.get("exposures", {}).values():
        if exposure.get("package_name") != project:
            continue
        problems = failures(exposure)
        if problems:
            bad.append((exposure.get("name", "?"), problems))
    return sorted(bad)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=Path("target/manifest.json"))
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"::error::{args.manifest} not found. Run `dbt parse` first.", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text())
    bad = audit(manifest)
    total = len(
        [
            exposure
            for exposure in manifest.get("exposures", {}).values()
            if exposure.get("package_name") == manifest.get("metadata", {}).get("project_name")
        ]
    )

    for name, problems in bad:
        for problem in problems:
            print(f"::error::exposure {name}: {problem}")

    if bad:
        print(
            f"so-what gate: {len(bad)} of {total} exposure(s) do not name a decision.",
            file=sys.stderr,
        )
        return 1

    print(f"so-what gate: all {total} exposure(s) name a decision fork, a reader and a moment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
