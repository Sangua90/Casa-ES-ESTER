"""Portable question exchange; validate the entire batch before learning."""
from copy import deepcopy
import hashlib
import json

from .questions import apply_answer, interpret_answer

FORMAT = "ester-question-exchange-v1"


def fingerprint(question):
    fields = {key: question.get(key) for key in
              ("question_id", "category", "area_id", "prompt", "comfort_season", "entity_ids")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def export_questions(data, rooms, now):
    items = []
    for q in data.get("questions", []):
        if q.get("status") != "open":
            continue
        items.append({
            "question_id": q["question_id"], "fingerprint": fingerprint(q),
            "room": rooms.get(q.get("area_id"), {}).get("name") or q.get("area_id") or "Casa",
            "category": q.get("category"),
            "question": q.get("display_prompt") or q.get("prompt"),
            "why": q.get("why_asking"), "observed": q.get("observed") or q.get("reasoning"),
            "suggested_answers": q.get("quick_answers", []),
            "action": "answer", "answer": None,
        })
    return {"format": FORMAT, "exported_at": now.isoformat(),
            "instructions": "Spiega e raggruppa le domande. Raccogli le risposte senza inventarle. Restituisci questo JSON mantenendo question_id e fingerprint. Compila answer, oppure action=defer per Non lo so, action=obsolete per una domanda non più pertinente. Lascia answer=null per non rispondere. L'importazione richiede anteprima e conferma; modifica solo la memoria, nessun dispositivo.",
            "questions": items}


def preview_answers(data, document):
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise ValueError("Formato non valido: usa il file esportato dalla pagina Domande.")
    items = document.get("questions")
    if not isinstance(items, list) or len(items) > 300:
        raise ValueError("Il file deve contenere al massimo 300 domande.")
    questions = {q["question_id"]: q for q in data.get("questions", [])}
    seen, plan = set(), []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Domanda non valida.")
        action = item.get("action", "answer")
        answer = item.get("answer")
        if action == "answer" and answer is None:
            continue
        qid = item.get("question_id")
        if not isinstance(qid, str) or qid in seen:
            raise ValueError("Identificativo mancante o duplicato.")
        seen.add(qid)
        q = questions.get(qid)
        if not q or q.get("status") != "open" or item.get("fingerprint") != fingerprint(q):
            raise ValueError("Una domanda è cambiata o è già chiusa: scarica nuovamente le domande.")
        if action not in {"answer", "defer", "obsolete"}:
            raise ValueError("Azione non valida.")
        if action == "answer" and (not isinstance(answer, str) or not answer.strip() or len(answer) > 2000):
            raise ValueError("Ogni risposta deve contenere da 1 a 2000 caratteri.")
        text = "Non lo so" if action == "defer" else answer
        interpretation = (interpret_answer(q, text) if action != "obsolete" else
                          {"kind": "obsolete", "summary": "Chiudo questa domanda come non più pertinente; non elimino sensori o stanze."})
        plan.append({"question_id": qid, "action": action, "answer": text,
                     "question": q.get("display_prompt") or q.get("prompt"),
                     "interpretation": interpretation})
    return plan


def import_answers(data, document, now):
    plan = preview_answers(data, document)
    staged = deepcopy(data)
    for item in plan:
        if item["action"] == "obsolete":
            q = next(q for q in staged["questions"] if q["question_id"] == item["question_id"])
            q.update(status="obsolete", updated_at=now.isoformat(), interpretation=item["interpretation"])
        else:
            apply_answer(staged, item["question_id"], item["answer"], now)
    data.update(staged)
    return plan
