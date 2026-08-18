# Archetype workflows — the caller surface

A repo's CI names **what the repo is**, not the checks it happens to need:

```yaml
name: ci
on: [pull_request, push]

permissions:
  contents: read

jobs:
  ci:
    uses: datumlabsio/actions/.github/workflows/docs.yml@v1.0.0
```

That is the whole file. The archetype workflow decides which language workflows run underneath.

## Why not call the language workflows directly

Because of where the edit lands when a gate is added.

Call `python-ci` and `container-ci` by name, and every repo has to know that an `application` means Python plus a Dockerfile plus YAML. Add a gate for all applications and you are opening a pull request in each of them — the per-repo effort DES §2 exists to remove.

Call `application.yml` and the same change is one edit here, picked up by each repo on its next version bump.

It also keeps the mapping our business rather than theirs. A repo should not need to know which linters its archetype implies.

## Available

| Archetype | Workflow | Runs |
|---|---|---|
| `docs` | `docs.yml` | commit-lint, docs-ci |
| `dbt-project` | `dbt-project.yml` | commit-lint, dbt-ci |
| `dlt-pipeline` | `dlt-pipeline.yml` | commit-lint, python-ci |

Each passes its language workflow's inputs straight through, so anything in [`docs-ci.md`](docs-ci.md), [`dbt-ci.md`](dbt-ci.md) or [`python-ci.md`](python-ci.md) can be set on the archetype workflow instead.

`commit-lint` is on by default and only runs on pull requests. Turn it off with `commit-lint: false` if a repo has its own arrangement.

## Not here yet, and why

| Archetype | Waiting on |
|---|---|
| `application` | `container-ci` and `security-baseline`. §8 says an application is containerised and §4 makes build, scan and publish part of the sequence — so a wrapper that ran only the Python gates would let a repo go green without any of that. Worse than having no wrapper, because it looks conformant. |
| `dagster-user-code` | The same. It builds an image (§8). |
| `web-app` | §5 names no JS or TypeScript tooling. RFC-0009 added the archetype to §8 without it, so there is nothing yet for a wrapper to run. |

Those three arrive with the workflows they depend on, complete rather than partial.

## `dlt-pipeline` has no container build on purpose

A dlt pipeline is Python that runs inside the user-code image (§8). The image belongs to the `dagster-user-code` repo that carries it, so the pipeline repo gets the Python gates and nothing else. That is the archetype table's answer, not an omission.

## Release is its own caller

Releasing is not part of the CI wrapper. It has a different trigger — a push to `main` rather than a pull request — and it needs `contents: write`, which a CI workflow should not carry.

```yaml
name: release
on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  release:
    uses: datumlabsio/actions/.github/workflows/release.yml@v1.0.0
```

See [`release.md`](release.md).

## Nesting

A repo's `ci.yml` calls an archetype workflow, which calls a language workflow — three levels, within GitHub's limit of four. An archetype workflow must not grow another layer beneath the language workflows.
