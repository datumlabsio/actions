#!/usr/bin/env python3
"""Every reusable workflow can be pushed onto a self-hosted runner, and pulled
back off it without touching a repo.

Four things have to hold at once, and each has burned us before:

  * a caller opts in per repo, through the runner-label input — a label no
    runner answers queues a job for 24 hours, so opting in has to be a
    deliberate act, not a default;
  * the org variable DATUM_RUNNER_OFFLINE overrides that input, so when the
    VM dies merges keep working without a pull request to every repo;
  * an archetype wrapper owns no runner of its own, so it has to hand the
    label DOWN — a wrapper that accepts the input and drops it is worse than
    one that never had it, because the caller thinks it worked;
  * a job that is handed a secret never lands on the self-hosted VM, which
    is stage-1 hardened and shares a LAN with everything else.

Run: python3 tests/runner_label_kill_switch.py
"""

import pathlib
import re
import sys

import yaml

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

# Workflows a caller may push onto the self-hosted runner.
OPTED_IN = ["python-ci", "web-ci", "docs-ci", "pre-commit", "gitops-ci",
            "security-baseline", "commit-lint", "changed-paths",
            "web-app", "dlt-pipeline"]

# Workflows that must NOT offer the input. dbt-ci and container-ci each hand a
# job a warehouse or registry credential; dbt-project is the wrapper around
# dbt-ci, so offering it there would be a promise its only real job cannot
# keep. That does not change until the egress allowlist is past stage 1.
EXCLUDED = ["dbt-ci", "container-ci", "dbt-project"]

KILL_SWITCH = ("${{ vars.DATUM_RUNNER_OFFLINE == 'true' && 'ubuntu-latest' "
               "|| inputs.runner-label }}")
PASSTHROUGH = "${{ inputs.runner-label }}"

# needs.<job>.outcome is not a secret; the job in security-baseline is called
# "secrets", which makes the naive pattern lie.
SECRET_REF = re.compile(r"(?<!needs\.)\bsecrets\.[A-Za-z0-9_-]+")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def call_of(doc):
    return (doc.get(True) or doc.get("on"))["workflow_call"]


for name in OPTED_IN:
    doc = yaml.safe_load((WF / f"{name}.yml").read_text())

    spec = (call_of(doc).get("inputs") or {}).get("runner-label")
    check(spec is not None, f"{name}: no runner-label input")
    if spec is None:
        continue
    check(spec.get("default") == "ubuntu-latest",
          f"{name}: runner-label defaults to {spec.get('default')!r}, not "
          f"ubuntu-latest — a repo would opt in without asking")
    check(spec.get("type") == "string", f"{name}: runner-label is not a string")

    for job, body in doc["jobs"].items():
        if "uses" in body:
            called = pathlib.Path(body["uses"]).stem
            passed = (body.get("with") or {}).get("runner-label")
            if called in EXCLUDED:
                check(passed is None,
                      f"{name}/{job} passes runner-label to {called}, which "
                      f"does not accept it")
            else:
                check(passed == PASSTHROUGH,
                      f"{name}/{job} calls {called} but passes "
                      f"runner-label={passed!r} — the wrapper swallows the "
                      f"label and the caller never finds out")
            continue

        runs_on = body.get("runs-on")
        if SECRET_REF.search(yaml.safe_dump(body)):
            check(runs_on == "ubuntu-latest",
                  f"{name}/{job} reads a secret but runs on {runs_on!r} — a "
                  f"secret must not reach the self-hosted VM")
        else:
            check(runs_on == KILL_SWITCH,
                  f"{name}/{job}: runs-on is {runs_on!r}, not the kill-switch "
                  f"expression — it would ignore DATUM_RUNNER_OFFLINE")

for name in EXCLUDED:
    doc = yaml.safe_load((WF / f"{name}.yml").read_text())
    check("runner-label" not in (call_of(doc).get("inputs") or {}),
          f"{name}: opted into the self-hosted runner, but it handles a "
          f"credential — see the comment at the top of this file")


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

if failures:
    print("\n".join(f"FAIL  {f}" for f in failures))
    sys.exit(1)
print(f"PASS  {len(OPTED_IN)} workflows opt in cleanly, wrappers pass the "
      f"label down, {len(EXCLUDED)} stay off the VM")
