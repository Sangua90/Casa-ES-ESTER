"""User-downloadable audit: stored evidence is distinct from operational readiness."""
from copy import deepcopy
from collections import Counter


def knowledge_audit(memory, current):
    """Account for every active note, without claiming context is executable."""
    applied = {}
    for decision in current.get("latest_decisions", []):
        for ref in decision.get("evidence", {}).get("knowledge_context", []):
            kid = ref.get("knowledge_id")
            if applied.get(kid) != "constraint_applied":
                applied[kid] = ref.get("application", "context_only")
    for row in current.get("knowledge_application", []):
        if row.get("status") == "applied":
            applied[row.get("knowledge_id")] = "mapping_applied"
    result = []
    for note in memory.get("knowledge", []):
        if note.get("status", "active") != "active":
            continue
        application = applied.get(note.get("knowledge_id"), "stored_not_used_in_current_evaluation")
        pending = note.get("kind") in {"rule", "constraint", "goal", "exception", "preference"} and application not in {"constraint_applied", "mapping_applied"}
        result.append({"knowledge_id": note.get("knowledge_id"), "domain": note.get("domain") or note.get("category"),
                       "area_id": note.get("area_id"), "scope": note.get("scope"), "application": application,
                       "operational_verification_pending": pending,
                       "statement": note.get("statement") or note.get("text"),
                       "explanation": "Da verificare nelle proposte: il salvataggio non dimostra che questa regola sia applicata." if pending else "Informazione conservata; consulta application per sapere come è stata usata."})
    return result


def learning_report(memory, current, version, now, provider="disabled"):
    stored = deepcopy(memory)
    # Checkpoints repeat the full memory; retain their identity, not nested copies.
    stored["memory_versions"] = [{k: v for k, v in item.items() if k != "memory"}
                                 for item in stored.get("memory_versions", [])]
    active = [k for k in stored.get("knowledge", []) if k.get("status", "active") == "active"]
    latest = current.get("latest_decisions", [])
    audit = knowledge_audit(memory, current)
    return {"format": "ester-learning-report-v1", "integration_version": version,
            "exported_at": now.isoformat(), "evaluated_at": current.get("evaluated_at"),
            "shadow_mode": True, "real_actuation_enabled": False,
            "ai": {"provider": provider, "configuration_credentials_included": False},
            "assessment": {
                "operational_readiness": "not_enabled_permanent_shadow_mode",
                "knowledge_count": len(active),
                "knowledge_by_domain": dict(Counter(k.get("domain") or k.get("category") or "other" for k in active)),
                "structured_preferences": len(stored.get("preferences", {})),
                "knowledge_mapping": current.get("knowledge_application", []),
                "knowledge_audit": audit,
                "decisions_with_knowledge": sum(bool(d.get("evidence", {}).get("knowledge_context")) for d in latest),
                "decisions_blocked_by_knowledge": sum(bool(d.get("evidence", {}).get("knowledge_blockers")) for d in latest),
                "limitations": ["Memoria salvata non equivale a regole implementate.",
                                "Vincoli ACS dinamica e gruppi multisplit sono blocchi di verifica, non ottimizzatori completi.",
                                "context_only indica un riferimento mostrato, non un vincolo applicato.",
                                "Gli outcome Shadow non provano il risultato di un'azione realmente eseguita.",
                                "Questo rapporto non abilita il controllo dei dispositivi."]},
            "memory_and_learning": stored, "current_evaluation": deepcopy(current)}
