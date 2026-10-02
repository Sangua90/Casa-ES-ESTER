"""Structured household knowledge for natural-language teaching."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
import re

from .usage import validate_profile

ALLOWED_INTENTS = {"preference", "context", "usage_profile", "knowledge_note", "feedback", "unknown"}
ALLOWED_MODES = {"normal", "vacation", "guests", "illness", "work_from_home"}
KNOWLEDGE_DOMAINS = {"presence","climate","lighting","hot_water","energy","ventilation","security","appliances","rooms","other"}
KNOWLEDGE_KINDS = {"preference","habit","rule","exception","temporary","constraint","fact","goal"}


def validate_interpretation(data: dict) -> dict:
    if not isinstance(data, dict):
        return {"intent": "unknown", "confidence": 0.0}
    intent = data.get("intent") if data.get("intent") in ALLOWED_INTENTS else "unknown"
    try: confidence=max(0.0,min(1.0,float(data.get("confidence",0))))
    except (TypeError,ValueError): confidence=0.0
    result={"intent":intent,"confidence":confidence}
    for key in ("area_id","key","value","mode","label","notes","text","start_time","end_time",
                "expected_occupancy","comfort_c","weekdays","duration_hours"):
        if key in data: result[key]=data[key]
    return result


def validate_teaching(data: dict, original_text: str) -> dict:
    """Normalize multi-item AI teaching output. It never contains executable actions."""
    if not isinstance(data,dict): data={}
    raw=data.get("items") if isinstance(data.get("items"),list) else []
    items=[]
    for entry in raw[:30]:
        if not isinstance(entry,dict): continue
        statement=str(entry.get("statement") or "").strip()[:1000]
        if not statement: continue
        domain=entry.get("domain") if entry.get("domain") in KNOWLEDGE_DOMAINS else "other"
        kind=entry.get("kind") if entry.get("kind") in KNOWLEDGE_KINDS else "fact"
        try: confidence=max(0.0,min(1.0,float(entry.get("confidence",.5))))
        except (TypeError,ValueError): confidence=.5
        item={"domain":domain,"kind":kind,"statement":statement,"confidence":confidence}
        for key in ("area_id","subject","condition","time_window","priority","supersedes_hint"):
            if entry.get(key) is not None: item[key]=str(entry[key])[:300]
        items.append(item)
    return {"summary":str(data.get("summary") or ("Ho separato quello che mi hai raccontato in %d informazioni."%len(items)))[:1000],
            "items":items,"original_text":original_text[:2000]}


def store_teaching_items(store: dict, teaching: dict, now: datetime) -> list[dict]:
    """Persist confirmed knowledge as versionable structured facts."""
    saved=[]
    knowledge=store.setdefault("knowledge",[])
    for item in teaching.get("items",[]):
        row={**item,"knowledge_id":str(uuid4()),"created_at":now.isoformat(),"updated_at":now.isoformat(),
             "source":"natural_language_confirmed","scope":"persistent","status":"active"}
        hint=(item.get("supersedes_hint") or "").strip().lower()
        if hint:
            for old in knowledge:
                hay=" ".join(str(old.get(k,"")) for k in ("statement","text","subject")).lower()
                if hint in hay and old.get("status","active")=="active":
                    old["status"]="superseded"; old["superseded_at"]=now.isoformat()
        knowledge.append(row); saved.append(row)
    del knowledge[:-1000]
    return saved


def knowledge_overview(store: dict) -> tuple[dict,list[dict]]:
    active=[k for k in store.get("knowledge",[]) if k.get("status","active")=="active"]
    coverage={}
    labels={
        "presence":"chi è in casa e quando","climate":"come preferite caldo e fresco",
        "lighting":"quando e perché usate le luci","hot_water":"quando vi serve acqua calda",
        "energy":"priorità tra FV, batteria, rete e carichi","ventilation":"quando arieggiare o ventilare",
        "security":"come deve comportarsi la sicurezza","appliances":"come usate gli apparecchi",
        "rooms":"come vengono usate le stanze","other":"altre abitudini della casa"}
    for domain in KNOWLEDGE_DOMAINS:
        n=sum(1 for k in active if (k.get("domain") or k.get("category"))==domain)
        coverage[domain]={"count":n,"meaning":("Ho già %d informazioni su %s."%(n,labels[domain])) if n else "Mi manca ancora capire "+labels[domain]+"."}
    gaps=[]
    for domain in ("presence","climate","lighting","hot_water","energy","ventilation","security"):
        if coverage[domain]["count"]==0:
            gaps.append({"domain":domain,"title":"Raccontami "+labels[domain],
                         "why":"Questa informazione mi aiuta a decidere come una persona che conosce davvero la casa."})
    return coverage,gaps


def apply_interpretation(store: dict, parsed: dict, now: datetime) -> dict:
    """Legacy bounded single-message memory update. Never performs device actions."""
    parsed=validate_interpretation(parsed); intent=parsed["intent"]
    if parsed["confidence"]<.7: intent="knowledge_note"
    if intent=="preference":
        key,value=parsed.get("key"),parsed.get("value")
        if isinstance(key,str) and key.startswith("comfort:"):
            try:value=float(value)
            except (TypeError,ValueError): intent="knowledge_note"
            else:
                if 5<=value<=35:
                    store.setdefault("preferences",{})[key]=value
                    return {"applied":"preference","key":key,"value":value}
                intent="knowledge_note"
    if intent=="context":
        mode=parsed.get("mode")
        if mode in ALLOWED_MODES:
            try: duration=min(24*30,max(1,float(parsed.get("duration_hours",24))))
            except (TypeError,ValueError): duration=24
            event={"event_id":str(uuid4()),"label":parsed.get("label") or mode,"mode":mode,
                   "areas":[parsed["area_id"]] if parsed.get("area_id") else [],
                   "starts_at":now.isoformat(),"ends_at":(now+timedelta(hours=duration)).isoformat(),
                   "notes":parsed.get("notes") or parsed.get("text") or "","source":"natural_language"}
            store.setdefault("context_events",[]).append(event); return {"applied":"context","event":event}
    if intent=="usage_profile":
        required=all(k in parsed for k in ("area_id","weekdays","start_time","end_time","expected_occupancy"))
        if required:
            profile={"profile_id":str(uuid4()),"area_id":parsed["area_id"],"label":parsed.get("label") or "Routine",
                     "weekdays":parsed["weekdays"],"start_time":parsed["start_time"],"end_time":parsed["end_time"],
                     "expected_occupancy":parsed["expected_occupancy"],"comfort_c":parsed.get("comfort_c"),
                     "notes":parsed.get("notes",""),"source":"natural_language"}
            if validate_profile(profile) and (profile["comfort_c"] is None or 5<=float(profile["comfort_c"])<=35):
                store.setdefault("usage_profiles",[]).append(profile); return {"applied":"usage_profile","profile":profile}
    note={"knowledge_id":str(uuid4()),"domain":"other","kind":"fact","category":"natural_language",
          "area_id":parsed.get("area_id"),"statement":parsed.get("text") or parsed.get("notes") or str(parsed),
          "text":parsed.get("text") or parsed.get("notes") or str(parsed),"scope":"persistent",
          "confidence":parsed.get("confidence",.5),"created_at":now.isoformat(),"source":"natural_language","status":"active"}
    store.setdefault("knowledge",[]).append(note); return {"applied":"knowledge_note","knowledge":note}


def local_interpret(message: str, area_ids: list[str]) -> dict:
    text=message.strip(); lower=text.lower(); area=next((a for a in area_ids if a.lower() in lower),None)
    temp=re.search(r"(?<!\d)([1-3]?\d(?:[.,]\d)?)\s*(?:°|gradi|grado|c\b)",lower)
    if area and temp and any(w in lower for w in ("voglio","prefer","comfort","tieni","tenere")):
        value=float(temp.group(1).replace(",","."))
        if 5<=value<=35:return {"intent":"preference","key":f"comfort:{area}","value":value,"area_id":area,"confidence":.96,"text":text}
    modes={"vacanza":"vacation","via":"vacation","ospiti":"guests","malat":"illness","lavoro da casa":"work_from_home","smart working":"work_from_home"}
    mode=next((v for token,v in modes.items() if token in lower),None)
    if mode:return {"intent":"context","mode":mode,"area_id":area,"duration_hours":72 if "weekend" in lower else 24,"label":text[:100],"notes":text,"confidence":.85,"text":text}
    return {"intent":"knowledge_note","area_id":area,"text":text,"confidence":.6}
