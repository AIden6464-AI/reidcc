"""The Firing System 4-Stage Dynamical Engine (`INJECT -> FIRE -> ADMIT -> COMPOSE`)."""

from .embedding_provider import (
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    SemanticProjectionEmbeddingProvider,
)
from .firing_engine import FiringEngine

__all__ = [
    "EmbeddingProvider",
    "FiringEngine",
    "OpenAICompatibleEmbeddingProvider",
    "SemanticProjectionEmbeddingProvider",
]
