"""Durable case memory: human validation and predicted confidence stay distinct."""
from copy import deepcopy
from math import isfinite


def remember(data, decision, now):
    rating = (decision.get("feedback") or {}).get("rating")
    if decision.get("category") in {"model", "operational_safety"}:
        return
    if not rating and decision.get("confidence", 0) < .85:
        return
    if (decision.get("evidence") or {}).get("question") or decision.get("status") == "suppressed":
        return
    rows = data.setdefault("brain_experiences", [])
    existing = next((r for r in rows if r["decision_id"] == decision["decision_id"]), None)
    if existing is None and len(rows) >= 2000:
        # Preserve validated experience; discard only an unvalidated candidate to make room.
        candidate = next((r for r in rows if not r.get("rating")), None)
        if candidate is None:
            return
        rows.remove(candidate)
    row = {k: deepcopy(decision.get(k)) for k in ("decision_id", "category", "area_id", "title", "entity_ids", "proposed_action", "reasoning", "confidence", "created_at")}
    evidence = decision.get("evidence") or {}
    row.update(observations=deepcopy(evidence.get("observations", {})), modes=evidence.get("modes", []),
               target_c=evidence.get("target_c"), comfort_season=evidence.get("comfort_season"),
               rating=rating, validation="human_feedback" if rating else "unverified_prediction",
               updated_at=now.isoformat(), causal_success_measured=False)
    if existing is not None:
        existing.clear(); existing.update(row)
    else:
        rows.append(row)


def similar_cases(data, decision, limit=3):
    evidence = decision.evidence
    result = []
    for row in data.get("brain_experiences", []):
        if (not row.get("rating") or row.get("category") != decision.category or row.get("area_id") != decision.area_id
                or row.get("title") != decision.title or set(row.get("entity_ids") or []) != set(decision.entity_ids)
                or set(row.get("modes") or []) != set(evidence.get("modes") or [])
                or row.get("target_c") != evidence.get("target_c")
                or row.get("comfort_season") != evidence.get("comfort_season")):
            continue
        observations, previous = evidence.get("observations", {}), row.get("observations", {})
        if not observations or set(observations) != set(previous):
            continue
        matched = True
        for entity, obs in observations.items():
            old = previous[entity]
            a, b = obs.get("value"), old.get("value")
            if obs.get("unit") != old.get("unit"):
                matched = False; break
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if not isfinite(a) or not isfinite(b) or abs(a-b) > max(1, abs(b)*.1):
                    matched = False; break
            elif obs.get("state") != old.get("state"):
                matched = False; break
        if matched:
            result.append({k: row.get(k) for k in ("decision_id", "proposed_action", "rating", "validation", "updated_at")})
    return sorted(result, key=lambda r: r.get("updated_at", ""), reverse=True)[:limit]
