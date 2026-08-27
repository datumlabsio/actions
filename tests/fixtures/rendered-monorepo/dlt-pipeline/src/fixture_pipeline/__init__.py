"""Ingestion pipeline for fixture.

Runs inside the Dagster user-code image (DES §8, archetype `dlt-pipeline`); it
does not build a container of its own.
"""

from .pipeline import build_pipeline, normalise_schema_name

__all__ = ["build_pipeline", "normalise_schema_name"]
