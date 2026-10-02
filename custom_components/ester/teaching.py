"""Bounded compilation of explicit teaching into reviewable household facts."""
from copy import deepcopy
from datetime import datetime, timedelta
from math import isfinite
import re
import unicodedata

from .brain import validate_effect
from .usage import validate_profile


def normalized(text):
    return unicodedata.normalize("NFKD", str(text).replace("€", " euro ").replace("°", " gradi ")).encode("ascii", "ignore").decode().lower()


def validate_routine(routine, area):
    allowed = {"start_time", "end_time", "weekdays", "expected_occupancy", "comfort_c"}
    if not isinstance(routine, dict) or set(routine)-allowed:
        raise ValueError("Abitudine non valida: orari, giorni e presenza prevista sono obbligatori.")
    result = {**deepcopy(routine), "area_id": area}
    if not validate_profile(result) or any(isinstance(d, bool) for d in result["weekdays"]):
        raise ValueError("Indica stanza, orari validi e giorni da 0 (lunedì) a 6 (domenica).")
    occupancy = result["expected_occupancy"]
    if isinstance(occupancy, bool) or not isfinite(occupancy):
        raise ValueError("Presenza prevista non valida.")
    comfort = result.get("comfort_c")
    if comfort is not None and (isinstance(comfort, bool) or not isinstance(comfort, (int, float)) or not isfinite(comfort) or not 5 <= comfort <= 35):
        raise ValueError("Comfort dell'abitudine: da 5 a 35 °C.")
    for field in ("start_time", "end_time"):
        hour, minute = map(int, result[field].split(":"))
        result[field] = f"{hour:02d}:{minute:02d}"
    return {k: v for k, v in result.items() if k != "area_id"}


def room_matches(text, rooms):
    matches = []
    for area, metadata in rooms.items():
        aliases = {normalized(area.replace("_", " ")), normalized(metadata.get("name", area))}
        for alias in aliases:
            match = re.search(r"(?<!\w)"+re.escape(alias)+r"(?!\w)", text)
            if match:
                matches.append((area, match.start(), match.end()))
    return {area for area, start, end in matches
            if not any(other != area and a <= start and b >= end and b-a > end-start for other, a, b in matches)}


