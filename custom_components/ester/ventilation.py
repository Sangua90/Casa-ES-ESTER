"""Local ventilation effectiveness learning."""
from __future__ import annotations
from statistics import mean


def ventilation_model(samples: list[dict]) -> dict:
    active_rates, inactive_rates = [], []
    points = sorted(samples, key=lambda x: x.get("t", 0))
    for a, b in zip(points, points[1:]):
        try:
            dt_h = (float(b["t"]) - float(a["t"])) / 3600
            h0, h1 = float(a["humidity"]), float(b["humidity"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0.08 <= dt_h <= 2 or not (0 <= h0 <= 100 and 0 <= h1 <= 100):
            continue
        rate = (h1 - h0) / dt_h
        (active_rates if a.get("active") else inactive_rates).append(rate)
    active = round(mean(active_rates), 3) if len(active_rates) >= 3 else None
    inactive = round(mean(inactive_rates), 3) if len(inactive_rates) >= 3 else None
    effectiveness = None
    if active is not None and inactive is not None:
        effectiveness = round(inactive - active, 3)
    return {
        "active_humidity_rate_pct_per_h": active,
        "inactive_humidity_rate_pct_per_h": inactive,
        "effectiveness_pct_per_h": effectiveness,
        "active_samples": len(active_rates),
        "inactive_samples": len(inactive_rates),
        "confidence": round(min(0.95, (len(active_rates)+len(inactive_rates))/24), 3),
    }


def ventilation_recommendation(*, humidity: float, model: dict, active: bool) -> dict:
    eff = model.get("effectiveness_pct_per_h")
    if humidity < 60:
        return {"strategy": "would_stop", "reason": "Umidità già sotto 60%.", "confidence": 0.9}
    if active and eff is not None and eff < 0.5:
        return {"strategy": "would_stop", "reason": "La ventilazione osservata sta portando poco beneficio.", "confidence": 0.82}
    if humidity > 68:
        return {"strategy": "would_run", "reason": "Umidità elevata e ventilazione potenzialmente utile.", "confidence": 0.82 if eff is not None else 0.65}
    return {"strategy": "hold", "reason": "Nessun cambio chiaramente utile.", "confidence": 0.75}
