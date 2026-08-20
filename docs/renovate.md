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

**Because the hosted app does not scan private repos, and 223 of the org's 228 repos are private.**

This was measured, not assumed. The app was installed on `.github`, `actions` and `scaffolds`:

| Repo | Visibility | Scanned |
|---|---|---|
| `actions` | public | yes, within 9 minutes |
| `.github` | public | yes, within 9 minutes |
| `scaffolds` | **private** | **never** |

`scaffolds` was not short of things to find — it carries SHA-pinned actions and an `actions_version` pin a full release behind — and `dependencyDashboard` creates its issue whether or not updates exist. Private repos need a paid Mend tier.

That leaves the hosted app covering two repos and none of the ones client work will live in. `scaffolds` is the worst of it: it holds the pin that decides which CI version *every new repo is born on*.

The §7 argument points the same way — an agent gets read-only by default and every bot acts under its own identity, which a third-party app holding write access cannot satisfy. **But coverage is the reason. A safer tool that cannot see the repos is not the safer choice.**

The cost is that we own the schedule and the token. That is the trade, and it is worth it.

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
