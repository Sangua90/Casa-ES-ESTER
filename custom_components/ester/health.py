"""Pre-autonomy health and readiness checks."""
from __future__ import annotations

REQUIRED_FOR_AUTONOMY = {
    "energy": ("solar_power", "load_power", "battery"),
    "climate": ("temperature", "climate", "presence"),
    "security": ("security", "presence"),
    "hot_water": ("hot_water",),
    "ventilation": ("humidity", "ventilation"),
}


def autonomy_health(profiles: list, models: dict, kpis: dict, migration: dict) -> dict:
    roles = {p.role for p in profiles if p.state not in {"unknown", "unavailable", None}}
    domains = {}
    for domain, needed in REQUIRED_FOR_AUTONOMY.items():
        missing = [role for role in needed if role not in roles]
        model_ready = True
        if domain == "climate":
            model_ready = any((m.get("confidence") or 0) >= 0.6 for m in models.get("thermal", {}).values())
        elif domain == "ventilation":
            model_ready = any((m.get("confidence") or 0) >= 0.5 for m in models.get("ventilation", {}).values())
        elif domain == "hot_water":
            model_ready = any((m.get("confidence") or 0) >= 0.5 for m in models.get("hot_water", {}).values())
        migration_state = (migration.get(domain) or {}).get("status")
        domains[domain] = {
            "missing_roles": missing,
            "model_ready": model_ready,
            "migration_status": migration_state,
            "ready": not missing and model_ready and migration_state in {"validate", "candidate_for_manual_migration"},
        }
    feedback_quality = (kpis.get("feedback") or {}).get("quality_score")
    overall = all(v["ready"] for v in domains.values()) and feedback_quality is not None and feedback_quality >= 0.9
    return {
        "overall_ready_for_executor": overall,
        "shadow_mode_required": True,
        "feedback_quality": feedback_quality,
        "domains": domains,
        "blocking_reasons": [
            name for name, value in domains.items() if not value["ready"]
        ] + ([] if feedback_quality is not None and feedback_quality >= 0.9 else ["feedback_validation"]),
    }
