"""Persistent question inbox and conservative answer interpretation."""
from __future__ import annotations

from datetime import datetime, timedelta
import re
from uuid import uuid4



def _friendly_question(decision: dict, prompt: str) -> dict:
    """Turn an internal question into a concise user-facing prompt."""
    category = decision.get("category")
    area = decision.get("area_id")
    area_label = (area or "casa").replace("_", " ").strip().title()
    reasoning = decision.get("reasoning") or ""

    base = {
        "display_title": decision.get("title") or "Mi serve un'informazione",
        "display_prompt": prompt,
        "observed": reasoning,
        "why_asking": "La risposta mi serve per aumentare la sicurezza della decisione e ridurre le ipotesi.",
        "answer_hint": "Puoi rispondere con parole normali.",
        "quick_answers": [],
    }

    p = prompt.lower()
    if category == "climate" and "sensore" in p:
        base.update({
            "display_title": f"Termometro di {area_label}",
            "display_prompt": f"Hai un sensore che misura la temperatura della stanza {area_label}?",
            "why_asking": "Mi serve la temperatura della stanza, non quella impostata sul riscaldamento.",
            "answer_hint": "Scrivi il nome con cui lo riconosci in Home Assistant. Se non sai quale sia, scegli Non lo so.",
            "quick_answers": ["Non ho un sensore in questa stanza"],
        })
    elif category == "climate" and ("comfort" in p or "temperatura desideri" in p):
        base.update({
            "display_title": f"Comfort di {area_label}",
            "display_prompt": f"Che temperatura vuoi normalmente in {area_label} quando la stanza è usata?",
            "why_asking": "Mi serve sapere a quale temperatura stai bene per valutare il riscaldamento.",
            "answer_hint": "Esempio: «21 gradi» oppure «20,5 °C».",
            "quick_answers": ["19 °C", "20 °C", "21 °C", "22 °C"],
        })
    elif category == "ventilation":
        base.update({
            "display_title": f"Ventilazione di {area_label}",
            "display_prompt": f"La ventilazione in {area_label} serve principalmente a ridurre umidità/aria viziata?",
            "why_asking": "Devo sapere qual è lo scopo dell'impianto prima di giudicare se sta funzionando bene.",
            "answer_hint": "Esempio: «Sì, soprattutto dopo la doccia» oppure «No, serve per altro».",
            "quick_answers": ["Sì", "No", "Soprattutto dopo la doccia"],
        })
    elif category == "presence":
        base.update({
            "display_title": f"Presenza in {area_label}",
            "display_prompt": f"In {area_label} può esserci qualcuno anche se per un po' non rilevo movimento?",
            "why_asking": "Voglio evitare di spegnere luci o cambiare comfort quando una persona è ferma o sta riposando.",
            "answer_hint": "Esempio: «Sì, capita spesso» oppure «No, se non c'è movimento è quasi sempre vuota».",
            "quick_answers": ["Sì, capita", "No, quasi mai"],
        })
    elif category == "lighting":
        base.update({
            "display_title": f"Luci di {area_label}",
            "display_prompt": f"Quando non rilevo presenza in {area_label}, posso considerare la stanza vuota per le luci?",
            "why_asking": "La sola assenza di movimento non prova sempre che la stanza sia vuota.",
            "answer_hint": "Esempio: «Sì» oppure «No, può esserci qualcuno fermo».",
            "quick_answers": ["Sì", "No"],
        })
    elif category == "security" and "antifurto" in p:
        base.update({
            "display_title": "Logica antifurto",
            "display_prompt": "Quando vuoi che l'antifurto sia attivo e quando spento?",
            "why_asking": "L'antifurto è un dominio ad alto rischio e non voglio imparare una regola sbagliata.",
            "answer_hint": "Puoi dire cosa deve succedere, ad esempio: «Di giorno, se siamo in casa, deve essere disarmato».",
            "quick_answers": [],
        })
    elif category == "hot_water":
        base.update({
            "display_title": "Temperatura del boiler",
            "display_prompt": "A quanti gradi tieni normalmente impostato il boiler?",
            "why_asking": "Mi serve conoscere la tua impostazione abituale per studiare i consumi dell'acqua calda.",
            "answer_hint": "Leggi la temperatura impostata sul boiler, non quella dell'acqua in questo momento. Non modificare le impostazioni per rispondere.",
            "quick_answers": [],
        })
    elif category == "energy":
        base.update({
            "display_title": "Configurazione energia",
            "display_prompt": "Come si chiamano in Home Assistant i valori dei pannelli solari, del consumo di casa e della batteria?",
            "why_asking": "Voglio distinguere l'energia prodotta da quella consumata, senza confondere i contatori.",
            "answer_hint": "Puoi descrivere anche un solo valore, per esempio: «Produzione solare indica i pannelli». La risposta sarà una nota da verificare, non un collegamento automatico.",
            "quick_answers": [],
        })
    elif category == "irrigation":
        base.update({
            "display_title": f"Irrigazione di {area_label}",
            "display_prompt": ("Hai un sensore che misura quanto è umido il terreno o se piove?" if "sensori" in p else "Ci sono regole o limiti da rispettare quando annaffi questa zona?"),
            "why_asking": "Voglio evitare di irrigare basandomi su una soglia non adatta alla zona.",
            "answer_hint": "Descrivi quello che sai con parole tue. Non serve inventare numeri o percentuali.",
            "quick_answers": [],
        })
    base["quick_answers"] = [*base["quick_answers"], "Non lo so"]
    season = (decision.get("evidence") or {}).get("comfort_season")
    if category == "climate" and season in {"winter", "summer", "shoulder"}:
        degrees = 26 if season == "summer" else 20
        label = {"winter": "riscaldamento", "summer": "raffrescamento", "shoulder": "mezza stagione"}[season]
        base.update({
            "display_prompt": f"Per {area_label}, partiamo da {degrees} °C come riferimento per {label}?",
            "why_asking": "È un punto di partenza da provare, non una temperatura perfetta per tutti. Puoi cambiarlo se senti caldo o freddo.",
            "answer_hint": "Conferma un valore oppure scrivi quello che preferisci. Salvo la scelta solo per questa stagione; non cambio il termostato. " + ("Il periodo è stimato dal calendario." if decision.get("evidence", {}).get("season_source") == "calendar" else "Mi baso sulla modalità attuale del climatizzatore."),
            "quick_answers": [f"{degrees} °C", f"{degrees-1} °C", f"{degrees+1} °C", "Non lo so"],
        })
    return base

