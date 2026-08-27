# dlt-pipeline — ingestion

Local context for this folder only. Conventions and guardrails for the whole
repo are in the root `CLAUDE.md`; nothing here restates them.

Pulls from **fixture**, lands in `raw_fixture`. Runs inside
the Dagster user-code image and builds no container of its own (DES §8).

## Commands

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest
```

Exactly what CI runs, from the versions pinned in `tool-versions.txt`.

## Guardrails

- **EVERY changed resource MUST carry a schema test** (DES §11).
- **NEVER commit a credential or a `.dlt/secrets.toml`.** Credentials come from
  the environment.
- **NEVER widen `write_disposition` to `replace`** to fix a duplicate. That
  deletes history; fix the primary key instead.
