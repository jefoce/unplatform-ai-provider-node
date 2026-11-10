"""API prompt builders shared by the export tests."""

import copy
import json
from pathlib import Path
from typing import Any, cast

FIXTURE_DIR = Path(__file__).resolve().parent / "workflows" / "api"


def workflow_fixture(name: str) -> dict[str, Any]:
    """Load one CPU API prompt fixture."""
    return cast(
        dict[str, Any],
        json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")),
    )


def node(class_type: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": class_type, "inputs": inputs}


def video_prompt() -> dict[str, Any]:
    """One valid video model with two image refs and a required start frame."""
    return {
        "1": node(
            "UPAIModel",
            id="wan",
            name="Wan",
            description="",
            kind="video",
            enabled=True,
            price_per_run_usd=0,
            limits=["2", 0],
        ),
        "2": node(
            "UPAILimits",
            image_max=2,
            image_required=1,
            video_max=0,
            video_required=0,
            audio_max=0,
            audio_required=0,
            start_frame="optional",
            end_frame="off",
            duration_min=2,
            duration_max=4,
            count_max=0,
        ),
        "3": node("UPAIPrompt", text="test", negative="", required=True, max_chars=1000),
        "4": node("UPAIStartFrame", required=True, image="start.png"),
        "5": node("UPAIImageRef", index=1, required=True, image="a.png"),
        "6": node("UPAIImageRef", index=2, required=False, image="b.png"),
        "7": node(
            "UPAISettings",
            resolutions="480p,720p",
            aspect_ratios="16:9,9:16",
            default_resolution="480p",
            default_aspect_ratio="16:9",
            align=16,
            size_overrides="480p 16:9 = 832x480",
            duration_min=1,
            duration_max=8,
            duration_default=5,
            duration_step=1,
            fps=16,
            frame_mod=4,
            frame_add=1,
            count_max=4,
        ),
        "8": node("CLIPTextEncode", text=["3", 0]),
        "9": node("KSampler", positive=["8", 0], image=["5", 0], mask=["6", 0], latent=["4", 0]),
        "10": node("CreateVideo", images=["9", 0]),
        "11": node(
            "UPAIOutput",
            model=["1", 0],
            images=["10", 0],
            fps=["7", 3],
            format="mp4",
            crf=19,
            preview=False,
            upai_job="",
        ),
    }


def image_prompt() -> dict[str, Any]:
    """One valid image model with one optional image reference."""
    return {
        "1": node(
            "UPAIModel",
            id="sdxl",
            name="SDXL",
            description="local",
            kind="image",
            enabled=True,
            price_per_run_usd=0,
        ),
        "2": node("UPAIPrompt", text="test", negative="", required=False, max_chars=200),
        "3": node(
            "UPAISettings",
            resolutions="1K",
            aspect_ratios="1:1",
            default_resolution="1K",
            default_aspect_ratio="1:1",
            align=16,
            size_overrides="",
            count_max=4,
        ),
        "4": node("UPAIImageRef", index=1, required=False, image="a.png"),
        "5": node("VAEDecode", text=["2", 0], image=["4", 0], latent=["3", 0]),
        "6": node(
            "UPAIOutput",
            model=["1", 0],
            images=["5", 0],
            format="png",
            crf=0,
            preview=False,
            upai_job="",
        ),
    }


def two_model_prompt() -> dict[str, Any]:
    """Two outputs sharing one prompt and settings node."""
    prompt = video_prompt()
    prompt["12"] = node(
        "UPAIModel",
        id="wan-t2v",
        name="Wan T2V",
        description="",
        kind="video",
        enabled=True,
        price_per_run_usd=0,
    )
    prompt["13"] = node("KSampler", positive=["8", 0], latent=["7", 2])
    prompt["14"] = node("CreateVideo", images=["13", 0])
    prompt["15"] = node(
        "UPAIOutput",
        model=["12", 0],
        images=["14", 0],
        format="mp4",
        crf=19,
        preview=False,
        upai_job="",
    )
    return prompt


def copy_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(prompt)