def compile_item(item, rooms, now, local_tz=None):
    """Infer only explicit numeric values/windows; incomplete facts stay context."""
    row = deepcopy(item)
    text = normalized(row.get("statement") or row.get("text") or "")
    warnings = []
    local = now.astimezone(local_tz or now.tzinfo)
    if re.search(r"\b(oggi|domani)\b", text):
        day = local.date()+timedelta(days=int(bool(re.search(r"\bdomani\b", text))))
        row["starts_at"] = datetime.combine(day, datetime.min.time(), tzinfo=local.tzinfo).isoformat()
        row["expires_at"] = datetime.combine(day+timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo).isoformat()
        if row.get("routine"):
            row["routine"]["weekdays"] = [day.weekday()]
            routine = row["routine"]
            if routine["start_time"]>routine["end_time"]:
                end = datetime.strptime(routine["end_time"], "%H:%M").time()
                row["expires_at"] = datetime.combine(day+timedelta(days=1), end, tzinfo=local.tzinfo).isoformat()
    if row.get("effect") or row.get("routine"):
        return row
    row.pop("clarifications", None)
    mentioned = room_matches(text, rooms)
    area = row.get("area_id") or (next(iter(mentioned)) if len(mentioned) == 1 else "")
    if area and rooms and area not in rooms:
        warnings.append("La stanza indicata non è presente nell'inventario.")
        area = ""
    if len(mentioned) > 1 or mentioned and area and mentioned != {area}:
        warnings.append("Sono citate più stanze: separa le informazioni per stanza.")
        area = ""
    if area:
        row["area_id"] = area
    # Negations and conditional exceptions must not become unconditional targets/routines.
    bounded = not row.get("condition") and not re.search(r"\b(non|se|quando|purche|solo|solamente|eccetto|salvo|tranne|soltanto|a volte|stasera|questa|questo|prossima|prossimo|per ora)\b", text)
    if re.search(r"\boggi\b", text) and re.search(r"\bdomani\b", text):
        bounded = False
        warnings.append("Sono citati oggi e domani: separa le informazioni per data.")
    temperature = re.findall(r"(?<![\d.,-])(\d{1,2}(?:[.,]\d+)?)\s*(?:gradi|grado|°\s*c?|c\b)", text)
    wants = re.search(r"\b(voglio|vogliamo|prefer\w*|comfort|desider\w*)\b", text)
    if temperature and wants and bounded:
        if area and len(temperature) == 1:
            season = "winter" if "inverno" in text else "summer" if "estate" in text else "shoulder" if "mezza stagione" in text else "all"
            try:
                row["effect"] = validate_effect({"type":"comfort", "value":float(temperature[0].replace(",", ".")), "season":season}, area)
                row.update(domain="climate", kind="preference")
            except ValueError as err:
                warnings.append(str(err))
        else:
            warnings.append("Per applicare il comfort indica una sola stanza e una sola temperatura.")
    price = re.findall(r"(?<![\d.,-])(\d+(?:[.,]\d+)?)\s*(?:€|euro)\s*(?:/|al|per)?\s*kwh\b", text)
    if price and bounded and any(term in text for term in ("costo", "prezzo", "pago", "tariffa", "energia")):
        if len(price) == 1 and not area:
            try:
                row["effect"] = validate_effect({"type":"energy_price", "value":float(price[0].replace(",", "."))})
                row.update(domain="energy", kind="preference")
            except ValueError as err:
                warnings.append(str(err))
        else:
            warnings.append("Per il costo energia indica un solo prezzo riferito alla casa.")
    window = re.search(r"\b(?:dalle|dalla|da)\s+(\d{1,2})(?:[:.](\d{2}))?\s+(?:alle|alla|a|fino\s+alle)\s+(\d{1,2})(?:[:.](\d{2}))?\b", text)
    use = re.search(r"\b(lavor\w*|us[oa]|utilizz\w*|occup\w*|dorm\w*|present\w*)\b", text)
    if use and (window or re.search(r"\b(?:fino\s+alle|alle)\s+\d", text)) and bounded:
        days = []
        if "tutti i giorni" in text or "ogni giorno" in text:
            days = list(range(7))
        elif "feriali" in text or re.search(r"(?:dal|da) lunedi (?:al|a) venerdi", text):
            days = list(range(5))
        elif "weekend" in text or "fine settimana" in text:
            days = [5, 6]
        else:
            names = ("lunedi","martedi","mercoledi","giovedi","venerdi","sabato","domenica")
            weekdays = "|".join(names)
            span = re.search(r"\b(?:dal|da)\s+("+weekdays+r")\s+(?:al|a)\s+("+weekdays+r")\b", text)
            if span:
                start_day, end_day = names.index(span[1]), names.index(span[2])
                days = [(start_day+i)%7 for i in range((end_day-start_day)%7+1)]
            else:
                days = [i for i, day in enumerate(names) if day in text]
        if re.search(r"\b(oggi|domani)\b", text):
            day = local.date()+timedelta(days=int(bool(re.search(r"\bdomani\b", text))))
            days = [day.weekday()]
            row["expires_at"] = datetime.combine(day+timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo).isoformat()
        if window and area and days:
            start = f"{int(window[1]):02}:{int(window[2] or 0):02}"
            end = f"{int(window[3]):02}:{int(window[4] or 0):02}"
            try:
                if start==end:
                    raise ValueError("Orari uguali: chiarisci se intendi un giorno intero o un intervallo diverso.")
                row["routine"] = validate_routine({"start_time":start, "end_time":end,"weekdays":days,"expected_occupancy":1.0}, area)
                if re.search(r"\b(oggi|domani)\b", text) and start>end:
                    row["expires_at"] = datetime.combine(day+timedelta(days=1), datetime.strptime(end, "%H:%M").time(), tzinfo=local.tzinfo).isoformat()
                row["kind"] = "habit"
                if not row.get("effect"):
                    row["domain"] = "presence"
            except ValueError as err:
                warnings.append(str(err))
        else:
            warnings.append("Per prevedere l'uso servono stanza, ora iniziale, ora finale e giorni. I dati mancanti non sono stati inventati.")
    if window and use and row.get("effect", {}).get("type")=="comfort":
        effect = row.pop("effect")
        if row.get("routine"):
            row["routine"]["comfort_c"] = effect["value"]
        else:
            warnings.append("Il comfort associato all'uso richiede un'abitudine completa: non è stato applicato a tutte le ore.")
    if not bounded and (temperature and wants or window and use):
        warnings.append("La frase contiene una condizione o negazione: resta contesto da chiarire.")
    if warnings:
        row["clarifications"] = warnings
    return row


def compile_message(message, rooms, now, local_tz=None):
    clauses = [s.strip() for s in re.split(r"[;\n]+|(?<=[.!?])\s+", message) if s.strip()]
    if len(clauses) > 30 or any(len(clause)>1000 for clause in clauses):
        raise ValueError("Dividi il racconto in massimo 30 frasi, da massimo 1000 caratteri ciascuna.")
    items = [compile_item({"statement":clause[:1000],"domain":"other","kind":"fact","confidence":.7}, rooms, now, local_tz) for clause in clauses[:30]]
    return {"items":items, "summary":f"Ho separato {len(items)} informazioni: {sum(bool(r.get('effect') or r.get('routine')) for r in items)} con un significato operativo da verificare."}
