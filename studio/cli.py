"""Kamień milowy Lab. 6: profil → pipeline czyszczenia → raport before/after → cleaned.csv.

Użycie::

    python -m studio.cli data/raw/california_housing_sample.csv
    python -m studio.cli dane.csv --config config/cleaning_config.json --out output --skip-bad-lines
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from studio.loading import CsvLoadError
from studio.pipeline import ConfigError, load_config, run_pipeline
from studio.report import ReportInput, build_report
from studio.session import DataSession

DEFAULT_CONFIG = Path("config/cleaning_config.json")
DEFAULT_OUTPUT = Path("output")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profil i czyszczenie pliku CSV (Lab. 6).")
    parser.add_argument("input", type=Path, help="plik CSV do analizy")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="plik JSON z regułami")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="katalog wynikowy")
    parser.add_argument("--sep", default=None, help="wymuszony separator (domyślnie: wykrywanie)")
    parser.add_argument("--encoding", default=None, help="wymuszone kodowanie (domyślnie: UTF-8/CP1250)")
    parser.add_argument("--skip-bad-lines", action="store_true", help="pomijaj wadliwe wiersze")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Path:
    config = load_config(args.config)
    session = DataSession.from_csv(
        args.input,
        separator=args.sep,
        encoding=args.encoding,
        on_bad_lines="skip" if args.skip_bad_lines else "error",
    )
    before = session.profile(raw=True)
    result = run_pipeline(session, config)
    after = session.profile()

    args.out.mkdir(parents=True, exist_ok=True)
    cleaned_path = session.export_current(args.out / "cleaned.csv")
    session.export_audit_log(args.out / "audit_log.csv")

    assert session.source is not None
    report = build_report(
        ReportInput(
            load_info=session.source,
            config_path=args.config,
            before=before,
            after=after,
            raw_frame=session.raw,
            clean_frame=session.current,
            pipeline=result,
            audit=session.audit_frame(),
            cleaned_path=cleaned_path,
            outlier_factor=config.outlier_factor,
        )
    )
    report_path = args.out / "report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"Wczytano: {before.rows} rekordów × {before.columns} kolumn "
          f"(separator: {session.source.separator_name}, kodowanie: {session.source.encoding})")
    print(f"Wykonano operacji: {len(result.records)}")
    for record in result.records:
        if record.rows_affected:
            print(f"  [{record.step:>2}] {record.operation:<22} {', '.join(record.columns):<40} "
                  f"rekordy: {record.rows_affected:>4}  ({record.rows_before} → {record.rows_after})")
    for warning in result.warnings:
        print(f"  ! {warning}")
    print(f"Po czyszczeniu: {after.rows} rekordów × {after.columns} kolumn, braki: {after.total_missing}, "
          f"duplikaty: {after.duplicate_rows}")
    print(f"Zapisano: {cleaned_path}, {report_path}, {args.out / 'audit_log.csv'}")
    return report_path


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # konsola Windows bywa w CP1250/CP852
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        run(args)
    except (CsvLoadError, ConfigError, ValueError, OSError) as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
