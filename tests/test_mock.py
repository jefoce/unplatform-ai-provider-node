"""Mock catalog caching."""

from conftest import load_fixture

import upai_provider.mock as mock


def test_catalog_tuples_and_size_table_are_cached() -> None:
    assert mock.video_models() is mock.video_models()
    assert mock.image_models() is mock.image_models()

    sizes = mock.image_models()[0].capabilities.sizes
    assert sizes is mock._IMAGE_SIZES
    assert sizes["1K"]["1:1"] == "1024x1024"


def test_video_prompt_reference_label_matches_fixture() -> None:
    fixtures = {model["id"]: model for model in load_fixture("models-video.json")["data"]}

    for model in mock.video_models():
        expected = fixtures[model.id]["capabilities"]["prompt"].get("reference_label")
        assert model.capabilities.prompt.reference_label == expected

    assert mock.video_models()[0].capabilities.prompt.reference_label == "<{kind}_{n}>"


def test_video_prompt_reference_labels_match_fixture() -> None:
    fixtures = {model["id"]: model for model in load_fixture("models-video.json")["data"]}

    for model in mock.video_models():
        expected = fixtures[model.id]["capabilities"]["prompt"].get("reference_labels")
        assert model.capabilities.prompt.reference_labels == expected

    assert mock.video_models()[0].capabilities.prompt.reference_labels == {
        "image": "<Picture {n}>",
        "video": "<Video {n}>",
        "audio": "<Audio {n}>",
    }
