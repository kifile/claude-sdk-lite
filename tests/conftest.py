"""Pytest configuration file."""

# Fix import path for test_helpers
import sys
from pathlib import Path

import pytest

# Add tests directory to path
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

from test_helpers import (
    get_cat_command,
    get_true_command,
    is_windows,
)


@pytest.fixture
def is_windows_fixture():
    """Fixture that returns True if running on Windows."""
    return is_windows


@pytest.fixture
def cat_command_fixture():
    """Fixture that returns platform-appropriate cat command."""
    return get_cat_command()


@pytest.fixture
def true_command_fixture():
    """Fixture that returns platform-appropriate true command."""
    return get_true_command()
