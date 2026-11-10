"""Tests for the UPAI V3 extension."""

import test_nodes_support as support

from upai_provider.constants import (
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_LIMITS,
    NODE_UPAI_MODEL,
    NODE_UPAI_OUTPUT,
    NODE_UPAI_PROMPT,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_VIDEO_REF,
)
from upai_provider.nodes.extension import NODE_CLASSES, UPaiExtension
from upai_provider.nodes.io_types import CATEGORY

support.install()


async def test_extension_lists_every_node_once() -> None:
    nodes = await UPaiExtension().get_node_list()

    assert nodes == list(NODE_CLASSES)
    assert len(nodes) == len(set(nodes)) == 10


def test_node_ids_and_category_match_the_contract() -> None:
    ids = [node.define_schema().node_id for node in NODE_CLASSES]

    assert ids == [
        NODE_UPAI_MODEL,
        NODE_UPAI_LIMITS,
        NODE_UPAI_PROMPT,
        NODE_UPAI_IMAGE_REF,
        NODE_UPAI_VIDEO_REF,
        NODE_UPAI_AUDIO_REF,
        NODE_UPAI_START_FRAME,
        NODE_UPAI_END_FRAME,
        NODE_UPAI_SETTINGS,
        NODE_UPAI_OUTPUT,
    ]
    assert {node.define_schema().category for node in NODE_CLASSES} == {CATEGORY}
