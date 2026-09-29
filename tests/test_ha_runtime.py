"""API and integration smoke tests on real HA, run in Linux CI."""
import asyncio
from datetime import timedelta
import importlib.util
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

HAS_HA = importlib.util.find_spec("homeassistant") is not None


@unittest.skipUnless(HAS_HA, "Home Assistant requires Linux/Python 3.14; covered by CI")
class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        from homeassistant.helpers import area_registry, device_registry, entity_registry
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config.time_zone = "Europe/Rome"
        device_registry.async_setup(self.hass)
        await area_registry.async_load(self.hass)
        await device_registry.async_load(self.hass)
        await entity_registry.async_load(self.hass)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_discovery_storage_coordinator_and_sensors(self):
        from homeassistant.helpers import area_registry
        from custom_components.ester.discovery import discover_entities
        from custom_components.ester.storage import EsterStorage
        from custom_components.ester.coordinator import EsterCoordinator
        from custom_components.ester.sensor import async_setup_entry
        room = area_registry.async_get(self.hass).async_create("Studio")
        self.hass.states.async_set("sensor.room_temperature", "18", {"device_class": "temperature", "unit_of_measurement": "°C"})
        self.hass.states.async_set("sensor.battery", "90", {"device_class": "battery", "unit_of_measurement": "%"})
        store = EsterStorage(self.hass)
        await store.async_load()
        store.data["classifications"]["sensor.room_temperature"] = {"role": "temperature", "area_id": room.id}
        await store.async_save()
        restored = EsterStorage(self.hass)
        await restored.async_load()
        self.assertEqual(restored.data["classifications"], store.data["classifications"])
        profiles = discover_entities(self.hass, restored.data["classifications"])
        self.assertEqual(next(p for p in profiles if p.entity_id == "sensor.battery").role, "battery")
        coordinator = EsterCoordinator(self.hass, None, restored)
        # Any accidental device-service call fails this runtime test.
        with patch.object(self.hass.services, "async_call", side_effect=AssertionError("Device services forbidden")):
            first = await coordinator._async_update_data()
            second = await coordinator._async_update_data()
        self.assertEqual(first["decision_count"], second["decision_count"])
        self.assertEqual(first["history"]["status"], "unavailable")
        self.assertIn(room.id, first["rooms"])
        coordinator.async_set_updated_data(second)
        entry = SimpleNamespace(entry_id="test", runtime_data=coordinator)
        sensors = []
        await async_setup_entry(self.hass, entry, sensors.extend)
        self.assertEqual(len(sensors), 6)
        self.assertEqual(sensors[0].native_value, "shadow")
        self.assertFalse(sensors[0].extra_state_attributes["real_actuation_enabled"])

    async def test_recorder_adapter_and_statistics_signature(self):
        from homeassistant.core import State
        from homeassistant.util import dt as dt_util
        from homeassistant.components.recorder.history import get_significant_states
        from homeassistant.components.recorder.statistics import statistics_during_period
        from custom_components.ester.history import HistoryReader
        from custom_components.ester.models import EntityProfile
        import inspect
        inspect.signature(get_significant_states).bind(self.hass, dt_util.utcnow(), dt_util.utcnow(), ["sensor.t"], significant_changes_only=False, minimal_response=False, no_attributes=False)
        inspect.signature(statistics_during_period).bind(self.hass, dt_util.utcnow(), dt_util.utcnow(), {"sensor.t"}, "hour", None, {"mean", "sum"})
        self.hass.config.components.add("recorder")
        now = dt_util.utcnow()
        profile = EntityProfile("sensor.t", "sensor", "T", "20", unit="°C", role="temperature", attributes={"state_class": "measurement"})
        rows = {"sensor.t": [State("sensor.t", "20", {"unit_of_measurement": "°C"}, last_updated=now-timedelta(hours=1))]}

        async def executor(job):
            return job()

        recorder = SimpleNamespace(async_add_executor_job=executor)
        with patch("homeassistant.helpers.recorder.get_instance", return_value=recorder), patch(
            "homeassistant.components.recorder.history.get_significant_states", return_value=rows), patch(
            "homeassistant.components.recorder.statistics.statistics_during_period", return_value={"sensor.t": [{"mean": 20}]}):
            reader = HistoryReader(self.hass)
            data = await reader.read([profile], now)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["samples"]["sensor.t"][0]["v"], 20)
        self.assertEqual(data["statistics"]["sensor.t"][0]["mean"], 20)

    async def test_internal_services_validation_and_local_explanation(self):
        from homeassistant.exceptions import ServiceValidationError
        from custom_components.ester.services import register_services
        from custom_components.ester.storage import EsterStorage
        from custom_components.ester.coordinator import EsterCoordinator
        from homeassistant.config_entries import ConfigEntryState
        store = EsterStorage(self.hass)
        coordinator = EsterCoordinator(self.hass, None, store)
        coordinator.async_request_refresh = AsyncMock()
        entry = SimpleNamespace(runtime_data=coordinator, state=ConfigEntryState.LOADED, options={})
        coordinator.entry = entry
        self.hass.config_entries = SimpleNamespace(async_entries=lambda domain: [entry], async_shutdown=AsyncMock())
        register_services(self.hass)
        await self.hass.services.async_call("ester", "add_context", {"label": "Ospiti", "mode": "guests"}, blocking=True)
        self.assertEqual(len(store.data["context_events"]), 1)
        with self.assertRaises(ServiceValidationError):
            await self.hass.services.async_call("ester", "add_context", {"label": "x", "ends_at": "invalid"}, blocking=True)
        with self.assertRaises(ServiceValidationError):
            await self.hass.services.async_call("ester", "add_feedback", {"decision_id": "missing", "rating": "wrong"}, blocking=True)
        response = await self.hass.services.async_call("ester", "get_summary", {}, blocking=True, return_response=True)
        self.assertFalse(response["real_actuation_enabled"])
        await self.hass.services.async_call("ester", "remove_context", {"event_id": store.data["context_events"][0]["event_id"]}, blocking=True)
        self.assertEqual(store.data["context_events"], [])
