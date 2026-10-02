"""Admin-only internal services; none accept executable service names."""
from __future__ import annotations

from datetime import timedelta
from copy import deepcopy
import json
from zoneinfo import ZoneInfo
from time import monotonic
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util

from .ai.factory import create_provider
from .const import DOMAIN, EVENT_FEEDBACK
from .home import MODES, ROLES
from .usage import validate_profile
from .questions import apply_answer
from .question_files import export_questions, preview_answers, import_answers
from .diagnostics_report import learning_report
from .const import VERSION
from .language_pipeline import interpret_and_store
from .language import store_teaching_items
from .knowledge_files import prepare_documents, append_documents
from .snapshots import create_snapshot, restore_snapshot, portable_memory
from .replay import run_historical_replay
from .scenario import simulate_scenario
from .discovery import discover_entities

TEXT = vol.All(cv.string, vol.Length(min=1, max=2000))
TEACH_TEXT = vol.All(cv.string, vol.Length(min=1, max=12000))
LONG_TEXT = vol.All(cv.string, vol.Length(min=2, max=100000))
SHORT = vol.All(cv.string, vol.Length(min=1, max=100))


def register_services(hass):
    last_ai = [float("-inf")]

    def runtime():
        entries = [e for e in hass.config_entries.async_entries(DOMAIN)
                   if getattr(e, "runtime_data", None) is not None and e.state.value == "loaded"]
        if not entries:
            raise ServiceValidationError("E.S.T.E.R. is not loaded")
        return entries[0].runtime_data

    def checkpoint(coordinator, label, reason):
        return create_snapshot(coordinator.storage.data, dt_util.utcnow(), label, reason)

    async def add_context(call):
        coordinator = runtime()
        now = dt_util.utcnow()
        start = dt_util.parse_datetime(call.data.get("starts_at", now.isoformat()))
        end = dt_util.parse_datetime(call.data.get("ends_at", (now + timedelta(hours=24)).isoformat()))
        if start is None or end is None or start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ServiceValidationError("Use timezone-aware ISO timestamps; ends_at must follow starts_at")
        event = {"event_id": str(uuid4()), "label": call.data["label"],
                 "mode": call.data.get("mode", "normal"), "areas": call.data.get("areas", []),
                 "starts_at": start.isoformat(), "ends_at": end.isoformat(),
                 "notes": call.data.get("notes", ""), "source": "user"}
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di aggiungere contesto", event["label"])
            coordinator.storage.data.setdefault("context_events", []).append(event)
            del coordinator.storage.data["context_events"][:-100]
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def remove_context(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            events = coordinator.storage.data["context_events"]
            if not any(e["event_id"] == call.data["event_id"] for e in events):
                raise ServiceValidationError("Unknown context")
            coordinator.storage.data["context_events"] = [e for e in events if e["event_id"] != call.data["event_id"]]
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def add_feedback(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            decision = next((d for d in coordinator.storage.data["decisions"]
                             if d["decision_id"] == call.data["decision_id"]), None)
            if decision is None:
                raise ServiceValidationError("Unknown or expired decision")
            feedback = {**dict(call.data), "feedback_id": str(uuid4()), "created_at": dt_util.utcnow().isoformat(),
                        "category": decision["category"]}
            # Repeated feedback replaces an earlier rating instead of multiplying its weight.
            coordinator.storage.data["feedback"] = [f for f in coordinator.storage.data["feedback"]
                                                    if f["decision_id"] != decision["decision_id"]]
            decision["feedback"] = feedback
            await coordinator.storage.add_feedback(feedback)
        hass.bus.async_fire(EVENT_FEEDBACK, feedback)
        await coordinator.async_request_refresh()

    async def classify(call):
        coordinator = runtime()
        entity_id = call.data["entity_id"]
        if hass.states.get(entity_id) is None:
            raise ServiceValidationError("Unknown entity")
        if "area_id" in call.data:
            from homeassistant.helpers import area_registry
            if area_registry.async_get(hass).async_get_area(call.data["area_id"]) is None:
                raise ServiceValidationError("Unknown area")
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di classificare entità", entity_id)
            coordinator.storage.data["classifications"][entity_id] = {k: v for k, v in call.data.items() if k != "entity_id"}
            await coordinator.storage.async_save()
        coordinator.history.last_read = None
        await coordinator.async_request_refresh()

    async def preference(call):
        coordinator = runtime()
        key, value = call.data["key"], call.data["value"]
        valid = (
            key.startswith("comfort:") and 5 <= value <= 35
            or key.startswith("soil_min:") and 0 <= value <= 100
            or key == "energy_price_eur_kwh" and 0 <= value <= 5
            or key == "gas_price_eur_m3" and 0 <= value <= 10
            or key == "battery_reserve_percent" and 0 <= value <= 100
            or key.startswith("climate_power_kw:") and 0 < value <= 30
            or key == "battery_capacity_kwh" and 0 < value <= 500
            or key == "battery_target_soc" and 0 <= value <= 100
            or key == "battery_target_hour_local" and 0 <= value <= 23
            or key == "base_load_w" and 0 <= value <= 50000
            or key == "grid_limit_w" and 0 <= value <= 100000
            or key == "inverter_limit_w" and 0 <= value <= 100000
            or key == "phase_limit_w" and 0 <= value <= 50000
            or key == "hot_water_target_c" and 35 <= value <= 70
            or key == "heat_pump_cop" and 1 <= value <= 8
            or key == "boiler_efficiency" and 0.5 <= value <= 1.1
            or key.startswith("lux_on:") and 0 <= value <= 5000
            or key == "night_start_hour" and 0 <= value <= 23
            or key == "morning_hour" and 0 <= value <= 23
            or key.startswith("objective_weight:") and 0 <= value <= 1
            or key == "season_winter_below_c" and -30 <= value <= 30
            or key == "season_summer_above_c" and 5 <= value <= 50
        )
        if not valid:
            raise ServiceValidationError(
                "Supported: comfort:<area>, soil_min:<area>, energy_price_eur_kwh, "
                "gas_price_eur_m3, battery_reserve_percent, climate_power_kw:<area>, "
                "battery_capacity_kwh, battery_target_soc, battery_target_hour_local, "
                "base_load_w, grid_limit_w, inverter_limit_w, phase_limit_w, "
                "hot_water_target_c, heat_pump_cop, boiler_efficiency, lux_on:<area>, "
                "night_start_hour, morning_hour, objective_weight:<name>, "
                "season_winter_below_c, season_summer_above_c"
            )
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di modificare preferenza", key)
            coordinator.storage.data.setdefault("preferences", {})[key] = value
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def set_usage_profile(call):
        coordinator = runtime()
        from homeassistant.helpers import area_registry
        area_id = call.data["area_id"]
        if area_registry.async_get(hass).async_get_area(area_id) is None:
            raise ServiceValidationError("Unknown area")
        profile_id = call.data.get("profile_id") or str(uuid4())
        profile = {
            "profile_id": profile_id,
            "area_id": area_id,
            "label": call.data["label"],
            "weekdays": list(call.data["weekdays"]),
            "start_time": call.data["start_time"],
            "end_time": call.data["end_time"],
            "expected_occupancy": float(call.data["expected_occupancy"]),
            "comfort_c": call.data.get("comfort_c"),
            "notes": call.data.get("notes", ""),
            "source": "user",
        }
        if not validate_profile(profile):
            raise ServiceValidationError("Invalid usage profile")
        if profile["comfort_c"] is not None and not 5 <= float(profile["comfort_c"]) <= 35:
            raise ServiceValidationError("comfort_c must be 5–35 °C")
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di modificare routine", profile["label"])
            profiles = coordinator.storage.data.setdefault("usage_profiles", [])
            coordinator.storage.data["usage_profiles"] = [p for p in profiles if p.get("profile_id") != profile_id]
            coordinator.storage.data["usage_profiles"].append(profile)
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()
        return {"profile_id": profile_id, "profile": profile}

    async def remove_usage_profile(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            profiles = coordinator.storage.data.setdefault("usage_profiles", [])
            if not any(p.get("profile_id") == call.data["profile_id"] for p in profiles):
                raise ServiceValidationError("Unknown usage profile")
            coordinator.storage.data["usage_profiles"] = [p for p in profiles if p.get("profile_id") != call.data["profile_id"]]
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def answer_question(call):
        coordinator = runtime()
        question_id = call.data["question_id"]
        answer = call.data["answer"].strip()
        if not answer:
            raise ServiceValidationError("Answer cannot be empty")
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di apprendere risposta", question_id)
            try:
                interpretation = apply_answer(coordinator.storage.data, question_id, answer, dt_util.utcnow())
            except KeyError:
                raise ServiceValidationError("Unknown question") from None
            except ValueError:
                raise ServiceValidationError("Question already answered") from None
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()
        return {"question_id": question_id, "status": "deferred" if interpretation["kind"] == "deferred" else "answered", "interpretation": interpretation}

    async def export_learning_report(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            return learning_report(coordinator.storage.data, coordinator.data or {}, VERSION,
                                   dt_util.utcnow(), coordinator.entry.options.get("ai_provider", "disabled"))

    async def export_question_file(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            current = coordinator.data or {}
            document = export_questions(coordinator.storage.data, current.get("rooms", {}), dt_util.utcnow())
            document["diagnostic_context"] = {key: current.get(key) for key in ("data_suggestions", "anomalies", "knowledge_application", "progress")}
            return document

    async def import_question_file(call):
        coordinator = runtime()
        try:
            document = json.loads(call.data["file_json"])
            async with coordinator.storage.lock:
                plan = preview_answers(coordinator.storage.data, document)
                if call.data.get("confirm", False) and plan:
                    snapshot = checkpoint(coordinator, "Prima di importare risposte", "question_file")
                    snapshot["memory"]["questions"] = deepcopy(coordinator.storage.data.get("questions", []))
                    import_answers(coordinator.storage.data, document, dt_util.utcnow())
                    await coordinator.storage.async_save()
        except (ValueError, TypeError) as err:
            raise ServiceValidationError(str(err)) from None
        if call.data.get("confirm", False):
            await coordinator.async_request_refresh()
        return {"items": plan, "confirmed": call.data.get("confirm", False)}

    async def select_voice_question(call):
        coordinator = runtime()
        question_id = call.data["question_id"]
        question = next(
            (q for q in coordinator.storage.data.setdefault("questions", [])
             if q.get("question_id") == question_id and q.get("status") == "open"),
            None,
        )
        if question is None:
            raise ServiceValidationError("Unknown or closed question")
        async with coordinator.storage.lock:
            coordinator.storage.data["voice_question_id"] = question_id
            await coordinator.storage.async_save()

    async def dismiss_question(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            question = next((q for q in coordinator.storage.data.setdefault("questions", [])
                             if q.get("question_id") == call.data["question_id"]), None)
            if question is None:
                raise ServiceValidationError("Unknown question")
            question["status"] = "dismissed"
            question["updated_at"] = dt_util.utcnow().isoformat()
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def interpret_message(call):
        coordinator = runtime()
        try:
            return await interpret_and_store(hass, coordinator, call.data["message"], preview=True)
        except Exception:
            raise HomeAssistantError("Natural-language interpretation failed; no memory was changed") from None

    async def preview_knowledge_files(call):
        coordinator = runtime()
        try:
            documents = json.loads(call.data["files_json"])
            return await prepare_documents(coordinator, documents)
        except (ValueError, TypeError) as err:
            raise ServiceValidationError(str(err)) from None

    async def confirm_teaching(call):
        coordinator=runtime()
        proposal_id=call.data["proposal_id"]
        async with coordinator.storage.lock:
            pending=coordinator.storage.data.setdefault("pending_teachings",[])
            proposal=next((p for p in pending if p.get("proposal_id")==proposal_id),None)
            if proposal is None: raise ServiceValidationError("Unknown or expired teaching proposal")
            previous = deepcopy(coordinator.storage.data)
            checkpoint(coordinator,"Prima di confermare insegnamento",proposal.get("original_text","")[:200])
            try:
                saved = (append_documents(coordinator.storage.data, proposal, dt_util.utcnow())
                         if proposal.get("source") == "knowledge_files" else
                         store_teaching_items(coordinator.storage.data,proposal,dt_util.utcnow()))
                coordinator.storage.data["pending_teachings"]=[p for p in pending if p.get("proposal_id")!=proposal_id]
                await coordinator.storage.async_save()
            except ValueError as err:
                coordinator.storage.data.clear()
                coordinator.storage.data.update(previous)
                raise ServiceValidationError(str(err)) from None
            except Exception:
                coordinator.storage.data.clear()
                coordinator.storage.data.update(previous)
                raise
        await coordinator.async_request_refresh()
        return {"saved":len(saved),"summary":f"Ho memorizzato {len(saved)} informazioni confermate.","items":saved}

    async def discard_teaching(call):
        coordinator=runtime()
        async with coordinator.storage.lock:
            pending=coordinator.storage.data.setdefault("pending_teachings",[])
            coordinator.storage.data["pending_teachings"]=[p for p in pending if p.get("proposal_id")!=call.data["proposal_id"]]
            await coordinator.storage.async_save()

    async def export_memory(call):
        coordinator = runtime()
        return {"version": 1, **portable_memory(coordinator.storage.data)}

    async def set_flexible_load(call):
        coordinator = runtime()
        entity_id = call.data["entity_id"]
        if hass.states.get(entity_id) is None:
            raise ServiceValidationError("Unknown entity")
        item = {
            "load_id": call.data.get("load_id") or str(uuid4()),
            "name": call.data["name"],
            "entity_id": entity_id,
            "power_w": float(call.data["power_w"]),
            "duration_minutes": int(call.data.get("duration_minutes", 60)),
            "priority": int(call.data.get("priority", 50)),
            "min_soc": float(call.data.get("min_soc", 0)),
            "interruptible": bool(call.data.get("interruptible", True)),
            "non_interruptible": bool(call.data.get("non_interruptible", False)),
            "phase": call.data.get("phase", "unknown"),
            "min_on_minutes": int(call.data.get("min_on_minutes", 0)),
            "min_off_minutes": int(call.data.get("min_off_minutes", 0)),
            "max_starts_per_day": int(call.data.get("max_starts_per_day", 99)),
            "window_start": call.data.get("window_start"),
            "window_end": call.data.get("window_end"),
            "allow_grid_w": float(call.data.get("allow_grid_w", 0)),
            "battery_discharge_limit_w": float(call.data.get("battery_discharge_limit_w", 0)),
            "power_sensor": call.data.get("power_sensor"),
            "area_id": call.data.get("area_id"),
            "source": "user",
        }
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima di modificare carico energetico", item["name"])
            loads = coordinator.storage.data.setdefault("flexible_loads", [])
            coordinator.storage.data["flexible_loads"] = [x for x in loads if x.get("load_id") != item["load_id"]]
            coordinator.storage.data["flexible_loads"].append(item)
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()
        return item

    async def remove_flexible_load(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            loads = coordinator.storage.data.setdefault("flexible_loads", [])
            if not any(x.get("load_id") == call.data["load_id"] for x in loads):
                raise ServiceValidationError("Unknown flexible load")
            coordinator.storage.data["flexible_loads"] = [x for x in loads if x.get("load_id") != call.data["load_id"]]
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()

    async def run_replay(call):
        coordinator = runtime()
        try:
            return await run_historical_replay(
                hass,
                coordinator,
                days=call.data.get("days", 7),
                step_minutes=call.data.get("step_minutes", 30),
            )
        except RuntimeError as err:
            raise ServiceValidationError(str(err)) from None

    async def simulate(call):
        coordinator = runtime()
        now = dt_util.utcnow()
        profiles = discover_entities(hass, coordinator.storage.data["classifications"])
        result = simulate_scenario(
            engine=coordinator.engine,
            profiles=profiles,
            data=coordinator.storage.data,
            now=now,
            local_tz=ZoneInfo(hass.config.time_zone),
            mode=call.data.get("mode", "normal"),
            area_id=call.data.get("area_id"),
            comfort_delta_c=call.data.get("comfort_delta_c", 0),
            energy_price_multiplier=call.data.get("energy_price_multiplier", 1),
        )
        async with coordinator.storage.lock:
            coordinator.storage.data["last_scenario"] = result
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()
        return result

    async def snapshot_memory(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            snap = create_snapshot(
                coordinator.storage.data,
                dt_util.utcnow(),
                call.data.get("label", "Snapshot manuale"),
                call.data.get("reason", "Creato manualmente"),
            )
            await coordinator.storage.async_save()
        await coordinator.async_request_refresh()
        return {k: snap[k] for k in ("snapshot_id", "created_at", "label", "reason")}

    async def rollback_memory(call):
        coordinator = runtime()
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima del rollback", call.data["snapshot_id"])
            try:
                restored = restore_snapshot(coordinator.storage.data, call.data["snapshot_id"])
            except KeyError:
                raise ServiceValidationError("Unknown snapshot") from None
            await coordinator.storage.async_save()
        coordinator.history.last_read = None
        await coordinator.async_request_refresh()
        return {"restored_snapshot_id": restored["snapshot_id"], "label": restored["label"]}

    async def import_memory(call):
        coordinator = runtime()
        try:
            incoming = json.loads(call.data["memory_json"])
        except json.JSONDecodeError:
            raise ServiceValidationError("Invalid JSON") from None
        if not isinstance(incoming, dict):
            raise ServiceValidationError("Memory import must be an object")
        allowed = set(portable_memory(coordinator.storage.data))
        if any(key not in allowed and key != "version" for key in incoming):
            raise ServiceValidationError("Import contains unsupported keys")
        async with coordinator.storage.lock:
            checkpoint(coordinator, "Prima dell'import memoria", "Import JSON")
            for key in allowed:
                if key in incoming:
                    expected_dict = key in {"preferences", "classifications", "safety_policies", "fallback_policies"}
                    if expected_dict and not isinstance(incoming[key], dict):
                        raise ServiceValidationError(f"{key} must be an object")
                    if not expected_dict and not isinstance(incoming[key], list):
                        raise ServiceValidationError(f"{key} must be a list")
                    coordinator.storage.data[key] = incoming[key]
            await coordinator.storage.async_save()
        coordinator.history.last_read = None
        await coordinator.async_request_refresh()
        return {"imported": True, "keys": sorted(k for k in incoming if k in allowed)}

    async def evaluate_now(call):
        await runtime().async_request_refresh()

    async def summary(call):
        coordinator = runtime()
        data = coordinator.data or {}
        return {"shadow_mode": True, "real_actuation_enabled": False,
                "inventory": data.get("inventory", {}), "rooms": data.get("rooms", {}),
                "contexts": data.get("contexts", []), "history": data.get("history", {}),
                "data_suggestions": data.get("data_suggestions", []), "usage": data.get("usage", {}),
                "usage_profiles": coordinator.storage.data.get("usage_profiles", []),
                "questions": coordinator.storage.data.get("questions", [])[-100:],
                "knowledge": coordinator.storage.data.get("knowledge", [])[-100:],
                "knowledge_coverage": data.get("knowledge_coverage", {}),
                "knowledge_gaps": data.get("knowledge_gaps", []),
                "thermal_models": data.get("thermal_models", {}),
                "ventilation_models": data.get("ventilation_models", {}),
                "hot_water_models": data.get("hot_water_models", {}),
                "occupancy_models": data.get("occupancy_models", {}),
                "calibration": data.get("calibration", {}),
                "automation_migration": data.get("automation_migration", {}),
                "migration_readiness": data.get("migration_readiness", {}),
                "flexible_loads": coordinator.storage.data.get("flexible_loads", []),
                "kpis": data.get("kpis", {}),
                "autonomy_health": data.get("autonomy_health", {}),
                "season": data.get("season", {}),
                "anomalies": data.get("anomalies", []),
                "last_replay": coordinator.storage.data.get("last_replay", {}),
                "last_scenario": coordinator.storage.data.get("last_scenario", {}),
                "memory_versions": [
                    {k: s.get(k) for k in ("snapshot_id","created_at","label","reason")}
                    for s in coordinator.storage.data.get("memory_versions", [])[-20:]
                ],
                "decisions": coordinator.storage.data["decisions"][-call.data.get("limit", 20):]}

    async def explain(call):
        coordinator = runtime()
        decision = next((d for d in coordinator.storage.data["decisions"] if d["decision_id"] == call.data["decision_id"]), None)
        if decision is None:
            raise ServiceValidationError("Unknown or expired decision")
        options = coordinator.entry.options
        if options.get("ai_provider", "disabled") == "disabled":
            return {"provider": "local", "text": decision["reasoning"], "alternatives": decision["alternatives"]}
        if monotonic() - last_ai[0] < 60:
            raise ServiceValidationError("Wait 60 seconds between AI requests")
        last_ai[0] = monotonic()
        try:
            provider = create_provider(hass, options)
            # No entity IDs, people, raw state attributes, context notes or credentials leave HA.
            safe = {k: decision[k] for k in ("category", "title", "proposed_action", "reasoning", "confidence", "risk")}
            response = await provider.async_explain(decision=safe, context={"shadow_mode": True})
            return {"provider": response.provider, "text": response.text}
        except Exception as err:
            raise HomeAssistantError("AI unavailable; local reasoning remains available") from None

    schemas = {
        "add_context": (add_context, {vol.Required("label"): SHORT, vol.Optional("mode", default="normal"): vol.In(MODES),
            vol.Optional("starts_at"): cv.string, vol.Optional("ends_at"): cv.string,
            vol.Optional("areas", default=[]): [SHORT], vol.Optional("notes"): TEXT}),
        "remove_context": (remove_context, {vol.Required("event_id"): SHORT}),
        "add_feedback": (add_feedback, {vol.Required("decision_id"): SHORT,
            vol.Required("rating"): vol.In(["correct", "wrong", "partial"]), vol.Optional("comment"): TEXT}),
        "classify_entity": (classify, {vol.Required("entity_id"): cv.entity_id,
            vol.Required("role"): vol.In(ROLES), vol.Optional("area_id"): SHORT}),
        "set_preference": (preference, {vol.Required("key"): SHORT, vol.Required("value"): vol.Coerce(float)}),
        "set_usage_profile": (set_usage_profile, {
            vol.Optional("profile_id"): SHORT,
            vol.Required("area_id"): SHORT,
            vol.Required("label"): SHORT,
            vol.Required("weekdays"): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
            vol.Required("start_time"): vol.Match(r"^(?:[01]\\d|2[0-3]):[0-5]\\d$"),
            vol.Required("end_time"): vol.Match(r"^(?:[01]\\d|2[0-3]):[0-5]\\d$"),
            vol.Required("expected_occupancy"): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Optional("comfort_c"): vol.All(vol.Coerce(float), vol.Range(min=5, max=35)),
            vol.Optional("notes"): TEXT,
        }),
        "remove_usage_profile": (remove_usage_profile, {vol.Required("profile_id"): SHORT}),
        "answer_question": (answer_question, {vol.Required("question_id"): SHORT, vol.Required("answer"): TEXT}),
        "export_question_file": (export_question_file, {}),
        "export_learning_report": (export_learning_report, {}),
        "import_question_file": (import_question_file, {vol.Required("file_json"): vol.All(cv.string, vol.Length(min=2, max=1000000)), vol.Optional("confirm", default=False): cv.boolean}),
        "select_voice_question": (select_voice_question, {vol.Required("question_id"): SHORT}),
        "dismiss_question": (dismiss_question, {vol.Required("question_id"): SHORT}),
        "interpret_message": (interpret_message, {vol.Required("message"): TEACH_TEXT, vol.Optional("preview", default=True): cv.boolean}),
        "confirm_teaching": (confirm_teaching, {vol.Required("proposal_id"): SHORT}),
        "discard_teaching": (discard_teaching, {vol.Required("proposal_id"): SHORT}),
        "export_memory": (export_memory, {}),
        "preview_knowledge_files": (preview_knowledge_files, {vol.Required("files_json"): LONG_TEXT}),
        "set_flexible_load": (set_flexible_load, {
            vol.Optional("load_id"): SHORT,
            vol.Required("name"): SHORT,
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("power_w"): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
            vol.Optional("duration_minutes", default=60): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Optional("priority", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            vol.Optional("min_soc", default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional("interruptible", default=True): cv.boolean,
            vol.Optional("non_interruptible", default=False): cv.boolean,
            vol.Optional("phase", default="unknown"): vol.In(["l1", "l2", "l3", "three_phase", "unknown"]),
            vol.Optional("min_on_minutes", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
            vol.Optional("min_off_minutes", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
            vol.Optional("max_starts_per_day", default=99): vol.All(vol.Coerce(int), vol.Range(min=1, max=999)),
            vol.Optional("window_start"): vol.Match(r"^(?:[01]\d|2[0-3]):[0-5]\d$"),
            vol.Optional("window_end"): vol.Match(r"^(?:[01]\d|2[0-3]):[0-5]\d$"),
            vol.Optional("allow_grid_w", default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
            vol.Optional("battery_discharge_limit_w", default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=50000)),
            vol.Optional("power_sensor"): cv.entity_id,
            vol.Optional("area_id"): SHORT,
        }),
        "remove_flexible_load": (remove_flexible_load, {vol.Required("load_id"): SHORT}),
        "run_replay": (run_replay, {
            vol.Optional("days", default=7): vol.All(vol.Coerce(int), vol.Range(min=1, max=56)),
            vol.Optional("step_minutes", default=30): vol.All(vol.Coerce(int), vol.Range(min=30, max=240)),
        }),
        "simulate_scenario": (simulate, {
            vol.Optional("mode", default="normal"): vol.In(MODES),
            vol.Optional("area_id"): SHORT,
            vol.Optional("comfort_delta_c", default=0): vol.All(vol.Coerce(float), vol.Range(min=-5, max=5)),
            vol.Optional("energy_price_multiplier", default=1): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10)),
        }),
        "snapshot_memory": (snapshot_memory, {
            vol.Optional("label", default="Snapshot manuale"): SHORT,
            vol.Optional("reason", default="Creato manualmente"): TEXT,
        }),
        "rollback_memory": (rollback_memory, {vol.Required("snapshot_id"): SHORT}),
        "import_memory": (import_memory, {vol.Required("memory_json"): LONG_TEXT}),
        "evaluate": (evaluate_now, {}),
        "get_summary": (summary, {vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=100))}),
        "explain_decision": (explain, {vol.Required("decision_id"): SHORT}),
    }
    for name, (handler, schema) in schemas.items():
        async_register_admin_service(hass, DOMAIN, name, handler, schema=vol.Schema(schema),
            supports_response=SupportsResponse.ONLY if name in {"export_learning_report", "export_question_file", "import_question_file", "get_summary", "explain_decision", "set_usage_profile", "answer_question", "interpret_message", "preview_knowledge_files", "confirm_teaching", "export_memory", "set_flexible_load", "run_replay", "simulate_scenario", "snapshot_memory", "rollback_memory", "import_memory"} else SupportsResponse.NONE)
