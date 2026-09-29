"""Observe, learn and journal proposals without a device service boundary."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import logging
from zoneinfo import ZoneInfo

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_DECISION, EVENT_QUESTION, MAX_DECISIONS
from .decision_engine import EsterDecisionEngine
from .discovery import discover_entities, summarize_inventory
from .history import HistoryReader, sample_value
from .home import active_contexts, home_model, learn, occupancy_learning, timestamp
from .policies import evaluate
from .quality import data_suggestions
from .models import RiskLevel, ImpactLevel

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
            contexts = active_contexts(data["context_events"], now)
            proposals = evaluate(self.engine, profiles, learning, contexts, data["preferences"], data["feedback"], now)
            suggestions = data_suggestions(profiles)
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
            await self.storage.async_save()
        for payload in events:
            self.hass.bus.async_fire(EVENT_DECISION, payload)
            if payload["status"] == "needs_input":
                self.hass.bus.async_fire(EVENT_QUESTION, payload)
        inventory = summarize_inventory(profiles)
        for suggestion in suggestions:
            suggestion["decision_id"] = next(d["decision_id"] for d in latest
                if d["evidence"].get("data_suggestion", {}).get("key") == suggestion["key"])
        inventory.update(unassigned_entities=sum(not p.area_id for p in profiles), shadow_mode=True)
        return {"inventory": inventory, "rooms": home_model(profiles, learning),
                "profiles": {p.entity_id: p.as_dict() for p in profiles}, "latest_decisions": latest,
                "decision_count": len(journal), "contexts": contexts,
                "history": {k: v for k, v in history.items() if k not in {"samples", "statistics"}},
                "learning_entities": len(learning), "data_suggestions": suggestions, "evaluated_at": now.isoformat()}
