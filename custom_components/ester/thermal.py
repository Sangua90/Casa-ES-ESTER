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
                               estimated_power_kw: float | None = None, pv_surplus_kw=None,
                               allow_delayed=True) -> list[dict]:
    """Predict wait/now/delayed alternatives without assuming an unreachable target."""
    from .deliberation import climate_candidates
    return climate_candidates(current_c=current_c, target_c=target_c, minutes_until_use=minutes_until_use,
        model=model, energy_price_eur_kwh=energy_price_eur_kwh, estimated_power_kw=estimated_power_kw,
        pv_surplus_kw=pv_surplus_kw, allow_delayed=allow_delayed)
