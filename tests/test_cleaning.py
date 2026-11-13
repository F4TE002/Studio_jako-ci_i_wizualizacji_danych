"""Czyszczenie: poprawność strategii, liczby zmian i brak wpływu na niezwiązane kolumny."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from studio import cleaning
from studio.cleaning import CleaningError
from studio.quality import AllowedValuesRule, RangeRule


def _assert_others_unchanged(before, after, touched):
    for column in before.columns:
        if column not in touched:
            pd.testing.assert_series_equal(after[column], before.loc[after.index, column])


# ----------------------------------------------------------------- duplikaty


def test_only_full_duplicates_are_removed(small_frame):
    result, info = cleaning.drop_duplicates(small_frame)
    assert info.rows_affected == 1
    assert result.index.tolist() == [0, 1, 2, 4, 5]  # wiersz 4 (inna kategoria) zostaje


def test_duplicates_by_explicit_key(small_frame):
    result, info = cleaning.drop_duplicates(small_frame, subset=["id"])
    assert info.rows_affected == 1
    assert result["id"].tolist() == [1, 2, 3, 5, 6]


def test_input_frame_is_not_modified(small_frame):
    copy = small_frame.copy()
    cleaning.drop_duplicates(small_frame)
    cleaning.fill_missing(small_frame, "price", "median")
    cleaning.handle_outliers(small_frame, "price", action="clip")
    pd.testing.assert_frame_equal(small_frame, copy)


# --------------------------------------------------------------------- braki


@pytest.mark.parametrize(
    "strategy, expected",
    [("mean", 320.0), ("median", 100.0), ("mode", 100.0)],
)
def test_numeric_imputation(small_frame, strategy, expected):
    result, info = cleaning.fill_missing(small_frame, "price", strategy)
    assert info.rows_affected == info.cells_changed == 1
    assert result.loc[1, "price"] == pytest.approx(expected)
    _assert_others_unchanged(small_frame, result, ("price",))


def test_text_missing_mode_and_constant(small_frame):
    by_mode, info = cleaning.fill_missing(small_frame, "category", "mode")
    assert by_mode.loc[2, "category"] == "A" and info.cells_changed == 1

    by_constant, _ = cleaning.fill_missing(small_frame, "category", "constant", "BRAK")
    assert by_constant.loc[2, "category"] == "BRAK"
    _assert_others_unchanged(small_frame, by_constant, ("category",))


def test_drop_rows_with_missing(small_frame):
    result, info = cleaning.fill_missing(small_frame, "area", "drop")
    assert info.rows_affected == 1 and len(result) == 5
    _assert_others_unchanged(small_frame, result, ())


def test_mean_on_text_column_is_rejected(small_frame):
    with pytest.raises(CleaningError, match="liczbowej"):
        cleaning.fill_missing(small_frame, "category", "mean")


def test_constant_without_value_is_rejected(small_frame):
    with pytest.raises(CleaningError, match="wymaga podania"):
        cleaning.fill_missing(small_frame, "price", "constant")


def test_unknown_strategy_is_rejected(small_frame):
    with pytest.raises(CleaningError, match="Nieznana"):
        cleaning.fill_missing(small_frame, "price", "magic")  # type: ignore[arg-type]


# ------------------------------------------------------------ reguły i typy


def test_coerce_numeric_counts_invalid_tokens():
    frame = pd.DataFrame({"x": ["1", "2", "?", None, "brak"], "y": [1, 2, 3, 4, 5]})
    result, info = cleaning.coerce_numeric(frame, "x")
    assert info.cells_changed == 2
    assert info.details["invalid_tokens"] == {"?": 1, "brak": 1}
    assert result["x"].isna().sum() == 3
    _assert_others_unchanged(frame, result, ("x",))


@pytest.mark.parametrize(
    "action, expected_values, expected_rows",
    [
        ("set_nan", [np.nan, 10.0, np.nan], 3),
        ("clip", [0.0, 10.0, 100.0], 3),
        ("drop", [10.0], 1),
        ("flag", [-5.0, 10.0, 500.0], 3),
    ],
)
def test_range_rule_actions(action, expected_values, expected_rows):
    frame = pd.DataFrame({"v": [-5.0, 10.0, 500.0], "keep": ["a", "b", "c"]})
    result, info = cleaning.apply_range_rule(frame, RangeRule("v", 0, 100), action)
    assert info.rows_affected == 2
    assert len(result) == expected_rows
    np.testing.assert_array_equal(result["v"].to_numpy(), np.array(expected_values))
    if action == "flag":
        assert result["v_out_of_range"].tolist() == [True, False, True]
    _assert_others_unchanged(frame, result, ("v", "v_out_of_range"))


def test_range_rule_on_text_column_requires_conversion():
    frame = pd.DataFrame({"v": ["1", "x"]})
    with pytest.raises(CleaningError, match="konwersję"):
        cleaning.apply_range_rule(frame, RangeRule("v", 0), "set_nan")


def test_normalize_then_allowed_values():
    frame = pd.DataFrame({"zone": [" near bay", "INLAND", None, "mars"], "n": [1, 2, 3, 4]})
    normalized, info = cleaning.normalize_text(frame, "zone")
    assert info.cells_changed == 2  # " near bay" i "mars"
    assert normalized["zone"].tolist()[:2] == ["NEAR BAY", "INLAND"]

    rule = AllowedValuesRule("zone", frozenset({"NEAR BAY", "INLAND"}))
    result, info = cleaning.apply_allowed_values(normalized, rule, "set_nan")
    assert info.rows_affected == 1
    assert result["zone"].isna().tolist() == [False, False, True, True]
    _assert_others_unchanged(frame, result, ("zone",))


# ------------------------------------------------------------------ outliery


def test_outliers_flag_keeps_data_and_adds_column():
    frame = pd.DataFrame({"x": [1.0, 2, 3, 4, 5, 2, 3, 4, 100], "y": range(9)})
    result, info = cleaning.handle_outliers(frame, "x", action="flag")
    assert info.rows_affected == 1 and info.cells_changed == 0
    pd.testing.assert_series_equal(result["x"], frame["x"])
    assert result["x_outlier_iqr"].sum() == 1


def test_outliers_clip_and_drop():
    frame = pd.DataFrame({"x": [1.0, 2, 3, 4, 5, 2, 3, 4, 100]})
    clipped, _ = cleaning.handle_outliers(frame, "x", action="clip")
    assert clipped["x"].max() == 7
    dropped, info = cleaning.handle_outliers(frame, "x", action="drop")
    assert len(dropped) == 8 and info.rows_affected == 1


def test_outliers_require_numeric_column(small_frame):
    with pytest.raises(CleaningError, match="liczbowa"):
        cleaning.handle_outliers(small_frame, "category")
