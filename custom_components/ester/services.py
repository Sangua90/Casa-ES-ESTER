"""Admin-only internal services; none accept executable service names."""
from __future__ import annotations

from datetime import timedelta
from time import monotonic
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util

from .ai.factory import create_provider
from .const import DOMAIN, EVENT_FEEDBACK
from .home import MODES, ROLES

TEXT = vol.All(cv.string, vol.Length(min=1, max=2000))
SHORT = vol.All(cv.string, vol.Length(min=1, max=100))


def register_services(hass):
    last_ai = [float("-inf")]

    def runtime():
        entries = [e for e in hass.config_entries.async_entries(DOMAIN)
                   if getattr(e, "runtime_data", None) is not None and e.state.value == "loaded"]
        if not entries:
            raise ServiceValidationError("E.S.T.E.R. is not loaded")
        return entries[0].runtime_data

    async def add_context(call):
        coordinator = runtime()
        now = dt_util.utcnow()
        start = dt_util.parse_datetime(call.data.get("starts_at", now.isoformat()))
        end = dt_util.parse_datetime(call.data.get("ends_at", (now + timedelta(hours=24)).isoformat()))
        if start is None or end is None or start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ServiceValidationError("Use timezone-aware ISO timestamps; ends_at must follow starts_at")
        event = {"event_id": str(uuid4()), "label": call.data["label"],
                 "mode": call.data.get("mode", "normal"), "areas": call.data.get("areas", []),
                 "starts_at": start.isoformat(), "ends_at": end.isoformat(),
                 "notes": call.data.get("notes", ""), "source": "user"}
        async with coordinator.storage.lock:
            await coordinator.storage.add_context_event(event)
        await coordinator.async_request_refresh()

    async def remove_context(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            events = coordinator.storage.data["context_events"]
            if not any(e["event_id"] == call.data["event_id"] for e in events):
                raise ServiceValidationError("Unknown context")
            coordinator.storage.data["context_events"] = [e for e in events if e["event_id"] != call.data["event_id"]]
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def add_feedback(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            decision = next((d for d in coordinator.storage.data["decisions"]
                             if d["decision_id"] == call.data["decision_id"]), None)
            if decision is None:
                raise ServiceValidationError("Unknown or expired decision")
            feedback = {**dict(call.data), "feedback_id": str(uuid4()), "created_at": dt_util.utcnow().isoformat(),
                        "category": decision["category"]}
            # Repeated feedback replaces an earlier rating instead of multiplying its weight.
            coordinator.storage.data["feedback"] = [f for f in coordinator.storage.data["feedback"]
                                                    if f["decision_id"] != decision["decision_id"]]
            decision["feedback"] = feedback
            await coordinator.storage.add_feedback(feedback)
        hass.bus.async_fire(EVENT_FEEDBACK, feedback)
        await coordinator.async_request_refresh()

    async def classify(call):
        coordinator = runtime()
        entity_id = call.data["entity_id"]
        if hass.states.get(entity_id) is None:
            raise ServiceValidationError("Unknown entity")
        if "area_id" in call.data:
            from homeassistant.helpers import area_registry
            if area_registry.async_get(hass).async_get_area(call.data["area_id"]) is None:
                raise ServiceValidationError("Unknown area")
        async with coordinator.storage.lock:
            coordinator.storage.data["classifications"][entity_id] = {k: v for k, v in call.data.items() if k != "entity_id"}
            await coordinator.storage.async_save()
        coordinator.history.last_read = None
        await coordinator.async_request_refresh()

    async def preference(call):
        coordinator = runtime()
        key, value = call.data["key"], call.data["value"]
        if not (key.startswith("comfort:") and 5 <= value <= 35 or key.startswith("soil_min:") and 0 <= value <= 100):
            raise ServiceValidationError("Supported keys: comfort:<area> (5–35 °C), soil_min:<area> (0–100 %)")
        async with coordinator.storage.lock:
            await coordinator.storage.set_preference(key, value)
        await coordinator.async_request_refresh()

    async def evaluate_now(call):
        await runtime().async_request_refresh()

    async def summary(call):
        coordinator = runtime()
        data = coordinator.data or {}
        return {"shadow_mode": True, "real_actuation_enabled": False,
                "inventory": data.get("inventory", {}), "rooms": data.get("rooms", {}),
                "contexts": data.get("contexts", []), "history": data.get("history", {}),
                "decisions": coordinator.storage.data["decisions"][-call.data.get("limit", 20):]}

    async def explain(call):
        coordinator = runtime()
        decision = next((d for d in coordinator.storage.data["decisions"] if d["decision_id"] == call.data["decision_id"]), None)
        if decision is None:
            raise ServiceValidationError("Unknown or expired decision")
        options = coordinator.entry.options
        if options.get("ai_provider", "disabled") == "disabled":
            return {"provider": "local", "text": decision["reasoning"], "alternatives": decision["alternatives"]}
        if monotonic() - last_ai[0] < 60:
            raise ServiceValidationError("Wait 60 seconds between AI requests")
        last_ai[0] = monotonic()
        try:
            provider = create_provider(hass, options)
            # No entity IDs, people, raw state attributes, context notes or credentials leave HA.
            safe = {k: decision[k] for k in ("category", "title", "proposed_action", "reasoning", "confidence", "risk")}
            response = await provider.async_explain(decision=safe, context={"shadow_mode": True})
            return {"provider": response.provider, "text": response.text}
        except Exception as err:
            raise HomeAssistantError("AI unavailable; local reasoning remains available") from None

    schemas = {
        "add_context": (add_context, {vol.Required("label"): SHORT, vol.Optional("mode", default="normal"): vol.In(MODES),
            vol.Optional("starts_at"): cv.string, vol.Optional("ends_at"): cv.string,
            vol.Optional("areas", default=[]): [SHORT], vol.Optional("notes"): TEXT}),
        "remove_context": (remove_context, {vol.Required("event_id"): SHORT}),
        "add_feedback": (add_feedback, {vol.Required("decision_id"): SHORT,
            vol.Required("rating"): vol.In(["correct", "wrong", "partial"]), vol.Optional("comment"): TEXT}),
        "classify_entity": (classify, {vol.Required("entity_id"): cv.entity_id,
            vol.Required("role"): vol.In(ROLES), vol.Optional("area_id"): SHORT}),
        "set_preference": (preference, {vol.Required("key"): SHORT, vol.Required("value"): vol.Coerce(float)}),
        "evaluate": (evaluate_now, {}),
        "get_summary": (summary, {vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=100))}),
        "explain_decision": (explain, {vol.Required("decision_id"): SHORT}),
    }
    for name, (handler, schema) in schemas.items():
        async_register_admin_service(hass, DOMAIN, name, handler, schema=vol.Schema(schema),
            supports_response=SupportsResponse.ONLY if name in {"get_summary", "explain_decision"} else SupportsResponse.NONE)

