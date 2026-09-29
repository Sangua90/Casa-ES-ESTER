"""Persistent usage prediction from observed presence."""
from __future__ import annotations
from datetime import datetime


def occupancy_model(samples: list[dict], tz) -> dict:
    buckets = {}
    for s in samples:
        try:
            stamp = datetime.fromtimestamp(float(s["t"]), tz)
            occupied = 1 if bool(s["occupied"]) else 0
        except (KeyError, TypeError, ValueError, OSError):
            continue
        key = f"{stamp.weekday()}:{stamp.hour}"
        b = buckets.setdefault(key, {"n": 0, "occupied": 0})
        b["n"] += 1
        b["occupied"] += occupied
    probabilities = {
        k: round(v["occupied"]/v["n"], 3)
        for k,v in buckets.items() if v["n"] >= 6
    }
    return {"probabilities": probabilities, "samples": sum(v["n"] for v in buckets.values())}


def predicted_occupancy(model: dict, when: datetime) -> float | None:
    key = f"{when.weekday()}:{when.hour}"
    return (model.get("probabilities") or {}).get(key)
