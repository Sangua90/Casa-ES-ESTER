"""HA-facing natural-language interpreter. Gemini is optional and never actuates devices."""
from __future__ import annotations

from .ai.factory import create_provider
from .language import apply_interpretation, local_interpret, validate_interpretation
from .snapshots import create_snapshot
from homeassistant.util import dt as dt_util


async def interpret_and_store(hass, coordinator, message: str) -> dict:
    area_ids = sorted((coordinator.data or {}).get("rooms", {}).keys())
    parsed = local_interpret(message, area_ids)
    provider_name = "local"

    options = coordinator.entry.options
    if options.get("ai_provider", "disabled") != "disabled" and parsed.get("confidence", 0) < 0.9:
        provider = create_provider(hass, options)
        response = await provider.async_interpret(
            message=message,
            context={
                "shadow_mode": True,
                "allowed_area_ids": area_ids,
                "open_question_titles": [
                    q.get("title") for q in (coordinator.data or {}).get("questions", [])[:10]
                ],
            },
        )
        if response.structured:
            parsed = validate_interpretation(response.structured)
            parsed["text"] = message
            if parsed.get("area_id") and parsed["area_id"] not in area_ids:
                parsed = {"intent": "knowledge_note", "confidence": 0.4, "text": message}
            provider_name = response.provider or "gemini"

    async with coordinator.storage.lock:
        create_snapshot(
            coordinator.storage.data,
            dt_util.utcnow(),
            "Prima di insegnamento naturale",
            message[:200],
        )
        result = apply_interpretation(
            coordinator.storage.data,
            parsed,
            dt_util.utcnow(),
        )
        await coordinator.storage.async_save()

    await coordinator.async_request_refresh()
    return {
        "provider": provider_name,
        "interpretation": parsed,
        "memory_result": result,
        "shadow_mode": True,
        "device_action": False,
    }
