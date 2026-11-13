"""Konfigurowalny pipeline czyszczenia.

Kolejność kroków jest stała i uzasadniona:

1. **duplikaty** – usuwamy dokładne kopie surowych wierszy, zanim cokolwiek zmienimy
   (po imputacji dwa różne rekordy mogłyby stać się identyczne),
2. **konwersja typów** – tokeny typu ``?``/``brak`` w kolumnach liczbowych → brak,
3. **normalizacja tekstu** – ``" near bay"`` → ``"NEAR BAY"``,
4. **reguły zakresu i kategorii** – wartości niemożliwe; akcja wybrana w konfiguracji,
5. **braki** – po krokach 2–4, bo one same mogą tworzyć braki (``set_nan``),
6. **outliery (IQR)** – na końcu, na danych bez błędów; domyślnie tylko oznaczane.

Reguły dla kolumn, których nie ma w pliku, są pomijane i raportowane jako ostrzeżenia —
dzięki temu jedna konfiguracja obsługuje oba popularne warianty California Housing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from studio import cleaning
from studio.profiling import invalid_numeric_tokens, numeric_columns
from studio.quality import AllowedValuesRule, QualityRule, RangeRule, RuleError
from studio.session import DataSession, OperationRecord


class ConfigError(ValueError):
    """Niepoprawny plik konfiguracji pipeline'u."""


@dataclass(frozen=True)
class MissingSpec:
    strategy: str
    value: Any = None


@dataclass(frozen=True)
class PipelineConfig:
    drop_duplicates: bool = True
    duplicate_subset: tuple[str, ...] | None = None
    coerce_numeric: bool = True
    coerce_min_numeric_share: float = 0.8
    text_normalization: dict[str, str] = field(default_factory=dict)
    range_rules: tuple[tuple[RangeRule, str], ...] = ()
    allowed_rules: tuple[tuple[AllowedValuesRule, str], ...] = ()
    missing_default_numeric: str = "median"
    missing_default_text: str = "mode"
    missing_per_column: dict[str, MissingSpec] = field(default_factory=dict)
    outlier_columns: tuple[str, ...] | None = None  # None = wszystkie liczbowe
    outlier_factor: float = 1.5
    outlier_action: str = "flag"

    @property
    def quality_rules(self) -> list[QualityRule]:
        return [rule for rule, _ in self.range_rules] + [rule for rule, _ in self.allowed_rules]


# --------------------------------------------------------------------- parsowanie


def _choice(value: Any, allowed: tuple[str, ...], where: str) -> str:
    if value not in allowed:
        raise ConfigError(f"{where}: niepoprawna wartość {value!r}. Dozwolone: {', '.join(allowed)}.")
    return value


def _parse_range_rules(items: list[dict[str, Any]]) -> tuple[tuple[RangeRule, str], ...]:
    parsed = []
    for i, item in enumerate(items, start=1):
        where = f"range_rules[{i}]"
        try:
            rule = RangeRule(item["column"], item.get("min"), item.get("max"))
        except KeyError as exc:
            raise ConfigError(f"{where}: brak pola 'column'.") from exc
        except RuleError as exc:
            raise ConfigError(f"{where}: {exc}") from exc
        parsed.append((rule, _choice(item.get("action", "set_nan"), cleaning.RANGE_ACTIONS, where)))
    return tuple(parsed)


def _parse_allowed_rules(items: list[dict[str, Any]]) -> tuple[tuple[AllowedValuesRule, str], ...]:
    parsed = []
    for i, item in enumerate(items, start=1):
        where = f"allowed_values[{i}]"
        try:
            rule = AllowedValuesRule(item["column"], frozenset(map(str, item["values"])))
        except KeyError as exc:
            raise ConfigError(f"{where}: wymagane pola 'column' i 'values'.") from exc
        except RuleError as exc:
            raise ConfigError(f"{where}: {exc}") from exc
        parsed.append((rule, _choice(item.get("action", "set_nan"), cleaning.ALLOWED_ACTIONS, where)))
    return tuple(parsed)


def _parse_missing(section: dict[str, Any]) -> dict[str, MissingSpec]:
    specs = {}
    for column, spec in section.get("columns", {}).items():
        if isinstance(spec, str):
            spec = {"strategy": spec}
        strategy = _choice(spec.get("strategy"), cleaning.MISSING_STRATEGIES, f"missing.{column}")
        if strategy == "constant" and "value" not in spec:
            raise ConfigError(f"missing.{column}: strategia 'constant' wymaga pola 'value'.")
        specs[column] = MissingSpec(strategy, spec.get("value"))
    return specs


