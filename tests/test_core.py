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
questions = importlib.import_module("ester_core.questions")
thermal = importlib.import_module("ester_core.thermal")
energy = importlib.import_module("ester_core.energy")
ventilation = importlib.import_module("ester_core.ventilation")
hot_water = importlib.import_module("ester_core.hot_water")
economics = importlib.import_module("ester_core.economics")
occupancy = importlib.import_module("ester_core.occupancy")
language = importlib.import_module("ester_core.language")
migration = importlib.import_module("ester_core.migration")
readiness = importlib.import_module("ester_core.readiness")
house_controls = importlib.import_module("ester_core.house_controls")
optimizer = importlib.import_module("ester_core.optimizer")
kpi = importlib.import_module("ester_core.kpi")
health = importlib.import_module("ester_core.health")
snapshots = importlib.import_module("ester_core.snapshots")
seasonal = importlib.import_module("ester_core.seasonal")
scenario = importlib.import_module("ester_core.scenario")
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
        self.assertEqual(next(d for d in result if d.category == "energy").evidence["energy_plan"]["instant_surplus_w"], 1300)
        duplicate = profile("solar_power", "2", "kW")
        self.assertFalse(any("energy_plan" in d.evidence for d in decisions([solar, load, duplicate])))

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
        models = {"room": {"active_rate_c_per_h": 2.0, "passive_rate_c_per_h": -0.2, "confidence": 0.8}}
        result = policies.evaluate(Engine(), profiles, {}, [], {"comfort:room": 20}, [], NOW, expected, models)
        proposal = next(d for d in result if d.title == "Uso stanza previsto")
        self.assertIn("pre-climatizzazione", proposal.proposed_action)
        self.assertEqual(proposal.outcome["type"], "not_executed")


    def test_question_inbox_deduplicates_and_learns_comfort(self):
        decision = {
            "decision_id": "d1", "category": "climate", "area_id": "room",
            "title": "Comfort da definire", "reasoning": "Serve un target",
            "confidence": 0.4, "risk": "medium",
            "evidence": {"question": "Quale temperatura desideri?"},
        }
        inbox, created = questions.merge_questions([], [decision], NOW)
        self.assertEqual(len(created), 1)
        inbox, created_again = questions.merge_questions(inbox, [decision], NOW + timedelta(minutes=5))
        self.assertEqual(created_again, [])
        data = {"questions": inbox, "preferences": {}, "knowledge": []}
        interpretation = questions.apply_answer(data, inbox[0]["question_id"], "Preferisco 21 gradi", NOW)
        self.assertEqual(interpretation["kind"], "preference")
        self.assertEqual(data["preferences"]["comfort:room"], 21)
        self.assertEqual(data["questions"][0]["status"], "answered")

    def test_ambiguous_answer_becomes_knowledge_not_rule(self):
        q = {
            "question_id": "q1", "category": "presence", "area_id": "room",
            "title": "Uso stanza", "prompt": "La stanza è usata?", "status": "open",
        }
        data = {"questions": [q], "preferences": {}, "knowledge": []}
        result = questions.apply_answer(data, "q1", "Di solito qui si legge dopo cena", NOW)
        self.assertEqual(result["kind"], "knowledge_note")
        self.assertEqual(result["scope"], "persistent")
        self.assertEqual(len(data["knowledge"]), 1)
        self.assertEqual(data["preferences"], {})


    def test_local_thermal_model_and_strategy(self):
        samples = [
            {"t": NOW.timestamp() + i * 600, "temp": 18 + i * 0.3, "active": True}
            for i in range(6)
        ]
        samples += [
            {"t": NOW.timestamp() + 7200 + i * 600, "temp": 20 - i * 0.1, "active": False}
            for i in range(6)
        ]
        model = thermal.build_room_thermal_model(samples)
        self.assertIsNotNone(model["active_rate_c_per_h"])
        self.assertGreater(model["active_rate_c_per_h"], 0)
        self.assertLess(model["passive_rate_c_per_h"], 0)
        opts = thermal.compare_climate_strategies(
            current_c=18, target_c=20, minutes_until_use=90, model=model,
            energy_price_eur_kwh=0.3, estimated_power_kw=1.5)
        self.assertTrue(any(o["strategy"] == "precondition" for o in opts))

    def test_energy_planner_protects_limits_and_ranks_loads(self):
        target = NOW + timedelta(hours=4)
        plan = energy.energy_plan(
            now=NOW, target=target, pv_w=3000, load_w=5800, grid_w=5900,
            battery_soc=50, battery_capacity_kwh=14.3, target_soc=90, reserve_soc=30,
            forecast_curve=[], forecast_remaining_kwh=8, base_load_w=500,
            grid_limit_w=6000, inverter_limit_w=10000, phase_w=[1000, 2000, 2500],
            phase_limit_w=3500)
        self.assertEqual(plan["strategy"], "protect_electrical_limits")
        ranked = energy.rank_flexible_loads([
            {"name": "boiler", "power_w": 1300, "duration_minutes": 60, "priority": 10}
        ], plan)
        self.assertFalse(ranked[0]["shadow_allowed"])

    def test_ventilation_learning_can_stop_when_ineffective(self):
        base = NOW.timestamp()
        samples = []
        for i in range(5):
            samples.append({"t": base + i*600, "humidity": 70 + i*0.02, "active": True})
        for i in range(5):
            samples.append({"t": base + 7200 + i*600, "humidity": 70 + i*0.03, "active": False})
        model = ventilation.ventilation_model(samples)
        plan = ventilation.ventilation_recommendation(humidity=70, model=model, active=True)
        self.assertIn(plan["strategy"], {"would_stop", "would_run"})

    def test_hot_water_and_heating_economics(self):
        base = NOW.timestamp()
        samples = [{"t": base+i*600, "temp": 45+i,} for i in range(5)]
        samples += [{"t": base+7200+i*600, "temp": 55-i*0.5} for i in range(5)]
        model = hot_water.hot_water_model(samples)
        self.assertGreaterEqual(model["confidence"], 0)
        costs = economics.heating_costs(
            electricity_eur_kwh=0.30, gas_eur_m3=0.35,
            heat_pump_cop=3.5, boiler_efficiency=0.9)
        self.assertIn(costs["preferred_source"], {"heat_pump", "gas"})

    def test_occupancy_model_predicts_weekday_hour(self):
        samples = []
        stamp = datetime(2026, 9, 28, 18, tzinfo=timezone.utc)
        for week in range(4):
            for i in range(6):
                samples.append({"t": (stamp - timedelta(days=7*week) + timedelta(minutes=5*i)).timestamp(),
                                "occupied": True})
        model = occupancy.occupancy_model(samples, timezone.utc)
        self.assertEqual(occupancy.predicted_occupancy(model, stamp), 1.0)

    def test_language_router_never_creates_device_action(self):
        store = {"preferences": {}, "context_events": [], "knowledge": [], "usage_profiles": []}
        parsed = language.local_interpret("Preferisco 21 gradi in room", ["room"])
        result = language.apply_interpretation(store, parsed, NOW)
        self.assertEqual(result["applied"], "preference")
        self.assertEqual(store["preferences"]["comfort:room"], 21)

    def test_alarm_and_lighting_planners_are_shadow_intents(self):
        light = house_controls.lighting_plan(
            light_on=False, occupied=True, presence_known=True,
            illuminance_lux=20, lux_threshold=80)
        self.assertEqual(light["strategy"], "would_turn_on")
        alarm = house_controls.alarm_plan(
            alarm_state="disarmed", occupied=False, presence_known=True,
            expected_occupancy=0, doors_open=False, local_hour=14)
        self.assertEqual(alarm["strategy"], "would_arm_away")

    def test_migration_inventory_and_readiness_never_auto_disables(self):
        p = profile("generic", "on", None, domain="automation")
        p.name = "Allerta Fotovoltaico"
        inv = migration.legacy_automation_inventory([p])
        self.assertEqual(inv["by_category"]["energy"], 1)
        result = readiness.migration_readiness(inv, [], {})
        self.assertFalse(result["energy"]["automatic_disable_allowed"])


    def test_multi_objective_scoring_prioritizes_safety(self):
        safety = {
            "category": "operational_safety", "confidence": 0.95,
            "risk": "high", "status": "shadow", "evidence": {}
        }
        lighting = {
            "category": "lighting", "confidence": 0.95,
            "risk": "low", "status": "shadow", "evidence": {}
        }
        a = optimizer.score_decision(safety, {})
        b = optimizer.score_decision(lighting, {})
        self.assertGreater(a["score"], b["score"])
        tuned = optimizer.score_decision(lighting, {"objective_weight:energy": 1.0})
        self.assertGreaterEqual(tuned["components"]["energy"], b["components"]["energy"])

    def test_shadow_kpis_use_explicit_feedback_only(self):
        decisions_data = [
            {"category": "energy", "confidence": 0.8, "risk": "medium",
             "status": "shadow", "outcome": {"type": "not_executed"}},
            {"category": "climate", "confidence": 0.9, "risk": "low",
             "status": "needs_input", "outcome": {"type": "observed_only"}},
        ]
        feedback = [
            {"category": "energy", "rating": "correct"},
            {"category": "climate", "rating": "partial"},
        ]
        result = kpi.shadow_kpis(decisions_data, feedback, [{"status": "open"}])
        self.assertEqual(result["feedback"]["samples"], 2)
        self.assertEqual(result["feedback"]["quality_score"], 0.75)
        self.assertEqual(result["shadow_actuations"], 0)
        self.assertEqual(result["open_questions"], 1)

    def test_memory_snapshot_rollback_restores_configuration(self):
        data = {
            "preferences": {"comfort:room": 20},
            "classifications": {},
            "usage_profiles": [],
            "knowledge": [],
            "context_events": [],
            "flexible_loads": [],
            "memory_versions": [],
        }
        snap = snapshots.create_snapshot(data, NOW, "before", "test")
        data["preferences"]["comfort:room"] = 24
        snapshots.restore_snapshot(data, snap["snapshot_id"])
        self.assertEqual(data["preferences"]["comfort:room"], 20)
        self.assertEqual(len(data["memory_versions"]), 1)

    def test_season_context_prefers_outside_temperature(self):
        result = seasonal.season_context(NOW, 8, {})
        self.assertEqual(result["season"], "winter")
        self.assertEqual(result["source"], "outside_temperature")
        result = seasonal.season_context(NOW, 29, {})
        self.assertEqual(result["season"], "summer")

    def test_autonomy_health_never_disables_shadow(self):
        profiles = [
            profile("solar_power", "2000", "W"),
            profile("load_power", "1000", "W"),
            profile("battery", "80", "%"),
        ]
        result = health.autonomy_health(
            profiles,
            {"thermal": {}, "ventilation": {}, "hot_water": {}, "occupancy": {}},
            {"feedback": {"quality_score": 1.0}},
            {"energy": {"status": "candidate_for_manual_migration"}},
        )
        self.assertFalse(result["overall_ready_for_executor"])
        self.assertTrue(result["shadow_mode_required"])

    def test_what_if_does_not_persist_changes(self):
        profiles = [
            profile("temperature", "18"),
            profile("climate", "heat", domain="climate"),
            profile("presence", "on", None, domain="binary_sensor"),
        ]
        data = {
            "preferences": {"comfort:room": 20, "energy_price_eur_kwh": 0.3},
            "context_events": [],
            "usage_profiles": [],
            "feedback": [],
            "learning": {},
            "thermal_models": {},
            "flexible_loads": [],
            "ventilation_models": {},
            "hot_water_models": {},
            "occupancy_models": {},
            "energy_runtime": {},
        }
        before = data["preferences"].copy()
        result = scenario.simulate_scenario(
            engine=Engine(), profiles=profiles, data=data, now=NOW,
            local_tz=timezone.utc, mode="vacation",
            comfort_delta_c=2, energy_price_multiplier=2,
        )
        self.assertFalse(result["persisted"])
        self.assertEqual(result["actuations"], 0)
        self.assertEqual(data["preferences"], before)

if __name__ == "__main__":
    unittest.main()
