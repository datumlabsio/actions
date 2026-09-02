# dbt-ci

CI for the `dbt-project` archetype (DES §8). Enforces the gates in `blocks/dbt.md` §6: `dbt build` green, YAML coverage, SQL linting, and artifacts kept so quality history is continuous.

## Calling it

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
    uses: datumlabsio/actions/.github/workflows/dbt-ci.yml@v0.1.0
    secrets: inherit
```

## Inputs

| Input | Type | Default | What it does |
|---|---|---|---|
| `python-version` | string | `"3.12"` | Version for uv to install. |
| `working-directory` | string | `"."` | The dbt project directory. |
| `config-dir` | string | `"."` | Where the vendored configs live. |
| `profiles-dir` | string | `"."` | Where `profiles.yml` lives. |
| `dbt-target` | string | `"ci"` | Target to run against. A CI target, never production. |
| `adapter-requirements` | string | `"requirements.txt"` | File declaring the warehouse adapter. |
| `mart-path` | string | `"marts"` | Path segment identifying marts, for the contract check. |
| `lint` | boolean | `true` | `sqlfluff lint models/`. |
| `yaml-coverage` | boolean | `true` | Documentation and test coverage. |
| `so-what` | boolean | `false` | Every exposure names a decision fork, a reader and a moment (DAS §1). |
| `one-door` | boolean | `false` | Every exposure depends on marts only (DAS §2). |
| `build` | boolean | `true` | `dbt build`. |
| `upload-artifacts` | boolean | `true` | Keep `manifest.json` and `run_results.json`. |

### Secrets

| Secret | Required | What it does |
|---|---|---|
| `dbt-env` | no | Newline-separated `KEY=VALUE` lines, exported before dbt runs, for a CI target that needs credentials. |

**Never pass production credentials.** CI publishes artifacts; the install pulls them (DES §4). A PR-time `dbt build` runs against a CI target — a scratch schema, or duckdb — not against the warehouse that serves the client.

## What the stages check

**Vendored configs present and stamped.** `.sqlfluff`, `dbt-tool-versions.txt` and `dbt-yaml-coverage.py` must exist and carry a `# datum-config:` stamp — plus `check_so_what.py` and `check_one_door.py`, but only when those gates are switched on, so turning a gate on is the only thing that can newly fail this step. Fails first, with a message saying where they come from, rather than surfacing later as a confusing "config not found".

**Warehouse adapter declared.** The adapter differs per install — `dbt-bigquery`, `dbt-clickhouse`, `dbt-duckdb` — so it is the repo's business, not part of the shared pins. `dbt-tool-versions.txt` pins `dbt-core` and `sqlfluff` only.

**YAML coverage.** Reads `target/manifest.json` after `dbt parse` and enforces `blocks/dbt.md` §2:

1. Every model has a YAML entry at all
2. Every model has a description
3. Every declared column has a description
4. Every model has at least one test
5. Every mart model enforces a contract (also DPS §4)

What it cannot check: whether every column that actually exists in the warehouse is documented. That needs `catalog.json` from `dbt docs generate`, which needs a live connection. This checks every column the YAML declares.

**So-what gate** (`so-what`, off by default). Reads the same manifest and enforces DAS §1: every exposure description names a **DECISION** that is a fork between options, a **WHO** who reads it, and a **WHEN** they read it. "Revenue visibility" is a topic, not a decision, and fails. An exposure with no owner email fails too — an unowned dashboard is not a decision surface.

**One door up** (`one-door`, off by default). Enforces DAS §2 on the declared graph: every exposure's `depends_on` must resolve to a mart. An exposure reading a source, a staging model or an intermediate model fails.

What it cannot check: SQL an analyst types straight into the BI tool, which never reaches the manifest. That half is enforced in the warehouse — the BI service account is granted select on the mart schema only (DES §4). The check and the grant are belt and suspenders; neither replaces the other.

**SQL lint.** `sqlfluff lint models/` against the shared config, using the dbt templater so `ref()` and `source()` resolve.

**dbt build.** Models and tests together. `blocks/dbt.md` §6 makes this a merge gate.

**Artifacts.** `manifest.json` and `run_results.json` kept for 30 days, uploaded even when a stage fails — a failed run is exactly the one whose artifacts you want.

## Running the same checks locally

```bash
dbt deps
dbt parse --no-partial-parse
python dbt-yaml-coverage.py --manifest target/manifest.json
python check_so_what.py  --manifest target/manifest.json   # if so-what is on
python check_one_door.py --manifest target/manifest.json   # if one-door is on
sqlfluff lint models/
dbt build
```

Same files, same pinned versions, same result. See [`configs/README.md`](../configs/README.md) for why the configs are vendored rather than fetched.

## Elementary

`blocks/dbt.md` §4 requires Elementary in every install, with its results flowing into the platform audit stream. That is not in this workflow yet: `edr` needs a warehouse connection and its own package install, and the audit-stream wiring is platform work, not CI work. The artifacts this workflow keeps are the input Elementary consumes.

## The fixture

`tests/fixtures/dbt-ok/` is a real dbt project on duckdb — a seed, a staging model, and a contracted mart. `self-test` runs this workflow against it on every pull request, so `dbt build` and the contract check are genuinely exercised with no warehouse and no credentials. A change to the shared sqlfluff config or the coverage script breaks there before it reaches an install.

It also shows the split the vendored-config rule depends on: shared rules in `.sqlfluff`, and the adapter in the repo's own `requirements.txt`.
