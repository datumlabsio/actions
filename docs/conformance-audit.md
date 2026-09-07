# `conformance-audit` — DES §12

```yaml
jobs:
  audit:
    uses: datumlabsio/actions/.github/workflows/conformance-audit.yml@v1.2.2
    with:
      repos: "datumlabsio/polaris datumlabsio/example"
      baseline-only-repos: "TheirOrg/their-repo"
    secrets:
      app-id: ${{ secrets.DATUM_POLICE_APP_ID }}
      private-key: ${{ secrets.DATUM_POLICE_PRIVATE_KEY }}
```

## Two tiers, and why

`repos` are audited on all seven §12 checks. `baseline-only-repos` are audited on
four, and **only** four.

An external adopter merges one file and is told, in the page we hand them, that
it *"changes nothing about how this repository is built"*. Auditing them on the
§12 list reports missing `CLAUDE.md`, `CODEOWNERS`, `.copier-answers.yml` and
`.pre-commit-config.yaml` — none of which that team agreed to, none fixable
without adopting the whole standard, and all of which the scheduled run
eventually **files as issues in their tracker**.

*A finding nobody can act on is a finding everybody learns to scroll past, and
it takes the real ones with it.*

| Baseline check | |
|---|---|
| `called` | some workflow calls `security-baseline.yml` — any filename, not just `datum-police.yml` |
| `pinned` | at a version tag, not a moving ref |
| `current` | at the current release, not thirteen behind |
| `ran` | **the gate has actually executed** |

The last has no §12 equivalent and is why this tier is worth more than a
file-presence sweep. An organisation set to *Allow select actions* without
`datumlabsio/*` allowlisted **skips** the workflow — and a skipped workflow
reports success. A repository can look adopted for a year while the gate has
never once run.

A **failing** run is not a finding here. Red means the gate is working; those
are their findings, not our conformance.

**It cannot reach a private repository in another organisation.** The job runs
as an App installation token scoped to one owner, so an external private repo
answers 404 — indistinguishable from a deleted one. We decided (2026-09-07) not
to hold a credential in a client's organisation for this, so external private
adopters are tracked by
[the register](adopting-a-repo-we-do-not-own.md) rather than by this workflow.
A **public** external repo needs no credential and can be passed by hand.

The split is explicit rather than inferred from the owner. "External" is not the
same as "not in our organisation": a client's repository can live in our org,
and we may fully adopt one in theirs.

## What it can and cannot see

**This distinction matters more than the check list.**

| Observable here | Not observable here |
|---|---|
| branch protection | "linters pass" |
| file presence — `CLAUDE.md`, `README`, `CODEOWNERS`, `docs/`, pre-commit | "coverage did not fall" |
| CI is a thin caller, pinned to a version tag | "no tag was moved" |
| vendored config stamps against canonical | |
| CODEOWNERS naming a team that **actually holds write access** | |
| the archetype, read from `.copier-answers.yml` | |

The right-hand column are facts about a **run**, not about a repo, and the repo's own CI is where they are decided. An audit that re-ran them would be a slower second CI that occasionally disagrees with the first.

**So a green audit means "this repo is set up to be checked", not "this repo is correct".** Conflating those is how a dashboard starts lying.

## One root cause, not five symptoms

A repo with no `.copier-answers.yml` was not born from a scaffold. That is **one** finding, and the archetype-specific checks are skipped rather than each reporting the same absence a different way.

The first version did not do this, and `actions` came back with five findings that were all the same fact. A report like that gets filtered out of somebody's inbox by the second week.

## Repos are explicit, never autodiscovered

Which repos the standard binds is a **decision** (B-30), not something a workflow should assume. Autodiscovery would quietly answer a question nobody has been asked.

## `dry-run` defaults to true

Running this against the fleet files an issue against every non-conforming repo. That is a scope decision (B-32), not a workflow change.

## One issue per repo, updated not duplicated

A new issue every run is how an audit becomes noise. Findings are matched on the title `Conformance drift: owner/repo` and PATCHed in place.

## A check that read prose

The first version detected a bespoke `run:` step by substring, and flagged `polaris` for a **comment** reading *"It is a call, not a `run:` step"* — a check that failed on prose describing the rule it enforces. It now parses the workflow and looks for an actual `run` key in a step.

## Verified against the real fleet

Run by hand across all five org repos, it reports exactly their drift and nothing else:

- four repos not born from a scaffold — true; they are the machinery and predate it
- four missing `.pre-commit-config.yaml` — true, §3 requires one
- `datum-standards` CODEOWNERS names **individuals**, not a team — true, and §3 says the owner is a team, never an individual
- `polaris` `main` unprotected, and not calling `security-baseline` — both true
