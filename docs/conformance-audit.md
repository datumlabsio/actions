# `conformance-audit` — DES §12

```yaml
jobs:
  audit:
    uses: datumlabsio/actions/.github/workflows/conformance-audit.yml@v0.14.0
    with:
      repos: "datumlabsio/polaris datumlabsio/example"
    secrets:
      app-id: ${{ secrets.DATUM_POLICE_APP_ID }}
      private-key: ${{ secrets.DATUM_POLICE_PRIVATE_KEY }}
```

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
