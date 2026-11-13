"""Operacje czyszczące jako czyste funkcje.

Każda funkcja:
* przyjmuje DataFrame i **nie modyfikuje go** (pracuje na kopii),
* zmienia wyłącznie kolumny wskazane w parametrach (oraz ewentualnie dodaje kolumnę-flagę),
* zwraca ``(nowy_frame, OperationResult)`` z liczbą rekordów i komórek dotkniętych operacją.

Sesja (:mod:`studio.session`) opakowuje te funkcje, dopisuje wpis do dziennika i sprawdza,
że kolumny niezwiązane z operacją pozostały nietknięte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
from pandas.api import types as ptypes

from studio.quality import AllowedValuesRule, RangeRule, RuleError, iqr_bounds

MissingStrategy = Literal["drop", "mean", "median", "mode", "constant"]
RuleAction = Literal["set_nan", "drop", "clip", "flag"]
OutlierAction = Literal["flag", "clip", "drop"]
TextCase = Literal["upper", "lower", "none"]

MISSING_STRATEGIES: tuple[str, ...] = ("drop", "mean", "median", "mode", "constant")
RANGE_ACTIONS: tuple[str, ...] = ("set_nan", "drop", "clip", "flag")
ALLOWED_ACTIONS: tuple[str, ...] = ("set_nan", "drop", "flag")
OUTLIER_ACTIONS: tuple[str, ...] = ("flag", "clip", "drop")


class CleaningError(ValueError):
    """Operacji nie można wykonać dla podanych parametrów (komunikat dla użytkownika)."""


@dataclass(frozen=True)
class OperationResult:
    """Skutek operacji: ile rekordów dotknęła, ile komórek zmieniła, które kolumny ruszyła."""

    rows_affected: int
    cells_changed: int
    touched_columns: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise CleaningError(f"Brak kolumn w danych: {missing}. Wybierz istniejące kolumny.")


def _changed_cells(before: pd.Series, after: pd.Series) -> pd.Series:
    """Maska komórek, które faktycznie zmieniły wartość (NaN → NaN nie jest zmianą)."""
    both_missing = before.isna() & after.isna()
    return ~both_missing & ~(before == after).fillna(False).astype(bool)


# --------------------------------------------------------------------------- duplikaty


def drop_duplicates(
    frame: pd.DataFrame, subset: list[str] | None = None, keep: Literal["first", "last"] = "first"
) -> tuple[pd.DataFrame, OperationResult]:
    """Usuwa pełne duplikaty (``subset=None``) albo duplikaty wg jawnie wskazanego klucza."""
    if subset:
        _require_columns(frame, subset)
    mask = frame.duplicated(subset=subset or None, keep=keep)
    result = frame.loc[~mask].copy()
    removed = int(mask.sum())
    return result, OperationResult(
        rows_affected=removed,
        cells_changed=0,
        touched_columns=(),
        details={"subset": subset or "wszystkie kolumny", "keep": keep, "removed_rows": removed},
    )


# ----------------------------------------------------------------- typy i normalizacja


def coerce_numeric(frame: pd.DataFrame, column: str) -> tuple[pd.DataFrame, OperationResult]:
    """Konwertuje kolumnę na liczbową; nieliczbowe tokeny (np. ``?``, ``brak``) → NaN."""
    _require_columns(frame, [column])
    result = frame.copy()
    before = frame[column]
    converted = pd.to_numeric(before, errors="coerce")
    invalid = before.notna() & converted.isna()
    result[column] = converted
    tokens = before[invalid].astype(str).value_counts().to_dict()
    return result, OperationResult(
        rows_affected=int(invalid.sum()),
        cells_changed=int(invalid.sum()),
        touched_columns=(column,),
        details={"invalid_tokens": {str(k): int(v) for k, v in tokens.items()}},
    )


def normalize_text(
    frame: pd.DataFrame, column: str, case: TextCase = "upper"
) -> tuple[pd.DataFrame, OperationResult]:
    """Usuwa białe znaki z brzegów i ujednolica wielkość liter w kolumnie tekstowej."""
    _require_columns(frame, [column])
    if ptypes.is_numeric_dtype(frame[column]):
        raise CleaningError(f"Kolumna '{column}' jest liczbowa — normalizacja tekstu nie ma sensu.")
    if case not in ("upper", "lower", "none"):
        raise CleaningError(f"Nieznana opcja wielkości liter: {case!r} (upper/lower/none).")
    def normalize(value: Any) -> Any:
        if not isinstance(value, str):
            return value  # braki i nie-teksty zostają bez zmian
        value = value.strip()
        return value.upper() if case == "upper" else value.lower() if case == "lower" else value

    result = frame.copy()
    before = frame[column]
    after = before.map(normalize).astype(before.dtype)
    result[column] = after
    changed = _changed_cells(before, after)
    return result, OperationResult(
        rows_affected=int(changed.sum()),
        cells_changed=int(changed.sum()),
        touched_columns=(column,),
        details={"case": case},
    )


# ---------------------------------------------------------------------- reguły jakości


def apply_range_rule(
    frame: pd.DataFrame, rule: RangeRule, action: RuleAction
) -> tuple[pd.DataFrame, OperationResult]:
    """Obsługa wartości spoza zakresu. Akcja jest *zawsze* jawnie wybierana przez użytkownika.

    * ``set_nan`` – błędna wartość → brak (potem strategia braków),
    * ``drop``    – usunięcie rekordu,
    * ``clip``    – przycięcie do najbliższej granicy,
    * ``flag``    – dane bez zmian, dodana kolumna ``<kolumna>_out_of_range``.
    """
    if action not in RANGE_ACTIONS:
        raise CleaningError(f"Nieznana akcja reguły zakresu: {action!r}. Dozwolone: {RANGE_ACTIONS}.")
    _require_columns(frame, [rule.column])
    if not ptypes.is_numeric_dtype(frame[rule.column]):
        raise CleaningError(
            f"Kolumna '{rule.column}' nie jest liczbowa — najpierw wykonaj konwersję typu."
        )
    mask = rule.violation_mask(frame)
    count = int(mask.sum())
    result = frame.copy()
    touched: tuple[str, ...] = (rule.column,)
    cells = count

    if action == "set_nan":
        result[rule.column] = frame[rule.column].mask(mask)
    elif action == "drop":
        result = frame.loc[~mask].copy()
        touched, cells = (), 0
    elif action == "clip":
        result[rule.column] = frame[rule.column].clip(rule.min_value, rule.max_value)
    else:  # flag
        flag_column = f"{rule.column}_out_of_range"
        result[flag_column] = mask
        touched, cells = (flag_column,), 0

    return result, OperationResult(
        rows_affected=count,
        cells_changed=cells,
        touched_columns=touched,
        details={"rule": rule.describe(), "action": action},
    )


def apply_allowed_values(
    frame: pd.DataFrame, rule: AllowedValuesRule, action: RuleAction
) -> tuple[pd.DataFrame, OperationResult]:
    """Obsługa niedozwolonych kategorii: ``set_nan`` / ``drop`` / ``flag``."""
    if action not in ALLOWED_ACTIONS:
        raise CleaningError(
            f"Nieznana akcja reguły kategorii: {action!r}. Dozwolone: {ALLOWED_ACTIONS}."
        )
    _require_columns(frame, [rule.column])
    mask = rule.violation_mask(frame)
    count = int(mask.sum())
    result = frame.copy()
    touched: tuple[str, ...] = (rule.column,)
    cells = count
    if action == "set_nan":
        result[rule.column] = frame[rule.column].mask(mask)
    elif action == "drop":
        result = frame.loc[~mask].copy()
        touched, cells = (), 0
    else:
        flag_column = f"{rule.column}_invalid_category"
        result[flag_column] = mask
        touched, cells = (flag_column,), 0
    return result, OperationResult(
        rows_affected=count,
        cells_changed=cells,
        touched_columns=touched,
        details={"rule": rule.describe(), "action": action},
    )


# ------------------------------------------------------------------------------- braki


def _fill_value(series: pd.Series, strategy: str, value: Any) -> Any:
    column = series.name
    is_numeric = ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series)
    if strategy in ("mean", "median") and not is_numeric:
        raise CleaningError(
            f"Strategia '{strategy}' wymaga kolumny liczbowej, a '{column}' jest tekstowa. "
            "Użyj 'mode', 'constant' lub 'drop'."
        )
    non_null = series.dropna()
    if strategy != "constant" and non_null.empty:
        raise CleaningError(f"Kolumna '{column}' nie ma żadnych wartości — użyj 'constant' lub 'drop'.")
    if strategy == "mean":
        return float(non_null.mean())
    if strategy == "median":
        return float(non_null.median())
    if strategy == "mode":
        return non_null.mode().iloc[0]  # mode() jest posortowane → wynik deterministyczny
    if value is None:
        raise CleaningError(f"Strategia 'constant' dla '{column}' wymaga podania wartości.")
    return value


def fill_missing(
    frame: pd.DataFrame, column: str, strategy: MissingStrategy, value: Any = None
) -> tuple[pd.DataFrame, OperationResult]:
    """Obsługa braków w jednej kolumnie.

    * ``drop``     – usunięcie rekordów z brakiem w tej kolumnie,
    * ``mean`` / ``median`` – imputacja (tylko kolumny liczbowe),
    * ``mode``     – najczęstsza wartość (liczby i tekst),
    * ``constant`` – wartość podana przez użytkownika.
    """
    if strategy not in MISSING_STRATEGIES:
        raise CleaningError(f"Nieznana strategia braków: {strategy!r}. Dozwolone: {MISSING_STRATEGIES}.")
    _require_columns(frame, [column])
    missing_mask = frame[column].isna()
    count = int(missing_mask.sum())

    if strategy == "drop":
        result = frame.loc[~missing_mask].copy()
        return result, OperationResult(count, 0, (), {"strategy": strategy, "removed_rows": count})

    fill = _fill_value(frame[column], strategy, value)
    result = frame.copy()
    if count:
        result[column] = frame[column].fillna(fill)
    return result, OperationResult(
        rows_affected=count,
        cells_changed=count,
        touched_columns=(column,),
        details={"strategy": strategy, "fill_value": fill},
    )


# ----------------------------------------------------------------------------- outliery


def handle_outliers(
    frame: pd.DataFrame, column: str, factor: float = 1.5, action: OutlierAction = "flag"
) -> tuple[pd.DataFrame, OperationResult]:
    """Obsługa obserwacji odstających wg IQR (Tukey).

    * ``flag`` – dane bez zmian, dodana kolumna ``<kolumna>_outlier_iqr`` (domyślnie),
    * ``clip`` – winsoryzacja do granic IQR,
    * ``drop`` – usunięcie rekordów (stosować tylko, gdy outlier jest błędem!).
    """
    if action not in OUTLIER_ACTIONS:
        raise CleaningError(f"Nieznana akcja dla outlierów: {action!r}. Dozwolone: {OUTLIER_ACTIONS}.")
    _require_columns(frame, [column])
    if not ptypes.is_numeric_dtype(frame[column]):
        raise CleaningError(f"Kolumna '{column}' nie jest liczbowa — metoda IQR wymaga liczb.")
    try:
        bounds = iqr_bounds(frame, column, factor)
    except RuleError as exc:
        raise CleaningError(str(exc)) from exc

    details: dict[str, Any] = {"method": "IQR", "factor": factor, "action": action}
    if bounds is None:
        mask = pd.Series(False, index=frame.index)
        details["note"] = "IQR = 0 lub brak danych — nie wykryto outlierów"
    else:
        values = frame[column]
        mask = ((values < bounds.lower) | (values > bounds.upper)).fillna(False).astype(bool)
        details.update(lower=round(bounds.lower, 6), upper=round(bounds.upper, 6))
    count = int(mask.sum())

    result = frame.copy()
    touched: tuple[str, ...] = (column,)
    cells = count
    if action == "flag":
        flag_column = f"{column}_outlier_iqr"
        result[flag_column] = mask
        touched, cells = (flag_column,), 0
    elif action == "clip" and bounds is not None:
        result[column] = frame[column].clip(bounds.lower, bounds.upper)
    elif action == "drop":
        result = frame.loc[~mask].copy()
        touched, cells = (), 0
    return result, OperationResult(count, cells, touched, details)
