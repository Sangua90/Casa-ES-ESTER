"""Persistent question inbox and conservative answer interpretation."""
from __future__ import annotations

from datetime import datetime
import re
from uuid import uuid4


def question_from_decision(decision: dict, now: datetime) -> dict | None:
    prompt = (decision.get("evidence") or {}).get("question")
    if not prompt:
        return None
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
    }


def merge_questions(existing: list[dict], decisions: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Deduplicate open questions by decision/category/area/title."""
    created = []
    by_key = {
        (q.get("decision_id"), q.get("category"), q.get("area_id"), q.get("title")): q
        for q in existing if q.get("status") == "open"
    }
    for decision in decisions:
        item = question_from_decision(decision, now)
        if item is None:
            continue
        key = (item["decision_id"], item["category"], item["area_id"], item["title"])
        if key in by_key:
            by_key[key]["updated_at"] = now.isoformat()
            by_key[key]["confidence"] = item["confidence"]
            continue
        existing.append(item)
        created.append(item)
        by_key[key] = item
    # Retain answered history, but keep storage bounded.
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
