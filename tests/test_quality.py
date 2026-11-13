from __future__ import annotations

import math

import pandas as pd
import pytest

from studio.quality import (
    AllowedValuesRule,
    RangeRule,
    RuleError,
    check_rules,
    iqr_bounds,
    iqr_mask,
)


def test_range_rule_detects_without_modifying():
    frame = pd.DataFrame({"age": [5, -1, 30, 200, None], "other": list("abcde")})
    copy = frame.copy()
    rule = RangeRule("age", 0, 120)

    mask = rule.violation_mask(frame)

    assert mask.tolist() == [False, True, False, True, False]  # brak ≠ naruszenie
    pd.testing.assert_frame_equal(frame, copy)


def test_check_rules_report():
    frame = pd.DataFrame({"age": [5, -1, 30], "zone": ["A", "X", "B"]})
    report = check_rules(frame, [RangeRule("age", 0), AllowedValuesRule("zone", frozenset("AB"))])
    assert report["violations"].tolist() == [1, 1]
    assert report["examples"].tolist() == ["-1", "X"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"column": "a"}, "min lub max"),
        ({"column": "a", "min_value": 10, "max_value": 1}, "min"),
        ({"column": "a", "min_value": math.nan}, "liczbą"),
        ({"column": "a", "min_value": "zero"}, "liczbą"),
    ],
)
def test_invalid_rule_parameters_raise(kwargs, message):
    with pytest.raises(RuleError, match=message):
        RangeRule(**kwargs)


def test_rule_on_missing_column_raises():
    with pytest.raises(RuleError, match="nie istnieje"):
        RangeRule("nope", 0).violation_mask(pd.DataFrame({"a": [1]}))


def test_iqr_known_values():
    # Q1 = 2, Q3 = 4, IQR = 2 → granice [-1, 7]
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5, 2, 3, 4, 100]})
    bounds = iqr_bounds(frame, "x")
    assert (bounds.q1, bounds.q3, bounds.lower, bounds.upper) == (2, 4, -1, 7)
    assert iqr_mask(frame, "x").tolist() == [False] * 8 + [True]


def test_iqr_constant_column_has_no_outliers():
    frame = pd.DataFrame({"x": [5, 5, 5, 5]})
    assert iqr_bounds(frame, "x") is None
    assert not iqr_mask(frame, "x").any()


def test_iqr_rejects_non_positive_factor():
    with pytest.raises(RuleError):
        iqr_bounds(pd.DataFrame({"x": [1, 2, 3]}), "x", factor=0)
