# dbt-project — the models

Local context for this folder only. Conventions and guardrails for the whole
repo are in the root `CLAUDE.md`; nothing here restates them.

Warehouse: **clickhouse**.

## Commands

```bash
sqlfluff lint models/
dbt build
python dbt-yaml-coverage.py --manifest target/manifest.json
```

Exactly what CI runs, from the versions pinned in `dbt-tool-versions.txt`.

## Guardrails

- **EVERY new or changed model MUST carry a test** (DES §11, DPS §5). Line
  coverage does not apply here; a model without a test is the gap.
- **NEVER put a credential in `profiles.yml`.** It reads from the environment;
  the values come from the secret manager.
- **NEVER edit `target/`.** It is build output.
- **NEVER rename a mart column without checking consumers.** A dashboard
  breaking is not visible from here.
