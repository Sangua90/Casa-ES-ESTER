"""Deterministic shadow proposals. No Home Assistant imports or execution path."""
from __future__ import annotations

from datetime import timedelta

from .home import number, numeric_value, timestamp
from .models import ImpactLevel, RiskLevel
from .thermal import compare_climate_strategies
from .energy import energy_plan, rank_flexible_loads
from .house_controls import lighting_plan, alarm_plan
from .ventilation import ventilation_recommendation
from .hot_water import hot_water_shadow_plan
from .economics import heating_costs
from .occupancy import predicted_occupancy


def evaluate(engine, profiles, learning, contexts, preferences, feedback, now, usage=None,
             thermal_models=None, flexible_loads=None, local_tz=None, ventilation_models=None,
             hot_water_models=None, occupancy_models=None):
    thermal_models = thermal_models or {}
    flexible_loads = flexible_loads or []
    ventilation_models = ventilation_models or {}
    hot_water_models = hot_water_models or {}
    occupancy_models = occupancy_models or {}
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
        local_now = now.astimezone(local_tz) if local_tz else now
        learned_occ = predicted_occupancy(occupancy_models.get(area, {}), local_now)
        if learned_occ is not None:
            expected_now = max(expected_now, learned_occ)
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
                    econ = heating_costs(
                        electricity_eur_kwh=number(preferences.get("energy_price_eur_kwh")),
                        gas_eur_m3=number(preferences.get("gas_price_eur_m3")),
                        heat_pump_cop=number(preferences.get("heat_pump_cop")),
                        boiler_efficiency=number(preferences.get("boiler_efficiency")),
                    )
                    if t < target and econ.get("preferred_source") == "heat_pump":
                        action = "Valutare riscaldamento con PDC"
                    elif t < target and econ.get("preferred_source") == "gas":
                        action = "Valutare riscaldamento a gas"
                    else:
                        action = "Valutare riscaldamento" if t < target else "Valutare raffrescamento"
                    emit("climate", "Scostamento dal comfort", action,
                         f"Stanza occupata o prevista in uso: {t:.1f} °C rispetto a {target:.1f} °C.",
                         temps + climates + presence, risk="medium",
                         evidence={"target_c": target, "expected_use": expected,
                                   "learned_occupancy": learned_occ, "heating_economics": econ})
            elif upcoming and "vacation" not in scope_modes:
                next_use = upcoming[0]
                t = sum(numeric_value(p) for p in temps) / len(temps)
                use_target = number(next_use.get("comfort_c")) or target
                if use_target is not None and abs(t - use_target) >= 1 and next_use["minutes_until"] <= 120:
                    model = thermal_models.get(area, {})
                    strategies = compare_climate_strategies(
                        current_c=t,
                        target_c=use_target,
                        minutes_until_use=next_use["minutes_until"],
                        model=model,
                        energy_price_eur_kwh=number(preferences.get("energy_price_eur_kwh")),
                        estimated_power_kw=number(preferences.get(f"climate_power_kw:{area}")),
                    )
                    pre = next((s for s in strategies if s["strategy"] == "precondition"), None)
                    if pre:
                        action = f"Valutare pre-climatizzazione tra {pre['start_in_minutes']} minuti"
                        reason = (
                            f"Uso previsto tra {next_use['minutes_until']} minuti; temperatura {t:.1f} °C, "
                            f"target {use_target:.1f} °C. Il modello locale stima circa "
                            f"{pre['estimated_runtime_minutes']} minuti di climatizzazione."
                        )
                    else:
                        action = "Continuare a osservare prima di pre-climatizzare"
                        reason = (
                            f"Uso previsto tra {next_use['minutes_until']} minuti; temperatura {t:.1f} °C, "
                            f"target {use_target:.1f} °C. Non ci sono ancora abbastanza dati termici locali "
                            "per stimare un anticipo affidabile."
                        )
                    emit("climate", "Uso stanza previsto", action, reason,
                         temps + climates + presence, risk="medium",
                         evidence={"target_c": use_target, "expected_use": expected,
                                   "thermal_model": model, "strategies": strategies})
            elif "vacation" in scope_modes:
                emit("climate", "Modalità vacanza", "Valutare un profilo di mantenimento da concordare",
                     "La vacanza cambia il comfort richiesto, ma protezione antigelo e limiti tecnici restano da verificare.",
                     climates, risk="high", question="Quali limiti di mantenimento sono previsti dall'impianto?")
        humid = [p for p in local if p.role == "humidity" and numeric_value(p) is not None]
        vents = [x for x in local if x.role == "ventilation"]
        if humid:
            humidity_value = sum(numeric_value(p) for p in humid) / len(humid)
            vent_model = ventilation_models.get(area, {})
            vent_active = any(v.state == "on" for v in vents)
            vr = ventilation_recommendation(
                humidity=humidity_value,
                model=vent_model,
                active=vent_active,
            )
            if vr["strategy"] != "hold":
                action = {
                    "would_run": "Avrei mantenuto/avviato la ventilazione",
                    "would_stop": "Avrei fermato la ventilazione",
                }.get(vr["strategy"], "Continuare a osservare")
                emit(
                    "ventilation", "Ventilazione adattiva", action, vr["reason"],
                    humid + vents, risk="medium",
                    question=None if vent_model.get("confidence", 0) >= 0.6 else
                    "Confermi che questa ventilazione serve a ridurre l'umidità di questa stanza?",
                    evidence={"ventilation_model": vent_model, "ventilation_plan": vr},
                )
        lights_all = [p for p in local if p.role == "lighting"]
        lux = [p for p in local if p.role == "illuminance" and numeric_value(p) is not None]
        if lights_all:
            light_on = any(p.state == "on" for p in lights_all)
            lux_value = sum(numeric_value(p) for p in lux) / len(lux) if lux else None
            plan = lighting_plan(
                light_on=light_on,
                occupied=occupied or expected_now >= 0.5,
                presence_known=bool(presence),
                illuminance_lux=lux_value,
                lux_threshold=number(preferences.get(f"lux_on:{area}")) or 80,
            )
            if plan["strategy"] == "would_turn_off":
                protected = scope_modes & {"guests", "illness", "work_from_home"}
                emit(
                    "lighting", "Luce potenzialmente non necessaria", "Avrei spento la luce",
                    plan["reason"] + (" Contesto protetto attivo." if protected else ""),
                    lights_all + presence + lux,
                    question="La stanza è davvero vuota o qualcuno è fermo, ospite o sta riposando?",
                    evidence={"lighting_plan": plan},
                )
            elif plan["strategy"] == "would_turn_on":
                emit(
                    "lighting", "Illuminazione utile", "Avrei acceso la luce",
                    plan["reason"], lights_all + presence + lux,
                    evidence={"lighting_plan": plan},
                )
        if presence:
            emit("presence", "Uso stanza osservato", "Continuare a imparare gli orari di utilizzo",
                 "Le frequenze per ora locale sono descrittive; non identificano persone e non garantiscono presenza futura.", presence,
                 evidence={"occupied": occupied, "context_modes": sorted(scope_modes)})

    valid = [p for p in profiles if usable(p)]
    hot = [p for p in valid if p.role == "hot_water"]
    pv_for_hot = [p for p in valid if p.role == "solar_power" and numeric_value(p) is not None]
    load_for_hot = [p for p in valid if p.role == "load_power" and numeric_value(p) is not None]
    pv_surplus_hot = None
    if len(pv_for_hot) == len(load_for_hot) == 1:
        pv_surplus_hot = max(0.0, numeric_value(pv_for_hot[0]) - numeric_value(load_for_hot[0]))
    for p in hot:
        temp = numeric_value(p)
        if temp is not None:
            target_hot = number(preferences.get("hot_water_target_c"))
            model = hot_water_models.get(p.area_id or "unassigned", {})
            if target_hot is None:
                emit(
                    "hot_water", "Target ACS da definire", "Raccogliere il target ACS",
                    f"Temperatura osservata {temp:.1f} °C; il target non viene dedotto automaticamente.",
                    [p], risk="high",
                    question="Quale temperatura ACS normale vuoi usare come target, rispettando il programma sanitario del produttore?",
                    evidence={"hot_water_model": model},
                )
            else:
                hp = hot_water_shadow_plan(
                    temp_c=temp,
                    target_c=target_hot,
                    expected_use_minutes=None,
                    model=model,
                    pv_surplus_w=pv_surplus_hot,
                )
                emit(
                    "hot_water", "Piano ACS Shadow",
                    hp["strategy"].replace("would_", "Avrei ").replace("_", " "),
                    hp["reason"] + " I cicli sanitari del produttore restano fuori dall'ottimizzazione.",
                    [p] + pv_for_hot + load_for_hot,
                    risk="high",
                    evidence={"hot_water_model": model, "hot_water_plan": hp,
                              "target_c": target_hot, "pv_surplus_w": pv_surplus_hot},
                )
    solar = [p for p in valid if p.role == "solar_power" and numeric_value(p) is not None]
    loads = [p for p in valid if p.role == "load_power" and numeric_value(p) is not None]
    grids = [p for p in valid if p.role == "grid_power" and numeric_value(p) is not None]
    batteries = [p for p in valid if p.role == "battery" and numeric_value(p) is not None]
    phases = [p for p in valid if p.role == "phase_power" and numeric_value(p) is not None]
    forecast_energy = [p for p in valid if p.role == "pv_forecast_energy" and numeric_value(p) is not None]

    energy_entities = solar + loads + grids + batteries + phases + forecast_energy
    if len(solar) == 1 and len(loads) == 1:
        local_now = now.astimezone(local_tz) if local_tz else now
        target_hour = int(number(preferences.get("battery_target_hour_local")) or 16)
        target = local_now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target <= local_now:
            target += timedelta(days=1)
        plan = energy_plan(
            now=local_now,
            target=target,
            pv_w=numeric_value(solar[0]),
            load_w=numeric_value(loads[0]),
            grid_w=numeric_value(grids[0]) if len(grids) == 1 else None,
            battery_soc=numeric_value(batteries[0]) if len(batteries) == 1 else None,
            battery_capacity_kwh=number(preferences.get("battery_capacity_kwh")),
            target_soc=number(preferences.get("battery_target_soc")),
            reserve_soc=number(preferences.get("battery_reserve_percent")),
            forecast_curve=[],
            forecast_remaining_kwh=numeric_value(forecast_energy[0]) if len(forecast_energy) == 1 else None,
            base_load_w=number(preferences.get("base_load_w")),
            grid_limit_w=number(preferences.get("grid_limit_w")),
            inverter_limit_w=number(preferences.get("inverter_limit_w")),
            phase_w=[numeric_value(p) for p in phases],
            phase_limit_w=number(preferences.get("phase_limit_w")),
        )
        ranked = rank_flexible_loads(flexible_loads, plan)
        strategy_labels = {
            "protect_electrical_limits": "Proteggere i limiti elettrici",
            "preserve_battery": "Preservare la riserva batteria",
            "battery_first": "Dare priorità alla batteria",
            "use_flexible_surplus": "Valutare carichi flessibili sul surplus",
            "balanced": "Mantenere strategia bilanciata",
        }
        action = strategy_labels.get(plan["strategy"], "Continuare a osservare")
        reason = (
            f"Planner locale: FV {plan['pv_w']:.0f} W, carico {plan['load_w']:.0f} W, "
            f"surplus istantaneo {plan['instant_surplus_w']:.0f} W."
        )
        if plan.get("battery_soc") is not None:
            reason += f" SOC {plan['battery_soc']:.0f}%."
        if plan.get("forecast_margin_kwh") is not None:
            reason += f" Margine energetico al target {plan['forecast_margin_kwh']:.2f} kWh."
        emit(
            "energy",
            "Piano energetico casa",
            action,
            reason,
            energy_entities,
            risk="medium",
            evidence={"energy_plan": plan, "flexible_load_ranking": ranked[:20]},
        )
    elif any(p.role in {"energy", "solar_power", "load_power", "grid_power", "battery_power", "phase_power", "battery"} for p in valid):
        emit(
            "energy",
            "Contatori energetici da completare",
            "Associare almeno FV e consumo totale; consigliati rete, SOC e fasi",
            "E.S.T.E.R. non somma contatori ambigui e richiede ruoli espliciti per il planner energetico.",
            energy_entities,
            question="Quali entità rappresentano FV, consumo totale, rete, SOC batteria e singole fasi? Usa classify_entity.",
        )

    for p in [p for p in valid if p.role == "soil_moisture" and numeric_value(p) is not None]:
        threshold = number(preferences.get(f"soil_min:{p.area_id}"))
        if threshold is None or numeric_value(p) < threshold:
            emit("irrigation", "Umidità del terreno", "Valutare necessità di irrigazione",
                 "Servono soglia calibrata sul terreno, pioggia prevista e vincoli idrici. Nessuna apertura valvole.", [p], risk="medium",
                 question="Quali soglia del terreno, previsioni pioggia e limiti idrici sono applicabili?")
    if any(p.role == "irrigation" for p in valid) and not any(p.role == "soil_moisture" for p in valid):
        emit("irrigation", "Dati irrigazione mancanti", "Associare sensori terreno e pioggia", "Una valvola da sola non misura il bisogno d'acqua.",
             question="Quali sensori descrivono terreno e pioggia?")
    alarm_panels = [p for p in valid if p.domain == "alarm_control_panel"]
    presence_all = [p for p in valid if p.role == "presence" and p.domain in {"binary_sensor", "person", "device_tracker"}]
    door_open = any(
        p.domain == "binary_sensor" and p.role == "security" and p.state == "on"
        and p.device_class in {"door", "window", "opening"}
        for p in valid
    )
    occupied_house = any(
        (p.domain == "binary_sensor" and p.state == "on")
        or (p.domain in {"person", "device_tracker"} and p.state == "home")
        for p in presence_all
    )
    presence_known = bool(presence_all)
    expected_house = max(
        [float(u.get("expected_occupancy", 0) or 0) for u in usage.values()] or [0]
    )
    if alarm_panels:
        alarm = alarm_panels[0]
        local_hour = (now.astimezone(local_tz).hour if local_tz else now.hour)
        ap = alarm_plan(
            alarm_state=alarm.state,
            occupied=occupied_house,
            presence_known=presence_known,
            expected_occupancy=expected_house,
            doors_open=door_open,
            local_hour=local_hour,
            vacation="vacation" in modes,
            guests="guests" in modes,
            night_start_hour=int(number(preferences.get("night_start_hour")) or 22),
            morning_hour=int(number(preferences.get("morning_hour")) or 7),
        )
        if ap["strategy"] != "hold":
            emit(
                "security",
                "Piano antifurto Shadow",
                ap["strategy"].replace("would_", "Avrei ").replace("_", " "),
                ap["reason"],
                [alarm] + presence_all,
                risk="high",
                impact="high",
                question="Confermi che questa logica antifurto corrisponde a come vuoi usare la casa?",
                evidence={"alarm_plan": ap},
            )

    for p in [p for p in valid if p.role == "security"]:
        if (p.domain == "binary_sensor" and p.state == "on") or p.state in {"triggered", "jammed"}:
            emit("operational_safety", "Segnale di sicurezza attivo", "Richiedere verifica umana del segnale",
                 "E.S.T.E.R. non sostituisce un allarme certificato e non disarma, sblocca o silenzia dispositivi.", [p],
                 risk="critical", impact="high", question="Il segnale è atteso ed è stato verificato?")
    if not rooms:
        emit("model", "Stanze non associate", "Associare aree alle entità", "Senza aree non collego sensori e dispositivi arbitrariamente.",
             question="A quali stanze appartengono le entità?")
    return decisions
