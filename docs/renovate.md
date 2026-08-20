# `renovate.yml` — self-hosted dependency updates

The engine. The **policy** lives in `datumlabsio/.github/default.json`, which every repo's `renovate.json` extends — see [that repo's docs](https://github.com/datumlabsio/.github/blob/main/docs/renovate.md).

## Calling it

```yaml
on:
  schedule:
    - cron: "0 4 * * 1"
  workflow_dispatch:

jobs:
  renovate:
    uses: datumlabsio/actions/.github/workflows/renovate.yml@v0.6.0
    secrets:
      renovate-token: ${{ secrets.RENOVATE_TOKEN }}
```

## Why self-hosted rather than the Mend-hosted app

**The hosted app needs write access to every repo it manages, held by a third party.** DES §7 says an agent gets read-only by default and every bot acts under its own identity. A Renovate we run, under a bot identity we own, satisfies both. The hosted app cannot.

It also takes a pricing question off the critical path, and it is the same shape as §12's conformance audit: logic here, scheduled caller in `.github`.

The cost is that we own the schedule and the token. That is the trade.

## No list of repositories to maintain

Two settings do the work:

```
RENOVATE_ONBOARDING: "false"        # never open a "Configure Renovate" PR
RENOVATE_REQUIRE_CONFIG: required   # skip any repo with no renovate.json
```

**A repo opts in by carrying the file**, and its scaffold writes that file at birth. So the 223 repos that predate the scaffold are untouched until someone adds it deliberately, and nothing has to be added to an allowlist when a repo is created.

This is the part the hosted app cannot do as cleanly: there, "All repositories" onboards everything, and "Selected" is a list someone has to remember to update.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `renovate-version` | `44` | Pinned, not floating — see below |
| `autodiscover-filter` | `datumlabsio/*` | Which repos are *considered*. Only those with a config are touched. |
| `dry-run` | `false` | Resolve and log everything, push nothing |
| `log-level` | `info` | `debug` when working out why a repo was skipped |

## Why the version is pinned, and why the preset is validated first

A Renovate major can rename a config field. When that happens **nothing errors** — Renovate ignores what it does not recognise, finds nothing to update, and reports success. That is indistinguishable from "everything is current", on a tool nobody watches closely.

This already applies to us: `default.json` uses `fileMatch`, which Renovate 44 accepts but auto-migrates to `managerFilePatterns`. A future major may drop it entirely, and the symptom would be silence.

So the workflow validates the preset **at the pinned version** before running, and `self-test` runs the whole thing in dry-run on every pull request. A version bump that breaks the config fails a check instead of quietly doing nothing.

## The token

Needs `contents: write` and `pull-requests: write` on the target repos, and nothing else. It belongs to a **bot identity**, not a person — DES §7 requires every bot and workflow to act under its own identity, so a personal access token would break the rule this workflow exists to serve.

Store it as `RENOVATE_TOKEN` in the calling repo's secrets.

## Reading a run

- **Dependency Dashboard** issue per repo — what Renovate is holding for approval. Not an error.
- **A repo you expected was skipped** — almost always no `renovate.json`. Run with `log-level: debug` and look for `repository has no config`.
- **Nothing happened at all** — check the `validate-preset` job first. If the preset failed to validate, the engine never ran.
