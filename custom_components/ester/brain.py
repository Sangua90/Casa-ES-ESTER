"""Shared working memory for live, replay and scenario Shadow reasoning."""
from copy import deepcopy
from datetime import datetime
from math import isfinite
import re


def validate_effect(effect, area=""):
    if not isinstance(effect, dict) or set(effect) - {"type", "value", "season"}:
        raise ValueError("Effetto sulla memoria non valido.")
    kind = effect.get("type")
    value = effect.get("value")
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError("Indica un valore numerico finito.")
    if kind == "comfort":
        if not area or not 5 <= value <= 35 or effect.get("season", "all") not in {"all", "winter", "summer", "shoulder"}:
            raise ValueError("Comfort: stanza obbligatoria, stagione valida e temperatura tra 5 e 35 °C.")
    elif kind == "energy_price":
        if area or "season" in effect or not 0 <= value <= 10:
            raise ValueError("Prezzo energia: da 0 a 10 €/kWh, riferito alla casa.")
    else:
        raise ValueError("Sono supportati comfort e prezzo energia; nessun comando ai dispositivi.")
    return deepcopy(effect)


def validity(item, now):
    if item.get("status", "active") != "active":
        return item.get("status")
    try:
        for field, past in (("starts_at", False), ("expires_at", True)):
            if item.get(field):
                stamp = datetime.fromisoformat(item[field])
                if stamp.tzinfo is None:
                    return "invalid_validity"
                if past and now >= stamp:
                    return "expired"
                if not past and now < stamp:
                    return "scheduled"
    except (ValueError, TypeError):
        return "invalid_validity"
    return "active"


def has_active_sources(item, sources, now):
    """Every ancestor must remain valid; broken links and cycles are excluded."""
    visited = set()
    while item.get("derived_from"):
        parent_id = item["derived_from"]
        if parent_id in visited:
            return False
        visited.add(parent_id)
        item = sources.get(parent_id)
        if item is None or validity(item, now) != "active":
            return False
    return True


def working_memory(data, profiles, now, preferences=None, contexts=None):
    """Resolve confirmed sources at the evaluation time, preserving original records."""
    effective = deepcopy(data.get("preferences", {}) if preferences is None else preferences)
    active_contexts = deepcopy(contexts or [])
    records = []
    routines = deepcopy(data.get("usage_profiles", []))
    sources = {r.get("knowledge_id"):r for r in data.get("knowledge", [])+data.get("brain_notes", [])}
    candidates = {}
    areas = {p.area_id for p in profiles if p.area_id}
    for item in data.get("knowledge", []) + data.get("brain_notes", []):
        row = {**deepcopy(item), "memory_status": validity(item, now), "application": "context_only"}
        if not has_active_sources(row, sources, now):
            row["memory_status"] = "source_inactive"
        if row["memory_status"] != "active":
            row["application"] = "inactive"
        elif row.get("effect"):
            try:
                effect = validate_effect(row["effect"], row.get("area_id", ""))
                if effect["type"] == "comfort":
                    if row.get("area_id") not in areas:
                        raise ValueError("La stanza non è associata ai profili correnti.")
                    season = effect.get("season", "all")
                    key = f"comfort:{row['area_id']}" if season == "all" else f"seasonal_comfort:{season}:{row['area_id']}"
                else:
                    key = "energy_price_eur_kwh"
                row["preference_key"] = key
                candidates.setdefault(key, []).append(row)
            except ValueError as err:
                row.update(application="needs_review", review_reason=str(err))
        if row["memory_status"] == "active" and row.get("mode") and row["mode"] != "normal":
            active_contexts.append({"mode": row["mode"], "areas": [row["area_id"]] if row.get("area_id") else [],
                                    "label": row.get("statement", ""), "source": "brain_note"})
            row["context_applied"] = True
        if row["memory_status"] == "active" and row.get("routine"):
            from .teaching import validate_routine
            try:
                routine = validate_routine(row["routine"], row.get("area_id", ""))
                if row.get("area_id") not in areas:
                    raise ValueError("L'abitudine cita una stanza senza profili correnti.")
                routines.append({**routine, "area_id":row["area_id"], "profile_id":row["knowledge_id"],
                                 "label":row.get("statement", ""), "knowledge_id":row["knowledge_id"]})
                row["routine_applied"] = True
                if not row.get("effect"):
                    row["application"] = "routine_applied"
            except ValueError as err:
                row.update(application="needs_review", review_reason=str(err))
        records.append(row)
    conflicts, applied = [], []
    all_season_notes = {key.split(":")[-1] for key, rows in candidates.items()
                        if key.startswith("comfort:") and any(r.get("source") == "brain_note" for r in rows)}
    for key in list(effective):
        if key.startswith("seasonal_comfort:") and key.split(":")[-1] in all_season_notes:
            effective.pop(key)
    for key, value in effective.items():
        source = next((q for q in reversed(data.get("questions", [])) if q.get("status") == "answered"
                       and q.get("area_id") == key.split(":")[-1] and "comfort" in key
                       and "comfort" in (q.get("prompt", "") + q.get("title", "")).lower()
                       and (not key.startswith("seasonal_comfort:") or q.get("comfort_season") == key.split(":")[1])), None)
        applied.append({"key": key, "value": value, "source": "answer" if source else "preference",
                        "question_id": source.get("question_id") if source else None})
    for key, rows in candidates.items():
        notes = [r for r in rows if r.get("source") == "brain_note"]
        if key.startswith("seasonal_comfort:") and key.split(":")[-1] in all_season_notes and not notes:
            for row in rows:
                row["application"] = "temporary_note_priority"
            continue
        selected = notes or rows
        values = {r["effect"]["value"] for r in selected}
        if not notes and key in effective:
            for row in rows:
                row["application"] = "explicit_preference_priority"
            continue
        if len(values) > 1:
            # Conflicting temporary overrides must not silently fall back to a default target.
            effective.pop(key, None)
            applied = [r for r in applied if r["key"] != key]
            conflicts.append({"key": key, "values": sorted(values), "knowledge_ids": [r.get("knowledge_id") for r in selected]})
            for row in selected:
                row["application"] = "conflict"
        else:
            effective[key] = next(iter(values))
            applied = [r for r in applied if r["key"] != key]
            for row in selected:
                row["application"] = "preference_applied"
                applied.append({"key": key, "value": effective[key], "knowledge_id": row.get("knowledge_id"),
                                "source": row.get("source"), "source_file": row.get("source_file")})
            for row in rows:
                if row not in selected:
                    row["application"] = "temporary_note_priority"
    resolved = {r.get("derived_from") for r in records if r.get("derived_from") and r["memory_status"]=="active"
                and (r.get("routine_applied") or r["application"]=="preference_applied")}
    for row in records:
        row["clarifications_resolved"] = row.get("knowledge_id") in resolved
    return {"knowledge": [r for r in records if r["memory_status"] == "active"],
            "records": records, "preferences": effective, "contexts": active_contexts,
            "usage_profiles": routines,
            "conflicts": conflicts, "applied": applied,
            "counts": {"active": sum(r["memory_status"] == "active" for r in records), "total": len(records),
                       "expired": sum(r["memory_status"] == "expired" for r in records),
                       "conflicts": len(conflicts), "preferences": len(effective),
                       "operational": sum(r["memory_status"]=="active" and (r.get("routine_applied") or r["application"]=="preference_applied") for r in records),
                       "to_clarify": sum(r["memory_status"]=="active" and bool(r.get("clarifications")) and not r["clarifications_resolved"] for r in records),
                       "routines": len(routines),
                       "answered_questions": sum(q.get("status") == "answered" for q in data.get("questions", []))}}


