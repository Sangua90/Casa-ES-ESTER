"""Validation and routing for natural-language interpretations."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

ALLOWED_INTENTS = {"preference", "context", "usage_profile", "knowledge_note", "feedback", "unknown"}
ALLOWED_MODES = {"normal", "vacation", "guests", "illness", "work_from_home"}


def validate_interpretation(data: dict) -> dict:
    if not isinstance(data, dict):
        return {"intent": "unknown", "confidence": 0.0}
    intent = data.get("intent") if data.get("intent") in ALLOWED_INTENTS else "unknown"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    result = {"intent": intent, "confidence": confidence}
    for key in ("area_id", "key", "value", "mode", "label", "notes", "text", "start_time", "end_time",
                "expected_occupancy", "comfort_c", "weekdays", "duration_hours"):
        if key in data:
            result[key] = data[key]
    return result


def apply_interpretation(store: dict, parsed: dict, now: datetime) -> dict:
    """Apply only bounded memory updates. Never performs device actions."""
    parsed = validate_interpretation(parsed)
    intent = parsed["intent"]
    if parsed["confidence"] < 0.7:
        intent = "knowledge_note"

    if intent == "preference":
        key = parsed.get("key")
        value = parsed.get("value")
        if isinstance(key, str) and key.startswith("comfort:"):
            try:
                value = float(value)
            except (TypeError, ValueError):
                intent = "knowledge_note"
            else:
                if 5 <= value <= 35:
                    store.setdefault("preferences", {})[key] = value
                    return {"applied": "preference", "key": key, "value": value}
                intent = "knowledge_note"

    if intent == "context":
        mode = parsed.get("mode")
        if mode in ALLOWED_MODES:
            duration = parsed.get("duration_hours", 24)
            try:
                duration = min(24 * 30, max(1, float(duration)))
            except (TypeError, ValueError):
                duration = 24
            event = {
                "event_id": str(uuid4()),
                "label": parsed.get("label") or mode,
                "mode": mode,
                "areas": [parsed["area_id"]] if parsed.get("area_id") else [],
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(hours=duration)).isoformat(),
                "notes": parsed.get("notes") or parsed.get("text") or "",
                "source": "natural_language",
            }
            store.setdefault("context_events", []).append(event)
            return {"applied": "context", "event": event}

    if intent == "usage_profile":
        required = all(k in parsed for k in ("area_id", "weekdays", "start_time", "end_time", "expected_occupancy"))
        if required:
            profile = {
                "profile_id": str(uuid4()),
                "area_id": parsed["area_id"],
                "label": parsed.get("label") or "Routine",
                "weekdays": parsed["weekdays"],
                "start_time": parsed["start_time"],
                "end_time": parsed["end_time"],
                "expected_occupancy": parsed["expected_occupancy"],
                "comfort_c": parsed.get("comfort_c"),
                "notes": parsed.get("notes", ""),
                "source": "natural_language",
            }
            store.setdefault("usage_profiles", []).append(profile)
            return {"applied": "usage_profile", "profile": profile}

    note = {
        "knowledge_id": str(uuid4()),
        "category": "natural_language",
        "area_id": parsed.get("area_id"),
        "text": parsed.get("text") or parsed.get("notes") or str(parsed),
        "scope": "persistent",
        "confidence": parsed.get("confidence", 0.5),
        "created_at": now.isoformat(),
        "source": "natural_language",
    }
    store.setdefault("knowledge", []).append(note)
    return {"applied": "knowledge_note", "knowledge": note}


def local_interpret(message: str, area_ids: list[str]) -> dict:
    """Small deterministic fallback for common Italian commands."""
    text = message.strip()
    lower = text.lower()
    area = next((a for a in area_ids if a.lower() in lower), None)

    # Comfort preference, only when an existing HA area is explicitly named.
    import re
    temp = re.search(r"(?<!\d)([1-3]?\d(?:[.,]\d)?)\s*(?:°|gradi|grado|c\b)", lower)
    if area and temp and any(word in lower for word in ("voglio", "prefer", "comfort", "tieni", "tenere")):
        value = float(temp.group(1).replace(",", "."))
        if 5 <= value <= 35:
            return {"intent": "preference", "key": f"comfort:{area}", "value": value,
                    "area_id": area, "confidence": 0.96, "text": text}

    modes = {
        "vacanza": "vacation", "via": "vacation", "ospiti": "guests",
        "malat": "illness", "lavoro da casa": "work_from_home", "smart working": "work_from_home",
    }
    mode = next((value for token, value in modes.items() if token in lower), None)
    if mode:
        hours = 24
        if "weekend" in lower:
            hours = 72
        elif "stasera" in lower:
            hours = 12
        elif "domani" in lower:
            hours = 36
        return {"intent": "context", "mode": mode, "area_id": area, "duration_hours": hours,
                "label": text[:100], "notes": text, "confidence": 0.85, "text": text}

    return {"intent": "knowledge_note", "area_id": area, "text": text, "confidence": 0.6}
