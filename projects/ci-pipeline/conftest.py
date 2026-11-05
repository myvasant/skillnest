"""Run the tests against starter/ (default) or the reference solution (GW_TARGET=solution)."""

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
TARGET = "solution" if os.environ.get("GW_TARGET") == "solution" else "starter"
sys.path.insert(0, str(HERE / TARGET))


@pytest.fixture
def workflow_path() -> Path:
    """The workflow file under test.

    Starter: your file in ``starter/.github/workflows/ci.yml``.
    Solution: the reference in ``.github/workflows/ci.yml`` at the kit root, which is
    where GitHub would look if this folder were the root of a repository.
    """
    if TARGET == "solution":
        return HERE / ".github" / "workflows" / "ci.yml"
    return HERE / "starter" / ".github" / "workflows" / "ci.yml"


@pytest.fixture
def kit_root() -> Path:
    """The folder that holds requirements-dev.txt (the repository root in CI)."""
    return HERE
