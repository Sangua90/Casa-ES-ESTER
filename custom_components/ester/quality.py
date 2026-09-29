"""Evidence-based suggestions for missing data, before suggesting hardware."""
from .home import numeric_value


def data_suggestions(profiles):
    suggestions = []
    by_area = {}
    for p in profiles:
        if p.area_id:
            by_area.setdefault(p.area_id, []).append(p)
    requirements = [
        ({"climate"}, "temperature", "temperatura ambiente", "sensore di temperatura ambiente",
         "Confrontare il comfort desiderato con la temperatura reale e imparare il trend termico.", "high"),
        ({"climate", "ventilation"}, "humidity", "umidità relativa", "sensore di umidità, anche combinato con temperatura",
         "Distinguere un bisogno di deumidificazione dal solo bisogno di riscaldamento o raffrescamento.", "medium"),
        ({"climate", "lighting"}, "presence", "presenza nella stanza", "sensore di presenza o movimento",
         "Contestualizzare comfort e luci; un sensore di movimento può non rilevare persone ferme.", "medium"),
        ({"irrigation"}, "soil_moisture", "umidità del terreno", "sensore di umidità del terreno calibrabile",
         "Valutare se il terreno richiede acqua senza dedurlo dallo stato della valvola.", "high"),
    ]
    for area, local in sorted(by_area.items()):
        roles = {p.role for p in local}
        name = local[0].attributes.get("area_name") or area
        for triggers, missing, label, hardware, benefit, priority in requirements:
            if not roles & triggers:
                continue
            existing = [p for p in local if p.role == missing]
            usable = [p for p in existing if p.state not in {"unknown", "unavailable", None}
                      and (missing == "presence" or numeric_value(p) is not None)]
            if usable:
                continue
            candidates = [p.entity_id for p in profiles if p.role == missing and not p.area_id]
            action = ("Verifica disponibilità, unità e configurazione del sensore già presente." if existing else
                      "Controlla le entità esistenti senza area prima di aggiungere hardware." if candidates else
                      f"Verifica prima eventuali entità non riconosciute; se il dato non esiste, valuta un {hardware} compatibile con Home Assistant.")
            suggestions.append({"key": f"{area}:{missing}", "area_id": area, "area_name": name,
                "missing_role": missing, "missing_data": label, "priority": priority,
                "title": f"{name}: manca un dato affidabile di {label}", "benefit": benefit,
                "suggested_device": None if existing or candidates else hardware,
                "next_step": action, "existing_entities": [p.entity_id for p in existing],
                "unassigned_candidates": candidates, "source": "local_data_audit"})
    return sorted(suggestions, key=lambda s: (s["priority"] != "high", s["key"]))[:30]
