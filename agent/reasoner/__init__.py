"""Reasoner selection.

The factory always succeeds: if the configured LLM cannot be constructed
(no key, no endpoint, unknown provider) the gate falls back to the free
offline reasoner rather than failing the pipeline. A gate that breaks when
a model is unreachable would be worse than no gate at all.
"""
from __future__ import annotations

from typing import Tuple

from ..config import ReasonerConfig
from .base import Reasoner
from .offline import OfflineReasoner

__all__ = ["Reasoner", "OfflineReasoner", "build_reasoner"]


class NullReasoner(Reasoner):
    """Layer 2 switched off entirely -- deterministic rules only."""

    name = "disabled"

    def analyse(self, resources, already_found):
        return []


def build_reasoner(config: ReasonerConfig) -> Tuple[Reasoner, str]:
    """Return (reasoner, note). `note` explains any fallback that happened."""
    if not config.enabled or config.provider in ("none", "disabled"):
        return NullReasoner(), "reasoning layer disabled by policy"

    if config.provider == "offline":
        return OfflineReasoner(min_confidence=config.min_confidence), ""

    try:
        from .llm import LLMReasoner, LLMUnavailable
    except ImportError as exc:  # pragma: no cover - defensive
        return (
            OfflineReasoner(min_confidence=config.min_confidence),
            "LLM reasoner import failed ({}); using offline reasoner".format(exc),
        )

    try:
        reasoner = LLMReasoner(
            provider=config.provider,
            model=config.model,
            max_resources=config.max_resources,
            max_output_tokens=config.max_output_tokens,
            temperature=config.temperature,
            min_confidence=config.min_confidence,
            cache_dir=config.cache_dir,
        )
        return reasoner, ""
    except LLMUnavailable as exc:
        return (
            OfflineReasoner(min_confidence=config.min_confidence),
            "{} Falling back to the free offline reasoner.".format(exc),
        )
