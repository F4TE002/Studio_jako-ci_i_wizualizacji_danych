"""Model sesji: dane surowe, dane aktualne i dziennik operacji (ślad zmian).

``DataSession`` jest jedynym miejscem, w którym przechowywany jest stan analizy.
GUI (Lab. 8) będzie trzymać referencję do obiektu sesji — bez zmiennych globalnych.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from studio import cleaning
from studio.loading import BadLinesPolicy, LoadInfo, load_csv
from studio.profiling import DataProfile, build_profile
from studio.quality import AllowedValuesRule, QualityRule, RangeRule, check_rules

Operation = Callable[[pd.DataFrame], tuple[pd.DataFrame, cleaning.OperationResult]]


class IntegrityError(RuntimeError):
    """Operacja zmieniła kolumnę, której nie powinna była dotykać."""


@dataclass(frozen=True)
class OperationRecord:
    """Jeden wpis śladu zmian."""

    step: int
    timestamp: str
    operation: str
    columns: tuple[str, ...]
    params: dict[str, Any]
    rows_before: int
    rows_after: int
    rows_affected: int
    cells_changed: int
    unrelated_columns_unchanged: bool

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["columns"] = ", ".join(self.columns)
        row["params"] = "; ".join(f"{k}={v}" for k, v in self.params.items())
        return row


def unrelated_columns_unchanged(
    before: pd.DataFrame, after: pd.DataFrame, touched: tuple[str, ...]
) -> bool:
    """Sprawdza, że kolumny spoza ``touched`` mają identyczne wartości w zachowanych wierszach.

    Usunięcie całego rekordu nie jest „modyfikacją kolumny” — porównujemy tylko wiersze,
    które przetrwały operację (po indeksie)."""
    if not after.index.isin(before.index).all():
        return False
    for column in before.columns:
        if column in touched:
            continue
        if column not in after.columns:
            return False
        if not after[column].equals(before.loc[after.index, column]):
            return False
    return True


@dataclass
class DataSession:
    """Sesja analizy. ``raw`` nigdy nie jest modyfikowane; wszystkie operacje działają na ``current``."""

    raw: pd.DataFrame
    source: LoadInfo | None = None
    current: pd.DataFrame = field(init=False)
    audit_log: list[OperationRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.raw.empty:
            raise ValueError("Zbiór danych nie zawiera rekordów.")
        self.raw = self.raw.copy(deep=True)  # odcięcie od obiektu przekazanego z zewnątrz
        self.current = self.raw.copy(deep=True)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        separator: str | None = None,
        encoding: str | None = None,
        on_bad_lines: BadLinesPolicy = "error",
    ) -> "DataSession":
        frame, info = load_csv(path, separator=separator, encoding=encoding, on_bad_lines=on_bad_lines)
        return cls(frame, source=info)

    # ------------------------------------------------------------------ diagnostyka

    def profile(self, raw: bool = False) -> DataProfile:
        return build_profile(self.raw if raw else self.current)

    def check_rules(self, rules: list[QualityRule], raw: bool = False) -> pd.DataFrame:
        """Tylko wykrywa naruszenia — dane pozostają bez zmian."""
        return check_rules(self.raw if raw else self.current, rules)

    # -------------------------------------------------------------------- operacje

    def apply(self, name: str, operation: Operation, params: dict[str, Any]) -> OperationRecord:
        """Wykonuje operację na kopii ``current``, weryfikuje ją i dopisuje do dziennika."""
        before = self.current
        after, result = operation(before)
        unchanged = unrelated_columns_unchanged(before, after, result.touched_columns)
        if not unchanged:
            raise IntegrityError(
                f"Operacja '{name}' zmieniła kolumny spoza zakresu {result.touched_columns}."
            )
        params = dict(params)
        target_columns = tuple(params.pop("columns", ()))
        record = OperationRecord(
            step=len(self.audit_log) + 1,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            operation=name,
            columns=tuple(dict.fromkeys((*target_columns, *result.touched_columns))),
            params={**params, **result.details},
            rows_before=len(before),
            rows_after=len(after),
            rows_affected=result.rows_affected,
            cells_changed=result.cells_changed,
            unrelated_columns_unchanged=unchanged,
        )
        self.current = after
        self.audit_log.append(record)
        return record

    def drop_duplicates(self, subset: list[str] | None = None) -> OperationRecord:
        return self.apply(
            "usunięcie duplikatów",
            lambda df: cleaning.drop_duplicates(df, subset=subset),
            {"columns": tuple(subset or ())},
        )

    def coerce_numeric(self, column: str) -> OperationRecord:
        return self.apply(
            "konwersja na liczby", lambda df: cleaning.coerce_numeric(df, column), {"columns": (column,)}
        )

    def normalize_text(self, column: str, case: cleaning.TextCase = "upper") -> OperationRecord:
        return self.apply(
            "normalizacja tekstu",
            lambda df: cleaning.normalize_text(df, column, case),
            {"columns": (column,)},
        )

    def apply_range_rule(self, rule: RangeRule, action: cleaning.RuleAction) -> OperationRecord:
        return self.apply(
            "reguła zakresu",
            lambda df: cleaning.apply_range_rule(df, rule, action),
            {"columns": (rule.column,)},
        )

    def apply_allowed_values(
        self, rule: AllowedValuesRule, action: cleaning.RuleAction
    ) -> OperationRecord:
        return self.apply(
            "reguła kategorii",
            lambda df: cleaning.apply_allowed_values(df, rule, action),
            {"columns": (rule.column,)},
        )

    def fill_missing(
        self, column: str, strategy: cleaning.MissingStrategy, value: Any = None
    ) -> OperationRecord:
        return self.apply(
            "obsługa braków",
            lambda df: cleaning.fill_missing(df, column, strategy, value),
            {"columns": (column,)},
        )

    def handle_outliers(
        self, column: str, factor: float = 1.5, action: cleaning.OutlierAction = "flag"
    ) -> OperationRecord:
        return self.apply(
            "outliery (IQR)",
            lambda df: cleaning.handle_outliers(df, column, factor, action),
            {"columns": (column,)},
        )

    # ------------------------------------------------------------------------ stan

    def reset(self) -> None:
        """Powrót do danych surowych bez ponownego wczytywania pliku."""
        rows_before = len(self.current)
        self.current = self.raw.copy(deep=True)
        self.audit_log.append(
            OperationRecord(
                step=len(self.audit_log) + 1,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                operation="reset do danych surowych",
                columns=(),
                params={},
                rows_before=rows_before,
                rows_after=len(self.current),
                rows_affected=0,
                cells_changed=0,
                unrelated_columns_unchanged=True,
            )
        )

    def audit_frame(self) -> pd.DataFrame:
        columns = list(OperationRecord.__dataclass_fields__)
        return pd.DataFrame([r.as_row() for r in self.audit_log], columns=columns)

    def export_audit_log(self, path: str | Path) -> Path:
        path = Path(path)
        self.audit_frame().to_csv(path, index=False, encoding="utf-8")
        return path

    def export_current(self, path: str | Path) -> Path:
        """Zapis oczyszczonych danych do CSV (UTF-8, przecinek, bez indeksu)."""
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.current.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        except OSError as exc:
            raise OSError(
                f"Nie można zapisać pliku {path}: {exc}. Wybierz inny katalog lub zamknij plik "
                "w innym programie (np. Excelu)."
            ) from exc
        return path
