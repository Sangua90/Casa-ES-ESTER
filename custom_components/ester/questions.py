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
    if category == "climate" and ("temperatura" in p or "comfort" in p):
        base.update({
            "display_title": f"Comfort di {area_label}",
            "display_prompt": f"Che temperatura vuoi normalmente in {area_label} quando la stanza è usata?",
            "why_asking": "Senza il tuo target non posso capire se conviene riscaldare, raffrescare o aspettare.",
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
    elif category == "security":
        base.update({
            "display_title": "Logica antifurto",
            "display_prompt": "Questa proposta di armamento/disarmo corrisponde a come vuoi usare normalmente l'antifurto?",
            "why_asking": "L'antifurto è un dominio ad alto rischio e non voglio imparare una regola sbagliata.",
            "answer_hint": "Puoi dire cosa deve succedere, ad esempio: «Di giorno, se siamo in casa, deve essere disarmato».",
            "quick_answers": ["Sì, è corretta", "No, va cambiata"],
        })
    elif category == "hot_water":
        base.update({
            "display_title": "Acqua calda sanitaria",
            "display_prompt": "Qual è il target normale dell'acqua calda che vuoi usare?",
            "why_asking": "Mi serve per confrontare disponibilità ACS, tempi di recupero, FV e costo senza toccare i cicli sanitari.",
            "answer_hint": "Esempio: «52 gradi».",
            "quick_answers": ["48 °C", "50 °C", "52 °C", "55 °C"],
        })
    elif category == "energy":
        base.update({
            "display_title": "Configurazione energia",
            "display_prompt": prompt,
            "why_asking": "Il planner energetico non deve indovinare quali contatori rappresentano FV, casa, rete, batteria o fasi.",
            "answer_hint": "Puoi indicarmi l'entità o spiegarmi a cosa corrisponde.",
            "quick_answers": [],
        })
    elif category == "irrigation":
        base.update({
            "display_title": f"Irrigazione di {area_label}",
            "display_prompt": prompt,
            "why_asking": "Voglio evitare di irrigare basandomi su una soglia non adatta alla zona.",
            "answer_hint": "Puoi indicare la soglia o descrivere quando vuoi irrigare.",
            "quick_answers": [],
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
        **friendly,
    }


def _stable_key(item: dict) -> tuple:
    return (item.get("category"), item.get("area_id"), item.get("title"), item.get("prompt"))


def merge_questions(existing: list[dict], decisions: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Deduplicate questions and respect recently answered/dismissed items."""
    created = []
    latest = {}
    for question in existing:
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
        key = _stable_key(item)
        previous = latest.get(key)
        if previous:
            stamp, question = previous
            if question.get("status") == "open":
                question["updated_at"] = now.isoformat()
                question["confidence"] = item["confidence"]
                question["decision_id"] = item["decision_id"]
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

    if category == "climate" and area:
        temp = _temperature(text)
        if temp is not None and any(token in lower for token in ("voglio", "prefer", "comfort", "tieni", "tenere", "gradi", "°")):
            return {
                "kind": "preference",
                "key": f"comfort:{area}",
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
    question["status"] = "answered"
    question["answer"] = answer.strip()
    question["interpretation"] = interpretation
    question["updated_at"] = now.isoformat()
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
