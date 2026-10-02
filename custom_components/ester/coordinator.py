"""Observe, learn and journal proposals without a device service boundary."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import logging
from zoneinfo import ZoneInfo

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_DECISION, EVENT_QUESTION, MAX_DECISIONS
from .decision_engine import EsterDecisionEngine
from .discovery import discover_entities, summarize_inventory
from .history import HistoryReader, sample_value
from .home import active_contexts, home_model, learn, occupancy_learning, timestamp
from .usage import usage_snapshot
from .policies import evaluate
from .quality import data_suggestions
from .models import RiskLevel, ImpactLevel
from .questions import merge_questions, retire_removed_questions
from .thermal import build_room_thermal_model
from .outcomes import evaluate_shadow_outcomes, calibration, calibrated_confidence
from .migration import legacy_automation_inventory
from .readiness import migration_readiness
from .ventilation import ventilation_model
from .hot_water import hot_water_model
from .occupancy import occupancy_model
from .managed_energy import update_runtime
from .optimizer import score_decision
from .kpi import shadow_kpis
from .health import autonomy_health
from .seasonal import season_context
from .anomaly import detect_anomalies
from .daily_forecast import daily_forecast
from .language import knowledge_overview
from .knowledge_policy import prepare_profiles
from .progress import progress_status

_LOGGER = logging.getLogger(__name__)


class EsterCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, entry, storage):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(minutes=5))
        self.entry, self.storage = entry, storage
        self.engine = EsterDecisionEngine(hass)
        self.history = HistoryReader(hass)

    async def _async_update_data(self):
        now = dt_util.utcnow()
        profiles = discover_entities(self.hass, self.storage.data["classifications"])
        profiles, knowledge_application = prepare_profiles(profiles, self.storage.data.get("knowledge", []), self.storage.data["classifications"])
        area_ids = {area.id for area in ar.async_get(self.hass).async_list_areas()}
        entity_ids = set(er.async_get(self.hass).entities) | {p.entity_id for p in profiles}
        history = await self.history.read(profiles, now)
        events = []
        async with self.storage.lock:
            data = self.storage.data
            live = data.setdefault("samples", {})
            learning = {}
            selected = {p.entity_id for p in profiles[:500]}
            for removed in set(live) - selected:
                del live[removed]
            for p in profiles[:500]:
                points = live.setdefault(p.entity_id, [])
                reported = timestamp(p.attributes.get("last_reported"))
                fresh = reported is not None and 0 <= now.timestamp() - reported <= 7200
                points.append({"t": now.timestamp(), "v": sample_value(p) if fresh else None})
                live[p.entity_id] = points = [s for s in points if now.timestamp() - s["t"] <= 86400][-300:]
                samples = history["samples"].get(p.entity_id, []) + points
                learning[p.entity_id] = learn(samples, now)
                if p.role == "presence":
                    learning[p.entity_id].update(occupancy_learning(samples, now, ZoneInfo(self.hass.config.time_zone)))
                stats = history["statistics"].get(p.entity_id, [])
                if stats:
                    learning[p.entity_id]["statistics"] = {"buckets": len(stats), "latest": stats[-1], "source": "recorder_hourly"}
            data["learning"] = learning
            # Build a local thermal history per room from live measured temperatures and climate activity.
            thermal_samples = data.setdefault("room_thermal_samples", {})
            rooms = sorted({p.area_id for p in profiles if p.area_id})
            for area in rooms:
                local = [p for p in profiles if p.area_id == area]
                temps = [sample_value(p) for p in local if p.role == "temperature" and sample_value(p) is not None]
                climates = [p for p in local if p.role == "climate"]
                if not temps:
                    continue
                active = any(
                    p.attributes.get("hvac_action") in {"heating", "cooling"}
                    or p.state in {"heat", "cool"}
                    for p in climates
                )
                points = thermal_samples.setdefault(area, [])
                points.append({"t": now.timestamp(), "temp": sum(temps) / len(temps), "active": active})
                thermal_samples[area] = [s for s in points if now.timestamp() - s["t"] <= 14 * 86400][-2000:]
            data["thermal_models"] = {
                area: build_room_thermal_model(points)
                for area, points in thermal_samples.items()
            }

            # Learn ventilation effectiveness, hot-water behavior and occupancy patterns.
            ventilation_samples = data.setdefault("ventilation_samples", {})
            occupancy_samples = data.setdefault("occupancy_samples", {})
            hot_water_samples = data.setdefault("hot_water_samples", {})
            local_tz = ZoneInfo(self.hass.config.time_zone)

            for area in rooms:
                local = [p for p in profiles if p.area_id == area]
                humid = [sample_value(p) for p in local if p.role == "humidity" and sample_value(p) is not None]
                fans = [p for p in local if p.role == "ventilation"]
                if humid:
                    pts = ventilation_samples.setdefault(area, [])
                    pts.append({"t": now.timestamp(), "humidity": sum(humid)/len(humid),
                                "active": any(p.state == "on" for p in fans)})
                    ventilation_samples[area] = [s for s in pts if now.timestamp()-s["t"] <= 14*86400][-2000:]

                presence = [p for p in local if p.role == "presence"]
                if presence:
                    occupied = any(
                        (p.domain == "binary_sensor" and p.state == "on")
                        or (p.domain in {"person","device_tracker"} and p.state == "home")
                        for p in presence
                    )
                    pts = occupancy_samples.setdefault(area, [])
                    pts.append({"t": now.timestamp(), "occupied": occupied})
                    occupancy_samples[area] = [s for s in pts if now.timestamp()-s["t"] <= 30*86400][-9000:]

                hot = [sample_value(p) for p in local if p.role == "hot_water" and sample_value(p) is not None]
                if hot:
                    pts = hot_water_samples.setdefault(area, [])
                    pts.append({"t": now.timestamp(), "temp": sum(hot)/len(hot)})
                    hot_water_samples[area] = [s for s in pts if now.timestamp()-s["t"] <= 30*86400][-4000:]

            data["ventilation_models"] = {area: ventilation_model(points) for area, points in ventilation_samples.items()}
            data["occupancy_models"] = {area: occupancy_model(points, local_tz) for area, points in occupancy_samples.items()}
            data["hot_water_models"] = {area: hot_water_model(points) for area, points in hot_water_samples.items()}

            update_runtime(
                data.get("flexible_loads", []),
                profiles,
                data.setdefault("energy_runtime", {}),
                now.astimezone(local_tz),
            )

            contexts = active_contexts(data["context_events"], now)
            usage = usage_snapshot(data.get("usage_profiles", []), now, ZoneInfo(self.hass.config.time_zone))
            proposals = evaluate(self.engine, profiles, learning, contexts, data["preferences"], data["feedback"], now, usage, data["thermal_models"], data.get("flexible_loads", []), ZoneInfo(self.hass.config.time_zone), data.get("ventilation_models", {}), data.get("hot_water_models", {}), data.get("occupancy_models", {}), data.get("energy_runtime", {}), knowledge=data.get("knowledge", []))
            suggestions = data_suggestions(profiles)
            outside_values = [
                sample_value(p) for p in profiles
                if p.role == "temperature" and not p.area_id and sample_value(p) is not None
            ]
            season = season_context(
                now.astimezone(local_tz),
                outside_values[0] if outside_values else None,
                data.get("preferences", {}),
            )
            anomalies = detect_anomalies(profiles, learning, now.timestamp())
            for suggestion in suggestions:
                proposal = self.engine.build_decision(category="model", title=suggestion["title"],
                    proposed_action=suggestion["next_step"], reasoning=suggestion["benefit"],
                    confidence=0.9, risk=RiskLevel.LOW, impact=ImpactLevel.MEDIUM,
                    area_id=suggestion["area_id"],
                    evidence={"data_suggestion": suggestion, "question": None},
                    alternatives=["Associare o ripristinare un sensore esistente", "Continuare con minore copertura dei dati"])
                proposal.outcome = {"type": "not_executed", "reason": "permanent_shadow_mode"}
                proposals.append(proposal)
            journal = data["decisions"]
            states = {p.entity_id: p.state for p in profiles}
            for previous in journal:
                if (previous.get("outcome") or {}).get("type") == "not_executed":
                    created = dt_util.parse_datetime(previous["created_at"])
                    if created and now - created >= timedelta(minutes=30):
                        previous["outcome"] = {"type": "observed_only", "observed_at": now.isoformat(),
                            "states": {i: states.get(i) for i in previous["entity_ids"]},
                            "causal_effect": "not_measurable_in_shadow_mode"}
            latest = []
            for proposal in proposals:
                payload = proposal.as_dict()
                payload["evidence"] = dict(payload.get("evidence") or {})
                conf = calibrated_confidence(payload, data.get("calibration", {}))
                payload["evidence"]["confidence_calibration"] = conf
                payload["confidence"] = conf["calibrated"]
                threshold = self.engine.risk_policy.threshold(RiskLevel(payload["risk"]))
                payload["status"] = "suppressed" if payload["evidence"].get("knowledge_blockers") else ("shadow" if payload["confidence"] >= threshold else "needs_input")
                payload["evidence"]["objective_score"] = score_decision(payload, data.get("preferences", {}))
                key = hashlib.sha256(json.dumps([payload["category"], payload["area_id"], payload["title"], sorted(payload["entity_ids"]),
                                                payload["proposed_action"], payload["evidence"].get("modes")]).encode()).hexdigest()[:24]
                previous = next((d for d in reversed(journal) if d.get("key") == key), None)
                if previous and now - dt_util.parse_datetime(previous["created_at"]) < timedelta(hours=6):
                    current = {**payload, "decision_id": previous["decision_id"], "created_at": previous["created_at"],
                               "key": key, "last_seen": now.isoformat(), "outcome": previous.get("outcome"),
                               "feedback": previous.get("feedback")}
                    previous["last_seen"] = now.isoformat()
                    latest.append(current)
                    continue
                payload["key"] = key
                journal.append(payload)
                latest.append(payload)
                events.append(payload)
            del journal[:-MAX_DECISIONS]
            current_numeric = {p.entity_id: sample_value(p) for p in profiles}
            evaluate_shadow_outcomes(journal, current_numeric, now)
            data["calibration"] = calibration(data.get("feedback", []))
            decisions_by_id = {d["decision_id"]: d for d in journal}
            for question in data.get("questions", []):
                if "entity_ids" not in question:
                    question["entity_ids"] = decisions_by_id.get(question.get("decision_id"), {}).get("entity_ids", [])
            questions, new_questions = merge_questions(data.setdefault("questions", []), latest, now)
            retire_removed_questions(questions, area_ids, entity_ids, now)
            new_questions = [q for q in new_questions if q.get("status") == "open"]
            data["questions"] = questions
            await self.storage.async_save()
        for payload in events:
            self.hass.bus.async_fire(EVENT_DECISION, payload)
        for question in new_questions:
            self.hass.bus.async_fire(EVENT_QUESTION, question)
        inventory = summarize_inventory(profiles)
        for suggestion in suggestions:
            suggestion["decision_id"] = next(d["decision_id"] for d in latest
                if d["evidence"].get("data_suggestion", {}).get("key") == suggestion["key"])
        inventory.update(unassigned_entities=sum(not p.area_id for p in profiles), shadow_mode=True)
        migration = migration_readiness(
            legacy_automation_inventory(profiles),
            journal,
            data.get("calibration", {}),
        )
        kpis = shadow_kpis(journal, data.get("feedback", []), data.get("questions", []))
        health = autonomy_health(
            profiles,
            {
                "thermal": data.get("thermal_models", {}),
                "ventilation": data.get("ventilation_models", {}),
                "hot_water": data.get("hot_water_models", {}),
                "occupancy": data.get("occupancy_models", {}),
            },
            kpis,
            migration,
        )
        day_forecast = daily_forecast(
            now.astimezone(local_tz),
            usage,
            season,
            journal,
            data.get("questions", []),
            anomalies,
        )
        knowledge_coverage, knowledge_gaps = knowledge_overview(data)
        result = {"inventory": inventory, "knowledge_application": knowledge_application, "rooms": home_model(profiles, learning),
                "profiles": {p.entity_id: p.as_dict() for p in profiles}, "latest_decisions": latest,
                "decision_count": len(journal), "contexts": contexts, "usage": usage,
                "questions": [q for q in data.get("questions", []) if q.get("status") == "open"],
                "usage_profiles": data.get("usage_profiles", []),
                "preferences": data.get("preferences", {}),
                "history": {k: v for k, v in history.items() if k not in {"samples", "statistics"}},
                "learning_entities": len(learning), "data_suggestions": suggestions,
                "thermal_models": {k: v for k, v in data.get("thermal_models", {}).items() if k in area_ids},
                "calibration": data.get("calibration", {}),
                "ventilation_models": {k: v for k, v in data.get("ventilation_models", {}).items() if k in area_ids},
                "hot_water_models": {k: v for k, v in data.get("hot_water_models", {}).items() if k in area_ids},
                "occupancy_models": {k: v for k, v in data.get("occupancy_models", {}).items() if k in area_ids},
                "automation_migration": legacy_automation_inventory(profiles),
                "migration_readiness": migration,
                "kpis": kpis,
                "autonomy_health": health,
                "season": season,
                "anomalies": anomalies,
                "last_replay": data.get("last_replay", {}),
                "last_scenario": data.get("last_scenario", {}),
                "memory_versions": [
                    {k: s.get(k) for k in ("snapshot_id","created_at","label","reason")}
                    for s in data.get("memory_versions", [])[-20:]
                ],
                "daily_forecast": day_forecast,
                "knowledge_items": [k for k in data.get("knowledge", []) if k.get("status","active")=="active"][-200:],
                "knowledge_coverage": knowledge_coverage,
                "knowledge_gaps": knowledge_gaps,
                "decision_history": [d for d in journal[-100:] if (not d.get("area_id") or d["area_id"] in area_ids) and (not d.get("entity_ids") or any(e in entity_ids for e in d["entity_ids"]))],
                "flexible_loads": data.get("flexible_loads", []),
                "evaluated_at": now.isoformat()}
        result["progress"] = progress_status(data, result, now)
        return result
