"""Conservative anomaly detection from learned observations."""
from __future__ import annotations


def detect_anomalies(profiles: list, learning: dict, now_ts: float) -> list[dict]:
    anomalies = []
    for p in profiles:
        model = learning.get(p.entity_id, {})
        reported = p.attributes.get("last_reported")
        if p.state in {"unknown", "unavailable", None}:
            anomalies.append({
                "entity_id": p.entity_id, "kind": "unavailable", "severity": "medium",
                "message": "Entità non disponibile.",
            })
            continue
        samples = model.get("samples", 0)
        slope = model.get("slope_per_hour")
        if samples >= 20 and slope == 0 and p.role in {"temperature", "humidity", "solar_power", "load_power"}:
            anomalies.append({
                "entity_id": p.entity_id, "kind": "possibly_frozen", "severity": "low",
                "message": "Valore invariato a lungo; verificare che il sensore stia aggiornando.",
            })
        value_range = model.get("range")
        if value_range is not None and value_range > 50 and p.role == "temperature":
            anomalies.append({
                "entity_id": p.entity_id, "kind": "implausible_variation", "severity": "high",
                "message": "Variazione termica anomala nello storico recente.",
            })
    return anomalies[:100]
