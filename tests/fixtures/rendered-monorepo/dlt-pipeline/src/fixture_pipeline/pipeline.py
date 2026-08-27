"""The fixture pipeline.

Replace `normalise_schema_name` and `build_pipeline` with the real source once
the credentials exist. What is here is deliberately runnable and typed, so the
repo passes its own gates on arrival rather than after a first commit.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Where this pipeline lands. Named per convention so downstream dbt does not
#: care which door the data came through (blocks/dlt.md §1).
RAW_SCHEMA = "raw_fixture"

#: `merge` is incremental and rerun-safe; `replace` is a full refresh.
WRITE_DISPOSITION = "merge"

#: `evolve` lands new columns and flags them; `freeze` fails the run loudly.
#: A contract-feeding pipeline chooses freeze (blocks/dlt.md §3).
SCHEMA_EVOLUTION = "evolve"


@dataclass(frozen=True)
class PipelineSpec:
    """What a pipeline declares about itself.

    Frozen because a run must not be able to change its own destination
    part-way through.
    """

    source: str
    destination_schema: str
    write_disposition: str
    schema_evolution: str

    def is_contract_feeding(self) -> bool:
        """A frozen schema is how a pipeline says something depends on its shape."""
        return self.schema_evolution == "freeze"


def normalise_schema_name(raw: str) -> str:
    """Lower-case a schema name and collapse separators to single underscores.

    Naming has to be predictable, because dbt sources are declared against
    these names and a rename is a breaking change downstream.
    """
    collapsed = "_".join(part for part in raw.replace("-", " ").split() if part)
    return collapsed.lower()


def build_pipeline() -> PipelineSpec:
    """The spec this repo's pipeline runs under."""
    return PipelineSpec(
        source="fixture",
        destination_schema=normalise_schema_name(RAW_SCHEMA),
        write_disposition=WRITE_DISPOSITION,
        schema_evolution=SCHEMA_EVOLUTION,
    )
