"""Coordinator for E.S.T.E.R."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_EVALUATION_INTERVAL_MINUTES, DOMAIN, EVENT_DECISION
from .decision_engine import EsterDecisionEngine
from .discovery import discover_entities, summarize_inventory
from .storage import EsterStorage

_LOGGER = logging.getLogger(__name__)


class EsterCoordinator(DataUpdateCoordinator[dict]):
    """Refresh the home model and execute shadow evaluations."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        storage: EsterStorage,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_EVALUATION_INTERVAL_MINUTES),
        )
        self.entry = entry
        self.storage = storage
        self.engine = EsterDecisionEngine(hass)

    async def _async_update_data(self) -> dict:
        profiles = discover_entities(self.hass)
        summary = summarize_inventory(profiles)
        summary["unassigned_entities"] = sum(1 for p in profiles if not p.area_id)
        summary["shadow_mode"] = True

        decisions = await self.engine.evaluate_snapshot(summary)
        for decision in decisions:
            payload = decision.as_dict()
            await self.storage.add_decision(payload)
            self.hass.bus.async_fire(EVENT_DECISION, payload)

        return {
            "inventory": summary,
            "profiles": {p.entity_id: p.as_dict() for p in profiles},
            "latest_decisions": [d.as_dict() for d in decisions],
            "decision_count": len(self.storage.data.get("decisions", [])),
        }
