"""Fixture package for exercising python-ci.

Deliberately small and deliberately clean: it must pass ruff, ruff format,
mypy and pytest. If a change to the shared configs breaks this package, that
change would have broken every repo in the org — which is the point of having
it here.
"""


def normalise_schema_name(raw: str) -> str:
    """Lower-case a schema name and collapse separators to underscores.

    Typed, documented, and boring on purpose — it exists to give the linters
    and mypy something real to look at.
    """
    collapsed = "_".join(part for part in raw.replace("-", " ").split() if part)
    return collapsed.lower()
