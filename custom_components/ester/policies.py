"""Deterministic shadow proposals. No Home Assistant imports or execution path."""
from __future__ import annotations

from .home import number, numeric_value, timestamp
from .models import ImpactLevel, RiskLevel


def evaluate(engine, profiles, learning, contexts, preferences, feedback, now, usage=None):
    usage = usage or {}
    decisions = []
    rooms = sorted({p.area_id for p in profiles if p.area_id})
    modes = {c.get("mode", "normal") for c in contexts}

    def usable(p):
        reported = timestamp(p.attributes.get("last_reported"))
        return p.state not in {None, "unknown", "unavailable"} and reported is not None and 0 <= now.timestamp() - reported <= 7200

    def emit(category, title, action, reason, entities=(), *, risk="low", impact="medium", question=None, evidence=None):
        ids = [p.entity_id for p in entities]
        trained = [learning.get(i, {}).get("samples", 0) >= 3 for i in ids]
        factors = dict(evidence_quality=0.95 if ids and all(usable(p) for p in entities) else 0.2,
                       historical_similarity=0.8 if trained and all(trained) else 0.25,
                       sensor_agreement=0.85 if len(ids) > 1 else 0.5,
                       data_freshness=1 if ids and all(usable(p) for p in entities) else 0)
        confidence = engine.confidence_from_evidence(**factors)
        # Negative feedback lowers confidence; never grants authority to operate devices.
        ratings = [f for f in feedback if f.get("category") == category][-20:]
        confidence -= min(0.25, sum(f.get("rating") == "wrong" for f in ratings) * 0.025)
        if question:
            confidence = min(confidence, 0.4)
        payload = {"observations": {p.entity_id: {"state": p.state, "value": numeric_value(p), "unit": p.unit} for p in entities},
                   "learning": {i: learning.get(i, {}) for i in ids}, "modes": sorted(modes),
                   "question": question, "confidence_factors": factors, **(evidence or {})}
        d = engine.build_decision(category=category, title=title, proposed_action=action,
            reasoning=reason, confidence=confidence, risk=RiskLevel(risk), impact=ImpactLevel(impact),
            area_id=entities[0].area_id if entities else None, entity_ids=ids, evidence=payload,
            alternatives=["Mantenere lo stato attuale e continuare a osservare", "Verificare dati e preferenze con una persona"])
        d.outcome = {"type": "not_executed", "reason": "permanent_shadow_mode"}
        decisions.append(d)

    bad = [p for p in profiles if p.role != "generic" and not usable(p)]
    if bad:
        emit("operational_safety", "Dati non affidabili", "Verificare disponibilità e aggiornamento dei sensori",
             "Dati sconosciuti o non aggiornati da oltre due ore non supportano proposte operative.", bad[:10],
             risk="high", question="I sensori sono raggiungibili e la frequenza di aggiornamento è corretta?",
             evidence={"affected_count": len(bad)})

    for area in rooms:
        local = [p for p in profiles if p.area_id == area and usable(p)]
        scope_modes = {c.get("mode", "normal") for c in contexts if not c.get("areas") or area in c["areas"]}
        expected = usage.get(area, {})
        expected_now = float(expected.get("expected_occupancy", 0) or 0)
        upcoming = expected.get("upcoming", [])
        presence = [p for p in local if p.role == "presence" and p.domain == "binary_sensor"]
        occupied = any(p.state == "on" for p in presence)
        absent = bool(presence) and all(p.state == "off" for p in presence)
        temps = [p for p in local if p.role == "temperature" and numeric_value(p) is not None]
        climates = [p for p in local if p.role == "climate"]
        if climates and not temps:
            emit("climate", "Temperatura stanza mancante", "Associare un sensore di temperatura ambiente",
                 "Non uso il setpoint del termostato come temperatura misurata.", climates,
                 question=f"Quale sensore misura la temperatura ambiente in {area}?")
        target = number(preferences.get(f"comfort:{area}"))
        if climates and temps:
            if target is None:
                emit("climate", "Comfort da definire", "Raccogliere la temperatura desiderata",
                     "La temperatura obiettivo non viene dedotta dal nome della stanza.", temps + climates,
                     question=f"Quale temperatura di comfort in °C desideri per {area}? Usa set_preference comfort:{area}.")
            elif (occupied or expected_now >= 0.5) and "vacation" not in scope_modes:
                t = sum(numeric_value(p) for p in temps) / len(temps)
                if abs(t - target) >= 1:
                    emit("climate", "Scostamento dal comfort", "Valutare riscaldamento" if t < target else "Valutare raffrescamento",
                         f"Stanza occupata: {t:.1f} °C rispetto a {target:.1f} °C. Il trend descrive l'andamento, non una previsione causale.",
                         temps + climates + presence, risk="medium", evidence={"target_c": target, "expected_use": expected})
            elif upcoming and "vacation" not in scope_modes:
                next_use = upcoming[0]
                t = sum(numeric_value(p) for p in temps) / len(temps)
                use_target = number(next_use.get("comfort_c")) or target
                if use_target is not None and abs(t - use_target) >= 1 and next_use["minutes_until"] <= 90:
                    emit("climate", "Uso stanza previsto", "Valutare pre-climatizzazione",
                         f"Uso previsto tra {next_use['minutes_until']} minuti; temperatura {t:.1f} °C rispetto a {use_target:.1f} °C.",
                         temps + climates + presence, risk="medium", evidence={"target_c": use_target, "expected_use": expected})
            elif "vacation" in scope_modes:
                emit("climate", "Modalità vacanza", "Valutare un profilo di mantenimento da concordare",
                     "La vacanza cambia il comfort richiesto, ma protezione antigelo e limiti tecnici restano da verificare.",
                     climates, risk="high", question="Quali limiti di mantenimento sono previsti dall'impianto?")
        humid = [p for p in local if p.role == "humidity" and numeric_value(p) is not None]
        for p in humid:
            if numeric_value(p) > 65:
                emit("ventilation", "Umidità elevata", "Valutare ventilazione o deumidificazione",
                     "Umidità relativa oltre 65%; senza umidità assoluta esterna non si può stabilire che aprire le finestre aiuti.",
                     [p] + [x for x in local if x.role == "ventilation"], risk="medium",
                     question="Sono disponibili condizioni esterne e limiti di rumore della stanza?")
        lights = [p for p in local if p.role == "lighting" and p.state == "on"]
        if lights and absent:
            protected = scope_modes & {"guests", "illness", "work_from_home"}
            emit("lighting", "Luci senza presenza rilevata", "Verificare prima di ipotizzare lo spegnimento",
                 "Assenza di movimento non equivale a stanza vuota." + (" Il contesto richiede comfort protetto." if protected else ""),
                 lights + presence, question="La stanza è davvero vuota o qualcuno è fermo, ospite o sta riposando?")
        if presence:
            emit("presence", "Uso stanza osservato", "Continuare a imparare gli orari di utilizzo",
                 "Le frequenze per ora locale sono descrittive; non identificano persone e non garantiscono presenza futura.", presence,
                 evidence={"occupied": occupied, "context_modes": sorted(scope_modes)})

    valid = [p for p in profiles if usable(p)]
    hot = [p for p in valid if p.role == "hot_water"]
    for p in hot:
        temp = numeric_value(p)
        if temp is not None:
            emit("hot_water", "Profilo ACS osservato", "Confrontare andamento ACS, richiesta e programma del produttore",
                 f"Temperatura osservata {temp:.1f} °C. I cali possono indicare prelievo o dispersione; non sono diagnosi. Nessuna modifica ai cicli sanitari.",
                 [p], risk="high", question="Quali programma sanitario, limiti del produttore e fasce d'uso ACS devono essere rispettati?")
    solar = [p for p in valid if p.role == "solar_power" and numeric_value(p) is not None]
    loads = [p for p in valid if p.role == "load_power" and numeric_value(p) is not None]
    batteries = [p for p in valid if p.role == "battery" and p.attributes.get("classification_source") == "user" and numeric_value(p) is not None]
    if len(solar) == len(loads) == 1:
        surplus = numeric_value(solar[0]) - numeric_value(loads[0])
        emit("energy", "Bilancio FV osservato", "Valutare lo spostamento di carichi flessibili" if surplus > 500 else "Continuare a osservare il bilancio",
             "Differenza istantanea FV-consumo; non è una previsione di produzione né una misura dell'energia risparmiata.",
             solar + loads + batteries, risk="medium", evidence={"surplus_w": round(surplus, 1)},
             question="Sono confermati perimetro dei contatori, riserva batteria e carichi flessibili?")
    elif any(p.role in {"energy", "solar_power", "load_power", "battery"} for p in valid):
        emit("energy", "Contatori da associare", "Associare un contatore FV e un contatore consumo totale",
             "Non sommo sensori con possibili sovrapposizioni e non confondo W, kWh e percentuali batteria.",
             question="Quali entità rappresentano FV, consumo totale e accumulo? Usa classify_entity.")
    for p in [p for p in valid if p.role == "soil_moisture" and numeric_value(p) is not None]:
        threshold = number(preferences.get(f"soil_min:{p.area_id}"))
        if threshold is None or numeric_value(p) < threshold:
            emit("irrigation", "Umidità del terreno", "Valutare necessità di irrigazione",
                 "Servono soglia calibrata sul terreno, pioggia prevista e vincoli idrici. Nessuna apertura valvole.", [p], risk="medium",
                 question="Quali soglia del terreno, previsioni pioggia e limiti idrici sono applicabili?")
    if any(p.role == "irrigation" for p in valid) and not any(p.role == "soil_moisture" for p in valid):
        emit("irrigation", "Dati irrigazione mancanti", "Associare sensori terreno e pioggia", "Una valvola da sola non misura il bisogno d'acqua.",
             question="Quali sensori descrivono terreno e pioggia?")
    for p in [p for p in valid if p.role == "security"]:
        if (p.domain == "binary_sensor" and p.state == "on") or p.state in {"triggered", "jammed"}:
            emit("operational_safety", "Segnale di sicurezza attivo", "Richiedere verifica umana del segnale",
                 "E.S.T.E.R. non sostituisce un allarme certificato e non disarma, sblocca o silenzia dispositivi.", [p],
                 risk="critical", impact="high", question="Il segnale è atteso ed è stato verificato?")
    if not rooms:
        emit("model", "Stanze non associate", "Associare aree alle entità", "Senza aree non collego sensori e dispositivi arbitrariamente.",
             question="A quali stanze appartengono le entità?")
    return decisions
