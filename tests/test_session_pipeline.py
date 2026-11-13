"""Sesja, ślad zmian, reset, pipeline na zbiorze z manifestem i powtarzalność wyników."""

from __future__ import annotations

import pandas as pd
import pytest

from studio.cli import main as cli_main
from studio.pipeline import ConfigError, load_config, parse_config, run_pipeline
from studio.profiling import build_profile, invalid_numeric_tokens
from studio.quality import check_rules
from studio.sample_data import make_sample
from studio.session import DataSession

from .conftest import CONFIG_PATH


def test_session_keeps_raw_and_resets(small_frame):
    session = DataSession(small_frame)
    session.drop_duplicates()
    session.fill_missing("price", "median")

    assert len(session.current) == 5
    pd.testing.assert_frame_equal(session.raw, small_frame)  # surowe nietknięte

    session.reset()
    pd.testing.assert_frame_equal(session.current, small_frame)
    assert [r.operation for r in session.audit_log][-1] == "reset do danych surowych"


def test_session_is_isolated_from_external_frame(small_frame):
    session = DataSession(small_frame)
    small_frame.loc[0, "price"] = -1
    assert session.raw.loc[0, "price"] == 100.0


def test_audit_log_records_counts(small_frame):
    session = DataSession(small_frame)
    record = session.drop_duplicates()
    assert (record.rows_before, record.rows_after, record.rows_affected) == (6, 5, 1)
    assert record.unrelated_columns_unchanged
    assert list(session.audit_frame()["operation"]) == ["usunięcie duplikatów"]


def test_empty_frame_is_rejected():
    with pytest.raises(ValueError):
        DataSession(pd.DataFrame({"a": []}))


# ------------------------------------------------- pipeline na zbiorze z manifestem


@pytest.fixture(scope="module")
def sample():
    return make_sample()


@pytest.fixture(scope="module")
def config():
    return load_config(CONFIG_PATH)


def test_profile_detects_all_injected_problems(sample, config, tmp_path):
    frame, manifest = sample
    injected = manifest["injected"]
    path = tmp_path / "sample.csv"
    frame.to_csv(path, index=False)
    raw = DataSession.from_csv(path).raw

    profile = build_profile(raw)
    assert profile.duplicate_rows == injected["full_duplicates"]
    table = profile.column_table
    assert table.loc["total_bedrooms", "missing"] == injected["missing_total_bedrooms"]
    assert table.loc["median_income", "missing"] == injected["missing_median_income"]
    assert table.loc["ocean_proximity", "missing"] == injected["missing_ocean_proximity"]
    tokens = invalid_numeric_tokens(raw)
    assert sum(tokens["housing_median_age"].values()) == injected["invalid_token_housing_median_age"]

    rules = check_rules(raw, config.quality_rules[:9] + config.quality_rules[-1:]).set_index("column")
    assert rules.loc["population", "violations"] == injected["out_of_range_population"]
    assert rules.loc["latitude", "violations"] == injected["out_of_range_latitude"]
    assert rules.loc["housing_median_age", "violations"] == injected["out_of_range_housing_median_age"]
    assert rules.loc["median_house_value", "violations"] == injected["out_of_range_median_house_value"]
    assert rules.loc["ocean_proximity", "violations"] == (
        injected["unnormalized_ocean_proximity"] + injected["invalid_category_ocean_proximity"]
    )


def test_pipeline_meets_expected_result(sample, config):
    frame, manifest = sample
    session = DataSession(frame)
    result = run_pipeline(session, config)
    expected = manifest["expected_after_cleaning"]

    assert len(session.current) == expected["rows"]
    assert int(session.current.isna().sum().sum()) == expected["missing_cells"]
    assert int(session.current.duplicated().sum()) == expected["full_duplicates"]
    assert check_rules(session.current, result.applicable_rules)["violations"].sum() == 0
    assert all(r.unrelated_columns_unchanged for r in result.records)
    pd.testing.assert_frame_equal(session.raw, frame)  # dane surowe nietknięte


def test_extreme_values_are_flagged_not_removed(sample, config):
    frame, manifest = sample
    session = DataSession(frame)
    run_pipeline(session, config)
    assert session.current["total_rooms_outlier_iqr"].sum() >= manifest["injected"]["extreme_total_rooms"]
    assert session.current["total_rooms"].max() == frame["total_rooms"].max()


def test_pipeline_is_reproducible(sample, config):
    frame, _ = sample
    first, second = DataSession(frame), DataSession(frame)
    run_pipeline(first, config)
    run_pipeline(second, config)
    pd.testing.assert_frame_equal(first.current, second.current)


def test_cli_writes_reloadable_outputs(sample, tmp_path):
    frame, _ = sample
    source = tmp_path / "input.csv"
    frame.to_csv(source, index=False)

    hashes = []
    for run in ("a", "b"):
        out = tmp_path / run
        assert cli_main([str(source), "--config", str(CONFIG_PATH), "--out", str(out)]) == 0
        assert (out / "report.md").read_text(encoding="utf-8").startswith("# Raport")
        assert len(pd.read_csv(out / "audit_log.csv")) > 0
        hashes.append((out / "cleaned.csv").read_bytes())

    assert hashes[0] == hashes[1]  # identyczny plik przy każdym uruchomieniu
    reloaded = DataSession.from_csv(tmp_path / "a" / "cleaned.csv").raw
    assert len(reloaded) == len(frame) - 30
    assert reloaded.isna().sum().sum() == 0


def test_cli_reports_bad_file_without_crash(test_data, tmp_path, capsys):
    code = cli_main([str(test_data / "bad_line.csv"), "--config", str(CONFIG_PATH), "--out", str(tmp_path)])
    assert code == 1
    assert "Wadliwy wiersz" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad_config, message",
    [
        ({"range_rules": [{"column": "a", "min": 5, "max": 1}]}, "min"),
        ({"range_rules": [{"column": "a", "min": 0, "action": "explode"}]}, "niepoprawna wartość"),
        ({"missing": {"columns": {"a": {"strategy": "constant"}}}}, "value"),
        ({"outliers": {"factor": -1}}, "dodatnią"),
        ({"missing": {"default_text": "mean"}}, "niepoprawna wartość"),
    ],
)
def test_invalid_config_is_rejected(bad_config, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(bad_config)
