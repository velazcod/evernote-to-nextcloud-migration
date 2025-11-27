"""Pytest configuration and fixtures."""

import pytest
from pathlib import Path


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--quick",
        action="store_true",
        default=False,
        help="Run quick validation tests (smallest ENEX file only)",
    )
    parser.addoption(
        "--full",
        action="store_true",
        default=False,
        help="Run full validation tests (all ENEX files)",
    )


@pytest.fixture
def quick_mode(request):
    """Return True if --quick flag is set."""
    return request.config.getoption("--quick")


@pytest.fixture
def full_mode(request):
    """Return True if --full flag is set."""
    return request.config.getoption("--full")


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_enex(fixtures_dir):
    """Return path to sample ENEX file."""
    return fixtures_dir / "sample.enex"


@pytest.fixture
def imported_notes_dir():
    """Return path to actual Imported Notes directory."""
    return Path(__file__).parent.parent / "Imported Notes"


@pytest.fixture
def output_dir(tmp_path):
    """Create and return a temporary output directory."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def enex_files(imported_notes_dir):
    """Return list of all ENEX files in Imported Notes."""
    if imported_notes_dir.exists():
        return sorted(imported_notes_dir.glob("*.enex"))
    return []


@pytest.fixture
def smallest_enex(enex_files):
    """Return the smallest ENEX file for quick tests."""
    if not enex_files:
        pytest.skip("No ENEX files found in Imported Notes/")
    return min(enex_files, key=lambda f: f.stat().st_size)
