"""Sensors exposed by E.S.T.E.R."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EsterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up E.S.T.E.R. sensors."""
    coordinator: EsterCoordinator = entry.runtime_data
    async_add_entities(
        [
            EsterStatusSensor(coordinator, entry),
            EsterEntityCountSensor(coordinator, entry),
            EsterDecisionCountSensor(coordinator, entry),
            EsterQuestionsSensor(coordinator, entry),
            EsterSummarySensor(coordinator, entry),
            EsterDataSuggestionsSensor(coordinator, entry),
        ]
    )


class EsterBaseSensor(CoordinatorEntity[EsterCoordinator], SensorEntity):
    """Base E.S.T.E.R. sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EsterCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "E.S.T.E.R.",
            "manufacturer": "Casa ES",
            "model": "Intelligent Home Manager",
            "sw_version": "1.2.0",
        }


class EsterStatusSensor(EsterBaseSensor):
    """Current operating mode."""

    _attr_name = "Status"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "status")

    @property
    def native_value(self) -> str:
        return "shadow"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        inventory = (self.coordinator.data or {}).get("inventory", {})
        return {
            "tagline": "Everything Seems Totally Easy, Right?",
            "real_actuation_enabled": False,
            "entities_observed": inventory.get("entities", 0),
            "roles": inventory.get("roles", {}),
        }


class EsterEntityCountSensor(EsterBaseSensor):
    """Observed HA entity count."""

    _attr_name = "Observed entities"
    _attr_icon = "mdi:home-search"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "entities")

    @property
    def native_value(self) -> int:
        return (self.coordinator.data or {}).get("inventory", {}).get("entities", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        inventory = (self.coordinator.data or {}).get("inventory", {})
        return {
            "controllable": inventory.get("controllable", 0),
            "sensitive": inventory.get("sensitive", 0),
            "unassigned": inventory.get("unassigned_entities", 0),
            "domains": inventory.get("domains", {}),
        }


class EsterDecisionCountSensor(EsterBaseSensor):
    """Persistent shadow decision count."""

    _attr_name = "Shadow decisions"
    _attr_icon = "mdi:thought-bubble"
    _unrecorded_attributes = frozenset({"latest"})

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "decisions")

    @property
    def native_value(self) -> int:
        return (self.coordinator.data or {}).get("decision_count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "latest": (self.coordinator.data or {}).get("latest_decisions", [])[-5:]
        }


class EsterQuestionsSensor(EsterBaseSensor):
    """Number of current shadow decisions requiring user input."""

    _attr_name = "Questions"
    _attr_icon = "mdi:comment-question"
    _unrecorded_attributes = frozenset({"items"})

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "questions")

    @property
    def native_value(self) -> int:
        return len((self.coordinator.data or {}).get("questions", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        questions = (self.coordinator.data or {}).get("questions", [])
        return {"items": questions[:20]}

class EsterSummarySensor(EsterBaseSensor):
    """Compact UI summary, with full details available through get_summary."""
    _attr_name = "Summary"
    _attr_icon = "mdi:home-analytics"
    _unrecorded_attributes = frozenset({"rooms", "contexts", "history", "usage"})

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "summary")

    @property
    def native_value(self):
        return len((self.coordinator.data or {}).get("rooms", {}))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {"rooms": {key: {"name": r["name"], "entities": len(r["entities"])} for key, r in data.get("rooms", {}).items()},
                "contexts": [{k: c.get(k) for k in ("event_id", "label", "mode", "ends_at")} for c in data.get("contexts", [])],
                "history": data.get("history", {}), "usage": data.get("usage", {}), "evaluated_at": data.get("evaluated_at"),
                "learning_entities": data.get("learning_entities", 0),
                "open_questions": len(data.get("questions", [])),
                "usage_profiles": len(data.get("usage_profiles", []))}

class EsterDataSuggestionsSensor(EsterBaseSensor):
    """Missing data and useful sensor types, without product endorsements."""
    _attr_name = "Data suggestions"
    _attr_icon = "mdi:lightbulb-on-outline"
    _unrecorded_attributes = frozenset({"items"})

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "data_suggestions")

    @property
    def native_value(self):
        return len((self.coordinator.data or {}).get("data_suggestions", []))

    @property
    def extra_state_attributes(self):
        return {"items": (self.coordinator.data or {}).get("data_suggestions", []),
                "source": "local_data_audit", "ai_explanation": "ester.explain_decision"}
