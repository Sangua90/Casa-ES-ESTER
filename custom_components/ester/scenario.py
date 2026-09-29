"""Read-only what-if scenarios using copies of E.S.T.E.R. state."""
from __future__ import annotations
from copy import deepcopy
from datetime import timedelta

from .home import active_contexts
from .usage import usage_snapshot
from .policies import evaluate


def simulate_scenario(
    *,
    engine,
    profiles,
    data: dict,
    now,
    local_tz,
    mode: str = "normal",
    area_id: str | None = None,
    comfort_delta_c: float = 0.0,
    energy_price_multiplier: float = 1.0,
) -> dict:
    preferences = deepcopy(data.get("preferences", {}))
    for key in list(preferences):
        if key.startswith("comfort:"):
            if area_id is None or key == f"comfort:{area_id}":
                try:
                    preferences[key] = float(preferences[key]) + float(comfort_delta_c)
                except (TypeError, ValueError):
                    pass
    if "energy_price_eur_kwh" in preferences:
        preferences["energy_price_eur_kwh"] = float(preferences["energy_price_eur_kwh"]) * float(energy_price_multiplier)

    contexts = deepcopy(data.get("context_events", []))
    if mode != "normal":
        contexts.append({
            "event_id": "scenario",
            "label": f"Scenario {mode}",
            "mode": mode,
            "areas": [area_id] if area_id else [],
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=24)).isoformat(),
            "source": "scenario",
        })

    active = active_contexts(contexts, now)
    usage = usage_snapshot(data.get("usage_profiles", []), now, local_tz)
    decisions = evaluate(
        engine, profiles, data.get("learning", {}), active, preferences,
        data.get("feedback", []), now, usage, data.get("thermal_models", {}),
        data.get("flexible_loads", []), local_tz,
        data.get("ventilation_models", {}), data.get("hot_water_models", {}),
        data.get("occupancy_models", {}), data.get("energy_runtime", {}),
    )
    return {
        "mode": mode,
        "area_id": area_id,
        "comfort_delta_c": comfort_delta_c,
        "energy_price_multiplier": energy_price_multiplier,
        "decision_count": len(decisions),
        "decisions": [d.as_dict() for d in decisions],
        "shadow_mode": True,
        "persisted": False,
        "actuations": 0,
    }
