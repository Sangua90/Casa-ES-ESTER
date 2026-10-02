"""Persistent storage for E.S.T.E.R."""

from __future__ import annotations

from typing import Any
from asyncio import Lock
from copy import deepcopy
from datetime import datetime, UTC
import hashlib
import json
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant, CoreState
from homeassistant.helpers.storage import Store

from .const import MAX_DECISIONS, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)
MEMORY_KEYS = ("knowledge", "knowledge_documents", "pending_teachings", "preferences", "classifications",
               "questions", "usage_profiles", "context_events", "flexible_loads", "safety_policies", "fallback_policies")


def memory_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def verify_saved(path, expected):
    """Read the actual disk file, not HA's in-memory pending-write cache."""
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if memory_digest(envelope.get("data")) != memory_digest(expected):
        raise OSError("Il contenuto riletto dal disco non corrisponde al salvataggio.")


def memory_files_exist(paths):
    return any(Path(path).exists() or any(Path(path).parent.glob(Path(path).name + ".corrupt.*")) for path in paths)


class EsterStorage:
    """Small persistent store for learned context and shadow decisions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.lock = Lock()
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY, atomic_writes=True, serialize_in_event_loop=False)
        self._backup_store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, "ester.memory_backup", atomic_writes=True, serialize_in_event_loop=False)
        self._backup: dict = {}
        self.backup_status: dict = {"status": "not_created", "home_assistant_backup_includes_memory": True}
        self.data: dict[str, Any] = {
            "decisions": [],
            "feedback": [],
            "context_events": [],
            "preferences": {},
            "classifications": {},
            "learning": {},
            "usage_profiles": [],
            "questions": [],
            "knowledge": [],
            "knowledge_documents": [],
            "pending_teachings": [],
            "safety_policies": {},
            "fallback_policies": {},
            "room_thermal_samples": {},
            "thermal_models": {},
            "calibration": {},
            "flexible_loads": [],
            "ventilation_samples": {},
            "ventilation_models": {},
            "hot_water_samples": {},
            "hot_water_models": {},
            "occupancy_samples": {},
            "occupancy_models": {},
            "energy_runtime": {},
            "memory_versions": [],
            "last_replay": {},
            "last_scenario": {},
            "voice_question_id": None,
        }

    async def async_load(self) -> None:
        had_files = await self._hass.async_add_executor_job(memory_files_exist, [self._store.path, self._backup_store.path])
        error = None
        try:
            saved = await self._store.async_load()
        except (ValueError, OSError) as err:
            saved, error = None, err
        try:
            self._backup = await self._backup_store.async_load() or {}
        except (ValueError, OSError):
            self._backup = {}
        if not saved:
            for copy in self._backup.get("copies", []):
                try:
                    valid = isinstance(copy.get("memory"), dict) and memory_digest(copy["memory"]) == copy.get("sha256")
                except (TypeError, ValueError):
                    valid = False
                if valid:
                    saved = deepcopy(copy["memory"])
                    self.backup_status.update(status="recovered", recovered_at=datetime.now(UTC).isoformat())
                    _LOGGER.warning("Memoria E.S.T.E.R. recuperata dalla copia locale verificata del %s", copy.get("created_at"))
                    break
            if error and not saved:
                raise error
            if self._backup.get("copies") and not saved:
                raise ValueError("Memoria principale assente e copie non verificabili: ripristina un backup Home Assistant. Nessuna memoria vuota verrà salvata.")
            if had_files and not saved:
                raise ValueError("File della memoria presenti ma illeggibili: ripristina un backup senza inizializzare una memoria vuota.")
        if saved:
            self.data.update(saved)
        if self._backup.get("copies"):
            self.backup_status["last_copy_at"] = self._backup["copies"][0].get("created_at")
            if self.backup_status["status"] != "recovered":
                self.backup_status["status"] = "available"

    async def async_create_backup(self) -> None:
        """Keep two complete, independently checksummed generations in /config/.storage."""
        memory = deepcopy(self.data)
        record = {"created_at": datetime.now(UTC).isoformat(), "sha256": memory_digest(memory), "memory": memory}
        copies = [record, *self._backup.get("copies", [])[:1]]
        await self._backup_store.async_save({"copies": copies})
        if self._hass.state is not CoreState.stopping:
            await self._hass.async_add_executor_job(verify_saved, self._backup_store.path, {"copies": copies})
        self._backup = {"copies": copies}
        self.backup_status.update(status="available", last_copy_at=record["created_at"])

    async def async_save(self) -> None:
        await self._store.async_save(deepcopy(self.data))
        if self._hass.state is not CoreState.stopping:
            await self._hass.async_add_executor_job(verify_saved, self._store.path, self.data)
        latest = (self._backup.get("copies") or [{}])[0]
        before = latest.get("memory", {})
        changed = any(self.data.get(key) != before.get(key) for key in MEMORY_KEYS)
        last = latest.get("created_at")
        try:
            due = not last or (datetime.now(UTC) - datetime.fromisoformat(last)).total_seconds() >= 86400
        except (TypeError, ValueError):
            due = True
        if changed or due:
            try:
                await self.async_create_backup()
            except (OSError, ValueError) as err:
                self.backup_status.update(status="copy_failed", error=str(err))
                _LOGGER.error("Memoria principale salvata, ma copia di sicurezza non riuscita: %s", err)

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
