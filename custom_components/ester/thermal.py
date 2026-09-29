"""Pure local predictive models for E.S.T.E.R.; no Home Assistant access."""
from __future__ import annotations

from math import isfinite
from statistics import mean


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def build_room_thermal_model(samples: list[dict]) -> dict:
    """Estimate passive and active temperature rates from observed samples.

    Samples: {"t": epoch_seconds, "temp": C, "active": bool|None}.
    This is descriptive and conservative; it never assumes causality.
    """
    points = sorted(
        (float(s["t"]), _num(s.get("temp")), s.get("active"))
        for s in samples
        if _num(s.get("t")) is not None and _num(s.get("temp")) is not None
    )
    passive, active = [], []
    for (t0, v0, a0), (t1, v1, a1) in zip(points, points[1:]):
        dt_h = (t1 - t0) / 3600
        if not 0.08 <= dt_h <= 2:
            continue
        rate = (v1 - v0) / dt_h
        if abs(rate) > 10:
            continue
        state = a0 if a0 is not None else a1
        (active if state else passive).append(rate)
    model = {
        "passive_rate_c_per_h": round(mean(passive), 3) if len(passive) >= 3 else None,
        "active_rate_c_per_h": round(mean(active), 3) if len(active) >= 3 else None,
        "passive_samples": len(passive),
        "active_samples": len(active),
    }
    total = len(passive) + len(active)
    model["confidence"] = round(min(0.95, total / 24), 3)
    return model


def predict_temperature(current_c: float, minutes: int, rate_c_per_h: float | None) -> float | None:
    if rate_c_per_h is None:
        return None
    return round(current_c + rate_c_per_h * minutes / 60, 2)


def minutes_to_target(current_c: float, target_c: float, active_rate_c_per_h: float | None) -> int | None:
    if active_rate_c_per_h is None:
        return None
    delta = target_c - current_c
    if delta == 0:
        return 0
    if delta * active_rate_c_per_h <= 0 or abs(active_rate_c_per_h) < 0.05:
        return None
    minutes = delta / active_rate_c_per_h * 60
    return max(0, min(720, round(minutes)))


def compare_climate_strategies(*, current_c: float, target_c: float, minutes_until_use: int,
                               model: dict, energy_price_eur_kwh: float | None = None,
                               estimated_power_kw: float | None = None) -> list[dict]:
    """Compare wait vs precondition using only locally learned rates."""
    passive = model.get("passive_rate_c_per_h")
    active = model.get("active_rate_c_per_h")
    wait_temp = predict_temperature(current_c, minutes_until_use, passive)
    needed = minutes_to_target(current_c, target_c, active)
    options = [{
        "strategy": "wait",
        "start_in_minutes": None,
        "predicted_temp_at_use": wait_temp,
        "estimated_cost_eur": 0.0,
    }]
    if needed is not None:
        start_in = max(0, minutes_until_use - needed)
        cost = None
        if energy_price_eur_kwh is not None and estimated_power_kw is not None:
            cost = round(max(0, needed) / 60 * estimated_power_kw * energy_price_eur_kwh, 3)
        options.append({
            "strategy": "precondition",
            "start_in_minutes": start_in,
            "predicted_temp_at_use": target_c,
            "estimated_runtime_minutes": needed,
            "estimated_cost_eur": cost,
        })
    return options
