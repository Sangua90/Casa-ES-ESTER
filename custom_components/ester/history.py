"""Optional Recorder adapter. All queries run on Recorder's executor."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from functools import partial
import logging

from .home import numeric_value

_LOGGER = logging.getLogger(__name__)
LEARN_ROLES = {"temperature", "humidity", "hot_water", "climate", "presence", "energy",
               "solar_power", "load_power", "battery", "soil_moisture"}


def sample_value(profile):
    if profile.role == "presence":
        if profile.state in {"unknown", "unavailable", None}:
            return None
        if profile.domain in {"person", "device_tracker"}:
            return int(profile.state == "home")
        return {"on": 1, "off": 0}.get(profile.state)
    return numeric_value(profile)


class HistoryReader:
    def __init__(self, hass):
        self.hass = hass
        self.last_read = None
        self.cache = {"status": "not_loaded", "samples": {}, "statistics": {}}

    async def read(self, profiles, now):
        if self.last_read and now - self.last_read < timedelta(minutes=30):
            return self.cache
        self.last_read = now
        if "recorder" not in self.hass.config.components:
            self.cache = {"status": "unavailable", "samples": {}, "statistics": {}}
            return self.cache
        selected = sorted((p for p in profiles if p.role in LEARN_ROLES), key=lambda p: p.entity_id)[:100]
        if not selected:
            self.cache = {"status": "no_entities", "samples": {}, "statistics": {}}
            return self.cache
        result = {"status": "ready", "samples": {}, "statistics": {}, "selected": len(selected),
                  "truncated": sum(p.role in LEARN_ROLES for p in profiles) > 100, "read_at": now.isoformat()}
        try:
            from homeassistant.helpers.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
            from homeassistant.components.recorder.statistics import statistics_during_period
            recorder = get_instance(self.hass)
            for offset in range(0, len(selected), 20):
                batch = selected[offset:offset + 20]
                states = await recorder.async_add_executor_job(partial(
                    get_significant_states, self.hass, now - timedelta(hours=24), now,
                    [p.entity_id for p in batch], significant_changes_only=False,
                    minimal_response=False, no_attributes=False))
                for p in batch:
                    samples = []
                    for state in states.get(p.entity_id, []):
                        historical = replace(p, state=state.state, unit=state.attributes.get("unit_of_measurement", p.unit),
                                             attributes=dict(state.attributes))
                        samples.append({"t": state.last_updated.timestamp(), "v": sample_value(historical)})
                    # Preserve endpoints while bounding retained samples; do not invent observations.
                    stride = max(1, (len(samples) + 998) // 999)
                    result["samples"][p.entity_id] = samples[::stride] + (samples[-1:] if stride > 1 else [])
            ids = {p.entity_id for p in selected if p.attributes.get("state_class") in {"measurement", "total", "total_increasing"}}
            if ids:
                try:
                    result["statistics"] = await recorder.async_add_executor_job(partial(
                        statistics_during_period, self.hass, now - timedelta(days=7), now, ids,
                        "hour", None, {"mean", "min", "max", "sum"}))
                except Exception:  # Optional statistics must not disable live observations.
                    result["status"] = "statistics_error"
                    _LOGGER.warning("E.S.T.E.R. statistics unavailable; retaining history and live data")
        except Exception:
            result["status"] = "history_error"
            _LOGGER.warning("E.S.T.E.R. Recorder unavailable; using live observations")
        self.cache = result
        return result
