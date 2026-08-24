# datumlabsio/actions — the CI every repo calls

Reusable workflows, versioned and tagged. Every repo's CI is a thin caller pinned to a version here. Bespoke CI is forbidden — see [DES §2](https://github.com/datumlabsio/datum-standards/blob/main/standards/engineering/README.md).

The point is simple: fix a gate once and every repo inherits it on the next bump.

## What a caller looks like

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/docs-ci.yml@v0.2.0
```

That is the whole file. If a repo's CI has steps of its own, something has gone wrong — either the gate belongs here, or the repo is doing something that needs an RFC.

## Available workflows

| Workflow | For | Docs |
|---|---|---|
| `docs-ci.yml` | archetype `docs` — standards and documentation repos | [docs/docs-ci.md](docs/docs-ci.md) |
| `python-ci.yml` | any Python surface — ruff, mypy, pytest, pre-commit, under uv | [docs/python-ci.md](docs/python-ci.md) |
| `dbt-ci.yml` | archetype `dbt-project` — sqlfluff, YAML coverage, dbt build | [docs/dbt-ci.md](docs/dbt-ci.md) |
| `release.yml` | cutting a SemVer release from Conventional Commits | [docs/release.md](docs/release.md) |
| `commit-lint.yml` | validating a pull request title, so the merge stays versionable | [docs/release.md](docs/release.md) |
| `gitops-ci.yml` | archetype `gitops` — kustomize build, kubeconform, helm lint, pinning and secret gates | [docs/gitops-ci.md](docs/gitops-ci.md) |
| `changed-paths.yml` | a monorepo deciding which components a pull request touched | [docs/changed-paths.md](docs/changed-paths.md) |
| `renovate.yml` | self-hosted dependency updates, on a schedule | [docs/renovate.md](docs/renovate.md) |
| `security-baseline.yml` | Semgrep, gitleaks and a dependency audit — DES §6 | [docs/security-baseline.md](docs/security-baseline.md) |
| `workflows-ci.yml` | a repo's own automation: actionlint, pins resolve, Renovate config valid | [docs/workflows-ci.md](docs/workflows-ci.md) |
| `web-ci.yml` | any JS/TS surface — pnpm, Biome, tsc, Vitest with coverage | [docs/web-ci.md](docs/web-ci.md) |

Archetype workflows are the surface a repo actually calls — a caller names its archetype and nothing else. See [docs/archetypes.md](docs/archetypes.md) for which exist and which are still waiting on the workflows they depend on.

| Archetype | Workflow |
|---|---|
| `docs` | `docs.yml` |
| `dbt-project` | `dbt-project.yml` |
| `dlt-pipeline` | `dlt-pipeline.yml` |
| `web-app` | `web-app.yml` |

Still to come, in this order: `security-baseline`, `container-ci` (needs the registry choice), `ai-review`, `conformance-audit`.

`web-app.yml` covers `lint → typecheck → test → build` and deliberately stops there: §8 says a `web-app` deploys as a container and the registry is not chosen yet, so `scan → publish` wait on that decision. Adding them is additive and needs no caller change.

## Configs are vendored, not fetched

Tool configs live in [`configs/`](configs/README.md) as the canonical copy, and every repo carries its own vendored copy with a version stamp. CI reads the repo's copy, not this one.

That is so a developer's local `ruff check` reads the same file the runner reads.

One of the original reasons no longer applies, and it is worth saying so rather than leaving a justification that has quietly expired: vendoring was partly chosen because this repo was private and a laptop could not fetch from it. Now it could. The remaining reasons stand on their own and were always the better ones — nothing is fetched at runtime, so CI has one less thing that can fail for a reason unrelated to the code, and a config change arrives as a reviewable bump in each repo rather than silently altering every build at once.

The cost is that configs can drift, which the version stamp, the conformance audit and Renovate between them catch. A vendored config is bumped, never hand-edited — the same rule RFC-0010 set for `.claude/`.

## Versioning

Callers pin an **exact version** — `@v1.4.2`. Never a moving tag.

The mechanism that carries a gate fix across the fleet is Renovate: when a release is cut here, it opens a bump pull request in every repo pinned to the old one. A moving tag is the one thing Renovate cannot bump, so a repo pinned to `@v1` would silently stop being tracked by the thing meant to keep it current.

Exact pins also mean a repo's CI changes only when a reviewed pull request lands in that repo. Nothing about its build changes because something moved elsewhere.

Breaking, for the purposes of that rule, means: removing an input, renaming one, changing a default in a way that makes a previously-passing repo fail, or adding a check that is on by default.

## Rules for anything added here

- **Third-party actions are pinned by commit SHA**, never by tag. A tag can be moved by someone else; a SHA cannot. DES §4.
- **Every workflow declares an explicit `permissions:` block**, least-privilege. Default to `contents: read` and add only what the workflow actually needs.
- **One exception, and it is a hard constraint rather than a preference:** a reusable workflow needing more than `contents: read` declares *no* `permissions:` block and the caller grants it. A called workflow cannot request more than its caller has, and asking for more fails at startup — no job runs and there is no log. `release.yml` is the only such workflow today.
- **No long-lived cloud credentials.** Cloud access uses OIDC federation. DES §4.
- **Every workflow is exercised by `self-test.yml` before it ships.** Every repo in the org is downstream of this one, so an untested change breaks the fleet's CI at once rather than one repo's.
- **New checks arrive switched off.** Add the input with a default that preserves current behaviour, let repos opt in, and only then discuss making it the default.

## Releasing

Merge to `main` and let `release.yml` cut it — the version comes from the Conventional Commits since the last tag, and CI creates the tag. Nothing is tagged by hand.

Renovate then opens the bump in each downstream repo. Once there are more than a handful, let a canary repo take the bump first and run a real pull request through it before the rest merge theirs.

**No published tag is ever rewritten or moved.** `release.yml` refuses to create a tag that already exists, locally or on the remote, and never passes `--force`. A version repos have run must stay what it was — rollback depends on it (DES §10).

## Access

This repo is **public**, so its workflows are callable from anywhere — any repo in the org whatever its visibility, and any per-install engagement org. While it was private neither of those worked: private reusable workflows reach only same-org private repos, which left the org's own public repos unable to call them at all, and cross-org sharing needing GitHub Enterprise.

Public is safe here because of one rule, enforced rather than remembered: **environment-specific values arrive as inputs or org variables, never as literals.** No account ids, role ARNs, workload-identity paths, internal hostnames, IP addresses or client names in a file. `tests/no_literal_env_values.py` checks it on every pull request.

None of those are secrets on their own. Together they are a map of what to attack and who to attack it for, and a map is worth withholding even when every road on it is public.
