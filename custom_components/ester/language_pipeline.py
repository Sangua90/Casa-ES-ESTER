"""HA-facing natural-language teaching. AI proposes; user confirms; no device actuation."""
from __future__ import annotations

from uuid import uuid4
from .ai.factory import create_provider
from .language import local_interpret, validate_teaching
from .brain import retrieval_context
from homeassistant.util import dt as dt_util


async def interpret_and_store(hass, coordinator, message: str, *, preview: bool = True) -> dict:
    """Create a pending teaching proposal. Memory is unchanged until confirmation."""
    area_ids=sorted((coordinator.data or {}).get("rooms",{}).keys())
    options=coordinator.entry.options
    provider_name="local"
    teaching=None
    if options.get("ai_provider","disabled")!="disabled":
        provider=create_provider(hass,options)
        response=await provider.async_extract_teaching(
            message=message,
            context={"shadow_mode":True,"allowed_area_ids":area_ids,
                     **retrieval_context(coordinator.storage.data, message, dt_util.utcnow())},
        )
        teaching=validate_teaching(response.structured or {},message)
        provider_name=response.provider or "gemini"
    else:
        # Safe local fallback: preserve the statement as one proposed fact.
        parsed=local_interpret(message,area_ids)
        domain="climate" if str(parsed.get("key","")).startswith("comfort:") else "other"
        teaching=validate_teaching({"summary":"Ho conservato la frase come informazione da confermare.",
                                    "items":[{"domain":domain,"kind":"fact","statement":message,"confidence":parsed.get("confidence",.5),
                                              **({"area_id":parsed["area_id"]} if parsed.get("area_id") else {})}]},message)

    proposal={"proposal_id":str(uuid4()),"created_at":dt_util.utcnow().isoformat(),"provider":provider_name,
              "summary":teaching["summary"],"items":teaching["items"],"original_text":message[:2000]}
    async with coordinator.storage.lock:
        pending=coordinator.storage.data.setdefault("pending_teachings",[])
        pending.append(proposal); del pending[:-20]
        await coordinator.storage.async_save()
    return {**proposal,"shadow_mode":True,"device_action":False,"memory_changed":False}
