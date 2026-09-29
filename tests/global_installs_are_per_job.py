#!/usr/bin/env python3
"""A global install must go somewhere the next job cannot read.

`npm install --global` writes into npm's prefix, which by default sits inside
the Node installation — and on a self-hosted runner that lives in the TOOL
CACHE, shared by every job on the box. Two ways that goes wrong, and they look
nothing alike:

  * the tool cache is read-only, and the job dies with
    `EROFS: read-only file system` naming a path nobody recognises. That is
    how this was found: polaris `web-app / web` broke on every run.
  * the tool cache is WRITABLE, and the job passes. One job then leaves a
    binary on PATH for the next job to execute, which is the isolation the
    ephemeral runner exists to provide, quietly gone.

The second is why this is a test and not a comment. The first announces
itself; the second never does.

Run: python3 tests/global_installs_are_per_job.py
"""

import pathlib
import re
import sys

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

# A global install: npm's --global/-g, and pnpm/yarn's equivalents.
GLOBAL = re.compile(r"\b(?:npm|pnpm|yarn)\s+(?:install|add|i)\b[^\n]*"
                    r"(?:--global\b|--location=global\b|\s-g\b)")
# The PREFIX itself has to point at the job's own temp. Checking merely that
# RUNNER_TEMP appears somewhere in the step is not enough -- a `mkdir` left
# behind after the prefix was repointed satisfies that, and two mutations
# escaped exactly that way.
PER_JOB = re.compile(
    r"""(?:
          config \s+ set \s+ prefix \s+ ["']? \$\{?RUNNER_TEMP    # npm config set prefix
        | (?:npm_config_prefix|NPM_CONFIG_PREFIX) \s* [:=] \s* ["']? \$?\{?\{?\s*
          (?:env\.)? (?:RUNNER_TEMP|runner\.temp)                  # via env
        | --prefix \s+ ["']? \$\{?RUNNER_TEMP                      # inline flag
        )""",
    re.X | re.I)

failures = []

for path in sorted(WF.glob("*.yml")):
    text = path.read_text()
    for m in GLOBAL.finditer(text):
        line_no = text[:m.start()].count("\n") + 1
        # The step's run: block — from the line back to the previous `- name:`
        # and forward to the next step at the same indent.
        before = text[:m.start()]
        step_start = before.rfind("\n      - ")
        after = text[m.end():]
        nxt = after.find("\n      - ")
        step = text[step_start if step_start != -1 else 0:
                    m.end() + (nxt if nxt != -1 else len(after))]

        if not PER_JOB.search(step):
            failures.append(
                f"{path.name}:{line_no} installs globally without pointing the "
                f"prefix at RUNNER_TEMP — it will land in the shared tool "
                f"cache: {m.group(0).strip()[:70]}")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    print("\nSet a per-job prefix in the same step, e.g.:")
    print('  npm config set prefix "$RUNNER_TEMP/npm-global"')
    print('  echo "$RUNNER_TEMP/npm-global/bin" >> "$GITHUB_PATH"')
    sys.exit(1)
print("PASS  every global install writes somewhere the next job cannot reach")
