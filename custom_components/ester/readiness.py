"""Migration readiness for legacy automations; advisory only."""
from __future__ import annotations


def migration_readiness(inventory: dict, decisions: list[dict], calibration: dict) -> dict:
    categories = set((inventory.get("by_category") or {}).keys())
    categories.update(d.get("category") for d in decisions if d.get("category"))
    result = {}
    for category in sorted(c for c in categories if c):
        legacy = int((inventory.get("by_category") or {}).get(category, 0))
        category_decisions = [d for d in decisions if d.get("category") == category]
        open_questions = sum(d.get("status") == "needs_input" for d in category_decisions[-100:])
        samples = len(category_decisions[-100:])
        empirical = (calibration.get(category) or {}).get("empirical_score")
        if samples < 10:
            status = "observe"
        elif open_questions > max(2, samples // 5):
            status = "needs_data"
        elif empirical is not None and empirical < 0.8:
            status = "needs_validation"
        elif empirical is not None and empirical >= 0.9 and samples >= 20:
            status = "candidate_for_manual_migration"
        else:
            status = "validate"
        result[category] = {
            "legacy_automations": legacy,
            "shadow_decisions_checked": samples,
            "open_questions": open_questions,
            "empirical_feedback_score": empirical,
            "status": status,
            "automatic_disable_allowed": False,
        }
    return result
