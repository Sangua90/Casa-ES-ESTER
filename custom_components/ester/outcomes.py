"""Outcome learning for simulated decisions."""
from __future__ import annotations

from datetime import datetime, timedelta


def evaluate_shadow_outcomes(decisions: list[dict], current_states: dict, now: datetime) -> list[dict]:
    """Score old shadow decisions when their observed metric can be checked."""
    updated = []
    for decision in decisions:
        outcome = decision.get("outcome") or {}
        if outcome.get("type") not in {"not_executed", "observed_only"}:
            continue
        created_raw = decision.get("created_at")
        try:
            created = datetime.fromisoformat(created_raw)
        except (TypeError, ValueError):
            continue
        if now - created < timedelta(minutes=30):
            continue
        evidence = decision.get("evidence") or {}
        observations = evidence.get("observations") or {}
        before = []
        after = []
        for entity_id, obs in observations.items():
            value = obs.get("value")
            current = current_states.get(entity_id)
            if isinstance(value, (int, float)) and isinstance(current, (int, float)):
                before.append(float(value))
                after.append(float(current))
        if not before:
            continue
        delta = sum(after) / len(after) - sum(before) / len(before)
        prediction_error_c = None
        strategies = evidence.get("strategies") or []
        temp_ids = evidence.get("temperature_entity_ids") or []
        wait = next((s for s in strategies if s.get("strategy") == "wait"), None)
        actual_temps = [
            float(current_states[i]) for i in temp_ids
            if isinstance(current_states.get(i), (int, float))
        ]
        if wait and wait.get("predicted_temp_at_use") is not None and actual_temps:
            actual = sum(actual_temps) / len(actual_temps)
            prediction_error_c = round(actual - float(wait["predicted_temp_at_use"]), 2)
        decision["outcome"] = {
            "type": "shadow_observation",
            "observed_at": now.isoformat(),
            "delta": round(delta, 3),
            "prediction_error_c": prediction_error_c,
            "causal_effect": "not_measurable_in_shadow_mode",
        }
        updated.append(decision)
    return updated


def calibration(feedback: list[dict]) -> dict:
    """Simple empirical quality by category from explicit user feedback."""
    buckets = {}
    for item in feedback[-500:]:
        category = item.get("category")
        rating = item.get("rating")
        if not category or rating not in {"correct", "wrong", "partial"}:
            continue
        b = buckets.setdefault(category, {"correct": 0, "wrong": 0, "partial": 0})
        b[rating] += 1
    result = {}
    for category, values in buckets.items():
        total = sum(values.values())
        score = (values["correct"] + 0.5 * values["partial"]) / total if total else None
        result[category] = {**values, "samples": total, "empirical_score": round(score, 3)}
    return result


def calibrated_confidence(decision: dict, calibration_data: dict) -> dict:
    """Calibrate confidence using category feedback without aggressive promotion."""
    raw = max(0.0, min(1.0, float(decision.get("confidence", 0) or 0)))
    category = decision.get("category")
    empirical = calibration_data.get(category) or {}
    samples = int(empirical.get("samples", 0) or 0)
    score = empirical.get("empirical_score")
    if samples < 5 or score is None:
        return {"raw": raw, "calibrated": raw, "samples": samples, "empirical_score": score}
    blended = 0.75 * raw + 0.25 * float(score)
    if samples < 20:
        blended = min(raw, blended)
    calibrated = round(max(0.0, min(1.0, blended)), 3)
    return {
        "raw": round(raw, 3),
        "calibrated": calibrated,
        "samples": samples,
        "empirical_score": float(score),
    }
