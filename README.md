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
    uses: datumlabsio/actions/.github/workflows/docs-ci.yml@v1
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

Still to come, in this order: `security-baseline`, `container-ci` (needs the registry choice), coverage checks, `ai-review`, `conformance-audit`. Two surfaces have no workflow because the standard names no tooling for them yet: JS/TS for the `web-app` archetype, and infrastructure, which has no archetype at all. Both need an RFC before they can have CI.

## Configs are vendored, not fetched

Tool configs live in [`configs/`](configs/README.md) as the canonical copy, and every repo carries its own vendored copy with a version stamp. CI reads the repo's copy, not this one.

That is so a developer's local `ruff check` reads the same file the runner reads. It also means no repo needs a token to read this private repo at runtime. The cost is that configs can drift, which the version stamp, the conformance audit, and Renovate between them catch. A vendored config is bumped, never hand-edited — the same rule RFC-0010 set for `.claude/`.

## Versioning

Callers pin the **moving major tag** — `@v1`. Patch and minor releases move that tag, so a gate fixed here reaches every repo without 200 pull requests. A breaking change to any input goes to `v2` and callers migrate deliberately.

A repo that needs frozen CI may pin an exact tag (`@v1.4.2`) instead. That is a deliberate choice with a cost: it stops receiving fixes.

Breaking, for the purposes of that rule, means: removing an input, renaming one, changing a default in a way that makes a previously-passing repo fail, or adding a check that is on by default.

## Rules for anything added here

- **Third-party actions are pinned by commit SHA**, never by tag. A tag can be moved by someone else; a SHA cannot. DES §4.
- **Every workflow declares an explicit `permissions:` block**, least-privilege. Default to `contents: read` and add only what the workflow actually needs.
- **No long-lived cloud credentials.** Cloud access uses OIDC federation. DES §4.
- **Every workflow is exercised by `self-test.yml` before it ships.** Every repo in the org is downstream of this one, so an untested change breaks the fleet's CI at once rather than one repo's.
- **New checks arrive switched off.** Add the input with a default that preserves current behaviour, let repos opt in, and only then discuss making it the default.

## Releasing

1. Merge to `main`.
2. Tag the release: `git tag v1.1.0 && git push origin v1.1.0`.
3. Move the major tag: `git tag -f v1 && git push -f origin v1`.

Step 3 is the one that reaches the fleet, and it is the one to be careful with. Once there is more than a handful of repos downstream, point a canary repo at the new exact tag first and let a real pull request run through it before moving `v1`.

Published tags are never rewritten except for the moving major. A version that repos have run must stay what it was.

## Access

This repo is private. Its workflows are callable from other repos in the org because **Settings → Actions → General → Access** is set to *Accessible from repositories in the datumlabsio organization*. If a caller ever fails with "workflow not found", check that setting first.
