# `changed-paths.yml`

Which of a monorepo's component folders changed, so a caller can skip the gates for the components a pull request did not touch.

## Why this exists rather than a `run:` step in each repo

DES §4 says a repo's CI is a thin caller and bespoke CI is forbidden. A monorepo needs to know what changed before it can decide which archetype workflows to call — and doing that with a `git diff` step inside each repo's `ci.yml` would be exactly the bespoke CI the rule forbids: the same twenty lines copied into every monorepo, fixed in none of them.

So the diff lives here, and a monorepo's CI stays what every other repo's CI is — jobs that are nothing but `uses:`.

## Calling it

```yaml
jobs:
  changes:
    uses: datumlabsio/actions/.github/workflows/changed-paths.yml@v0.4.0
    with:
      paths: "platform analytics"
      run-all-on: ".pre-commit-config.yaml ruff.toml .github/"

  platform:
    needs: changes
    if: contains(needs.changes.outputs.changed, 'platform')
    uses: datumlabsio/actions/.github/workflows/gitops-ci.yml@v0.4.0
    with:
      root: platform/gitops

  analytics:
    needs: changes
    if: contains(needs.changes.outputs.changed, 'analytics')
    uses: datumlabsio/actions/.github/workflows/dbt-project.yml@v0.4.0
    with:
      working-directory: analytics
```

## Inputs

| Input | Required | Default | What it does |
|---|---|---|---|
| `paths` | yes | — | Space-separated top-level folders to test. A folder counts as changed when any file under it changed. |
| `run-all-on` | no | `""` | Space-separated path prefixes meaning *everything changed*. Prefix match: a bare filename matches that file, a folder name matches everything under it. |

**Put the repo's shared root files in `run-all-on`.** Without it, a pull request that changes only `.pre-commit-config.yaml` or a vendored `ruff.toml` touches no component folder, so every component is skipped and a config change that breaks all of them merges green. This is the one failure mode of path-filtered CI that actually costs you something, and it is silent.

## Outputs

| Output | Example | Notes |
|---|---|---|
| `changed` | `platform analytics` | Space-separated. Test with `contains(needs.<job>.outputs.changed, '<folder>')`. |
| `any` | `true` | `'true'` when at least one folder changed, else `'false'`. |

One output rather than one per folder, because a reusable workflow must declare its outputs statically and the folder list is the caller's business.

### Matching is prefix-anchored, and that matters

`contains()` does a substring test, so a folder whose name is a prefix of another — `platform` and `platform-tools` — would make `contains(…, 'platform')` true for both. The workflow's own matching is anchored (`^platform/`), so `changed` is correct; it is the caller's `if:` that can go wrong. Where two folder names share a prefix, compare exactly instead:

```yaml
if: contains(format(' {0} ', needs.changes.outputs.changed), ' platform ')
```

## When it runs everything

By design, in three cases — because a CI run that quietly checks nothing is worse than one that checks too much:

- **A `run-all-on` prefix changed.** A shared config affects every component.
- **No usable base commit.** A first push to a branch, a force-push, or a squash can leave `github.event.before` empty or pointing at a commit that no longer exists.
- **Every folder genuinely changed.**

Each case logs a `::notice::` saying which one it was, so a run that took longer than expected explains itself.

## What it does not do

- **No third-party action.** Path filtering is a `git diff`; a dependency for it is a supply-chain surface for no gain.
- **It does not decide the merge gate.** A skipped job reports neither success nor failure. If a required status check names a job that gets skipped, the pull request blocks forever — so make the *caller* jobs required, or require a final aggregating job, not the per-component ones.
