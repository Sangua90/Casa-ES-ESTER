"""Automatic seasonal operating context."""
from __future__ import annotations


def season_context(now, outside_c: float | None, preferences: dict) -> dict:
    """Return a soft seasonal context; explicit user context always overrides it."""
    month = now.month
    if outside_c is not None:
        if outside_c <= float(preferences.get("season_winter_below_c", 12)):
            season = "winter"
        elif outside_c >= float(preferences.get("season_summer_above_c", 24)):
            season = "summer"
        else:
            season = "shoulder"
        source = "outside_temperature"
    else:
        season = "winter" if month in {11,12,1,2,3} else "summer" if month in {6,7,8,9} else "shoulder"
        source = "calendar"
    return {
        "season": season,
        "source": source,
        "outside_c": outside_c,
        "heating_expected": season in {"winter", "shoulder"},
        "cooling_expected": season in {"summer", "shoulder"},
    }
