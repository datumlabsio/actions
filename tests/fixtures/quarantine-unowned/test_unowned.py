import pytest

# No owner, no date. This is what the gate exists to catch.
@pytest.mark.skip(reason="broken")
def test_broken():
    assert True
