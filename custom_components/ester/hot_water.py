"""Local domestic hot-water descriptive model."""
from __future__ import annotations
from statistics import mean


def hot_water_model(samples: list[dict]) -> dict:
    drops, rises = [], []
    points = sorted(samples, key=lambda x: x.get("t", 0))
    for a, b in zip(points, points[1:]):
        try:
            dt_h = (float(b["t"]) - float(a["t"])) / 3600
            t0, t1 = float(a["temp"]), float(b["temp"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0.08 <= dt_h <= 3 or not (0 <= t0 <= 90 and 0 <= t1 <= 90):
            continue
        rate = (t1 - t0) / dt_h
        if rate < -0.2:
            drops.append(rate)
        elif rate > 0.2:
            rises.append(rate)
    return {
        "avg_drop_c_per_h": round(mean(drops), 3) if len(drops) >= 3 else None,
        "avg_recovery_c_per_h": round(mean(rises), 3) if len(rises) >= 3 else None,
        "drop_samples": len(drops),
        "recovery_samples": len(rises),
        "confidence": round(min(0.95, (len(drops)+len(rises))/20), 3),
    }


def hot_water_shadow_plan(*, temp_c: float, target_c: float, expected_use_minutes: int | None,
                          model: dict, pv_surplus_w: float | None = None) -> dict:
    recovery = model.get("avg_recovery_c_per_h")
    if temp_c >= target_c:
        return {"strategy": "hold", "reason": "ACS già al target.", "confidence": 0.9}
    needed_h = None
    if recovery and recovery > 0:
        needed_h = max(0.0, (target_c-temp_c)/recovery)
    if expected_use_minutes is not None and needed_h is not None:
        if needed_h*60 >= expected_use_minutes:
            return {"strategy": "would_heat_now", "reason": "Il recupero stimato richiede di iniziare ora.", "confidence": 0.86}
    if pv_surplus_w is not None and pv_surplus_w > 1200 and temp_c < target_c-2:
        return {"strategy": "would_use_pv", "reason": "Surplus FV utile e ACS sotto target.", "confidence": 0.8}
    return {"strategy": "wait", "reason": "Non c'è urgenza dimostrata per scaldare ora.", "confidence": 0.75}
