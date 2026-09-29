"""Shadow performance KPIs and confidence calibration."""
from __future__ import annotations
from statistics import mean


def shadow_kpis(decisions: list[dict], feedback: list[dict], questions: list[dict]) -> dict:
    recent = decisions[-500:]
    confidences = [float(d.get("confidence", 0) or 0) for d in recent]
    risk_counts = {}
    categories = {}
    outcome_counts = {}
    for d in recent:
        risk = d.get("risk", "unknown")
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
        category = d.get("category", "unknown")
        c = categories.setdefault(category, {"decisions": 0, "avg_confidence": [], "needs_input": 0})
        c["decisions"] += 1
        c["avg_confidence"].append(float(d.get("confidence", 0) or 0))
        c["needs_input"] += int(d.get("status") == "needs_input")
        outcome = (d.get("outcome") or {}).get("type", "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    ratings = {"correct": 0, "partial": 0, "wrong": 0}
    for f in feedback[-500:]:
        rating = f.get("rating")
        if rating in ratings:
            ratings[rating] += 1
    rated = sum(ratings.values())
    quality = ((ratings["correct"] + 0.5 * ratings["partial"]) / rated) if rated else None

    for c in categories.values():
        values = c["avg_confidence"]
        c["avg_confidence"] = round(mean(values), 3) if values else None

    open_questions = sum(q.get("status") == "open" for q in questions)
    return {
        "decisions": len(recent),
        "avg_confidence": round(mean(confidences), 3) if confidences else None,
        "risk_counts": risk_counts,
        "outcomes": outcome_counts,
        "feedback": {**ratings, "samples": rated, "quality_score": round(quality, 3) if quality is not None else None},
        "open_questions": open_questions,
        "categories": categories,
        "shadow_actuations": 0,
    }
