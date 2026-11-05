"""Run the tests against starter/ (default) or the reference solution (GW_TARGET=solution)."""

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
TARGET = "solution" if os.environ.get("GW_TARGET") == "solution" else "starter"
sys.path.insert(0, str(HERE / TARGET))


def pytest_configure(config: pytest.Config) -> None:
    """Hide a third-party deprecation notice that is not actionable in this project."""
    config.addinivalue_line("filterwarnings", "ignore:Using `httpx` with `starlette.testclient`")


@pytest.fixture
def target_dir() -> Path:
    """The directory under test (starter/ or solution/): also the Docker build context."""
    return HERE / TARGET
