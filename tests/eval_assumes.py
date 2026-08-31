#!/usr/bin/env python3
"""Do the eval cases still assume the standard as it actually is?

An eval case is a regression test for a spec. When the spec moves and the case does not,
the case goes on asserting the old answer -- and the run it produces is not a measurement,
it is a fake failure rate against work that already landed.

This is not hypothetical. On 2026-08-31, in `datumlabsio/datum-standards`:

  - a ten-case battery sat open citing `DSS §1` and assuming `rfcs: ["0007-draft"]`, three
    weeks after RFC-0008 renamed DSS to DAS and RFC-0007 was rejected as superseded;
  - two *merged* cases declared `des: 0.1.0-draft` while the DES had reached `0.4.0-draft`.

Nothing reported either. Both sets still parsed, still validated, still looked like tests.

Usage:
    eval_assumes.py --cases <dir> --specs <dir> --rfcs <dir> --map dps=platform,des=engineering

Exit 0 = every `assumes` block matches the repository. Exit 1 = at least one has drifted.
A case with no `assumes` block is skipped, not failed -- declaring what you were written
against is encouraged, not yet mandatory.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

VERSION_RE = re.compile(r"\*\*Version:\*\*\s*(\S+)")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([A-Za-z]+)")


def spec_version(specs: str, mapping: dict, short: str):
    """(version, error). The mapping is supplied by the repo because the short names in an
    `assumes` block are its own vocabulary, not this checker's."""
    d = mapping.get(short)
    if not d:
        return None, f"no mapping for {short!r} — add it to --map"
    path = os.path.join(specs, d, "README.md")
    if not os.path.exists(path):
        return None, f"{path} does not exist"
    m = VERSION_RE.search(open(path).read())
    return (m.group(1), None) if m else (None, f"no '**Version:**' line in {path}")


def rfc_status(rfcs: str, num: str):
    """(status, error). Status is taken as the first word, so 'Rejected — superseded by …'
    reads as 'rejected' and matches an assumed 'rejected-superseded'."""
    hits = sorted(glob.glob(os.path.join(rfcs, f"{num}-*.md")))
    if not hits:
        return None, f"no proposal file matching {num}-*.md"
    m = STATUS_RE.search(open(hits[0]).read())
    return (m.group(1).lower(), None) if m else (None, f"no '**Status:**' line in {hits[0]}")


def check(cases: str, specs: str, rfcs: str, mapping: dict):
    problems, checked = [], 0
    for f in sorted(glob.glob(os.path.join(cases, "*.json"))):
        name = os.path.basename(f)
        try:
            case = json.load(open(f))
        except json.JSONDecodeError as exc:
            problems.append(f"{name}: not valid JSON — {exc}")
            continue
        assumes = case.get("assumes")
        if not assumes:
            continue
        checked += 1
        for key, declared in assumes.items():
            if key == "rfcs":
                for entry in declared:
                    num, _, want = str(entry).partition("-")
                    actual, err = rfc_status(rfcs, num)
                    if err:
                        problems.append(f"{name}: rfcs {entry!r} — {err}")
                    elif actual and not want.lower().startswith(actual):
                        problems.append(
                            f"{name}: assumes RFC-{num} is {want!r}, but it is {actual!r}")
                continue
            actual, err = spec_version(specs, mapping, key)
            if err:
                problems.append(f"{name}: {key} — {err}")
            elif actual != declared:
                problems.append(
                    f"{name}: assumes {key} {declared!r}, but the spec says {actual!r}")
    return checked, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--specs", required=True)
    ap.add_argument("--rfcs", default="")
    ap.add_argument("--map", default="", help="key=dir pairs, comma separated")
    a = ap.parse_args()
    mapping = dict(kv.split("=", 1) for kv in a.map.split(",") if "=" in kv)

    checked, problems = check(a.cases, a.specs, a.rfcs, mapping)
    if not checked:
        print(f"No cases with an `assumes` block under {a.cases}; nothing to check.")
        return 0
    if problems:
        print(f"::error::{len(problems)} eval case(s) assume a standard that has moved.")
        for p in problems:
            print(f"::error::{p}")
        print()
        print("Update the case in the same change that moved the spec, or the number it")
        print("produces measures the old standard. If the expected answer genuinely still")
        print("holds, bump the `assumes` stamp — after re-reading the claim, not instead of.")
        return 1
    print(f"{checked} eval case(s) assume the standard as it currently is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
