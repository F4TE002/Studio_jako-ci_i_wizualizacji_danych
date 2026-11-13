"""Syntetyczny zbiór w schemacie California Housing (wariant Kaggle) z kontrolowanymi problemami.

Służy do rozwoju i testów, zanim dostępny będzie zbiór referencyjny od prowadzącej.
Wszystkie wstrzyknięte problemy są zapisywane w manifeście JSON, więc testy mogą
sprawdzić, że raport wykrywa **dokładnie** przygotowane problemy.

Generowanie jest deterministyczne (stałe ziarno) — ten sam plik przy każdym uruchomieniu::

    python -m studio.sample_data
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SEED = 42
BASE_ROWS = 2000
OCEAN_CATEGORIES = ["<1H OCEAN", "INLAND", "NEAR OCEAN", "NEAR BAY", "ISLAND"]
OCEAN_PROBS = [0.44, 0.32, 0.13, 0.109, 0.001]

# liczba rekordów dotkniętych każdym problemem
INJECTIONS: dict[str, int] = {
    "missing_total_bedrooms": 60,
    "missing_median_income": 20,
    "missing_ocean_proximity": 30,
    "invalid_token_housing_median_age": 15,
    "out_of_range_housing_median_age": 5,
    "out_of_range_population": 8,
    "out_of_range_latitude": 6,
    "out_of_range_median_house_value": 5,
    "unnormalized_ocean_proximity": 6,
    "invalid_category_ocean_proximity": 4,
    "extreme_total_rooms": 10,
    "full_duplicates": 25,
}


def _base_frame(rng: np.random.Generator, n: int) -> pd.DataFrame:
    households = np.round(rng.lognormal(mean=6.1, sigma=0.5, size=n)).clip(2, None)
    rooms_per_household = rng.normal(5.3, 0.9, n).clip(2.0, 9.0)
    total_rooms = np.round(households * rooms_per_household)
    total_bedrooms = np.round(total_rooms * rng.normal(0.21, 0.03, n).clip(0.1, 0.4))
    population = np.round(households * rng.normal(2.9, 0.6, n).clip(1.2, 6.0))
    income = rng.lognormal(mean=1.28, sigma=0.45, size=n).clip(0.4999, 15.0001).round(4)
    value = (income * 40_000 + rng.normal(25_000, 35_000, n)).clip(14_999, 500_001).round(-2)
    return pd.DataFrame(
        {
            "longitude": rng.uniform(-124.3, -114.4, n).round(2),
            "latitude": rng.uniform(32.6, 41.9, n).round(2),
            "housing_median_age": rng.integers(1, 53, n).astype(float),
            "total_rooms": total_rooms,
            "total_bedrooms": total_bedrooms,
            "population": population,
            "households": households,
            "median_income": income,
            "median_house_value": value,
            "ocean_proximity": rng.choice(OCEAN_CATEGORIES, size=n, p=OCEAN_PROBS),
        }
    )


def _take(order: list[int], count: int) -> list[int]:
    """Pobiera kolejne, rozłączne indeksy — każdy rekord ma co najwyżej jeden problem."""
    taken, order[:] = order[:count], order[count:]
    return taken


def make_sample(seed: int = SEED, rows: int = BASE_ROWS) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Zwraca (DataFrame z problemami, manifest wstrzykniętych problemów)."""
    rng = np.random.default_rng(seed)
    frame = _base_frame(rng, rows)
    frame["housing_median_age"] = frame["housing_median_age"].astype(object)
    order = [int(i) for i in rng.permutation(rows)]
    n = INJECTIONS

    frame.loc[_take(order, n["missing_total_bedrooms"]), "total_bedrooms"] = np.nan
    frame.loc[_take(order, n["missing_median_income"]), "median_income"] = np.nan
    frame.loc[_take(order, n["missing_ocean_proximity"]), "ocean_proximity"] = np.nan
    tokens = _take(order, n["invalid_token_housing_median_age"])
    frame.loc[tokens, "housing_median_age"] = ["?" if i % 2 else "brak" for i in range(len(tokens))]
    frame.loc[_take(order, n["out_of_range_housing_median_age"]), "housing_median_age"] = 999.0
    frame.loc[_take(order, n["out_of_range_population"]), "population"] = -5.0
    frame.loc[_take(order, n["out_of_range_latitude"]), "latitude"] = 0.0
    frame.loc[_take(order, n["out_of_range_median_house_value"]), "median_house_value"] = 9_999_999.0
    frame.loc[_take(order, n["unnormalized_ocean_proximity"]), "ocean_proximity"] = " near bay"
    frame.loc[_take(order, n["invalid_category_ocean_proximity"]), "ocean_proximity"] = "UNKNOWN_ZONE"
    extreme = _take(order, n["extreme_total_rooms"])
    frame.loc[extreme, "total_rooms"] = frame.loc[extreme, "total_rooms"] * 25

    duplicate_sources = _take(order, n["full_duplicates"])  # wyłącznie „czyste” rekordy
    frame = pd.concat([frame, frame.loc[duplicate_sources]], ignore_index=True)
    frame = frame.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    manifest = {
        "seed": seed,
        "base_rows": rows,
        "total_rows": len(frame),
        "injected": dict(n),
        "expected_after_cleaning": {
            "rows": rows - n["out_of_range_median_house_value"],
            "missing_cells": 0,
            "full_duplicates": 0,
            "rule_violations": 0,
        },
    }
    return frame, manifest


def write_sample(directory: str | Path = "data/raw", seed: int = SEED) -> tuple[Path, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frame, manifest = make_sample(seed)
    csv_path = directory / "california_housing_sample.csv"
    manifest_path = directory / "california_housing_sample_manifest.json"
    frame.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return csv_path, manifest_path


if __name__ == "__main__":
    for written in write_sample():
        print(f"Zapisano {written}")
