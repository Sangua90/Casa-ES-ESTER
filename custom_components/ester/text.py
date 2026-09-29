"""Writable internal text entity for answering the oldest open E.S.T.E.R. question."""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .questions import apply_answer
from .language_pipeline import interpret_and_store


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([EsterAnswerText(entry.runtime_data, entry), EsterTeachText(entry.runtime_data, entry)])


class EsterAnswerText(CoordinatorEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Answer current question"
    _attr_icon = "mdi:message-reply-text"
    _attr_native_min = 1
    _attr_native_max = 2000
    _attr_mode = TextMode.TEXT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_answer_current_question"
        self._value = ""
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "E.S.T.E.R.",
            "manufacturer": "Casa ES",
            "model": "Intelligent Home Manager",
            "sw_version": "1.3.0",
        }

    def _question(self):
        questions = (self.coordinator.data or {}).get("questions", [])
        return next((q for q in questions if q.get("status") == "open"), None)

    @property
    def native_value(self):
        return self._value

    @property
    def extra_state_attributes(self):
        question = self._question()
        if not question:
            return {"question_id": None, "prompt": None, "status": "idle"}
        return {
            "question_id": question.get("question_id"),
            "title": question.get("title"),
            "prompt": question.get("prompt"),
            "category": question.get("category"),
            "area_id": question.get("area_id"),
            "confidence": question.get("confidence"),
            "risk": question.get("risk"),
            "status": "waiting_answer",
        }

    async def async_set_value(self, value: str) -> None:
        question = self._question()
        if question is None:
            self._value = ""
            self.async_write_ha_state()
            return
        async with self.coordinator.storage.lock:
            apply_answer(
                self.coordinator.storage.data,
                question["question_id"],
                value,
                dt_util.utcnow(),
            )
            await self.coordinator.storage.async_save()
        self._value = ""
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class EsterTeachText(CoordinatorEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Teach E.S.T.E.R."
    _attr_icon = "mdi:head-cog-outline"
    _attr_native_min = 1
    _attr_native_max = 2000
    _attr_mode = TextMode.TEXT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_teach_ester"
        self._value = ""
        self._last_result = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "E.S.T.E.R.",
            "manufacturer": "Casa ES",
            "model": "Intelligent Home Manager",
            "sw_version": "1.3.0",
        }

    @property
    def native_value(self):
        return self._value

    @property
    def extra_state_attributes(self):
        return {"last_result": self._last_result, "shadow_mode": True, "device_action": False}

    async def async_set_value(self, value: str) -> None:
        self._last_result = await interpret_and_store(self.hass, self.coordinator, value)
        self._value = ""
        self.async_write_ha_state()
