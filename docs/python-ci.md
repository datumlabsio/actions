# python-ci

CI for Python: `ruff`, `mypy`, `pytest`, and the repo's `pre-commit` hooks, all under `uv`.

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
    uses: datumlabsio/actions/.github/workflows/python-ci.yml@v1.0.0
```

## Inputs

| Input | Type | Default | What it does |
|---|---|---|---|
| `python-version` | string | `"3.12"` | Version for uv to install. |
| `working-directory` | string | `"."` | Where the project is, if not the repo root. |
| `config-dir` | string | `"."` | Where the vendored configs live, relative to `working-directory`. |
| `lint` | boolean | `true` | `ruff check` and `ruff format --check`. |
| `typecheck` | boolean | `true` | `mypy`. |
| `test` | boolean | `true` | `pytest`. |
| `pre-commit` | boolean | `true` | The repo's hooks. Fails if there is no config — DES §3 requires one. |

## Where the configs come from

**Not from here.** Your repo carries its own copy of `ruff.toml`, `mypy.ini` and `tool-versions.txt`, vendored in by its scaffold. The canonical copies live in [`configs/`](../configs/README.md), and each vendored file starts with a `# datum-config:` version stamp.

This is on purpose. It means `ruff check` on your laptop reads the same file the runner reads, so a lint rule is never something you meet for the first time in a failing pull request. It also means CI fetches nothing at runtime and needs no token.

The trade is that the config physically exists in every repo, so it can drift. Three things stop that:

- The version stamp says which version the repo carries.
- The org conformance workflow flags repos behind a supported version.
- Renovate opens the bump.

A vendored config is **bumped, never hand-edited** — the same rule RFC-0010 set for `.claude/`. Extend it in your own `pyproject.toml` if you need to; do not weaken it without a written reason (DES §5).

## Running the same checks locally

```bash
uv run --with-requirements tool-versions.txt -- ruff check --config ruff.toml .
uv run --with-requirements tool-versions.txt -- mypy --config-file mypy.ini .
uv run --with-requirements tool-versions.txt -- pytest -q
```

Same files, same pinned versions, same result.

## The stamp check

Before anything runs, the workflow confirms all three files exist and each carries a `# datum-config:` stamp. Missing means the scaffold never put it there; unstamped means somebody hand-wrote it. Both fail immediately with a message that says what to do, rather than surfacing as a confusing "config not found" from ruff three steps later.

CI can only check that the stamp is present — it cannot tell whether the body was edited, because it has no access to the canonical copy. Detecting an edited config is the conformance audit's job; it can read both repos.

## Path-shaped settings

Keep `exclude`, `src`, `files`, `mypy_path`, `testpaths` and per-file ignores in your `pyproject.toml`, never in a vendored config. Those resolve against the config's own location, and the vendored files sit at a different depth in every repo.

The fixture under `tests/fixtures/python-ok/` shows the split: shared rules in the vendored files, `pythonpath` and `testpaths` in `pyproject.toml`.

## Tool versions

From your repo's `tool-versions.txt`, pinned exactly. A new ruff release cannot break the fleet overnight; it breaks that file's next bump, on a pull request, where someone can look at it.
