"""Raport before/after w formacie Markdown (czytelny na GitHubie i w każdym edytorze)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from studio.loading import LoadInfo
from studio.pipeline import PipelineResult
from studio.profiling import DataProfile
from studio.quality import QualityRule, check_rules, outlier_summary


def _format_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float):
        if value.is_integer() or abs(value) >= 1000:
            text = f"{value:,.0f}" if value.is_integer() else f"{value:,.1f}"
            return text.replace(",", " ")  # spacja jako separator tysięcy
        return f"{value:.4g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(frame: pd.DataFrame, index: bool = True) -> str:
    """Prosta tabela Markdown bez zależności od pakietu ``tabulate``."""
    if frame.empty:
        return "_(brak danych)_"
    data = frame.reset_index() if index else frame
    header = "| " + " | ".join(map(str, data.columns)) + " |"
    separator = "|" + "|".join("---" for _ in data.columns) + "|"
    body = [
        "| " + " | ".join(_format_cell(v) for v in row) + " |"
        for row in data.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *body])


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class ReportInput:
    load_info: LoadInfo
    config_path: Path
    before: DataProfile
    after: DataProfile
    raw_frame: pd.DataFrame
    clean_frame: pd.DataFrame
    pipeline: PipelineResult
    audit: pd.DataFrame
    cleaned_path: Path
    outlier_factor: float


def _summary_table(data: ReportInput, rules: list[QualityRule]) -> pd.DataFrame:
    before_rules = check_rules(data.raw_frame, rules)["violations"].sum() if rules else 0
    after_rules = check_rules(data.clean_frame, rules)["violations"].sum() if rules else 0
    invalid_before = sum(sum(t.values()) for t in data.before.invalid_tokens.values())
    invalid_after = sum(sum(t.values()) for t in data.after.invalid_tokens.values())
    rows = [
        ("Liczba rekordów", data.before.rows, data.after.rows),
        ("Liczba kolumn", data.before.columns, data.after.columns),
        ("Braki (komórki)", data.before.total_missing, data.after.total_missing),
        ("Pełne duplikaty", data.before.duplicate_rows, data.after.duplicate_rows),
        ("Błędne tokeny w kolumnach liczbowych", invalid_before, invalid_after),
        ("Naruszenia reguł jakości", int(before_rules), int(after_rules)),
    ]
    return pd.DataFrame(rows, columns=["miara", "przed", "po"]).set_index("miara")


def _invalid_tokens_table(profile: DataProfile) -> pd.DataFrame:
    rows = [
        {"column": column, "token": token, "count": count}
        for column, tokens in profile.invalid_tokens.items()
        for token, count in tokens.items()
    ]
    return pd.DataFrame(rows)


def _outlier_comparison(data: ReportInput) -> pd.DataFrame:
    columns = data.pipeline.outlier_columns
    if not columns:
        return pd.DataFrame()
    raw_numeric = data.raw_frame.copy()
    for column in columns:  # surowe kolumny mogą być tekstowe (np. przez tokeny „?”)
        raw_numeric[column] = pd.to_numeric(raw_numeric[column], errors="coerce")
    before = outlier_summary(raw_numeric, columns, data.outlier_factor).set_index("column")
    after = outlier_summary(data.clean_frame, columns, data.outlier_factor).set_index("column")
    return pd.DataFrame(
        {
            "granica dolna (po)": after["lower"],
            "granica górna (po)": after["upper"],
            "outliery przed": before["outliers"],
            "outliery po": after["outliers"],
            "% po": after["outliers_pct"],
        }
    )


def _describe_comparison(before: DataProfile, after: DataProfile) -> pd.DataFrame:
    stats = ["mean", "std", "min", "50%", "max"]
    left = before.numeric_stats.reindex(columns=stats).add_suffix(" (przed)")
    right = after.numeric_stats.reindex(columns=stats).add_suffix(" (po)")
    combined = right.join(left, how="left")
    ordered = [f"{s} ({w})" for s in stats for w in ("przed", "po")]
    return combined.reindex(columns=ordered)


def build_report(data: ReportInput) -> str:
    info = data.load_info
    rules = data.pipeline.applicable_rules
    raw_rules = check_rules(data.raw_frame, rules) if rules else pd.DataFrame()
    clean_rules = check_rules(data.clean_frame, rules) if rules else pd.DataFrame()
    profile_cols = ["dtype", "missing", "missing_pct", "unique", "constant"]

    sections = [
        "# Raport jakości danych — przed i po czyszczeniu",
        "",
        "## 1. Źródło i parametry",
        f"- Plik wejściowy: `{info.path.as_posix()}` (SHA-256: `{file_sha256(info.path)[:16]}…`)",
        f"- Separator: {info.separator_name}, kodowanie: `{info.encoding}`, "
        f"separator dziesiętny: `{info.decimal}`, pominięte wadliwe wiersze: {info.skipped_bad_lines}",
        f"- Konfiguracja reguł: `{data.config_path.as_posix()}`",
        f"- Plik wynikowy: `{data.cleaned_path.as_posix()}` "
        f"(SHA-256: `{file_sha256(data.cleaned_path)[:16]}…`) — identyczny skrót przy każdym "
        "uruchomieniu potwierdza powtarzalność.",
        "",
        "## 2. Podsumowanie",
        markdown_table(_summary_table(data, rules)),
        "",
        "## 3. Wykryte problemy (dane surowe)",
        "### 3.1 Profil kolumn",
        markdown_table(data.before.column_table[profile_cols]),
        "",
        "### 3.2 Nieliczbowe tokeny w kolumnach liczbowych",
        markdown_table(_invalid_tokens_table(data.before), index=False),
        "",
        "### 3.3 Reguły jakości (tylko wykrycie — bez zmiany danych)",
        markdown_table(raw_rules, index=False),
        "",
        f"### 3.4 Pełne duplikaty: **{data.before.duplicate_rows}**",
        "",
        "## 4. Dziennik operacji (ślad zmian)",
        "Kolumna `unrelated_columns_unchanged` potwierdza, że operacja nie zmieniła kolumn "
        "spoza swojego zakresu (sprawdzane automatycznie po każdym kroku).",
        "",
        markdown_table(data.audit.drop(columns=["timestamp"]), index=False),
        "",
        "## 5. Stan po czyszczeniu",
        "### 5.1 Profil kolumn",
        markdown_table(data.after.column_table[profile_cols]),
        "",
        "### 5.2 Reguły jakości po czyszczeniu",
        markdown_table(clean_rules, index=False),
        "",
        f"### 5.3 Obserwacje odstające (IQR, k = {data.outlier_factor:g})",
        "Outliery są **oznaczane** kolumnami `*_outlier_iqr`, a nie usuwane: w danych spisowych "
        "duże wartości (np. liczba pokoi w dużym obszarze) są zwykle prawdziwe. Błędy "
        "(wartości niemożliwe) obsługują reguły zakresu w kroku 4.",
        "",
        markdown_table(_outlier_comparison(data)),
        "",
        "## 6. Statystyki opisowe kolumn liczbowych",
        markdown_table(_describe_comparison(data.before, data.after)),
        "",
        "## 7. Ostrzeżenia",
        "\n".join(f"- {w}" for w in data.pipeline.warnings) or "_(brak)_",
        "",
    ]
    return "\n".join(sections)
