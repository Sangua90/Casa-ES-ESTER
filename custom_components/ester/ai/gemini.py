"""Gemini provider adapter for E.S.T.E.R.

The adapter is intentionally not activated by v0.1. It defines the boundary
between E.S.T.E.R. and Gemini so a provider can be replaced without touching
the home-management engine.
"""

from __future__ import annotations

from typing import Any

from .base import AIProvider, AIResponse


class GeminiProvider(AIProvider):
    """Gemini provider placeholder."""

    name = "gemini"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model

    async def async_interpret(
        self,
        *,
        message: str,
        context: dict[str, Any],
    ) -> AIResponse:
        raise RuntimeError(
            "Gemini is not enabled in E.S.T.E.R. v0.1 Shadow Mode yet."
        )

    async def async_explain(
        self,
        *,
        decision: dict[str, Any],
        context: dict[str, Any],
    ) -> AIResponse:
        raise RuntimeError(
            "Gemini is not enabled in E.S.T.E.R. v0.1 Shadow Mode yet."
        )
