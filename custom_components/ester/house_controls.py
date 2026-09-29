"""Deterministic local planners for lighting and alarm Shadow decisions."""
from __future__ import annotations


def lighting_plan(*, light_on: bool, occupied: bool, presence_known: bool,
                  illuminance_lux: float | None, lux_threshold: float = 80.0) -> dict:
    dark = illuminance_lux is not None and illuminance_lux < lux_threshold
    if light_on and presence_known and not occupied:
        return {"strategy": "would_turn_off", "confidence": 0.82, "reason": "Luce accesa e assenza rilevata."}
    if not light_on and occupied and dark:
        return {"strategy": "would_turn_on", "confidence": 0.88,
                "reason": f"Presenza rilevata e illuminamento {illuminance_lux:.0f} lx sotto soglia."}
    if illuminance_lux is None:
        return {"strategy": "hold", "confidence": 0.55, "reason": "Illuminamento non disponibile."}
    return {"strategy": "hold", "confidence": 0.8, "reason": "Nessun intervento luce utile."}


def alarm_plan(*, alarm_state: str | None, occupied: bool, presence_known: bool,
               expected_occupancy: float, doors_open: bool, local_hour: int,
               vacation: bool = False, guests: bool = False,
               night_start_hour: int = 22, morning_hour: int = 7) -> dict:
    """Return a Shadow intent only. Alarm changes always remain high-risk."""
    if doors_open:
        return {"strategy": "hold", "confidence": 0.98, "reason": "Apertura rilevata: nessuna proposta di armamento."}
    if guests:
        return {"strategy": "hold", "confidence": 0.9, "reason": "Modalità ospiti: evitare inferenze automatiche sull'allarme."}
    if not presence_known and not vacation:
        return {"strategy": "hold", "confidence": 0.45, "reason": "Presenza non sufficientemente osservabile."}

    night = local_hour >= night_start_hour or local_hour < morning_hour
    if vacation and alarm_state in {"disarmed", "unknown", None}:
        return {"strategy": "would_arm_away", "confidence": 0.94, "reason": "Vacanza attiva e nessuna apertura rilevata."}
    if presence_known and not occupied and expected_occupancy < 0.2 and alarm_state == "disarmed":
        return {"strategy": "would_arm_away", "confidence": 0.86, "reason": "Casa apparentemente vuota e uso previsto basso."}
    if occupied and night and alarm_state == "disarmed":
        return {"strategy": "would_arm_night", "confidence": 0.84, "reason": "Presenza rilevata in fascia notte."}
    if occupied and not night and alarm_state in {"armed_away", "armed_night", "armed_home"}:
        return {"strategy": "would_disarm_home", "confidence": 0.82, "reason": "Presenza rilevata in casa durante fascia attiva."}
    return {"strategy": "hold", "confidence": 0.8, "reason": "Stato allarme coerente con il contesto osservato."}
