"""Measured-value climate alternatives; scores are comparisons, never success odds."""
from math import ceil, isfinite
from .optimizer import normalize_weights


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def climate_candidates(*, current_c, target_c, minutes_until_use, model,
                       energy_price_eur_kwh=None, estimated_power_kw=None, pv_surplus_kw=None,
                       allow_delayed=True):
    passive = numeric(model.get("passive_rate_c_per_h"))
    active = numeric(model.get("active_rate_c_per_h"))
    horizon = max(1, min(720, int(minutes_until_use)))
    power, price, pv = map(numeric, (estimated_power_kw, energy_price_eur_kwh, pv_surplus_kw))
    power = power if power is not None and power > 0 else None
    price = price if price is not None and price >= 0 else None
    pv = max(0, pv) if pv is not None else None
    wait_temp = current_c+passive*horizon/60 if passive is not None else None
    options = [{"strategy":"wait", "start_in_minutes":None, "estimated_runtime_minutes":0,
                "predicted_temp_at_use":round(wait_temp, 2) if wait_temp is not None else None,
                "estimated_energy_kwh":0.0, "estimated_grid_energy_kwh":0.0, "estimated_cost_eur":0.0,
                "assumptions":["Nessuna energia aggiuntiva per la climatizzazione; il resto della casa è escluso."]}]
    delta = target_c-current_c
    if active is None or abs(active) < .05 or (delta*active <= 0 and (wait_temp is None or (target_c-wait_temp)*active <= 0)):
        return options
    if delta*active > 0:
        needed = max(1, ceil(delta/active*60))
        runtime = min(horizon, needed)
        predicted = current_c+active*runtime/60
        if runtime < horizon:
            predicted = predicted+passive*(horizon-runtime)/60 if passive is not None else None
        options.append({"strategy":"condition_now", "start_in_minutes":0, "estimated_runtime_minutes":runtime,
                        "predicted_temp_at_use":round(predicted, 2) if predicted is not None else None,
                        "required_runtime_minutes":needed, "assumptions":["Modello termico locale lineare; dopo il target si considera la deriva passiva."]})
    if allow_delayed and passive is not None and active != passive:
        # Passive evolution before activation + active evolution until the use time.
        duration = (target_c-current_c-passive*horizon/60)/(active-passive)*60
        if duration > 0:
            runtime = min(horizon, ceil(duration))
            start = horizon-runtime
            predicted = current_c+passive*start/60+active*runtime/60
            options.append({"strategy":"precondition", "start_in_minutes":start, "estimated_runtime_minutes":runtime,
                "required_runtime_minutes":ceil(duration), "predicted_temp_at_use":round(predicted, 2),
                "assumptions":["Deriva passiva prima dell'avvio e tasso attivo costanti fino all'uso previsto."]})
    for row in options[1:]:
        energy = power*row["estimated_runtime_minutes"]/60 if power is not None else None
        # Future surplus is deliberately not extrapolated from a single current observation.
        grid = energy
        if row["start_in_minutes"] == 0 and power is not None and pv is not None:
            grid = max(0, power-pv)*row["estimated_runtime_minutes"]/60
            row["assumptions"].append("Il surplus FV osservato ora è ipotizzato costante durante il funzionamento: stima condizionata, non previsione FV.")
            row["solar_assumption"] = True
        row["estimated_energy_kwh"] = round(energy, 4) if energy is not None else None
        row["estimated_grid_energy_kwh"] = round(grid, 4) if grid is not None else None
        row["estimated_cost_eur"] = round(grid*price, 4) if grid is not None and price is not None else None
    return options


def compare_alternatives(candidates, target_c, preferences=None, model=None):
    """Comfort feasibility first, then compare available costs/energy/temperature."""
    weights = normalize_weights(preferences or {})
    rows = [dict(row) for row in candidates]
    missing = []
    if any(r.get("predicted_temp_at_use") is None for r in rows):
        missing.append("Mancano tassi termici per stimare alcune alternative.")
    if any(r.get("estimated_energy_kwh") is None for r in rows):
        missing.append("Potenza della climatizzazione non disponibile: energia non stimata.")
    if any(r.get("estimated_cost_eur") is None for r in rows):
        missing.append("Costo non stimabile per tutte le alternative: non viene inventato.")
    if any(r.get("solar_assumption") for r in rows):
        missing.append("Il costo FV dipende da un surplus costante ipotizzato, non da una previsione di produzione.")
    comparable_cost = all(r.get("estimated_cost_eur") is not None for r in rows)
    comparable_energy = all(r.get("estimated_energy_kwh") is not None for r in rows)
    max_cost = max((r.get("estimated_cost_eur") or 0 for r in rows), default=0) or 1
    max_energy = max((r.get("estimated_energy_kwh") or 0 for r in rows), default=0) or 1
    for row in rows:
        temp = row.get("predicted_temp_at_use")
        error = abs(temp-target_c) if temp is not None else None
        row["comfort_error_c"] = round(error, 2) if error is not None else None
        row["meets_comfort"] = error is not None and error <= .5
        row["score"] = None if error is None else round(
            weights["comfort"]*min(error/5, 1)
            + (weights["cost"]*row["estimated_cost_eur"]/max_cost if comparable_cost else 0)
            + (weights["energy"]*row["estimated_energy_kwh"]/max_energy if comparable_energy else 0), 4)
        row["selected"] = False
    feasible = [r for r in rows if r["meets_comfort"]]
    known = [r for r in rows if r["score"] is not None]
    selected = min(feasible, key=lambda r:(r["score"], r["comfort_error_c"])) if feasible else None
    if selected is None and len(known)>1:
        selected = min(known, key=lambda r:(r["comfort_error_c"], r["score"]))
        missing.append("Nessuna alternativa raggiunge il comfort previsto: scelta parziale da verificare.")
    if selected:
        selected["selected"] = True
        reason = ("Rispetta il comfort previsto e offre il confronto migliore sui dati disponibili."
                  if selected["meets_comfort"] else "Riduce maggiormente lo scostamento; non raggiunge il target nel tempo disponibile.")
    else:
        reason = "Dati insufficienti per scegliere una soluzione operativa tra le alternative."
    confidence = numeric((model or {}).get("confidence"))
    if confidence is None or confidence < .5:
        missing.append("Modello termico ancora poco consolidato: la stima richiede verifica.")
    return {"candidates":rows, "selected_strategy":selected["strategy"] if selected else None,
            "reason":reason, "uncertainties":missing, "weights":weights,
            "score_meaning":"Punteggio relativo (minore è migliore), non probabilità di successo.",
            "comfort_tolerance_c":.5, "model_confidence":confidence, "causal_savings_measured":False}
