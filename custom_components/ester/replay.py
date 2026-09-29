"""Historical Recorder replay for E.S.T.E.R. Shadow validation."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from functools import partial

from homeassistant.helpers.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt as dt_util

from .discovery import discover_entities
from .home import active_contexts
from .usage import usage_snapshot
from .policies import evaluate

REPLAY_ROLES = {
    "temperature", "humidity", "hot_water", "climate", "presence",
    "solar_power", "load_power", "grid_power", "battery_power", "phase_power",
    "battery", "pv_forecast_power", "pv_forecast_remaining_energy",
    "soil_moisture", "lighting", "ventilation", "security",
}


async def run_historical_replay(hass, coordinator, *, days: int = 7, step_minutes: int = 30) -> dict:
    """Replay historical states through the current Shadow policy engine."""
    if "recorder" not in hass.config.components:
        raise RuntimeError("Recorder is unavailable")
    days = max(1, min(30, int(days)))
    step_minutes = max(30, min(240, int(step_minutes)))
    now = dt_util.utcnow()
    start = now - timedelta(days=days)

    profiles = [
        p for p in discover_entities(hass, coordinator.storage.data["classifications"])
        if p.role in REPLAY_ROLES
    ][:80]
    if not profiles:
        return {"status": "no_entities", "days": days, "checkpoints": 0}

    recorder = get_instance(hass)
    states = await recorder.async_add_executor_job(partial(
        get_significant_states,
        hass,
        start,
        now,
        [p.entity_id for p in profiles],
        significant_changes_only=False,
        minimal_response=False,
        no_attributes=False,
    ))

    series = {p.entity_id: list(states.get(p.entity_id, [])) for p in profiles}
    positions = {p.entity_id: 0 for p in profiles}
    current = {}
    checkpoint = start
    checkpoints = 0
    decision_count = 0
    needs_input = 0
    confidence_sum = 0.0
    category_counts = {}
    risk_counts = {}
    samples = []

    local_tz = __import__("zoneinfo").ZoneInfo(hass.config.time_zone)
    data = coordinator.storage.data

    while checkpoint <= now and checkpoints < 1500:
        historical_profiles = []
        for base in profiles:
            seq = series.get(base.entity_id, [])
            pos = positions[base.entity_id]
            while pos < len(seq) and seq[pos].last_updated <= checkpoint:
                current[base.entity_id] = seq[pos]
                pos += 1
            positions[base.entity_id] = pos
            state = current.get(base.entity_id)
            if state is None:
                continue
            attrs = dict(state.attributes)
            attrs["last_reported"] = checkpoint.isoformat()
            historical_profiles.append(replace(
                base,
                state=state.state,
                unit=state.attributes.get("unit_of_measurement", base.unit),
                attributes=attrs,
            ))

        if historical_profiles:
            contexts = active_contexts(data.get("context_events", []), checkpoint)
            usage = usage_snapshot(data.get("usage_profiles", []), checkpoint, local_tz)
            proposals = evaluate(
                coordinator.engine,
                historical_profiles,
                {},
                contexts,
                data.get("preferences", {}),
                data.get("feedback", []),
                checkpoint,
                usage,
                data.get("thermal_models", {}),
                data.get("flexible_loads", []),
                local_tz,
                data.get("ventilation_models", {}),
                data.get("hot_water_models", {}),
                data.get("occupancy_models", {}),
                {},
            )
            if proposals:
                decision_count += len(proposals)
                avg = sum(float(p.confidence) for p in proposals) / len(proposals)
                confidence_sum += avg
                for p in proposals:
                    category_counts[p.category] = category_counts.get(p.category, 0) + 1
                    risk_counts[p.risk.value] = risk_counts.get(p.risk.value, 0) + 1
                    needs_input += int(p.status.value == "needs_input")
                samples.append({
                    "at": checkpoint.isoformat(),
                    "decisions": len(proposals),
                    "avg_confidence": round(avg, 3),
                    "categories": sorted({p.category for p in proposals}),
                })
        checkpoints += 1
        checkpoint += timedelta(minutes=step_minutes)

    report = {
        "status": "ready",
        "generated_at": now.isoformat(),
        "days": days,
        "step_minutes": step_minutes,
        "entities": len(profiles),
        "checkpoints": checkpoints,
        "decisions": decision_count,
        "needs_input": needs_input,
        "avg_checkpoint_confidence": round(confidence_sum / max(1, len(samples)), 3),
        "categories": category_counts,
        "risk_counts": risk_counts,
        "samples": samples[-250:],
        "shadow_mode": True,
        "actuations": 0,
        "note": "Historical replay uses current learned models/preferences against past states; it never executes actions.",
    }
    async with coordinator.storage.lock:
        coordinator.storage.data["last_replay"] = report
        await coordinator.storage.async_save()
    await coordinator.async_request_refresh()
    return report