def decision_memory(decisions, frame):
    """Attach provenance and block only decisions affected by conflicting preference keys."""
    for decision in decisions:
        def relevant(key):
            return (key == "energy_price_eur_kwh" and decision.category in {"energy", "climate"}
                    or key.startswith(("comfort:", "seasonal_comfort:")) and decision.category == "climate"
                    and key.split(":")[-1] == decision.area_id
                    and (not key.startswith("seasonal_comfort:") or not decision.evidence.get("comfort_season")
                         or key.split(":")[1] == decision.evidence["comfort_season"]))
        decision.evidence["brain_preferences"] = [r for r in frame["applied"] if relevant(r["key"])
            and ("comfort:" not in r["key"] or decision.evidence.get("target_c") == r["value"])]
        used = (decision.evidence.get("expected_use") or {})
        routine_ids = {r.get("profile_id") for r in used.get("current", [])+used.get("upcoming", [])}
        decision.evidence["brain_routines"] = [{"knowledge_id":r.get("knowledge_id"), "statement":r.get("statement"), "routine":r["routine"]}
            for r in frame["knowledge"] if r.get("routine_applied") and r.get("knowledge_id") in routine_ids]
        conflicts = [c for c in frame["conflicts"] if relevant(c["key"])]
        if conflicts:
            from .models import DecisionStatus
            decision.evidence["brain_conflicts"] = conflicts
            decision.evidence["question"] = "Ci sono valori confermati in conflitto nella memoria: " + "; ".join(f"{c['key']}: {c['values']}" for c in conflicts) + ". Quale informazione resta valida?"
            decision.proposed_action = "Chiarire le informazioni in conflitto prima di proporre un cambiamento"
            decision.reasoning = decision.evidence["question"]
            decision.status = DecisionStatus.NEEDS_INPUT
            decision.confidence = min(decision.confidence, .3)
    return decisions


def reconcile_questions(questions, frame, now):
    """Resolve only exact comfort questions answered by an effective preference."""
    for question in questions:
        prompt = question.get("prompt", "").lower()
        if question.get("category") != "climate" or "comfort" not in prompt or "conflitto" in prompt:
            continue
        area, season = question.get("area_id"), question.get("comfort_season")
        keys = [f"comfort:{area}"] + ([f"seasonal_comfort:{season}:{area}"] if season else [])
        known = any(key in frame["preferences"] for key in keys)
        if known and question.get("status") == "open":
            question.update(status="resolved_by_memory", updated_at=now.isoformat())
        elif not known and question.get("status") == "resolved_by_memory":
            question.update(status="open", updated_at=now.isoformat())
    return questions


def retrieval_context(data, message, now, budget=24000):
    """Rank the whole valid memory, bounding provider context without last-N truncation."""
    terms = set(re.findall(r"\w{3,}", message.casefold()))
    all_rows = data.get("knowledge", [])+data.get("brain_notes", [])
    sources = {r.get("knowledge_id"):r for r in all_rows}
    rows = [r for r in all_rows if validity(r, now) == "active" and has_active_sources(r, sources, now)]
    ranked = sorted(rows, key=lambda r: len(terms & set(re.findall(r"\w{3,}", r.get("statement", "").casefold()))), reverse=True)
    chosen, used = [], 0
    for row in ranked:
        statement = row.get("statement") or row.get("text") or ""
        if used + len(statement) > budget:
            continue
        chosen.append({**{k: row.get(k) for k in ("domain", "kind", "area_id", "effect", "routine", "starts_at", "expires_at")}, "statement": statement})
        used += len(statement)
    return {"existing_knowledge": chosen, "memory_available": len(rows), "memory_retrieved": len(chosen),
            "confirmed_preferences": data.get("preferences", {}), "confirmed_routines": data.get("usage_profiles", [])[:100]}
