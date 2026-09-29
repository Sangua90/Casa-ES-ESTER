"""E.S.T.E.R. - Everything Seems Totally Easy, Right?"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, EVENT_FEEDBACK, PLATFORMS
from .coordinator import EsterCoordinator
from .storage import EsterStorage

SERVICE_ADD_CONTEXT = "add_context"
SERVICE_ADD_FEEDBACK = "add_feedback"

_CONTEXT_SCHEMA = vol.Schema(
    {
        vol.Required("label"): cv.string,
        vol.Optional("starts_at"): cv.string,
        vol.Optional("ends_at"): cv.string,
        vol.Optional("notes"): cv.string,
    }
)

_FEEDBACK_SCHEMA = vol.Schema(
    {
        vol.Required("decision_id"): cv.string,
        vol.Required("rating"): vol.In(["correct", "wrong", "partial"]),
        vol.Optional("comment"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register E.S.T.E.R. internal actions.

    These actions only write E.S.T.E.R. context/feedback data. They never
    control Home Assistant devices.
    """

    def _runtime():
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            return None
        return next(iter(entries.values()))

    async def handle_add_context(call: ServiceCall) -> None:
        runtime = _runtime()
        if runtime is None:
            return
        storage: EsterStorage = runtime["storage"]
        coordinator: EsterCoordinator = runtime["coordinator"]
        now = datetime.now().astimezone()
        payload = {
            "event_id": str(uuid4()),
            "label": call.data["label"],
            "starts_at": call.data.get("starts_at", now.isoformat()),
            "ends_at": call.data.get("ends_at"),
            "notes": call.data.get("notes"),
            "source": "user",
        }
        await storage.add_context_event(payload)
        await coordinator.async_request_refresh()

    async def handle_add_feedback(call: ServiceCall) -> None:
        runtime = _runtime()
        if runtime is None:
            return
        storage: EsterStorage = runtime["storage"]
        coordinator: EsterCoordinator = runtime["coordinator"]
        payload = {
            "feedback_id": str(uuid4()),
            "decision_id": call.data["decision_id"],
            "rating": call.data["rating"],
            "comment": call.data.get("comment"),
            "created_at": datetime.now().astimezone().isoformat(),
        }
        await storage.add_feedback(payload)
        hass.bus.async_fire(EVENT_FEEDBACK, payload)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CONTEXT,
        handle_add_context,
        schema=_CONTEXT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FEEDBACK,
        handle_add_feedback,
        schema=_FEEDBACK_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up E.S.T.E.R. from a config entry."""
    storage = EsterStorage(hass)
    await storage.async_load()

    coordinator = EsterCoordinator(hass, entry, storage)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "storage": storage,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload E.S.T.E.R."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
