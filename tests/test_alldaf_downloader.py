"""Tests for the pure helper functions in alldaf_downloader.py.
No network, no window, and no changes to the app's behavior."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alldaf_downloader import (  # noqa: E402
    count_downloaded,
    fast_name,
    fmt_eta,
    gematria,
    is_yerushalmi,
    parse_daf_range,
    recommend_workers,
    safe_name,
    snap_speed,
    speed_text,
    title_with_speed,
    WORKERS,
)


# ---------- Hebrew daf numbers ----------

@pytest.mark.parametrize("number, letters", [
    (121, "קכא"), (2, "ב"), (15, "טו"), (16, "טז"), (51, "נא"), (116, "קטז"),
])
def test_gematria_matches_daf_letters(number, letters):
    assert gematria(number) == letters


# ---------- titles and file names ----------

def test_title_puts_speed_after_english_and_before_hebrew():
    assert title_with_speed("Pesachim 121", "1.50x") == "Pesachim 121 (1.50x) פסחים דף קכא"


def test_title_handles_special_daf_numbers():
    assert title_with_speed("Pesachim 15", "1.50x") == "Pesachim 15 (1.50x) פסחים דף טו"


def test_title_keeps_yerushalmi_suffix_at_the_end():
    assert title_with_speed("Pesachim 7 (Yerushalmi)", "1.50x") == "Pesachim 7 (1.50x) פסחים דף ז (Yerushalmi)"


def test_title_falls_back_when_mesechta_is_unknown():
    assert title_with_speed("Unknown 5", "1.50x") == "Unknown 5 (1.50x)"


def test_fast_name_adds_speed_before_extension():
    assert fast_name(Path("Pesachim 7.mp3"), "1.50x") == "Pesachim 7 (1.50x).mp3"


def test_safe_name_removes_characters_windows_forbids():
    assert safe_name('a:b*c?"d"') == "a_b_c__d_"


def test_safe_name_prefixes_reserved_names():
    assert safe_name("CON") == "_CON"
    assert safe_name("nul.txt") == "_nul.txt"


def test_safe_name_leaves_normal_names_alone():
    assert safe_name("Pesachim 7") == "Pesachim 7"


# ---------- speed slider ----------

def test_snap_speed_rounds_to_nearest_step():
    assert snap_speed(1.2999999) == 1.3


def test_snap_speed_clamps_to_slider_range():
    assert snap_speed(3) == 2.5
    assert snap_speed(0.2) == 1.0


def test_speed_text_shows_normal_or_multiplier():
    assert speed_text(1.0) == "Normal"
    assert speed_text(1.5) == "1.50x"


# ---------- speed recommendation ----------

def test_recommend_prefers_lowest_fast_setting_without_retries():
    results = [
        {"w": 1, "secs": 90, "retries": 0, "failed": 0},
        {"w": 3, "secs": 40, "retries": 0, "failed": 0},
        {"w": 5, "secs": 38, "retries": 0, "failed": 0},
    ]
    assert recommend_workers(results) == 3


def test_recommend_ignores_fast_runs_that_needed_retries():
    results = [
        {"w": 1, "secs": 90, "retries": 0, "failed": 0},
        {"w": 3, "secs": 40, "retries": 0, "failed": 0},
        {"w": 5, "secs": 30, "retries": 4, "failed": 0},
    ]
    assert recommend_workers(results) == 3


def test_recommend_picks_one_when_all_speeds_are_equal():
    results = [
        {"w": 1, "secs": 40, "retries": 0, "failed": 0},
        {"w": 3, "secs": 40, "retries": 0, "failed": 0},
        {"w": 5, "secs": 41, "retries": 0, "failed": 0},
    ]
    assert recommend_workers(results) == 1


def test_recommend_falls_back_to_default_when_every_run_failed():
    results = [{"w": 1, "secs": 40, "retries": 0, "failed": 2}]
    assert recommend_workers(results) == WORKERS


# ---------- shiur records ----------

def test_is_yerushalmi_from_series_name():
    assert is_yerushalmi({"series": {"name": "The Quick Yerushalmi"}, "title": "Pesachim 7"}) is True


def test_is_yerushalmi_from_title():
    assert is_yerushalmi({"title": "Yerushalmi Pesachim 3"}) is True


def test_is_yerushalmi_false_for_bavli():
    assert is_yerushalmi({"series": {"name": "The Quick Daf"}, "title": "Pesachim 7"}) is False


# ---------- time remaining ----------

@pytest.mark.parametrize("seconds, text", [
    (0, "0s"), (59, "59s"), (61, "1m 01s"), (3600, "1h 00m"), (3725, "1h 02m"),
])
def test_fmt_eta_formats_time_left(seconds, text):
    assert fmt_eta(seconds) == text


# ---------- already downloaded ----------

def test_count_downloaded_ignores_fast_copies(tmp_path):
    mesechta = tmp_path / "Rabbi Test" / "Pesachim"
    (mesechta / "Fast 1.50x").mkdir(parents=True)
    (mesechta / "Pesachim 1.mp3").write_bytes(b"x")
    (mesechta / "Pesachim 2.mp3").write_bytes(b"x")
    (mesechta / "Fast 1.50x" / "Pesachim 1 (1.50x).mp3").write_bytes(b"x")
    assert count_downloaded(tmp_path, "Rabbi Test", "Pesachim") == 2


def test_count_downloaded_is_zero_when_folder_missing(tmp_path):
    assert count_downloaded(tmp_path, "Nobody", "Berachos") == 0


# ---------- daf range input ----------

def test_daf_range_blank_means_all():
    assert parse_daf_range("", "") == (None, None)


def test_daf_range_valid():
    assert parse_daf_range("20", "40") == (20, 40)


def test_daf_range_backwards_raises():
    with pytest.raises(ValueError):
        parse_daf_range("40", "20")


def test_daf_range_non_number_raises():
    with pytest.raises(ValueError):
        parse_daf_range("x", "")
