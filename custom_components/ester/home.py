"""Pure, bounded home model and descriptive learning; no device access."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from statistics import mean

ROLES = {"generic", "temperature", "humidity", "climate", "hot_water",
         "lighting", "presence", "ventilation", "irrigation", "soil_moisture",
         "security", "energy", "solar_power", "load_power", "battery", "rain"}
MODES = {"normal", "vacation", "guests", "illness", "work_from_home"}


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
        return dt.timestamp() if isinstance(dt, datetime) and dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def active_contexts(events, now):
    current = now.timestamp()
    return [e for e in events if (start := timestamp(e.get("starts_at"))) is not None
            and start <= current and (e.get("ends_at") is None or
            ((end := timestamp(e["ends_at"])) is not None and current < end))]


def infer_role(domain, device_class, unit, name):
    text = name.lower()
    domains = {"climate": "climate", "water_heater": "hot_water", "light": "lighting",
               "fan": "ventilation", "humidifier": "ventilation", "person": "presence",
               "device_tracker": "presence", "alarm_control_panel": "security",
               "lock": "security", "siren": "security"}
    if domain in domains:
        return domains[domain]
    if device_class in {"moisture", "smoke", "gas", "carbon_monoxide", "safety", "problem", "tamper", "door", "window", "opening"}:
        return "security"
    if device_class in {"occupancy", "motion", "presence"}:
        return "presence"
    if device_class == "battery":
        return "battery"
    if device_class == "precipitation_intensity":
        return "rain"
    if any(k in text for k in ("soil", "terreno")) and unit == "%":
        return "soil_moisture"
    if any(k in text for k in ("boiler", "acqua calda", "water heater", "acs")):
        return "hot_water"
    if domain in {"valve", "switch"} and any(k in text for k in ("irrig", "sprinkler")):
        return "irrigation"
    if device_class == "humidity":
        return "humidity"
    if device_class == "temperature" or unit in {"°C", "°F", "K"}:
        return "temperature"
    if device_class in {"power", "energy"} or unit in {"W", "kW", "Wh", "kWh"}:
        # PV/load bindings are deliberately explicit: names cannot identify a meter topology.
        return "energy"
    return "generic"


def numeric_value(profile):
    value = number(profile.state)
    if profile.domain in {"climate", "water_heater"}:
        value = number(profile.attributes.get("current_temperature"))
    if value is None:
        return None
    if profile.role in {"temperature", "hot_water", "climate"}:
        if profile.unit == "°F":
            return (value - 32) * 5 / 9
        if profile.unit == "K":
            return value - 273.15
        return value if profile.unit == "°C" else None
    if profile.role in {"solar_power", "load_power"}:
        return value * 1000 if profile.unit == "kW" else value if profile.unit == "W" else None
    if profile.role in {"humidity", "soil_moisture", "battery"}:
        return value if profile.unit == "%" and 0 <= value <= 100 else None
    return value


def learn(samples, now):
    """Regression over valid recent observations, never over unknown or NaN."""
    points = sorted({float(s["t"]): number(s.get("v")) for s in samples
                     if number(s.get("t")) is not None
                     and now.timestamp() - 86400 <= float(s["t"]) <= now.timestamp()}.items())
    valid = [(t, v) for t, v in points if v is not None]
    result = {"samples": len(valid), "coverage_hours": 0, "slope_per_hour": None}
    if not valid:
        return result
    result.update(mean=round(mean(v for _, v in valid), 3), minimum=min(v for _, v in valid),
                  maximum=max(v for _, v in valid), last=valid[-1][1])
    span = (valid[-1][0] - valid[0][0]) / 3600
    result["coverage_hours"] = round(span, 3)
    # Unknown values and gaps split episodes; trend uses only the latest contiguous episode.
    episode = []
    for t, v in points:
        if v is None or (episode and t - episode[-1][0] > 7200):
            episode = []
        if v is not None:
            episode.append((t, v))
    if len(episode) >= 3 and episode[-1][0] - episode[0][0] >= 1800:
        xs = [(t - episode[0][0]) / 3600 for t, _ in episode]
        ys = [v for _, v in episode]
        mx, my = mean(xs), mean(ys)
        denominator = sum((x - mx) ** 2 for x in xs)
        result["slope_per_hour"] = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator, 4)
    return result


def occupancy_learning(samples, now, tz):
    """Time-weighted local-hour usage; gaps above two hours remain unknown."""
    points = sorted({s["t"]: s.get("v") for s in samples if number(s.get("t")) is not None
                     and now.timestamp() - 86400 <= s["t"] <= now.timestamp()}.items())
    observed, occupied = [0.0] * 24, [0.0] * 24
    for (start, value), (end, _) in zip(points, points[1:]):
        if value not in (0, 1) or end - start > 7200:
            continue
        while start < end:
            stop = min(end, (int(start // 60) + 1) * 60)
            hour = datetime.fromtimestamp(start, timezone.utc).astimezone(tz).hour
            observed[hour] += stop - start
            occupied[hour] += (stop - start) * value
            start = stop
    return {"observed_minutes": round(sum(observed) / 60, 1),
            "hourly_occupancy": [round(o / t, 3) if t >= 900 else None for o, t in zip(occupied, observed)]}


def home_model(profiles, learning):
    rooms = {}
    for p in profiles:
        key = p.area_id or "unassigned"
        room = rooms.setdefault(key, {"name": p.attributes.get("area_name") or key, "entities": [], "roles": {}, "learning": {}})
        room["entities"].append(p.entity_id)
        room["roles"].setdefault(p.role, []).append(p.entity_id)
        if p.entity_id in learning:
            room["learning"][p.entity_id] = learning[p.entity_id]
    return rooms
