"""Odporne wczytywanie plików CSV.

Obsługiwane:
* automatyczne wykrywanie separatora (``,``, ``;``, tabulator, ``|``),
* automatyczne wykrywanie przecinka dziesiętnego (typowe dla CSV z polskiego Excela),
* kodowanie UTF-8 (także z BOM) z awaryjną próbą CP1250,
* kontrolowane błędy: brak pliku, pusty plik, sam nagłówek, złe kodowanie, wadliwy wiersz.

Każdy błąd jest zgłaszany jako :class:`CsvLoadError` z komunikatem wskazującym rozwiązanie,
dzięki czemu GUI (Lab. 8) może go pokazać użytkownikowi zamiast się zamknąć.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

CANDIDATE_SEPARATORS: tuple[str, ...] = (",", ";", "\t", "|")
DEFAULT_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1250")
SAMPLE_LINES = 50

BadLinesPolicy = Literal["error", "skip"]


class CsvLoadError(Exception):
    """Kontrolowany błąd wczytywania pliku CSV (komunikat jest gotowy dla użytkownika)."""


@dataclass(frozen=True)
class LoadInfo:
    """Metadane wczytania — trafiają do raportu, żeby wynik dało się odtworzyć."""

    path: Path
    separator: str
    encoding: str
    decimal: str
    rows: int
    columns: int
    skipped_bad_lines: int = 0

    @property
    def separator_name(self) -> str:
        names = {",": "przecinek", ";": "średnik", "\t": "tabulator", "|": "kreska pionowa"}
        return names.get(self.separator, repr(self.separator))


def detect_encoding(raw_bytes: bytes, candidates: tuple[str, ...] = DEFAULT_ENCODINGS) -> str:
    """Zwraca pierwsze kodowanie, w którym cały plik daje się zdekodować."""
    for encoding in candidates:
        try:
            raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    raise CsvLoadError(
        "Nie udało się odczytać pliku w kodowaniach: "
        f"{', '.join(candidates)}. Zapisz plik jako CSV UTF-8 "
        "(np. w Excelu: Zapisz jako → CSV UTF-8) i spróbuj ponownie."
    )


def _field_counts(lines: list[str], separator: str) -> list[int]:
    reader = csv.reader(lines, delimiter=separator)
    return [len(row) for row in reader if row]


def detect_separator(sample: str) -> str:
    """Wykrywa separator na podstawie spójności liczby pól w pierwszych wierszach.

    Kandydat jest poprawny, gdy nagłówek ma > 1 pole, a większość wierszy danych ma tyle
    samo pól co nagłówek. Spośród poprawnych wybierany jest ten z największą liczbą kolumn.
    Dzięki analizie nagłówka przecinek dziesiętny w pliku rozdzielanym średnikiem nie myli
    detekcji (nazwy kolumn nie zawierają przecinków).
    """
    lines = [line for line in sample.splitlines() if line.strip()][:SAMPLE_LINES]
    if not lines:
        raise CsvLoadError("Plik nie zawiera danych.")

    best_separator, best_columns = ",", 1
    for separator in CANDIDATE_SEPARATORS:
        counts = _field_counts(lines, separator)
        header_fields = counts[0]
        if header_fields < 2:
            continue
        data_counts = counts[1:] or [header_fields]
        consistent_share = sum(c == header_fields for c in data_counts) / len(data_counts)
        if consistent_share >= 0.8 and header_fields > best_columns:
            best_separator, best_columns = separator, header_fields
    return best_separator


def detect_decimal(sample: str, separator: str) -> str:
    """Przecinek dziesiętny jest możliwy tylko, gdy separatorem pól nie jest przecinek."""
    if separator != "," and re.search(r"\d,\d", sample):
        return ","
    return "."


def _read_frame(
    text: str, separator: str, decimal: str, on_bad_lines: BadLinesPolicy
) -> tuple[pd.DataFrame, int]:
    skipped: list[list[str]] = []

    def remember_bad_line(fields: list[str]) -> None:
        skipped.append(fields)
        return None  # None = pomiń wiersz

    handler = remember_bad_line if on_bad_lines == "skip" else "error"
    frame = pd.read_csv(
        io.StringIO(text),
        sep=separator,
        decimal=decimal,
        engine="python",
        on_bad_lines=handler,
        skipinitialspace=True,
    )
    return frame, len(skipped)


def load_csv(
    path: str | Path,
    separator: str | None = None,
    encoding: str | None = None,
    on_bad_lines: BadLinesPolicy = "error",
) -> tuple[pd.DataFrame, LoadInfo]:
    """Wczytuje CSV i zwraca (DataFrame, LoadInfo).

    Args:
        path: ścieżka do pliku.
        separator: wymuszony separator; ``None`` = wykrywanie automatyczne.
        encoding: wymuszone kodowanie; ``None`` = UTF-8, a awaryjnie CP1250.
        on_bad_lines: ``"error"`` – wadliwy wiersz przerywa wczytywanie z komunikatem,
            ``"skip"`` – wadliwe wiersze są pomijane i liczone w ``LoadInfo``.

    Raises:
        CsvLoadError: przy każdym przewidzianym problemie z plikiem.
    """
    path = Path(path)
    if not path.is_file():
        raise CsvLoadError(f"Plik nie istnieje: {path}. Sprawdź ścieżkę.")

    raw_bytes = path.read_bytes()
    if not raw_bytes.strip():
        raise CsvLoadError(f"Plik {path.name} jest pusty. Wybierz plik z nagłówkiem i danymi.")

    if encoding is None:
        encoding = detect_encoding(raw_bytes)
    try:
        text = raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise CsvLoadError(
            f"Nie można zdekodować pliku jako {encoding}: {exc}. Wybierz inne kodowanie."
        ) from exc

    sample = "\n".join(text.splitlines()[:SAMPLE_LINES])
    separator = separator or detect_separator(sample)
    decimal = detect_decimal(sample, separator)

    try:
        frame, skipped = _read_frame(text, separator, decimal, on_bad_lines)
    except pd.errors.EmptyDataError as exc:
        raise CsvLoadError(f"Plik {path.name} nie zawiera danych.") from exc
    except (pd.errors.ParserError, csv.Error) as exc:
        raise CsvLoadError(
            f"Wadliwy wiersz w pliku {path.name}: {exc}. "
            "Popraw wiersz w pliku albo wczytaj z opcją pomijania wadliwych wierszy."
        ) from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.empty:
        raise CsvLoadError(
            f"Plik {path.name} zawiera tylko nagłówek — brak rekordów do analizy."
        )
    duplicated_names = [n for n, c in Counter(frame.columns).items() if c > 1]
    if duplicated_names:
        raise CsvLoadError(f"Powtórzone nazwy kolumn: {duplicated_names}. Zmień nazwy w pliku.")

    info = LoadInfo(
        path=path,
        separator=separator,
        encoding=encoding,
        decimal=decimal,
        rows=len(frame),
        columns=frame.shape[1],
        skipped_bad_lines=skipped,
    )
    return frame, info
