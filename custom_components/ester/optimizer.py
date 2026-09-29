"""Whole-home multi-objective scoring for Shadow decisions."""
from __future__ import annotations

DEFAULT_WEIGHTS = {
    "safety": 1.00,
    "comfort": 0.75,
    "cost": 0.60,
    "energy": 0.65,
    "equipment": 0.55,
    "confidence": 0.90,
}

CATEGORY_OBJECTIVES = {
    "operational_safety": {"safety": 1.0, "comfort": 0.1, "cost": 0.0, "energy": 0.0, "equipment": 0.4},
    "security": {"safety": 1.0, "comfort": 0.2, "cost": 0.0, "energy": 0.0, "equipment": 0.2},
    "climate": {"safety": 0.35, "comfort": 1.0, "cost": 0.6, "energy": 0.65, "equipment": 0.45},
    "hot_water": {"safety": 0.55, "comfort": 0.8, "cost": 0.55, "energy": 0.65, "equipment": 0.45},
    "ventilation": {"safety": 0.45, "comfort": 0.7, "cost": 0.25, "energy": 0.3, "equipment": 0.35},
    "energy": {"safety": 0.55, "comfort": 0.35, "cost": 0.9, "energy": 1.0, "equipment": 0.6},
    "lighting": {"safety": 0.25, "comfort": 0.55, "cost": 0.2, "energy": 0.3, "equipment": 0.2},
    "presence": {"safety": 0.5, "comfort": 0.5, "cost": 0.1, "energy": 0.1, "equipment": 0.1},
    "irrigation": {"safety": 0.2, "comfort": 0.1, "cost": 0.35, "energy": 0.25, "equipment": 0.2},
    "model": {"safety": 0.2, "comfort": 0.2, "cost": 0.1, "energy": 0.1, "equipment": 0.1},
}

RISK_PENALTY = {"low": 0.02, "medium": 0.10, "high": 0.25, "critical": 0.50}


def normalize_weights(preferences: dict) -> dict:
    weights = DEFAULT_WEIGHTS.copy()
    for key in weights:
        raw = preferences.get(f"objective_weight:{key}")
        if raw is None:
            continue
        try:
            weights[key] = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    return weights


def score_decision(decision: dict, preferences: dict) -> dict:
    """Score a proposed Shadow decision without changing the proposal."""
    weights = normalize_weights(preferences)
    category = decision.get("category", "model")
    profile = CATEGORY_OBJECTIVES.get(category, CATEGORY_OBJECTIVES["model"])
    confidence = max(0.0, min(1.0, float(decision.get("confidence", 0) or 0)))
    components = {
        "safety": profile["safety"] * weights["safety"],
        "comfort": profile["comfort"] * weights["comfort"],
        "cost": profile["cost"] * weights["cost"],
        "energy": profile["energy"] * weights["energy"],
        "equipment": profile["equipment"] * weights["equipment"],
        "confidence": confidence * weights["confidence"],
    }
    positive = sum(components.values()) / max(0.001, sum(weights.values()))
    penalty = RISK_PENALTY.get(decision.get("risk", "medium"), 0.10)
    if decision.get("status") == "needs_input":
        penalty += 0.15
    score = max(0.0, min(1.0, positive - penalty))
    return {
        "score": round(score, 3),
        "components": {k: round(v, 3) for k, v in components.items()},
        "risk_penalty": round(penalty, 3),
        "weights": weights,
        "objective": "whole_home",
    }


def rank_decisions(decisions: list[dict], preferences: dict) -> list[dict]:
    enriched = []
    for item in decisions:
        score = score_decision(item, preferences)
        copy = dict(item)
        evidence = dict(copy.get("evidence") or {})
        evidence["objective_score"] = score
        copy["evidence"] = evidence
        enriched.append(copy)
    return sorted(enriched, key=lambda x: x["evidence"]["objective_score"]["score"], reverse=True)
