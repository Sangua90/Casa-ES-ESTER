"""Local deterministic whole-home energy planner for Shadow Mode."""
from __future__ import annotations

from datetime import datetime
from math import isfinite


def _num(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def integrate_forecast_kwh(curve: list[dict], now: datetime, target: datetime) -> tuple[float | None, bool]:
    points = []
    for item in curve or []:
        try:
            stamp = datetime.fromisoformat(str(item.get("time")))
        except (TypeError, ValueError):
            continue
        power = _num(item.get("power_w"))
        if stamp.tzinfo is None or power is None or stamp < now:
            continue
        points.append((stamp, max(0.0, power)))
    points.sort()
    if len(points) < 2:
        return None, False
    wh = 0.0
    used = False
    for (ta, pa), (tb, pb) in zip(points, points[1:]):
        if ta >= target:
            break
        end = min(tb, target)
        if end <= ta:
            continue
        fraction = (end - ta).total_seconds() / (tb - ta).total_seconds()
        pend = pa + (pb - pa) * fraction
        wh += (pa + pend) / 2 * (end - ta).total_seconds() / 3600
        used = True
        if end >= target:
            break
    return (round(wh / 1000, 3) if used else None, points[-1][0] >= target)


def energy_plan(*, now: datetime, target: datetime, pv_w: float | None, load_w: float | None,
                grid_w: float | None, battery_soc: float | None, battery_capacity_kwh: float | None,
                target_soc: float | None, reserve_soc: float | None, forecast_curve: list[dict] | None,
                base_load_w: float | None, grid_limit_w: float | None,
                inverter_limit_w: float | None, phase_w: list[float] | None = None,
                phase_limit_w: float | None = None) -> dict:
    """Return a read-only energy strategy with deterministic guardrails."""
    pv = max(0.0, _num(pv_w) or 0.0)
    load = max(0.0, _num(load_w) or 0.0)
    grid = _num(grid_w)
    soc = _num(battery_soc)
    capacity = _num(battery_capacity_kwh)
    target_soc = _num(target_soc)
    reserve_soc = _num(reserve_soc)
    base = max(0.0, _num(base_load_w) or 0.0)

    import_w = max(0.0, grid or 0.0)
    surplus_w = max(0.0, pv - load)
    hours = max(0.0, (target - now).total_seconds() / 3600)
    forecast_kwh, forecast_complete = integrate_forecast_kwh(forecast_curve or [], now, target)

    needed_kwh = None
    if soc is not None and capacity is not None and target_soc is not None:
        needed_kwh = max(0.0, target_soc - soc) / 100 * capacity
    base_kwh = base * hours / 1000
    margin_kwh = None
    if forecast_complete and forecast_kwh is not None and needed_kwh is not None:
        margin_kwh = round(forecast_kwh - needed_kwh - base_kwh, 3)

    grid_headroom = None
    if grid_limit_w is not None:
        grid_headroom = max(0.0, float(grid_limit_w) - import_w)
    inverter_headroom = None
    if inverter_limit_w is not None:
        inverter_headroom = max(0.0, float(inverter_limit_w) - load)
    valid_phases = [max(0.0, float(x)) for x in (phase_w or []) if _num(x) is not None]
    min_phase_headroom = None
    if valid_phases and phase_limit_w is not None:
        min_phase_headroom = min(max(0.0, float(phase_limit_w) - p) for p in valid_phases)

    protection = (
        grid_headroom is not None and grid_headroom < 500
        or inverter_headroom is not None and inverter_headroom < 750
        or min_phase_headroom is not None and min_phase_headroom < 300
    )

    reserve_breached = (
        soc is not None and reserve_soc is not None and soc <= reserve_soc
    )
    target_tight = margin_kwh is not None and margin_kwh < 1.0
    flexible_budget_kwh = max(0.0, (margin_kwh or 0.0) - 0.75) if margin_kwh is not None else None

    if protection:
        strategy = "protect_electrical_limits"
    elif reserve_breached:
        strategy = "preserve_battery"
    elif target_tight and needed_kwh and needed_kwh > 0:
        strategy = "battery_first"
    elif surplus_w >= 500 and (flexible_budget_kwh is None or flexible_budget_kwh > 0):
        strategy = "use_flexible_surplus"
    else:
        strategy = "balanced"

    return {
        "strategy": strategy,
        "pv_w": round(pv, 1),
        "load_w": round(load, 1),
        "grid_import_w": round(import_w, 1),
        "instant_surplus_w": round(surplus_w, 1),
        "battery_soc": soc,
        "battery_energy_needed_kwh": round(needed_kwh, 3) if needed_kwh is not None else None,
        "forecast_to_target_kwh": forecast_kwh,
        "forecast_complete": forecast_complete,
        "base_load_to_target_kwh": round(base_kwh, 3),
        "forecast_margin_kwh": margin_kwh,
        "flexible_budget_kwh": round(flexible_budget_kwh, 3) if flexible_budget_kwh is not None else None,
        "grid_headroom_w": round(grid_headroom, 1) if grid_headroom is not None else None,
        "inverter_headroom_w": round(inverter_headroom, 1) if inverter_headroom is not None else None,
        "min_phase_headroom_w": round(min_phase_headroom, 1) if min_phase_headroom is not None else None,
        "reserve_breached": reserve_breached,
        "protection_required": bool(protection),
        "shadow_mode": True,
    }


def rank_flexible_loads(loads: list[dict], plan: dict) -> list[dict]:
    """Rank flexible loads for a shadow recommendation, never execution."""
    ranked = []
    budget = plan.get("flexible_budget_kwh")
    for item in loads:
        power_kw = max(0.0, (_num(item.get("power_w")) or 0.0) / 1000)
        duration_h = max(0.0, (_num(item.get("duration_minutes")) or 60) / 60)
        energy = power_kw * duration_h
        priority = _num(item.get("priority")) or 50
        allowed = (
            not plan.get("protection_required")
            and not plan.get("reserve_breached")
            and (budget is None or energy <= budget)
        )
        ranked.append({
            **item,
            "estimated_energy_kwh": round(energy, 3),
            "shadow_allowed": allowed,
            "score": round((101 - priority) * 10 - energy * 5, 3),
        })
    return sorted(ranked, key=lambda x: x["score"], reverse=True)
