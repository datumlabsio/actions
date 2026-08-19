#!/usr/bin/env python3
"""Fail if a workflow hardcodes something environment-specific.

This repo is public. That is fine for CI logic and deliberately fine for the
shared configs, but it means anything committed here is readable by anyone,
permanently, including in forks and mirrors. The rule that makes public safe is:

    environment-specific values arrive as inputs or org variables, never as
    literals in a file.

Cloud account IDs, role ARNs, workload-identity paths, internal hostnames, IP
addresses and client names are the ones that matter. None of them are secrets
on their own — they are a map of what to attack and who to attack it for, and a
map is worth withholding even when every road on it is public.

Enforced rather than remembered, because "be careful forever" is not a control.

    python3 tests/no_literal_env_values.py .github/workflows
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Named so a finding says what to do, not just what matched.
RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "AWS role ARN",
        re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:"),
        "pass the role as an input; the caller supplies it",
    ),
    (
        "cloud account or project id",
        # A standalone 12-digit run: AWS account ids. Not part of a longer
        # alphanumeric run, so SHA pins and version strings are untouched.
        re.compile(r"(?<![0-9A-Za-z._-])[0-9]{12}(?![0-9A-Za-z._-])"),
        "pass the account as an input, or use an org variable",
    ),
    (
        "workload identity path",
        re.compile(r"workloadIdentityPools|projects/[^/\s]+/locations/"),
        "pass the provider as an input",
    ),
    (
        "internal hostname",
        re.compile(r"[a-z0-9-]+\.(?:datumlabs\.io|internal)\b"),
        "pass the host as an input; it differs per install",
    ),
    (
        "IP address",
        re.compile(r"(?<![0-9.:])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])"),
        "pass the address as an input",
    ),
    (
        "client name",
        re.compile(
            r"\b(?:westwise|ember|vero|pitchlane|synthflow|voltera|swantje)\b",
            re.I,
        ),
        "a client never appears in shared CI; use a neutral fixture name",
    ),
]

# Lines that legitimately carry a host or a long number.
ALLOW = re.compile(
    r"""
      raw\.githubusercontent\.com    # the CRD catalog schema location
    | get\.helm\.sh                  # helm's own download host
    | github\.com/[\w.-]+/[\w.-]+/releases   # pinned tool downloads
    | pypi\.org
    | @[0-9a-f]{40}\b                # a SHA-pinned action
    | ^\s*\#\s                       # a comment explaining the rule itself
    """,
    re.X,
)


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    files = sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml"))
    if not files:
        findings.append(f"no workflow files found under {root}")
        return findings

    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ALLOW.search(line):
                continue
            for name, pattern, fix in RULES:
                if pattern.search(line):
                    findings.append(
                        f"{path}:{n}: {name} — {fix}\n      {line.strip()[:100]}"
                    )
                    break
    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".github/workflows")
    findings = scan(root)
    if findings:
        print("::error::A workflow hardcodes something environment-specific.")
        print("This repo is public; these arrive as inputs or org variables.")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"No literal environment-specific values under {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
