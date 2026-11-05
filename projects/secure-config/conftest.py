"""Run the tests against starter/ (default) or the reference solution (GW_TARGET=solution)."""

import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
TARGET = "solution" if os.environ.get("GW_TARGET") == "solution" else "starter"
sys.path.insert(0, str(HERE / TARGET))
