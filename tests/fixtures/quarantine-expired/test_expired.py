import pytest

# Owned, but the date has passed.
@pytest.mark.xfail(reason="quarantined(@humayun-1, 2020-01-01): waiting on upstream")
def test_upstream():
    assert True
