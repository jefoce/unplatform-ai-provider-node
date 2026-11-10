"""Reference label validator tests."""

import pytest

from upai_provider.protocol import (
    REFERENCE_LABEL_MAX_CHARS,
    split_reference_labels,
    validate_reference_label,
)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_is_valid(value: str | None) -> None:
    assert validate_reference_label(value) is None


@pytest.mark.parametrize(
    "value",
    ["{n}", "{i}", "{kind} {n}", "{Kind}_{n}", "frame {kind} slot {i}", "<{kind}_{n}>"],
)
def test_valid_templates(value: str) -> None:
    assert validate_reference_label(value) is None


def test_exactly_max_chars_is_valid() -> None:
    value = "{n}" + "x" * (REFERENCE_LABEL_MAX_CHARS - 3)
    assert len(value) == REFERENCE_LABEL_MAX_CHARS
    assert validate_reference_label(value) is None


def test_over_max_chars_is_rejected() -> None:
    value = "{n}" + "x" * (REFERENCE_LABEL_MAX_CHARS - 2)
    assert validate_reference_label(value) == (
        f"reference_label must be at most {REFERENCE_LABEL_MAX_CHARS} characters"
    )


def test_unknown_placeholder_is_rejected() -> None:
    assert validate_reference_label("{foo}_{n}") == (
        "reference_label has an unknown placeholder {foo}"
    )


@pytest.mark.parametrize("value", ["{n", "n}", "{n}}", "{{n}}"])
def test_stray_brace_is_rejected(value: str) -> None:
    assert validate_reference_label(value) == "reference_label has a stray brace"


def test_missing_slot_placeholder_is_rejected() -> None:
    assert validate_reference_label("{kind}") == "reference_label must contain {n} or {i}"


def test_empty_placeholder_is_unknown() -> None:
    assert validate_reference_label("{}") == "reference_label has an unknown placeholder {}"


def test_split_valid_map() -> None:
    labels, warnings, errors = split_reference_labels(
        {"image": " <Picture {n}> ", "video": "<Video {i}>"}
    )
    assert labels == {"image": "<Picture {n}>", "video": "<Video {i}>"}
    assert warnings == ()
    assert errors == ()


def test_split_none_is_empty() -> None:
    assert split_reference_labels(None) == ({}, (), ())


def test_split_non_mapping_is_error() -> None:
    assert split_reference_labels(["x"]) == (
        {},
        (),
        ("reference_labels must be an object",),
    )


def test_split_unknown_kind_warns() -> None:
    labels, warnings, errors = split_reference_labels({"image": "<{n}>", "sound": "<{n}>"})
    assert labels == {"image": "<{n}>"}
    assert warnings == ("reference_labels has unknown kind 'sound', dropped",)
    assert errors == ()


def test_split_skips_none_and_empty() -> None:
    labels, warnings, errors = split_reference_labels({"image": None, "video": "", "audio": "  "})
    assert labels == {}
    assert warnings == ()
    assert errors == ()


def test_split_non_string_is_error() -> None:
    labels, warnings, errors = split_reference_labels({"image": 3})
    assert labels == {}
    assert warnings == ()
    assert errors == ("reference_labels.image must be a string",)


def test_split_invalid_image_names_kind() -> None:
    labels, warnings, errors = split_reference_labels({"image": "{foo}_{n}"})
    assert labels == {}
    assert warnings == ()
    assert errors == ("reference_labels.image: reference_label has an unknown placeholder {foo}",)
