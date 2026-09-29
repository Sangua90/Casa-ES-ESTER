"""Persistent storage for E.S.T.E.R."""

from __future__ import annotations

from typing import Any
from asyncio import Lock
from copy import deepcopy

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import MAX_DECISIONS, STORAGE_KEY, STORAGE_VERSION


class EsterStorage:
    """Small persistent store for learned context and shadow decisions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.lock = Lock()
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {
            "decisions": [],
            "feedback": [],
            "context_events": [],
            "preferences": {},
            "classifications": {},
            "learning": {},
            "usage_profiles": [],
        }

    async def async_load(self) -> None:
        saved = await self._store.async_load()
        if saved:
            self.data.update(saved)

    async def async_save(self) -> None:
        await self._store.async_save(deepcopy(self.data))

    async def add_decision(self, decision: dict[str, Any]) -> None:
        decisions = self.data.setdefault("decisions", [])
        decisions.append(decision)
        if len(decisions) > MAX_DECISIONS:
            del decisions[:-MAX_DECISIONS]
        await self.async_save()

    async def add_feedback(self, feedback: dict[str, Any]) -> None:
        self.data.setdefault("feedback", []).append(feedback)
        del self.data["feedback"][:-500]
        await self.async_save()

    async def add_context_event(self, event: dict[str, Any]) -> None:
        self.data.setdefault("context_events", []).append(event)
        del self.data["context_events"][:-100]
        await self.async_save()

    async def set_preference(self, key: str, value: Any) -> None:
        self.data.setdefault("preferences", {})[key] = value
        await self.async_save()
