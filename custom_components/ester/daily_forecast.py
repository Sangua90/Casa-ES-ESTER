"""Compact local daily operating forecast."""
from __future__ import annotations


def daily_forecast(now, usage: dict, season: dict, decisions: list[dict], questions: list[dict], anomalies: list[dict]) -> dict:
    upcoming = []
    for area, data in usage.items():
        for item in data.get("upcoming", []):
            upcoming.append({
                "area_id": area,
                "label": item.get("label"),
                "minutes_until": item.get("minutes_until"),
                "expected_occupancy": item.get("expected_occupancy"),
                "comfort_c": item.get("comfort_c"),
            })
    upcoming.sort(key=lambda x: x.get("minutes_until", 999999))
    energy = next((d for d in reversed(decisions) if d.get("category") == "energy"), None)
    climate = [d for d in decisions if d.get("category") == "climate"][-5:]
    confidence_values = [float(d.get("confidence", 0) or 0) for d in decisions[-20:]]
    return {
        "generated_at": now.isoformat(),
        "season": season.get("season"),
        "next_uses": upcoming[:12],
        "energy_strategy": ((energy or {}).get("evidence") or {}).get("energy_plan", {}).get("strategy"),
        "climate_actions": [
            {"area_id": d.get("area_id"), "action": d.get("proposed_action"), "confidence": d.get("confidence")}
            for d in climate
        ],
        "open_questions": sum(q.get("status") == "open" for q in questions),
        "anomalies": len(anomalies),
        "avg_recent_confidence": round(sum(confidence_values)/len(confidence_values), 3) if confidence_values else None,
        "scope": "local_house_forecast",
        "shadow_mode": True,
    }
