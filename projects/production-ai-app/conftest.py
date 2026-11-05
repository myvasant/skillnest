"""Run the tests against starter/ (default) or the reference solution (GW_TARGET=solution)."""

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
TARGET = "solution" if os.environ.get("GW_TARGET") == "solution" else "starter"
sys.path.insert(0, str(HERE / TARGET))


def pytest_configure(config: pytest.Config) -> None:
    """Register the opt-in `network` marker and hide a non-actionable third-party notice."""
    config.addinivalue_line("markers", "network: needs network access or an external service")
    config.addinivalue_line("filterwarnings", "ignore:Using `httpx` with `starlette.testclient`")
