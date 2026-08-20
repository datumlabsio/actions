# configs — the canonical copies

This directory holds the org's shared tool configs. It is the source of truth; it is not what CI reads at runtime.

Every repo carries its own copy of the configs that apply to it, vendored in by its scaffold with a version stamp at the top. CI reads the repo's copy. That means:

- **A developer's local run matches CI.** `ruff check` on a laptop reads the same file the runner reads. Nobody discovers a lint rule at pull-request time.
- **Nothing is fetched at runtime**, so CI has one less thing that can fail for a reason unrelated to the code, and a config change arrives as a reviewable bump rather than silently altering every build at once. This repo is public now, so fetching *would* work — vendoring is a choice, not a workaround.
- **Drift is caught rather than prevented.** The stamp says which version a repo carries; the org conformance workflow flags repos behind a supported version, and Renovate opens the bump.

The rule that makes this work is the same one RFC-0010 set for `.claude/`: a vendored asset is **bumped, never hand-edited**. A repo MAY extend a config in its own `pyproject.toml`; it MUST NOT weaken one without a written reason in the repo (DES §5).

## What is here

| File | Vendored into | Read by |
|---|---|---|
| `ruff.toml` | every Python repo | `ruff check`, `ruff format` |
| `mypy.ini` | every Python repo | `mypy` |
| `tool-versions.txt` | every Python repo | `python-ci`, and `uv run --with-requirements` locally |

## Changing one

A pull request here, with a review. Then `scaffolds` picks up the new version for new repos, and Renovate opens bumps for existing ones.

Style arguments are pull requests against these files. They are not comments on somebody else's code — that is what DES §5 means by *the linters are the convention*.

## The one constraint

**No path-shaped keys.** No `exclude`, no `src`, no `files`, no `mypy_path`, no per-file ignores. Those resolve differently depending on where the config sits, and these files sit in a different place in every repo. Anything path-shaped belongs in the repo's own `pyproject.toml`.

## The web-app configs

| File | Vendored into | Read by |
|---|---|---|
| `biome.json` | every `web-app` repo | `biome ci` |
| `tsconfig.base.json` | every `web-app` repo | the repo's `tsconfig.json`, via `extends` |
| `web-tool-versions.txt` | every `web-app` repo | `web-ci`, and a developer's local run |
| `no-stale-quarantine.py` | any repo with tests | `python-ci` and `web-ci`, DES §11 |

`tsconfig.base.json` obeys the no-path-shaped-keys rule the same way the others do: it carries compiler options only. `include`, `exclude` and `paths` belong in the repo's own `tsconfig.json`, because they resolve relative to wherever the file sits.

Two of the pins are deliberately behind the newest release, and the reasoning is in [docs/web-ci.md](../docs/web-ci.md#why-the-pinned-versions-are-not-the-newest): Node tracks Active LTS rather than current, and TypeScript stays on 5.9 until the 7.x native rewrite has more than a handful of patch releases behind it.
