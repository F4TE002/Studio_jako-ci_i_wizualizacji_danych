"""Profil danych: rozmiar, typy, statystyki opisowe, braki, duplikaty i unikalność.

Wszystkie funkcje są tylko do odczytu — nigdy nie modyfikują przekazanego DataFrame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from pandas.api import types as ptypes

ColumnKind = Literal["numeric", "text", "bool", "datetime"]


def column_kind(series: pd.Series) -> ColumnKind:
    """Upraszcza dtype pandas do czterech kategorii używanych w aplikacji."""
    if ptypes.is_bool_dtype(series):
        return "bool"
    if ptypes.is_numeric_dtype(series):
        return "numeric"
    if ptypes.is_datetime64_any_dtype(series):
        return "datetime"
    return "text"


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if column_kind(frame[c]) == "numeric"]


def text_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if column_kind(frame[c]) == "text"]


def column_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Tabela: kolumna → typ, rodzaj, niepuste, braki, % braków, unikalne, stała?"""
    rows = len(frame)
    missing = frame.isna().sum()
    unique = frame.nunique(dropna=True)
    profile = pd.DataFrame(
        {
            "dtype": frame.dtypes.astype(str),
            "kind": [column_kind(frame[c]) for c in frame.columns],
            "non_null": frame.notna().sum(),
            "missing": missing,
            "missing_pct": (missing / rows * 100).round(2) if rows else 0.0,
            "unique": unique,
            "constant": unique <= 1,
        },
        index=pd.Index(frame.columns, name="column"),  # nowy obiekt — nie zmieniamy frame.columns
    )
    return profile


def numeric_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Statystyki opisowe kolumn liczbowych (count, mean, std, min, kwartyle, max)."""
    columns = numeric_columns(frame)
    if not columns:
        return pd.DataFrame()
    return frame[columns].describe().T


def text_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Statystyki kolumn tekstowych (count, unique, top, freq)."""
    columns = text_columns(frame)
    if not columns:
        return pd.DataFrame()
    return frame[columns].astype("object").describe().T


def count_full_duplicates(frame: pd.DataFrame, subset: list[str] | None = None) -> int:
    """Liczba rekordów, które są powtórzeniem wcześniejszego rekordu (pierwsze wystąpienie
    nie jest liczone). Bez ``subset`` porównywane są wszystkie kolumny (pełne duplikaty)."""
    return int(frame.duplicated(subset=subset, keep="first").sum())


def invalid_numeric_tokens(
    frame: pd.DataFrame, min_numeric_share: float = 0.8
) -> dict[str, dict[str, int]]:
    """Wykrywa kolumny tekstowe, które *powinny* być liczbowe (≥ ``min_numeric_share``
    niepustych wartości to liczby), i zwraca dla nich licznik błędnych tokenów,
    np. ``{"housing_median_age": {"?": 7, "brak": 8}}``."""
    result: dict[str, dict[str, int]] = {}
    for column in text_columns(frame):
        values = frame[column].dropna()
        if values.empty:
            continue
        parsed = pd.to_numeric(values, errors="coerce")
        share = parsed.notna().mean()
        if min_numeric_share <= share < 1.0:
            bad = values[parsed.isna()].astype(str)
            result[column] = {str(k): int(v) for k, v in bad.value_counts().items()}
    return result


@dataclass
class DataProfile:
    """Kompletny profil zbioru — sześć elementów wymaganych w rubryce oceny."""

    rows: int
    columns: int
    column_table: pd.DataFrame
    numeric_stats: pd.DataFrame
    text_stats: pd.DataFrame
    duplicate_rows: int
    invalid_tokens: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_missing(self) -> int:
        return int(self.column_table["missing"].sum())

    @property
    def columns_with_missing(self) -> list[str]:
        table = self.column_table
        return table.index[table["missing"] > 0].tolist()


def build_profile(frame: pd.DataFrame, min_numeric_share: float = 0.8) -> DataProfile:
    return DataProfile(
        rows=len(frame),
        columns=frame.shape[1],
        column_table=column_profile(frame),
        numeric_stats=numeric_summary(frame),
        text_stats=text_summary(frame),
        duplicate_rows=count_full_duplicates(frame),
        invalid_tokens=invalid_numeric_tokens(frame, min_numeric_share),
    )
