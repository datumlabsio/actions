#!/usr/bin/env python3
"""Every GitHub App token is minted with `client-id`, never `app-id`.

actions/create-github-app-token deprecated its `app-id` input, and GitHub
prints that on every run that passes it -- in every repository that calls these
workflows. The shared workflows now take a `client-id` secret and fall back to
`app-id`, so a caller still passing the numeric App ID keeps working: the
action hands either one to the same JWT issuer. What must not come back is the
deprecated input itself, or an `app-id` marked required, which would refuse a
caller that has already moved.

Run: python3 tests/app_tokens_use_client_id.py
"""

import pathlib
import re
import sys

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"
USES = re.compile(r"^(\s*)(-\s+)?uses:\s*actions/create-github-app-token@")

failures = []
steps = 0


def indent(line):
    return len(line) - len(line.lstrip(" "))


def step_block(lines, i):
    """The whole step around the `uses:` on line i, whatever its key order."""
    m = USES.match(lines[i])
    key_col = len(m.group(1)) + (len(m.group(2)) if m.group(2) else 0)
    start = i
    if not m.group(2):  # `uses:` is not the first key: walk back to the `- `
        while start > 0:
            start -= 1
            if re.match(r"^\s*-\s+\S", lines[start]) and indent(lines[start]) == key_col - 2:
                break
    end = i + 1
    while end < len(lines) and (not lines[end].strip() or indent(lines[end]) >= key_col):
        end += 1
    return lines[start:end], key_col


for path in sorted(WF.glob("*.yml")):
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if not USES.match(line):
            continue
        steps += 1
        block, key_col = step_block(lines, i)
        keys = [re.match(r"^\s*([a-z-]+):", l).group(1) for l in block
                if re.match(r"^\s*[a-z-]+:", l) and indent(l) == key_col + 2]
        where = f"{path.name}:{i + 1}"
        if "app-id" in keys:
            failures.append(f"{where} mints a token with the deprecated app-id input")
        if "client-id" not in keys:
            failures.append(f"{where} mints a token with no client-id")

    # The workflow_call interface: an app-id the caller must pass would reject
    # a caller that passes only client-id.
    for i, line in enumerate(lines):
        if re.match(r"^\s+(violation-)?app-id:\s*$", line):
            col = indent(line)
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or indent(lines[j]) > col):
                if re.match(r"^\s+required:\s*true\b", lines[j]):
                    failures.append(f"{path.name}:{i + 1} still requires {line.strip()[:-1]}")
                j += 1

if steps == 0:
    failures.append("found no create-github-app-token step at all -- the scanner "
                    "broke, and a scanner that finds nothing reports success")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    sys.exit(1)
print(f"PASS  {steps} token steps use client-id, and no workflow requires app-id")
