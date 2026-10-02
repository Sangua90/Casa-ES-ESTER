"""Expected home-use profiles: persistent routines plus near-term lookup."""
from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil


def _minutes(value: str) -> int | None:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except (AttributeError, TypeError, ValueError):
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour * 60 + minute


def validate_profile(profile: dict) -> bool:
    weekdays = profile.get("weekdays")
    occupancy = profile.get("expected_occupancy")
    return (
        isinstance(profile.get("area_id"), str)
        and bool(profile["area_id"])
        and isinstance(weekdays, list)
        and bool(weekdays)
        and all(isinstance(day, int) and 0 <= day <= 6 for day in weekdays)
        and _minutes(profile.get("start_time")) is not None
        and _minutes(profile.get("end_time")) is not None
        and isinstance(occupancy, (int, float))
        and 0 <= occupancy <= 1
    )


def _contains(profile: dict, local: datetime) -> bool:
    start = _minutes(profile["start_time"])
    end = _minutes(profile["end_time"])
    minute = local.hour * 60 + local.minute
    weekday = local.weekday()
    if start == end:
        return weekday in profile["weekdays"]
    if start < end:
        return weekday in profile["weekdays"] and start <= minute < end
    # Overnight: Monday 22:00-02:00 also covers Tuesday 00:00-02:00.
    if minute >= start:
        return weekday in profile["weekdays"]
    return minute < end and (weekday - 1) % 7 in profile["weekdays"]


def usage_snapshot(profiles: list[dict], now: datetime, tz, horizon_minutes: int = 120) -> dict:
    """Return current and upcoming expected use grouped by area.

    This is declared intent/routine, not detected occupancy.
    """
    local_now = now.astimezone(tz)
    result: dict[str, dict] = {}
    valid = [p for p in profiles if validate_profile(p)]
    for profile in valid:
        area = profile["area_id"]
        bucket = result.setdefault(area, {"current": [], "upcoming": [], "expected_occupancy": 0.0})
        if _contains(profile, local_now):
            bucket["current"].append(profile)
            bucket["expected_occupancy"] = max(bucket["expected_occupancy"], float(profile["expected_occupancy"]))
            continue
        # Find scheduled boundaries directly, rather than scanning every future minute.
        start = _minutes(profile["start_time"])
        if start == _minutes(profile["end_time"]):
            start = 0  # The existing equal-time convention means a whole calendar day.
        for days_ahead in range(horizon_minutes//1440+2):
            date = local_now+timedelta(days=days_ahead)
            candidate = date.replace(hour=start//60, minute=start%60, second=0, microsecond=0)
            offset = ceil((candidate-local_now).total_seconds()/60)
            if candidate.weekday() in profile["weekdays"] and 0 < offset <= horizon_minutes:
                bucket["upcoming"].append({
                    "profile_id": profile["profile_id"],
                    "label": profile.get("label", ""),
                    "minutes_until": offset,
                    "expected_occupancy": float(profile["expected_occupancy"]),
                    "comfort_c": profile.get("comfort_c"),
                })
                break
        bucket["upcoming"].sort(key=lambda item: item["minutes_until"])
    return result