def question_from_decision(decision: dict, now: datetime) -> dict | None:
    prompt = (decision.get("evidence") or {}).get("question")
    if not prompt:
        return None
    friendly = _friendly_question(decision, prompt)
    return {
        "question_id": str(uuid4()),
        "decision_id": decision["decision_id"],
        "category": decision["category"],
        "area_id": decision.get("area_id"),
        "title": decision["title"],
        "prompt": prompt,
        "reasoning": decision["reasoning"],
        "confidence": decision["confidence"],
        "risk": decision["risk"],
        "status": "open",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "answer": None,
        "interpretation": None,
        "comfort_season": (decision.get("evidence") or {}).get("comfort_season"),
        "season_source": (decision.get("evidence") or {}).get("season_source"),
        **friendly,
    }


def _stable_key(item: dict) -> tuple:
    return (item.get("category"), item.get("area_id"), item.get("title"), item.get("prompt"))


def merge_questions(existing: list[dict], decisions: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Deduplicate questions and respect recently answered/dismissed items."""
    created = []
    latest = {}
    for question in existing:
        if question.get("status") == "open":
            # Refresh presentation even when the originating proposal has changed.
            evidence = {"comfort_season": question.get("comfort_season"), "season_source": question.get("season_source", "calendar")}
            question.update(_friendly_question({**question, "evidence": evidence}, question.get("prompt", "")))
        key = _stable_key(question)
        updated = question.get("updated_at") or question.get("created_at")
        try:
            stamp = datetime.fromisoformat(updated) if updated else None
        except ValueError:
            stamp = None
        current = latest.get(key)
        if current is None or (stamp and stamp > current[0]):
            latest[key] = (stamp or datetime.min.replace(tzinfo=now.tzinfo), question)

    for decision in decisions:
        item = question_from_decision(decision, now)
        if item is None:
            continue
        if item.get("comfort_season"):
            for old in existing:
                if (old.get("status") == "open" and old.get("category") == "climate"
                        and old.get("area_id") == item.get("area_id")
                        and not old.get("comfort_season")
                        and "comfort" in ((old.get("title") or "") + (old.get("prompt") or "")).lower()):
                    old["status"] = "superseded"
                    old["updated_at"] = now.isoformat()
        key = _stable_key(item)
        previous = latest.get(key)
        if previous:
            stamp, question = previous
            if question.get("status") == "open":
                question["updated_at"] = now.isoformat()
                question["confidence"] = item["confidence"]
                question["decision_id"] = item["decision_id"]
                for field in (
                    "display_title", "display_prompt", "observed",
                    "why_asking", "answer_hint", "quick_answers", "comfort_season", "season_source",
                ):
                    question[field] = item.get(field)
                continue
            if now - stamp < timedelta(days=7):
                continue
        existing.append(item)
        created.append(item)
        latest[key] = (now, item)
    return existing[-300:], created


def _temperature(text: str) -> float | None:
    match = re.search(r"(?<!\d)([1-3]?\d(?:[.,]\d)?)\s*(?:°|gradi|grado|c\b)", text.lower())
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 5 <= value <= 35 else None


def interpret_answer(question: dict, answer: str) -> dict:
    """Interpret only bounded, reversible memory updates locally.

    Unstructured answers are stored as knowledge notes instead of becoming rules.
    """
    text = answer.strip()
    lower = text.lower()
    area = question.get("area_id")
    category = question.get("category")

    if lower.rstrip(".! ") == "non lo so":
        return {"kind": "deferred", "summary": "Va bene: te lo richiederò tra qualche giorno. Non ho imparato nessuna preferenza da questa risposta."}

    if category == "climate" and area and "sensore" not in question.get("prompt", "").lower():
        temp = _temperature(text)
        if temp is not None and any(token in lower for token in ("voglio", "prefer", "comfort", "tieni", "tenere", "gradi", "°")):
            return {
                "kind": "preference",
                "key": (f"seasonal_comfort:{question['comfort_season']}:{area}"
                        if question.get("comfort_season") in {"winter", "summer", "shoulder"} else f"comfort:{area}"),
                "value": temp,
                "confidence": 0.98,
                "summary": f"Comfort {area}: {temp:g} °C",
            }

    permanence = "temporary"
    if any(token in lower for token in ("sempre", "di solito", "normalmente", "regola", "preferisco")):
        permanence = "persistent"
    if any(token in lower for token in ("oggi", "stasera", "domani", "questa volta", "solo stavolta")):
        permanence = "temporary"

    return {
        "kind": "knowledge_note",
        "category": category,
        "area_id": area,
        "text": text,
        "scope": permanence,
        "confidence": 0.7,
        "summary": "Risposta conservata come conoscenza; nessuna regola automatica creata.",
    }


def apply_answer(data: dict, question_id: str, answer: str, now: datetime) -> dict:
    """Apply a user answer to E.S.T.E.R. memory without touching devices."""
    question = next((q for q in data.setdefault("questions", [])
                     if q.get("question_id") == question_id), None)
    if question is None:
        raise KeyError("unknown_question")
    if question.get("status") == "answered":
        raise ValueError("already_answered")
    interpretation = interpret_answer(question, answer)
    question["status"] = "deferred" if interpretation["kind"] == "deferred" else "answered"
    question["answer"] = answer.strip()
    question["interpretation"] = interpretation
    question["updated_at"] = now.isoformat()
    if interpretation["kind"] == "deferred":
        return interpretation
    if interpretation["kind"] == "preference":
        data.setdefault("preferences", {})[interpretation["key"]] = interpretation["value"]
    else:
        knowledge = data.setdefault("knowledge", [])
        knowledge.append({
            "knowledge_id": str(uuid4()),
            "question_id": question_id,
            "category": interpretation.get("category"),
            "area_id": interpretation.get("area_id"),
            "text": interpretation.get("text", answer.strip()),
            "scope": interpretation.get("scope", "temporary"),
            "confidence": interpretation.get("confidence", 0.5),
            "created_at": now.isoformat(),
            "source": "user_answer",
        })
        del knowledge[:-500]
    return interpretation
