from __future__ import annotations

import pandas as pd

from studio.loading import load_csv
from studio.profiling import build_profile, count_full_duplicates, invalid_numeric_tokens


def test_profile_counts_on_small_frame(small_frame):
    profile = build_profile(small_frame)
    table = profile.column_table

    assert (profile.rows, profile.columns) == (6, 4)
    assert table.loc["price", "missing"] == 1
    assert table.loc["price", "missing_pct"] == round(100 / 6, 2)
    assert table.loc["category", "missing"] == 1
    assert table.loc["category", "kind"] == "text"
    assert table.loc["price", "kind"] == "numeric"
    assert table.loc["category", "unique"] == 2
    assert profile.duplicate_rows == 1  # tylko wiersz 3 jest pełnym duplikatem
    assert profile.total_missing == 3
    assert set(profile.numeric_stats.index) == {"id", "price", "area"}


def test_profile_does_not_modify_input(small_frame):
    copy = small_frame.copy()
    build_profile(small_frame)
    pd.testing.assert_frame_equal(small_frame, copy)


def test_duplicates_by_key_differ_from_full_duplicates(small_frame):
    assert count_full_duplicates(small_frame) == 1
    assert count_full_duplicates(small_frame, subset=["id"]) == 1
    assert count_full_duplicates(small_frame, subset=["price", "area"]) == 2


def test_constant_column_is_marked():
    frame = pd.DataFrame({"x": [1, 1, 1], "y": [1, 2, 3]})
    table = build_profile(frame).column_table
    assert bool(table.loc["x", "constant"]) is True
    assert bool(table.loc["y", "constant"]) is False


def test_invalid_tokens_detected_in_numeric_like_text(test_data):
    frame, _ = load_csv(test_data / "quality_problems.csv")
    tokens = invalid_numeric_tokens(frame)
    assert tokens == {"price": {"?": 1}}
