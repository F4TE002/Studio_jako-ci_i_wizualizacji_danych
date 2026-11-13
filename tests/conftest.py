from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "data" / "test"
CONFIG_PATH = ROOT / "config" / "cleaning_config.json"


@pytest.fixture
def test_data() -> Path:
    return TEST_DATA


@pytest.fixture
def small_frame() -> pd.DataFrame:
    """Mały, ręcznie kontrolowany zbiór: 1 pełny duplikat (wiersz 3 = wiersz 0),
    1 „prawie duplikat” (wiersz 4 różni się kategorią), braki liczbowe i tekstowe."""
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 1, 5, 6],
            "price": [100.0, np.nan, 300.0, 100.0, 100.0, 1000.0],
            "area": [50.0, 40.0, np.nan, 50.0, 50.0, 45.0],
            "category": ["A", "B", None, "A", "B", "A"],
        }
    )
