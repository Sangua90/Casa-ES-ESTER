"""Read-only inventory of legacy Home Assistant automations for migration planning."""
from __future__ import annotations


def classify_automation(name: str) -> str:
    text = (name or "").lower()
    groups = [
        ("energy", ("fv", "fotovolta", "batter", "boiler", "spa", "inverter", "potenza", "energy", "surplus")),
        ("security", ("allarme", "antifurto", "alarm", "sirena", "porta", "portone", "garage")),
        ("lighting", ("luce", "luci", "light", "lamp")),
        ("climate", ("clima", "climat", "pompa di calore", "termost", "riscald", "raffresc")),
        ("ventilation", ("ventola", "ventil", "cappa", "voc", "pm2", "umid")),
        ("presence", ("presenza", "geofenc", "rientro", "uscita", "ospiti")),
        ("irrigation", ("irrig", "giardino", "sprinkler")),
    ]
    for category, words in groups:
        if any(word in text for word in words):
            return category
    return "other"


def legacy_automation_inventory(profiles: list) -> dict:
    items = []
    counts = {}
    for p in profiles:
        if p.domain != "automation":
            continue
        category = classify_automation(p.name)
        counts[category] = counts.get(category, 0) + 1
        items.append({
            "entity_id": p.entity_id,
            "name": p.name,
            "enabled": p.state == "on",
            "category": category,
            "last_triggered": p.attributes.get("last_triggered"),
            "migration_status": "legacy_active" if p.state == "on" else "legacy_disabled",
        })
    return {
        "count": len(items),
        "by_category": counts,
        "items": sorted(items, key=lambda x: (x["category"], x["name"].lower()))[:200],
        "note": "Read-only inventory: E.S.T.E.R. does not disable automations in Shadow Mode.",
    }
