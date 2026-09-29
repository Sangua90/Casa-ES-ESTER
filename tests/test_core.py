"""Run without HA: python -m unittest discover -s tests -v."""
import ast
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Import the pure domain under a separate namespace, without executing HA setup.
package = types.ModuleType("ester_core")
package.__path__ = [str(ROOT / "custom_components/ester")]
sys.modules.setdefault("ester_core", package)
home = importlib.import_module("ester_core.home")
models = importlib.import_module("ester_core.models")
policies = importlib.import_module("ester_core.policies")
Engine = importlib.import_module("ester_core.decision_engine").EsterDecisionEngine
quality = importlib.import_module("ester_core.quality")
usage = importlib.import_module("ester_core.usage")
NOW = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


def profile(role, state="20", unit="°C", area="room", domain="sensor", **attrs):
    return models.EntityProfile(f"{domain}.{role}", domain, role, state, area_id=area,
        unit=unit, role=role, attributes={"last_reported": NOW.isoformat(), **attrs})


def decisions(profiles, contexts=(), preferences=None, feedback=()):
    return policies.evaluate(Engine(), profiles, {}, contexts, preferences or {}, feedback, NOW)


class CoreTests(unittest.TestCase):
    def test_missing_data_suggestions_prefer_existing_entities(self):
        climate = profile("climate", "heat", domain="climate")
        results = quality.data_suggestions([climate])
        temperature = next(s for s in results if s["missing_role"] == "temperature")
        self.assertIn("temperatura", temperature["suggested_device"])
        sensor = profile("temperature", "20", area=None)
        temperature = next(s for s in quality.data_suggestions([climate, sensor]) if s["missing_role"] == "temperature")
        self.assertIsNone(temperature["suggested_device"])
        self.assertEqual(temperature["unassigned_candidates"], [sensor.entity_id])
        sensor.area_id = "room"
        self.assertFalse(any(s["missing_role"] == "temperature" for s in quality.data_suggestions([climate, sensor])))
        sensor.state = "unavailable"
        temperature = next(s for s in quality.data_suggestions([climate, sensor]) if s["missing_role"] == "temperature")
        self.assertIsNone(temperature["suggested_device"])
        self.assertEqual(temperature["existing_entities"], [sensor.entity_id])

    def test_percent_is_not_humidity(self):
        self.assertEqual(home.infer_role("sensor", "battery", "%", "battery"), "battery")
        self.assertEqual(home.infer_role("sensor", None, "%", "unknown"), "generic")
        self.assertEqual(home.infer_role("sensor", None, None, "window"), "generic")

    def test_domain_and_safety_classification(self):
        for device_class in ("smoke", "moisture", "carbon_monoxide", "door"):
            self.assertEqual(home.infer_role("binary_sensor", device_class, None, "x"), "security")
        self.assertEqual(home.infer_role("binary_sensor", "occupancy", None, "x"), "presence")
        self.assertEqual(home.infer_role("sensor", "power", "W", "solar"), "energy")

    def test_units(self):
        self.assertAlmostEqual(home.numeric_value(profile("temperature", "68", "°F")), 20)
        self.assertEqual(home.numeric_value(profile("solar_power", "1.5", "kW")), 1500)
        self.assertIsNone(home.numeric_value(profile("solar_power", "10", "kWh")))
        self.assertIsNone(home.numeric_value(profile("humidity", "1000", "%")))
        for value in ("NaN", "inf", "unavailable", None):
            self.assertIsNone(home.number(value))

    def test_context_expiry_and_future(self):
        start = (NOW - timedelta(hours=1)).isoformat()
        contexts = [{"starts_at": start, "ends_at": NOW.isoformat()},
                    {"starts_at": (NOW + timedelta(hours=1)).isoformat()},
                    {"starts_at": start}, {"starts_at": "invalid"}, {"starts_at": "2026-09-29T11:00:00"}]
        self.assertEqual(home.active_contexts(contexts, NOW), [contexts[2]])

    def test_regression_and_unknown_gap(self):
        points = [{"t": NOW.timestamp() - (2-i)*1800, "v": 18+i} for i in range(3)]
        result = home.learn(points + points, NOW)
        self.assertEqual(result["samples"], 3)
        self.assertEqual(result["slope_per_hour"], 2)
        points[1]["v"] = None
        self.assertIsNone(home.learn(points, NOW)["slope_per_hour"])

    def test_weighted_occupancy(self):
        points = [{"t": NOW.timestamp()-3600, "v": 1}, {"t": NOW.timestamp()-1800, "v": 0}, {"t": NOW.timestamp(), "v": 0}]
        result = home.occupancy_learning(points, NOW, timezone.utc)
        self.assertEqual(result["observed_minutes"], 60)
        self.assertEqual(result["hourly_occupancy"][11], 0.5)

    def test_climate_requires_presence_and_target(self):
        profiles = [profile("temperature", "17"), profile("climate", "heat", domain="climate"), profile("presence", "on", None, domain="binary_sensor")]
        self.assertTrue(any(d.evidence["question"] for d in decisions(profiles) if d.category == "climate"))
        result = decisions(profiles, preferences={"comfort:room": 21})
        self.assertTrue(any(d.proposed_action == "Valutare riscaldamento" for d in result))
        profiles[-1].state = "unavailable"
        self.assertFalse(any(d.proposed_action == "Valutare riscaldamento" for d in decisions(profiles, preferences={"comfort:room": 21})))

    def test_vacation_area_scope(self):
        profiles = [profile("temperature", "17"), profile("climate", "heat", domain="climate"), profile("presence", "on", None, domain="binary_sensor")]
        contexts = [{"mode": "vacation", "areas": ["other"]}]
        self.assertTrue(any(d.proposed_action == "Valutare riscaldamento" for d in decisions(profiles, contexts, {"comfort:room": 21})))

    def test_all_engines_and_shadow_outcome(self):
        profiles = [profile("temperature", "17"), profile("climate", "heat", domain="climate"),
            profile("presence", "off", None, domain="binary_sensor"), profile("lighting", "on", None, domain="light"),
            profile("humidity", "75", "%"), profile("hot_water", "55"), profile("soil_moisture", "12", "%"),
            profile("security", "on", None, domain="binary_sensor"), profile("energy", "100", "W")]
        result = decisions(profiles)
        self.assertEqual({d.category for d in result}, {"climate", "presence", "lighting", "ventilation", "hot_water", "irrigation", "operational_safety", "energy"})
        for decision in result:
            self.assertIn(decision.status, (models.DecisionStatus.SHADOW, models.DecisionStatus.NEEDS_INPUT))
            self.assertEqual(decision.outcome["type"], "not_executed")
            self.assertTrue(decision.reasoning)
            self.assertTrue(decision.alternatives)
            self.assertGreaterEqual(decision.confidence, 0)
            self.assertLessEqual(decision.confidence, 1)

    def test_energy_does_not_double_count(self):
        solar = profile("solar_power", "2", "kW")
        load = profile("load_power", "700", "W")
        result = decisions([solar, load])
        self.assertEqual(next(d for d in result if d.category == "energy").evidence["surplus_w"], 1300)
        duplicate = profile("solar_power", "2", "kW")
        self.assertFalse(any("surplus_w" in d.evidence for d in decisions([solar, load, duplicate])))

    def test_feedback_only_lowers_confidence(self):
        profiles = [profile("presence", "on", None, domain="binary_sensor")]
        base = decisions(profiles)[0].confidence
        result = decisions(profiles, feedback=[{"category": "presence", "rating": "wrong"}])
        self.assertLess(result[0].confidence, base)

    def test_stale_data_blocks_climate(self):
        p = profile("temperature", "10", last_reported=(NOW - timedelta(hours=3)).isoformat())
        result = decisions([p, profile("climate", "heat", domain="climate")], preferences={"comfort:room": 21})
        self.assertTrue(any(d.category == "operational_safety" for d in result))
        self.assertFalse(any(d.proposed_action == "Valutare riscaldamento" for d in result))

    def test_no_actuation_or_dynamic_execution_anywhere(self):
        forbidden = {"async_call", "call_service", "async_turn_on", "async_turn_off", "async_set_temperature", "exec", "eval"}
        for path in (ROOT / "custom_components/ester").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                    self.assertNotIn(name, forbidden, f"{path}:{node.lineno}")


    def test_expected_usage_current_upcoming_and_overnight(self):
        profiles = [
            {"profile_id": "weekend", "area_id": "room", "label": "Weekend",
             "weekdays": [5, 6], "start_time": "18:00", "end_time": "23:30",
             "expected_occupancy": 0.9},
            {"profile_id": "night", "area_id": "bed", "label": "Night",
             "weekdays": [0], "start_time": "22:00", "end_time": "02:00",
             "expected_occupancy": 1.0},
        ]
        saturday = datetime(2026, 10, 3, 17, tzinfo=timezone.utc)
        snap = usage.usage_snapshot(profiles, saturday, timezone.utc)
        self.assertEqual(snap["room"]["upcoming"][0]["minutes_until"], 60)
        monday_night = datetime(2026, 10, 5, 23, tzinfo=timezone.utc)
        self.assertEqual(usage.usage_snapshot(profiles, monday_night, timezone.utc)["bed"]["expected_occupancy"], 1.0)
        tuesday_after_midnight = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)
        self.assertEqual(usage.usage_snapshot(profiles, tuesday_after_midnight, timezone.utc)["bed"]["expected_occupancy"], 1.0)

    def test_expected_use_can_create_preconditioning_shadow_proposal(self):
        profiles = [profile("temperature", "17"), profile("climate", "heat", domain="climate")]
        expected = {"room": {"current": [], "expected_occupancy": 0.0,
                    "upcoming": [{"profile_id": "x", "label": "Gym", "minutes_until": 45,
                                  "expected_occupancy": 0.9, "comfort_c": 20}]}}
        result = policies.evaluate(Engine(), profiles, {}, [], {"comfort:room": 20}, [], NOW, expected)
        proposal = next(d for d in result if d.title == "Uso stanza previsto")
        self.assertEqual(proposal.proposed_action, "Valutare pre-climatizzazione")
        self.assertEqual(proposal.outcome["type"], "not_executed")


if __name__ == "__main__":
    unittest.main()
