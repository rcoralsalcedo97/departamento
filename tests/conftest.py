import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.normalize.currency import FxRate  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def fx():
    return FxRate(3.40, "test rate", "2026-09-24T00:00:00-05:00", live=False)