def parse_config(data: dict[str, Any]) -> PipelineConfig:
    """Zamienia słownik (np. z JSON) na zwalidowany :class:`PipelineConfig`."""
    if not isinstance(data, dict):
        raise ConfigError("Konfiguracja musi być obiektem JSON.")
    duplicates = data.get("duplicates", {})
    coerce = data.get("coerce_numeric", {})
    missing = data.get("missing", {})
    outliers = data.get("outliers", {})

    factor = outliers.get("factor", 1.5)
    if not isinstance(factor, (int, float)) or factor <= 0:
        raise ConfigError(f"outliers.factor musi być liczbą dodatnią (podano {factor!r}).")
    share = coerce.get("min_numeric_share", 0.8)
    if not isinstance(share, (int, float)) or not 0 < share <= 1:
        raise ConfigError(f"coerce_numeric.min_numeric_share musi być w (0, 1] (podano {share!r}).")
    normalization = data.get("text_normalization", {})
    for column, case in normalization.items():
        _choice(case, ("upper", "lower", "none"), f"text_normalization.{column}")
    outlier_columns = outliers.get("columns", "auto")
    subset = duplicates.get("subset")

    return PipelineConfig(
        drop_duplicates=bool(duplicates.get("enabled", True)),
        duplicate_subset=tuple(subset) if subset else None,
        coerce_numeric=bool(coerce.get("enabled", True)),
        coerce_min_numeric_share=float(share),
        text_normalization=dict(normalization),
        range_rules=_parse_range_rules(data.get("range_rules", [])),
        allowed_rules=_parse_allowed_rules(data.get("allowed_values", [])),
        missing_default_numeric=_choice(
            missing.get("default_numeric", "median"), cleaning.MISSING_STRATEGIES, "missing.default_numeric"
        ),
        missing_default_text=_choice(
            missing.get("default_text", "mode"), ("drop", "mode", "constant"), "missing.default_text"
        ),
        missing_per_column=_parse_missing(missing),
        outlier_columns=None if outlier_columns == "auto" else tuple(outlier_columns),
        outlier_factor=float(factor),
        outlier_action=_choice(outliers.get("action", "flag"), cleaning.OUTLIER_ACTIONS, "outliers.action"),
    )


def load_config(path: str | Path) -> PipelineConfig:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Nie znaleziono pliku konfiguracji: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Błąd składni JSON w {path.name}: {exc}.") from exc
    return parse_config(data)


# --------------------------------------------------------------------- wykonanie


@dataclass
class PipelineResult:
    records: list[OperationRecord]
    warnings: list[str]
    applicable_rules: list[QualityRule]
    outlier_columns: list[str]


class _Runner:
    """Wykonuje kroki konfiguracji na sesji i zbiera ostrzeżenia."""

    def __init__(self, session: DataSession, config: PipelineConfig) -> None:
        self.session = session
        self.config = config
        self.records: list[OperationRecord] = []
        self.skipped: dict[str, list[str]] = {}

    def _has(self, column: str, context: str) -> bool:
        if column in self.session.current.columns:
            return True
        self.skipped.setdefault(context, []).append(column)
        return False

    @property
    def warnings(self) -> list[str]:
        return [
            f"{context}: pominięto — kolumny nieobecne w danych: {', '.join(cols)}"
            for context, cols in self.skipped.items()
        ]

    def duplicates(self) -> None:
        if self.config.drop_duplicates:
            subset = list(self.config.duplicate_subset) if self.config.duplicate_subset else None
            self.records.append(self.session.drop_duplicates(subset))

    def coerce(self) -> None:
        if not self.config.coerce_numeric:
            return
        suspects = invalid_numeric_tokens(self.session.current, self.config.coerce_min_numeric_share)
        for column in suspects:
            self.records.append(self.session.coerce_numeric(column))

    def normalize(self) -> None:
        for column, case in self.config.text_normalization.items():
            if self._has(column, "normalizacja tekstu"):
                self.records.append(self.session.normalize_text(column, case))  # type: ignore[arg-type]

    def rules(self) -> list[QualityRule]:
        applied: list[QualityRule] = []
        for rule, action in self.config.range_rules:
            if self._has(rule.column, "reguły jakości"):
                self.records.append(self.session.apply_range_rule(rule, action))  # type: ignore[arg-type]
                applied.append(rule)
        for rule, action in self.config.allowed_rules:
            if self._has(rule.column, "reguły jakości"):
                self.records.append(self.session.apply_allowed_values(rule, action))  # type: ignore[arg-type]
                applied.append(rule)
        return applied

    def missing(self) -> None:
        numeric = set(numeric_columns(self.session.current))
        for column in self.config.missing_per_column:
            self._has(column, "strategia braków")
        # Najpierw kolumny ze strategią 'drop', żeby imputacja nie liczyła statystyk
        # na rekordach, które i tak zostaną usunięte.
        order = sorted(
            self.session.current.columns,
            key=lambda c: self.config.missing_per_column.get(c, MissingSpec("")).strategy != "drop",
        )
        for column in order:
            if not self.session.current[column].isna().any():
                continue
            spec = self.config.missing_per_column.get(column)
            if spec is None:
                default = (
                    self.config.missing_default_numeric if column in numeric else self.config.missing_default_text
                )
                spec = MissingSpec(default)
            self.records.append(self.session.fill_missing(column, spec.strategy, spec.value))  # type: ignore[arg-type]

    def outliers(self) -> list[str]:
        frame = self.session.current
        if self.config.outlier_columns is None:
            candidates = [c for c in numeric_columns(frame) if not c.endswith(("_outlier_iqr", "_out_of_range"))]
        else:
            candidates = [c for c in self.config.outlier_columns if self._has(c, "outliery")]
        for column in candidates:
            self.records.append(
                self.session.handle_outliers(column, self.config.outlier_factor, self.config.outlier_action)  # type: ignore[arg-type]
            )
        return candidates


def applicable_rules(config: PipelineConfig, columns: list[str]) -> list[QualityRule]:
    return [rule for rule in config.quality_rules if rule.column in columns]


def run_pipeline(session: DataSession, config: PipelineConfig) -> PipelineResult:
    """Wykonuje cały pipeline na ``session.current``. Dane surowe pozostają nietknięte."""
    runner = _Runner(session, config)
    runner.duplicates()
    runner.coerce()
    runner.normalize()
    rules = runner.rules()
    runner.missing()
    outlier_columns = runner.outliers()
    return PipelineResult(runner.records, runner.warnings, rules, outlier_columns)
