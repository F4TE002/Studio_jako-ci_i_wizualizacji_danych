"""Reguły jakości i wykrywanie wartości odstających.

Funkcje w tym module tylko **wykrywają** problemy (zwracają maski / raporty).
Decyzja, co zrobić z wykrytymi rekordami, należy do użytkownika i jest realizowana
w module :mod:`studio.cleaning` — zgodnie z wymaganiem „reguła wykrywa rekord
i nie zmienia danych bez decyzji użytkownika”.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


class RuleError(ValueError):
    """Niepoprawne parametry reguły jakości."""


def _require_column(frame: pd.DataFrame, column: str) -> None:
    if column not in frame.columns:
        raise RuleError(f"Kolumna '{column}' nie istnieje w danych.")


@dataclass(frozen=True)
class RangeRule:
    """Zakres poprawnych wartości liczbowych (granice włącznie). Brak granicy = ``None``."""

    column: str
    min_value: float | None = None
    max_value: float | None = None

    def __post_init__(self) -> None:
        if self.min_value is None and self.max_value is None:
            raise RuleError(f"Reguła zakresu dla '{self.column}' musi mieć min lub max.")
        for bound in (self.min_value, self.max_value):
            if bound is not None and (not isinstance(bound, (int, float)) or math.isnan(bound)):
                raise RuleError(f"Granica reguły dla '{self.column}' musi być liczbą: {bound!r}.")
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise RuleError(
                f"Reguła dla '{self.column}': min ({self.min_value}) > max ({self.max_value}). "
                "Zamień granice miejscami."
            )

    def describe(self) -> str:
        low = "-∞" if self.min_value is None else f"{self.min_value:g}"
        high = "+∞" if self.max_value is None else f"{self.max_value:g}"
        return f"{self.column} ∈ [{low}, {high}]"

    def violation_mask(self, frame: pd.DataFrame) -> pd.Series:
        """True dla rekordów z wartością poza zakresem (braki nie są naruszeniem)."""
        _require_column(frame, self.column)
        values = pd.to_numeric(frame[self.column], errors="coerce")
        mask = pd.Series(False, index=frame.index)
        if self.min_value is not None:
            mask |= values < self.min_value
        if self.max_value is not None:
            mask |= values > self.max_value
        return mask.fillna(False).astype(bool)


@dataclass(frozen=True)
class AllowedValuesRule:
    """Zbiór dozwolonych wartości kolumny kategorialnej."""

    column: str
    allowed: frozenset[str]

    def __post_init__(self) -> None:
        if not self.allowed:
            raise RuleError(f"Reguła dla '{self.column}' ma pustą listę dozwolonych wartości.")

    def describe(self) -> str:
        return f"{self.column} ∈ {{{', '.join(sorted(self.allowed))}}}"

    def violation_mask(self, frame: pd.DataFrame) -> pd.Series:
        _require_column(frame, self.column)
        values = frame[self.column]
        return (values.notna() & ~values.astype(str).isin(self.allowed)).astype(bool)


QualityRule = RangeRule | AllowedValuesRule


def check_rules(frame: pd.DataFrame, rules: list[QualityRule], examples: int = 5) -> pd.DataFrame:
    """Raport reguł jakości: liczba i procent naruszeń oraz przykładowe błędne wartości."""
    rows = []
    for rule in rules:
        mask = rule.violation_mask(frame)
        bad_values = frame.loc[mask, rule.column].astype(str).unique()[:examples]
        rows.append(
            {
                "rule": rule.describe(),
                "column": rule.column,
                "violations": int(mask.sum()),
                "violations_pct": round(mask.mean() * 100, 2) if len(frame) else 0.0,
                "examples": ", ".join(bad_values),
            }
        )
    return pd.DataFrame(rows, columns=["rule", "column", "violations", "violations_pct", "examples"])


@dataclass(frozen=True)
class OutlierBounds:
    column: str
    q1: float
    q3: float
    iqr: float
    lower: float
    upper: float


def iqr_bounds(frame: pd.DataFrame, column: str, factor: float = 1.5) -> OutlierBounds | None:
    """Granice Tukeya: [Q1 − k·IQR, Q3 + k·IQR]. ``None``, gdy IQR = 0 lub brak liczb."""
    _require_column(frame, column)
    if factor <= 0:
        raise RuleError(f"Współczynnik IQR musi być dodatni (podano {factor}).")
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    q1, q3 = (float(q) for q in values.quantile([0.25, 0.75]))
    iqr = q3 - q1
    if iqr == 0:
        return None
    return OutlierBounds(column, q1, q3, iqr, q1 - factor * iqr, q3 + factor * iqr)


def iqr_mask(frame: pd.DataFrame, column: str, factor: float = 1.5) -> pd.Series:
    """True dla obserwacji odstających wg reguły IQR."""
    bounds = iqr_bounds(frame, column, factor)
    if bounds is None:
        return pd.Series(False, index=frame.index)
    values = pd.to_numeric(frame[column], errors="coerce")
    return ((values < bounds.lower) | (values > bounds.upper)).fillna(False).astype(bool)


def outlier_summary(frame: pd.DataFrame, columns: list[str], factor: float = 1.5) -> pd.DataFrame:
    """Dla każdej kolumny: granice IQR, liczba i procent obserwacji odstających."""
    rows = []
    for column in columns:
        bounds = iqr_bounds(frame, column, factor)
        count = int(iqr_mask(frame, column, factor).sum())
        rows.append(
            {
                "column": column,
                "q1": bounds.q1 if bounds else None,
                "q3": bounds.q3 if bounds else None,
                "lower": bounds.lower if bounds else None,
                "upper": bounds.upper if bounds else None,
                "outliers": count,
                "outliers_pct": round(count / len(frame) * 100, 2) if len(frame) else 0.0,
            }
        )
    return pd.DataFrame(rows)
