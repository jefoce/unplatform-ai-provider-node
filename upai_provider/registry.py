"""Model catalog helpers."""

from .protocol import Model
from .protocol.shapes import ModelKind


def find_model(catalog: tuple[Model, ...], model_id: str, kind: ModelKind) -> Model | None:
    """Find one model by id within a kind."""
    return next(
        (model for model in catalog if model.kind == kind and model.id == model_id),
        None,
    )
