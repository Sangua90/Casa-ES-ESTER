"""Conservative, traceable use of confirmed memory in Shadow evaluations."""
from dataclasses import replace
import re
import unicodedata

from .models import DecisionStatus


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower())


def active_knowledge(items):
    # Preview documents and proposals are deliberately not accepted here.
    return [k for k in items if k.get("status", "active") == "active"]


def prepare_profiles(profiles, knowledge, classifications=None):
    """Accept only explicit energy entity IDs with compatible units; never guess names."""
    candidates = {}
    by_id = {p.entity_id: p for p in profiles}
    applications = []
    for k in active_knowledge(knowledge):
        if (k.get("domain") or k.get("category")) != "energy":
            continue
        text = k.get("statement") or k.get("text") or ""
        matches = list(re.finditer(r"\bsensor\.[a-z0-9_]+\b", text))
        for index, match in enumerate(matches):
            entity_id = match.group()
            # Do not let a preceding sensor's label leak into this association.
            start = matches[index-1].end() if index else 0
            end = matches[index+1].start() if index+1 < len(matches) else len(text)
            before = text[start:match.start()].strip().rstrip("` :")
            prefix = normalized(re.split(r"[;,.]", before)[-1])
            after = text[match.end():end]
            suffix = re.match(r"^[`\s]*per\s+([^,;.]+)", after, re.IGNORECASE)
            if suffix:
                prefix = normalized(suffix.group(1))
            role = None
            if "soc" in prefix or "statodicarica" in prefix:
                role = "battery"
            elif "potenzabatteria" in prefix:
                role = "battery_power"
            elif "fvpotenzial" in prefix or "stimato" in prefix:
                continue  # A prediction must not become measured PV.
            elif "fv" in prefix and ("reale" in prefix or "perfv" in prefix):
                role = "solar_power"
            elif "consumototale" in prefix or "icarichi" in prefix:
                role = "load_power"
            elif "rete" in prefix:
                role = "grid_power"
            if not role:
                continue
            profile = by_id.get(entity_id)
            valid_unit = profile and (profile.unit == "%" if role == "battery" else profile.unit in {"W", "kW"})
            override = (classifications or {}).get(entity_id, {}).get("role")
            if profile and profile.attributes.get("classification_source") == "user":
                override = profile.role
            status = "candidate" if valid_unit and (not override or override == role) else "needs_review"
            row = {"knowledge_id": k.get("knowledge_id"), "entity_id": entity_id, "role": role, "status": status}
            applications.append(row)
            if status == "candidate":
                candidates.setdefault(entity_id, set()).add(role)
    roles = {entity: next(iter(values)) for entity, values in candidates.items() if len(values) == 1}
    # Multiple sensors claiming the same whole-house role are ambiguous.
    for role in set(roles.values()):
        ids = [entity for entity, value in roles.items() if value == role]
        if len(ids) > 1:
            for entity in ids:
                roles.pop(entity)
    for row in applications:
        if row["status"] == "candidate":
            row["status"] = "applied" if roles.get(row["entity_id"]) == row["role"] else "conflict"
    result = [replace(p, role=roles[p.entity_id], attributes={**p.attributes, "classification_source": "confirmed_knowledge"})
              if p.entity_id in roles else p for p in profiles]
    return result, applications


def relevant_knowledge(knowledge, category, area, profiles):
    names = {normalized(area)} if area else set()
    names.update(normalized(p.attributes.get("area_name")) for p in profiles if p.area_id == area and p.attributes.get("area_name"))
    return [k for k in active_knowledge(knowledge)
            if (k.get("domain") or k.get("category")) == category
            and (not k.get("area_id") or normalized(k["area_id"]) in names)]


def apply_constraints(decisions, profiles, knowledge):
    """Block unsupported proposals and show the exact memory used; no confidence boost."""
    for decision in decisions:
        notes = relevant_knowledge(knowledge, decision.category, decision.area_id, profiles)
        decision.evidence["knowledge_context"] = [
            {"knowledge_id": k.get("knowledge_id"), "statement": k.get("statement") or k.get("text"),
             "scope": k.get("scope"), "application": "context_only"} for k in notes]
        blockers = []
        for k, reference in zip(notes, decision.evidence["knowledge_context"]):
            text = (k.get("statement") or k.get("text") or "").lower()
            reason = None
            if decision.category == "lighting" and decision.evidence.get("lighting_plan", {}).get("strategy") == "would_turn_off" and any(w in text for w in ("immobile", "fermo", "dorme", "divano")):
                reason = "La memoria segnala presenza possibile senza movimento: non propongo lo spegnimento sulla sola assenza rilevata."
            if decision.category == "hot_water" and any(w in text for w in ("target fisso", "temperatura dinamica")) and any(w in text for w in ("non", "nessun", "dinamic")):
                reason = "Hai richiesto ACS adattiva: il piano con target fisso non soddisfa questa richiesta. Serve verificare previsione dei prelievi e modello di recupero; non invento una temperatura."
            if decision.category == "climate" and "multisplit" in text and len({p.state for p in profiles if p.role == "climate"} & {"heat", "cool"}) > 1:
                reason = "La memoria segnala un multisplit: verificare il gruppo di split prima di proporre modalità incompatibili."
            if reason:
                blockers.append({"knowledge_id": k.get("knowledge_id"), "reason": reason})
                reference["application"] = "constraint_applied"
        if blockers:
            decision.evidence["proposal_before_knowledge"] = decision.proposed_action
            decision.evidence["title_before_knowledge"] = decision.title
            decision.title = {"lighting": "Presenza incerta: luce mantenuta",
                              "hot_water": "ACS adattiva: modello da verificare",
                              "climate": "Climatizzazione: gruppo multisplit da verificare"}.get(decision.category, decision.title)
            decision.evidence["knowledge_blockers"] = blockers
            decision.evidence["question"] = None
            decision.proposed_action = "Continuare a osservare: proposta sospesa dai vincoli memorizzati"
            decision.reasoning = " ".join(b["reason"] for b in blockers)
            decision.status = DecisionStatus.SUPPRESSED
            decision.confidence = min(decision.confidence, .4)
    return decisions
