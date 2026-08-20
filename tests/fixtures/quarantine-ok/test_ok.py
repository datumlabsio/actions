import platform
import pytest

# Owned and in date — the gate lets this through.
@pytest.mark.skip(reason="quarantined(@humayun-1, 2099-01-01): flaky under xdist")
def test_flaky():
    assert True

# CONDITIONAL. Not a quarantine: a permanent statement that this test does not
# apply here, not a test nobody is looking at. Must pass with no annotation.
@pytest.mark.skipif(platform.system() == "Windows", reason="posix only")
def test_posix_only():
    assert True

def test_needs_optional_dep():
    pytest.importorskip("scipy")
    assert True
