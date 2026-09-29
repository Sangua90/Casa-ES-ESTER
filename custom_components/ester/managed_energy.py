"""Shadow-only managed energy load planning.

This module models the operational constraints that previously lived in a
standalone energy manager. It never calls Home Assistant services.
"""
from __future__ import annotations

from datetime import datetime


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _minutes_since(iso_value: str | None, now: datetime) -> float | None:
    if not iso_value:
        return None
    try:
        stamp = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return max(0.0, (now - stamp.astimezone(now.tzinfo)).total_seconds() / 60)


def _inside_window(now: datetime, start: str | None, end: str | None) -> bool:
    if not start or not end:
        return True
    try:
        sh, sm = (int(x) for x in start.split(":", 1))
        eh, em = (int(x) for x in end.split(":", 1))
    except (ValueError, AttributeError):
        return False
    minute = now.hour * 60 + now.minute
    a, b = sh * 60 + sm, eh * 60 + em
    return a <= minute < b if a < b else (minute >= a or minute < b)


def update_runtime(loads: list[dict], profiles: list, runtime: dict, now: datetime) -> None:
    """Observe actual states and track starts/transition times without acting."""
    by_id = {p.entity_id: p for p in profiles}
    today = now.date().isoformat()
    for load in loads:
        load_id = load.get("load_id")
        entity_id = load.get("entity_id")
        if not load_id or entity_id not in by_id:
            continue
        current = by_id[entity_id].state
        item = runtime.setdefault(load_id, {})
        if item.get("date") != today:
            item.update({"date": today, "starts_today": 0})
        previous = item.get("state")
        if previous is not None and previous != current:
            item["last_transition"] = now.isoformat()
            if current == "on" or current not in {"off", "unknown", "unavailable"} and previous == "off":
                item["starts_today"] = int(item.get("starts_today", 0)) + 1
        item["state"] = current
        item["last_seen"] = now.isoformat()


def plan_managed_loads(
    *,
    loads: list[dict],
    profiles: list,
    runtime: dict,
    energy_plan: dict,
    now: datetime,
) -> list[dict]:
    """Return ordered start/hold/stop Shadow recommendations."""
    by_id = {p.entity_id: p for p in profiles}
    recommendations = []
    flexible_budget = energy_plan.get("flexible_budget_kwh")
    available_power = min(
        [
            x for x in (
                energy_plan.get("grid_headroom_w"),
                energy_plan.get("inverter_headroom_w"),
            ) if x is not None
        ] or [float("inf")]
    )

    for load in loads:
        entity_id = load.get("entity_id")
        p = by_id.get(entity_id)
        state = p.state if p else "unavailable"
        is_on = state not in {"off", "unknown", "unavailable", None}
        power_w = max(0.0, _num(load.get("power_w"), 0.0))
        duration_min = max(1.0, _num(load.get("duration_minutes"), 60.0))
        need_kwh = power_w / 1000 * duration_min / 60
        priority = int(_num(load.get("priority"), 50))
        min_soc = _num(load.get("min_soc"), 0)
        soc = energy_plan.get("battery_soc")
        rt = runtime.get(load.get("load_id"), {})
        since_transition = _minutes_since(rt.get("last_transition") or (p.attributes.get("last_changed") if p else None), now)
        min_on = _num(load.get("min_on_minutes"), 0)
        min_off = _num(load.get("min_off_minutes"), 0)
        max_starts = int(_num(load.get("max_starts_per_day"), 99))
        starts_today = int(rt.get("starts_today", 0))
        in_window = _inside_window(now, load.get("window_start"), load.get("window_end"))

        reasons = []
        can_start = True
        if p is None or state in {"unknown", "unavailable"}:
            can_start = False; reasons.append("entità non disponibile")
        if not in_window:
            can_start = False; reasons.append("fuori finestra oraria")
        if soc is not None and soc < min_soc:
            can_start = False; reasons.append("SOC sotto minimo")
        if energy_plan.get("reserve_breached"):
            can_start = False; reasons.append("riserva batteria da preservare")
        if energy_plan.get("protection_required"):
            can_start = False; reasons.append("protezione elettrica prioritaria")
        if not is_on and since_transition is not None and since_transition < min_off:
            can_start = False; reasons.append("tempo minimo OFF non completato")
        if starts_today >= max_starts:
            can_start = False; reasons.append("numero massimo avvii raggiunto")
        if power_w > available_power:
            can_start = False; reasons.append("headroom elettrico insufficiente")
        if flexible_budget is not None and need_kwh > flexible_budget:
            can_start = False; reasons.append("budget energetico insufficiente")

        interruptible = bool(load.get("interruptible", True))
        can_stop = is_on and interruptible
        if is_on and since_transition is not None and since_transition < min_on:
            can_stop = False
        if bool(load.get("non_interruptible", False)):
            can_stop = False

        if is_on:
            if energy_plan.get("protection_required") and can_stop:
                action = "would_stop_for_protection"
                score = 10000 - priority
                reason = "Protezione elettrica prioritaria; carico interrompibile."
            elif energy_plan.get("reserve_breached") and can_stop:
                action = "would_stop_to_preserve_battery"
                score = 8000 - priority
                reason = "SOC alla riserva; carico interrompibile."
            else:
                action = "hold_on"
                score = 0
                reason = "Carico già attivo; nessun motivo sicuro per interromperlo."
        else:
            if can_start and energy_plan.get("strategy") == "use_flexible_surplus":
                action = "would_start"
                score = (101 - priority) * 100 - need_kwh * 10
                reason = "Vincoli rispettati e surplus/budget disponibile."
            else:
                action = "hold_off"
                score = -priority
                reason = "; ".join(reasons) if reasons else "Nessuna opportunità energetica sufficiente."

        recommendations.append({
            **load,
            "observed_state": state,
            "estimated_energy_kwh": round(need_kwh, 3),
            "starts_today": starts_today,
            "minutes_since_transition": round(since_transition, 1) if since_transition is not None else None,
            "inside_window": in_window,
            "shadow_action": action,
            "shadow_reason": reason,
            "can_start": can_start,
            "can_stop": can_stop,
            "score": round(score, 3),
        })

    order = {
        "would_stop_for_protection": 0,
        "would_stop_to_preserve_battery": 1,
        "would_start": 2,
        "hold_on": 3,
        "hold_off": 4,
    }
    return sorted(recommendations, key=lambda x: (order.get(x["shadow_action"], 9), -x["score"]))
