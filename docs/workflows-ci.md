# `workflows-ci` — CI for a repo's own automation

Every repo in the org has workflows. Until this existed, nothing checked them except this repo's own `self-test`.

```yaml
jobs:
  workflows:
    uses: datumlabsio/actions/.github/workflows/workflows-ci.yml@v0.9.0
```

## What it checks

| Job | What it catches |
|---|---|
| `lint` | actionlint + shellcheck over every workflow |
| `pins` | every `datumlabsio/actions` pin resolves, and the workflow declares what is passed to it |
| `renovate` | any Renovate config in the repo actually parses as Renovate config |

## Why actionlint and not a YAML parse

Two failures were already paid for in this repo:

1. **A duplicated job key.** PyYAML silently keeps the last duplicate, so a YAML parse passes and Actions sees a workflow missing a job.
2. **A called workflow requesting more permissions than its caller granted.**

Both fail at **startup** — the run is `startup_failure` with no log to read. Both are things actionlint catches and a parser cannot. They broke `main` here once; that is not a lesson worth every repo learning separately.

## Why the pin check earns its own job

DES §4 requires a thin caller to pin an exact version tag. **A pin that does not resolve satisfies the letter of that rule** and fails in the first repo somebody creates — as `workflow not found`, which reads like their mistake rather than the template's.

`scaffolds` has had this check since scaffolds#5, where it caught three real bugs. This is the same idea for any repo, not just rendered templates.

It checks three things per pin:

- the workflow **exists** at that ref
- it **declares** every `with:` and `secrets:` key being passed — an input that does not exist is another startup failure with no log
- the pin **exists at all** — a missing `@ref` is flagged

`secrets: inherit` is accepted, and local `./` references are ignored.

**One trap worth knowing about**, because it is the kind of bug this job would otherwise have: YAML 1.1 parses a bare `on` as the boolean `True`, so a workflow's trigger block is `doc[True]`, not `doc["on"]`. Reading only `doc["on"]` finds nothing, declares every caller valid, and passes forever. A gate that always passes is indistinguishable from no gate.

## Why the Renovate config is validated at a pinned version

A Renovate major can rename a config field, and when it does **nothing errors** — Renovate ignores what it does not recognise, finds nothing to update, and reports success. Indistinguishable from "everything is current" on a tool nobody watches closely.

This already applies: `default.json` in `.github` uses `fileMatch`, which Renovate 44 accepts but silently auto-migrates to `managerFilePatterns`. A future major may drop it.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `actionlint` | `true` | |
| `actionlint-version` | `1.7.12` | pinned, so a new release cannot change what CI accepts overnight |
| `verify-pins` | `true` | needs no token for public refs |
| `validate-renovate` | `true` | skips with a notice when there is no config |
| `renovate-version` | `44` | validate against the major that actually runs |
| `working-directory` | `.` | for a monorepo component, or a fixture |

## Verified

`self-test` runs it against this repo (must be clean) **and** against `tests/fixtures/pins-bad`, which pins a version that does not exist and passes an input never declared. The negative case lifts the checker out of this workflow and runs that exact source, so there is no second copy to drift — a `uses:` job cannot be `continue-on-error`, so a job meant to fail would otherwise just fail the run.
