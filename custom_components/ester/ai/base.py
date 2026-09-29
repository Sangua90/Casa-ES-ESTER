"""Provider-independent AI contract for E.S.T.E.R."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AIResponse:
    """Normalized response returned by any AI provider."""

    text: str
    structured: dict[str, Any] | None = None
    confidence: float | None = None
    provider: str | None = None
    model: str | None = None


class AIProvider(ABC):
    """Abstract AI provider used by E.S.T.E.R."""

    name: str

    @abstractmethod
    async def async_interpret(
        self,
        *,
        message: str,
        context: dict[str, Any],
    ) -> AIResponse:
        """Interpret a user message against E.S.T.E.R. context."""
        raise NotImplementedError

    @abstractmethod
    async def async_explain(
        self,
        *,
        decision: dict[str, Any],
        context: dict[str, Any],
    ) -> AIResponse:
        """Explain a decision in natural language."""
        raise NotImplementedError
