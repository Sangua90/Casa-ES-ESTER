"""Entity discovery and classification for E.S.T.E.R."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .models import EntityProfile

_READ_ONLY_DOMAINS = {
    "sensor", "binary_sensor", "weather", "sun", "person", "device_tracker",
    "event", "calendar", "camera", "image", "update",
}
_SENSITIVE_DOMAINS = {
    "alarm_control_panel", "lock", "siren", "button",
}
_CONTROLLABLE_DOMAINS = {
    "light", "switch", "climate", "cover", "fan", "humidifier",
    "water_heater", "valve", "media_player", "vacuum", "number",
    "select", "input_boolean", "input_number", "input_select",
    "alarm_control_panel", "lock", "siren", "button",
}


def _infer_role(domain: str, device_class: str | None, unit: str | None, name: str) -> str:
    """Infer a broad functional role without hard-coding the user's house."""
    text = f"{name} {device_class or ''} {unit or ''}".lower()

    if domain == "climate":
        return "climate"
    if domain == "water_heater" or any(k in text for k in ("boiler", "acqua calda", "water heater")):
        return "hot_water"
    if domain in {"light"}:
        return "lighting"
    if domain in {"alarm_control_panel", "lock", "siren"}:
        return "security"
    if domain in {"person", "device_tracker"}:
        return "presence"
    if domain in {"fan"}:
        return "ventilation"
    if domain in {"valve"} and any(k in text for k in ("irrig", "garden", "giardino", "sprinkler")):
        return "irrigation"
    if any(k in text for k in ("humidity", "umid", "%")):
        return "humidity"
    if any(k in text for k in ("temperature", "temperatura", "°c", "°f")):
        return "temperature"
    if any(k in text for k in ("power", "potenza", "energy", "energia", "kwh", "kw", "w")):
        return "energy"
    if domain == "binary_sensor" and any(k in text for k in ("occup", "motion", "presence", "presenza")):
        return "presence"
    return "generic"


def discover_entities(hass: HomeAssistant) -> list[EntityProfile]:
    """Build a normalized snapshot of HA entities."""
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    profiles: list[EntityProfile] = []

    for state in hass.states.async_all():
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        reg_entry = entity_reg.async_get(entity_id)

        device_id = reg_entry.device_id if reg_entry else None
        area_id = reg_entry.area_id if reg_entry else None

        if not area_id and device_id:
            device = device_reg.async_get(device_id)
            if device:
                area_id = device.area_id

        friendly_name = state.attributes.get("friendly_name", entity_id)
        unit = state.attributes.get("unit_of_measurement")
        device_class = state.attributes.get("device_class")

        profile = EntityProfile(
            entity_id=entity_id,
            domain=domain,
            name=friendly_name,
            state=state.state,
            area_id=area_id,
            device_id=device_id,
            unit=unit,
            device_class=device_class,
            role=_infer_role(domain, device_class, unit, friendly_name),
            controllable=domain in _CONTROLLABLE_DOMAINS and domain not in _READ_ONLY_DOMAINS,
            sensitive=domain in _SENSITIVE_DOMAINS,
            attributes={
                "area_name": area_reg.async_get_area(area_id).name if area_id and area_reg.async_get_area(area_id) else None,
            },
        )
        profiles.append(profile)

    return profiles


def summarize_inventory(profiles: list[EntityProfile]) -> dict[str, Any]:
    """Return a compact inventory summary."""
    domains = Counter(p.domain for p in profiles)
    roles = Counter(p.role for p in profiles if p.role)
    areas = Counter(p.area_id for p in profiles if p.area_id)
    return {
        "entities": len(profiles),
        "controllable": sum(1 for p in profiles if p.controllable),
        "sensitive": sum(1 for p in profiles if p.sensitive),
        "domains": dict(domains),
        "roles": dict(roles),
        "areas": dict(areas),
    }
