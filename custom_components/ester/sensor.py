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
    coordinator: EsterCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            EsterStatusSensor(coordinator, entry),
            EsterEntityCountSensor(coordinator, entry),
            EsterDecisionCountSensor(coordinator, entry),
            EsterQuestionsSensor(coordinator, entry),
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
            "sw_version": "0.1.0",
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

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "questions")

    @property
    def native_value(self) -> int:
        latest = (self.coordinator.data or {}).get("latest_decisions", [])
        return sum(1 for item in latest if item.get("status") == "needs_input")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = (self.coordinator.data or {}).get("latest_decisions", [])
        return {
            "items": [item for item in latest if item.get("status") == "needs_input"]
        }
