from datum_fixture import normalise_schema_name


def test_lowercases() -> None:
    assert normalise_schema_name("RawEvents") == "rawevents"


def test_collapses_separators() -> None:
    assert normalise_schema_name("raw-events  stripe") == "raw_events_stripe"


def test_empty_string() -> None:
    assert normalise_schema_name("") == ""
