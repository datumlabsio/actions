#!/usr/bin/env python3
"""Every reusable workflow can be pushed onto a self-hosted runner, and pulled
back off it without touching a repo.

Three things have to hold at once, and each has burned us before:

  * a caller opts in per repo, through the runner-label input — a label no
    runner answers queues a job for 24 hours, so opting in has to be a
    deliberate act, not a default;
  * the org variable DATUM_RUNNER_OFFLINE overrides that input, so when the
    VM dies merges keep working without a pull request to every repo;
  * a job that is handed a secret never lands on the self-hosted VM, which
    is stage-1 hardened and shares a LAN with everything else.

Run: python3 tests/runner_label_kill_switch.py
"""

import pathlib
import re
import sys

import yaml

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Reusable workflows that may schedule onto the self-hosted runner. dbt-ci and
# container-ci are deliberately absent: both hand a job a warehouse or registry
# credential, and that does not go on the VM until the egress allowlist is past
# stage 1.
OPTED_IN = ["python-ci", "web-ci", "docs-ci", "pre-commit", "gitops-ci",
            "security-baseline"]

KILL_SWITCH = ("${{ vars.DATUM_RUNNER_OFFLINE == 'true' && 'ubuntu-latest' "
               "|| inputs.runner-label }}")

# needs.<job>.outcome is not a secret; the job in security-baseline is called
# "secrets", which makes the naive pattern lie.
SECRET_REF = re.compile(r"(?<!needs\.)\bsecrets\.[A-Za-z0-9_-]+")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


for name in OPTED_IN:
    path = WF / f"{name}.yml"
    doc = yaml.safe_load(path.read_text())
    call = (doc.get(True) or doc.get("on"))["workflow_call"]

    spec = (call.get("inputs") or {}).get("runner-label")
    check(spec is not None, f"{name}: no runner-label input")
    if spec is None:
        continue
    check(spec.get("default") == "ubuntu-latest",
          f"{name}: runner-label defaults to {spec.get('default')!r}, not "
          f"ubuntu-latest — a repo would opt in without asking")
    check(spec.get("type") == "string", f"{name}: runner-label is not a string")

    for job, body in doc["jobs"].items():
        runs_on = body.get("runs-on")
        takes_secret = bool(SECRET_REF.search(yaml.safe_dump(body)))

        if takes_secret:
            check(runs_on == "ubuntu-latest",
                  f"{name}/{job} reads a secret but runs on {runs_on!r} — a "
                  f"secret must not reach the self-hosted VM")
        else:
            check(runs_on == KILL_SWITCH,
                  f"{name}/{job}: runs-on is {runs_on!r}, not the kill-switch "
                  f"expression — it would ignore DATUM_RUNNER_OFFLINE")

# The kill switch is only worth having if it resolves the right way round.
# Model both branches the way GitHub evaluates `a && b || c`.
def resolve(offline, label):
    return ("ubuntu-latest" if offline == "true" else False) or label


check(resolve("true", "datum") == "ubuntu-latest",
      "kill switch on does not fall back to ubuntu-latest")
check(resolve("false", "datum") == "datum",
      "kill switch off does not honour the runner label")
check(resolve("", "datum") == "datum",
      "an unset DATUM_RUNNER_OFFLINE must mean the runner is up")
check(resolve("true", "ubuntu-latest") == "ubuntu-latest",
      "kill switch changes anything for a repo that never opted in")

# Workflows that must stay off the runner entirely.
for name in ["dbt-ci", "container-ci"]:
    doc = yaml.safe_load((WF / f"{name}.yml").read_text())
    call = (doc.get(True) or doc.get("on"))["workflow_call"]
    check("runner-label" not in (call.get("inputs") or {}),
          f"{name}: opted into the self-hosted runner, but it handles a "
          f"credential — see the comment at the top of this file")

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    sys.exit(1)
print(f"PASS  {len(OPTED_IN)} workflows opt in cleanly; secrets stay hosted")
