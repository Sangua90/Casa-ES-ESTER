"""Evidence checklist; neither confidence nor elapsed time implies readiness."""
from .home import timestamp


def progress_status(memory, current, now):
    knowledge = [k for k in memory.get("knowledge", []) if k.get("status", "active") == "active"]
    profiles = [p for p in current.get("profiles", {}).values() if p.get("role") != "generic"]
    fresh = [p for p in profiles if p.get("state") not in {None, "unknown", "unavailable"}
             and timestamp(p.get("attributes", {}).get("last_reported")) is not None
             and 0 <= now.timestamp() - timestamp(p["attributes"]["last_reported"]) <= 7200]
    models = [v for key in ("thermal_models", "ventilation_models", "hot_water_models", "occupancy_models")
              for v in current.get(key, {}).values()]
    domains = [v for key, v in current.get("migration_readiness", {}).items()
               if key in {"climate", "lighting", "hot_water", "energy", "ventilation", "irrigation", "security"}]
    checks = [
        {"id": "memory", "label": "Memorie confermate presenti", "verified": bool(knowledge)},
        {"id": "inventory", "label": "Tutti i sensori classificati disponibili e aggiornati entro due ore", "verified": bool(profiles) and len(fresh) == len(profiles)},
        {"id": "history", "label": "Storico Recorder disponibile", "verified": current.get("history", {}).get("status") == "ready"},
        {"id": "models", "label": "Almeno un modello con confidence ≥ 60%", "verified": any((v.get("confidence") or 0) >= .6 for v in models)},
        {"id": "replay", "label": "Replay storico completato con decisioni", "verified": memory.get("last_replay", {}).get("status") == "ready" and memory.get("last_replay", {}).get("decisions", 0) > 0},
        {"id": "validation", "label": "Domini valutati candidati alla verifica manuale", "verified": bool(domains) and all(v.get("status") == "candidate_for_manual_migration" for v in domains)},
        {"id": "actuation", "label": "Controllo reale implementato, verificato e autorizzato", "verified": False},
    ]
    verified = sum(c["verified"] for c in checks)
    feedback = current.get("kpis", {}).get("feedback", {})
    return {"format": "ester-evidence-checklist-v1", "verified": verified, "total": len(checks),
            "verified_percent": round(100*verified/len(checks)), "checks": checks,
            "remaining": [c["label"] for c in checks if not c["verified"]],
            "operational": False, "real_efficiency_percent": None,
            "efficiency_reason": "Non misurabile in Shadow Mode: nessuna azione eseguita e nessun confronto reale con una baseline.",
            "feedback_quality_percent": round(100*feedback["quality_score"]) if feedback.get("quality_score") is not None else None,
            "feedback_samples": feedback.get("samples", 0),
            "note": "Percentuale di questa checklist, non percentuale di intelligenza o conto alla rovescia. Il controllo reale richiede uno sviluppo successivo; nessuna attivazione automatica al 100%."}
