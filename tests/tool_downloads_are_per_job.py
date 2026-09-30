#!/usr/bin/env python3
"""A tool a job downloads must land in that job's own temp.

`astral-sh/setup-uv` stores the uv it downloads in the runner's TOOL CACHE. On
a self-hosted runner that cache is shared by every job on the box, and it is
root-owned and read-only on purpose (docs/self-hosted-runners.md). So the step
works only while the uv it wants is one already cached — and with no version
pinned it wants the latest. The day uv 0.12.21 came out, every Python job in
the fleet failed at:

    ENOENT: no such file or directory, mkdir '/opt/hostedtoolcache/uv/0.12.21'

Making the cache writable is not the fix: one job could then leave a uv binary
on PATH for the next job to run. Each step sets RUNNER_TOOL_CACHE to the job's
own temp instead, and this test keeps it that way.

Run: python3 tests/tool_downloads_are_per_job.py
"""

import pathlib
import re
import sys

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

SETUP_UV = re.compile(r"uses:\s*astral-sh/setup-uv@")
# The variable itself has to point at the job's temp, in this step's env. A
# RUNNER_TEMP mentioned anywhere else in the step would not move the download.
PER_JOB = re.compile(
    r"^\s+RUNNER_TOOL_CACHE:\s*[\"']?\$\{\{\s*runner\.temp\s*\}\}", re.M)

failures = []

for path in sorted(WF.glob("*.yml")):
    text = path.read_text()
    for m in SETUP_UV.finditer(text):
        line_no = text[:m.start()].count("\n") + 1
        # The step: from its `- name:` back to the previous step, forward to
        # the next step at the same indent.
        before = text[:m.start()]
        step_start = before.rfind("\n      - ")
        after = text[m.end():]
        nxt = after.find("\n      - ")
        step = text[step_start if step_start != -1 else 0:
                    m.end() + (nxt if nxt != -1 else len(after))]

        if not PER_JOB.search(step):
            failures.append(
                f"{path.name}:{line_no} runs setup-uv without pointing "
                f"RUNNER_TOOL_CACHE at the job's temp — on a self-hosted "
                f"runner it will try to write the shared, read-only tool cache")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    print("\nSet it in the step's env, e.g.:")
    print("  env:")
    print("    RUNNER_TOOL_CACHE: ${{ runner.temp }}/tool-cache")
    sys.exit(1)
print("PASS  every setup-uv step downloads into the job's own temp")
