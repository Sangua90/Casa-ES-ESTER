"""HA-facing natural-language teaching. AI proposes; user confirms; no device actuation."""
from __future__ import annotations

from uuid import uuid4
from .ai.factory import create_provider
from .language import validate_teaching
from .brain import retrieval_context, validity
from .teaching import compile_message, compile_item
from zoneinfo import ZoneInfo
from homeassistant.util import dt as dt_util


async def interpret_and_store(hass, coordinator, message: str, *, preview: bool = True, source_knowledge_id=None) -> dict:
    """Create a pending teaching proposal. Memory is unchanged until confirmation."""
    rooms=(getattr(coordinator, "data", None) or {}).get("rooms",{})
    if not rooms:
        from homeassistant.helpers import area_registry
        rooms = {area.id:{"name":area.name} for area in area_registry.async_get(hass).async_list_areas()}
    area_ids=sorted(rooms)
    options=coordinator.entry.options
    now=dt_util.utcnow()
    local_tz=ZoneInfo(hass.config.time_zone)
    parent = next((r for r in coordinator.storage.data.get("knowledge", []) if r.get("knowledge_id")==source_knowledge_id), None) if source_knowledge_id else None
    if source_knowledge_id and (parent is None or validity(parent, now) not in {"active", "scheduled"}):
        raise ValueError("La fonte da completare non è più disponibile.")
    provider_name="local"
    teaching=None
    if options.get("ai_provider","disabled")!="disabled":
        provider=create_provider(hass,options)
        response=await provider.async_extract_teaching(
            message=message,
            context={"shadow_mode":True,"allowed_area_ids":area_ids,"area_names":{area:meta.get("name",area) for area,meta in rooms.items()},
                     **retrieval_context(coordinator.storage.data, message, dt_util.utcnow())},
        )
        teaching=validate_teaching(response.structured or {},message, area_ids)
        teaching["items"]=[compile_item(item, rooms, now, local_tz) for item in teaching["items"]]
        provider_name=response.provider or "gemini"
    else:
        teaching=validate_teaching(compile_message(message, rooms, now, local_tz),message,area_ids)

    if parent:
        for item in teaching["items"]:
            item["derived_from"] = parent["knowledge_id"]
            item.pop("supersedes_hint", None)
            if not item.get("area_id") and parent.get("area_id") in rooms and (item.get("effect") or {}).get("type")!="energy_price":
                item["area_id"] = parent["area_id"]
                item.update(compile_item(item, rooms, now, local_tz))
            for field in ("source_file", "source_digest", "starts_at", "expires_at"):
                if parent.get(field) and not item.get(field):
                    item[field] = parent[field]

    proposal={"proposal_id":str(uuid4()),"created_at":dt_util.utcnow().isoformat(),"provider":provider_name,
              "summary":teaching["summary"],"items":teaching["items"],"original_text":message[:2000]}
    async with coordinator.storage.lock:
        pending=coordinator.storage.data.setdefault("pending_teachings",[])
        pending.append(proposal); del pending[:-20]
        await coordinator.storage.async_save()
    return {**proposal,"shadow_mode":True,"device_action":False,"memory_changed":False}
