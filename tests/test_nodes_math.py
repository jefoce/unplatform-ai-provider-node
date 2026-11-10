"""Unit tests for UPAI Settings math."""

import pytest

from upai_provider.nodes.settings_math import clamp, clamp_count, round_frames
from upai_provider.sizing import (
    parse_ratio,
    parse_size_overrides,
    resolve_size,
    round_to_align,
)


def test_round_to_align_uses_nearest_multiple() -> None:
    assert round_to_align(480, 16) == 480
    assert round_to_align(853.3, 16) == 848
    assert round_to_align(0, 16) == 16


def test_parse_ratio() -> None:
    assert parse_ratio("16:9") == pytest.approx(16 / 9)
    assert parse_ratio("9:19.5") == pytest.approx(9 / 19.5)

    with pytest.raises(ValueError):
        parse_ratio("16")
    with pytest.raises(ValueError):
        parse_ratio("0:9")


def test_parse_size_overrides_reads_valid_lines_only() -> None:
    text = "480p 16:9 = 832x480\nbad line\n720p 9:16 = 480x832\nx y = 0x5"

    assert parse_size_overrides(text) == {
        ("480p", "16:9"): (832, 480),
        ("720p", "9:16"): (480, 832),
    }


def test_resolve_size_uses_short_side_and_ratio() -> None:
    assert resolve_size("1K", "1:1", align=16, overrides={}) == (1024, 1024)
    assert resolve_size("1K", "16:9", align=16, overrides={}) == (1824, 1024)
    assert resolve_size("1K", "9:16", align=16, overrides={}) == (1024, 1824)


def test_resolve_size_video_labels() -> None:
    assert resolve_size("480p", "16:9", align=16, overrides={}) == (848, 480)
    assert resolve_size("720p", "16:9", align=16, overrides={}) == (1280, 720)
    assert resolve_size("768p", "1:1", align=16, overrides={}) == (768, 768)
    assert resolve_size("1080p", "9:16", align=16, overrides={}) == (1088, 1920)


def test_resolve_size_override_wins() -> None:
    overrides = parse_size_overrides("1K 16:9 = 832x480")

    assert resolve_size("1K", "16:9", align=16, overrides=overrides) == (832, 480)


def test_round_frames_snaps_to_the_rule() -> None:
    assert round_frames(5.0, fps=16.0, mod=4, add=1) == 81
    assert round_frames(0.0, fps=16.0, mod=4, add=1) == 1
    assert round_frames(1.0, fps=1.0, mod=1, add=0) == 1


def test_clamp_and_count() -> None:
    assert clamp(5.0, 1.0, 10.0) == 5.0
    assert clamp(0.0, 1.0, 10.0) == 1.0
    assert clamp(20.0, 1.0, 10.0) == 10.0
    assert clamp(5.0, 10.0, 1.0) == 10.0
    assert clamp_count(0, 4) == 1
    assert clamp_count(9, 4) == 4
