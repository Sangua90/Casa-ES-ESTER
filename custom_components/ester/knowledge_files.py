"""Additive, local knowledge documents. Never interpret content as commands."""
from __future__ import annotations

import hashlib
import json
import re
from uuid import uuid4

from .language import KNOWLEDGE_DOMAINS, KNOWLEDGE_KINDS


def identity(item: dict) -> tuple:
    return (item.get("domain", "other"), item.get("area_id", ""),
            " ".join((item.get("statement") or item.get("text") or "").casefold().split()))


def parse_documents(files: list) -> list[dict]:
    if not isinstance(files, list) or not 1 <= len(files) <= 5:
        raise ValueError("Scegli da uno a cinque file.")
    items = []
    total = 0
    for file in files:
        if not isinstance(file, dict) or set(file) != {"name", "content"}:
            raise ValueError("Documento non valido.")
        name, content = file["name"], file["content"]
        if not isinstance(name, str) or not 1 <= len(name) <= 150 or not isinstance(content, str):
            raise ValueError("Nome o contenuto del file non valido.")
        size = len(content.encode("utf-8"))
        total += size
        if not 1 <= size <= 32000 or total > 64000:
            raise ValueError("Limite: 32 KB per file, 64 KB complessivi.")
        suffix = name.rsplit(".", 1)[-1].lower()
        if suffix == "json":
            try:
                document = json.loads(content)
            except ValueError as err:
                raise ValueError("JSON non valido: " + name) from err
            if not isinstance(document, dict) or set(document) != {"format", "items"} or document["format"] != "ester-knowledge-v1":
                raise ValueError("Usa il formato ester-knowledge-v1, non un backup della memoria.")
            rows = document["items"]
        elif suffix in {"txt", "md"}:
            rows = [{"statement": p.strip(), "domain": "other", "kind": "fact"}
                    for p in re.split(r"\n\s*\n", content.replace("\r\n", "\n")) if p.strip()]
        else:
            raise ValueError("Sono supportati file JSON, TXT e Markdown.")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Il file non contiene informazioni.")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"statement", "domain", "kind", "area_id"}:
                raise ValueError("Ogni informazione può contenere solo statement, domain, kind e area_id.")
            statement = row.get("statement")
            if not isinstance(statement, str) or not 1 <= len(statement.strip()) <= 1000:
                raise ValueError("Dividi il testo in paragrafi da 1 a 1000 caratteri.")
            domain, kind = row.get("domain", "other"), row.get("kind", "fact")
            if domain not in KNOWLEDGE_DOMAINS or kind not in KNOWLEDGE_KINDS:
                raise ValueError("Argomento o tipo di informazione non riconosciuto.")
            area = row.get("area_id", "")
            if not isinstance(area, str) or len(area) > 100:
                raise ValueError("Identificativo della stanza non valido.")
            items.append({"statement": statement.strip(), "domain": domain, "kind": kind,
                          "area_id": area, "source_file": name, "source_digest": digest,
                          "confidence": 0.5})
            if len(items) > 100:
                raise ValueError("Carica al massimo 100 informazioni alla volta.")
    return items


def additions(existing: list[dict], items: list[dict]) -> list[dict]:
    seen = {identity(row) for row in existing}
    result = []
    for item in items:
        key = identity(item)
        if key not in seen:
            result.append(item)
            seen.add(key)
    if len(existing) + len(result) > 1000:
        raise ValueError("Spazio conoscenze insufficiente: nessuna informazione esistente è stata cancellata.")
    return result


def append_documents(store: dict, proposal: dict, now) -> list[dict]:
    """Recheck duplicates under the caller's lock, then append without replacement."""
    rows = additions(store.get("knowledge", []), proposal["items"])
    saved = [{**row, "knowledge_id": str(uuid4()), "source": "knowledge_file_confirmed",
              "created_at": now.isoformat(), "updated_at": now.isoformat(),
              "status": "active", "scope": "persistent"} for row in rows]
    store.setdefault("knowledge", []).extend(saved)
    return saved
