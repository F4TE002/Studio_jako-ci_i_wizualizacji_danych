"""Macierz testów: CSV z przecinkiem i średnikiem, błędne pliki, kodowanie."""

from __future__ import annotations

import pandas as pd
import pytest

from studio.loading import CsvLoadError, detect_separator, load_csv


def test_comma_and_semicolon_give_same_frame(test_data):
    comma, comma_info = load_csv(test_data / "comma.csv")
    semicolon, semi_info = load_csv(test_data / "semicolon_decimal_comma.csv")

    assert comma_info.separator == ","
    assert semi_info.separator == ";"
    assert semi_info.decimal == ","
    assert comma.shape == semicolon.shape == (4, 5)
    pd.testing.assert_frame_equal(comma, semicolon)
    assert semicolon["price"].iloc[0] == pytest.approx(450000.5)


def test_semicolon_with_decimal_comma_is_not_detected_as_comma():
    sample = "a;b;c\n1,5;2,5;3,5\n4,5;5,5;6,5\n"
    assert detect_separator(sample) == ";"


def test_bad_line_raises_controlled_error(test_data):
    with pytest.raises(CsvLoadError, match="Wadliwy wiersz"):
        load_csv(test_data / "bad_line.csv")


def test_bad_line_can_be_skipped_and_counted(test_data):
    frame, info = load_csv(test_data / "bad_line.csv", on_bad_lines="skip")
    assert len(frame) == 2
    assert info.skipped_bad_lines == 1


def test_cp1250_fallback_keeps_polish_characters(test_data):
    frame, info = load_csv(test_data / "cp1250.csv")
    assert info.encoding == "cp1250"
    assert frame["miasto"].tolist() == ["Kraków", "Łódź", "Gdańsk"]


def test_undecodable_file_gives_hint(test_data):
    with pytest.raises(CsvLoadError, match="UTF-8"):
        load_csv(test_data / "broken_encoding.csv")


@pytest.mark.parametrize("name", ["empty.csv", "header_only.csv", "does_not_exist.csv"])
def test_unusable_files_raise_controlled_error(test_data, name):
    with pytest.raises(CsvLoadError):
        load_csv(test_data / name)
