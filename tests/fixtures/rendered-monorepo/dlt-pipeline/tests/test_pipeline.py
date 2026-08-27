"""Tests for the fixture pipeline.

blocks/dlt.md §5 requires a dry-run against the source before a first
production run. That needs credentials, so it is not here — these cover the
parts that hold without a network.
"""

from fixture_pipeline import build_pipeline, normalise_schema_name


def test_destination_is_the_raw_zone() -> None:
    assert build_pipeline().destination_schema == "raw_fixture"


def test_schema_name_is_predictable() -> None:
    assert normalise_schema_name("Raw-fixture  Events") == "raw_fixture_events"


def test_empty_schema_name() -> None:
    assert normalise_schema_name("") == ""


def test_write_disposition_is_declared() -> None:
    assert build_pipeline().write_disposition in {"merge", "replace"}


def test_contract_feeding_follows_schema_evolution() -> None:
    spec = build_pipeline()
    assert spec.is_contract_feeding() == (spec.schema_evolution == "freeze")
