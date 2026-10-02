from copy import deepcopy
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType("ester_core")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/ester")]
sys.modules.setdefault("ester_core", package)
policy = importlib.import_module("ester_core.knowledge_policy")
report = importlib.import_module("ester_core.diagnostics_report")
models = importlib.import_module("ester_core.models")
evaluate = importlib.import_module("ester_core.policies").evaluate
Engine = importlib.import_module("ester_core.decision_engine").EsterDecisionEngine
progress = importlib.import_module("ester_core.progress")
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def sensor(entity, role, state="off", unit=None, area="room"):
    return models.EntityProfile(entity, entity.split(".")[0], entity, state, area_id=area,
                                role=role, unit=unit, attributes={"last_reported": NOW.isoformat(), "area_name": "Salotto"})


class LearningReportTests(unittest.TestCase):
    def test_plain_text_memory_is_used_without_changing_its_category(self):
        profiles = [sensor("light.room", "lighting", "on"), sensor("binary_sensor.motion", "presence")]
        memory = [{"knowledge_id": "plain", "domain": "other", "source_file": "casa.txt",
                   "statement": "In Salotto qualcuno può rimanere immobile sul divano."}]
        before = deepcopy(memory)
        light = next(d for d in evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=memory) if d.category == "lighting")
        self.assertEqual(light.status, models.DecisionStatus.SUPPRESSED)
        self.assertEqual(light.evidence['knowledge_context'][0]['source_file'], 'casa.txt')
        self.assertEqual(memory, before)
        memory[0]['status'] = 'superseded'
        light = next(d for d in evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=memory) if d.category == "lighting")
        self.assertEqual(light.proposed_action, "Avrei spento la luce")

    def test_text_scope_does_not_move_a_rule_to_another_room(self):
        profiles = [sensor("light.room", "lighting", "on"), sensor("binary_sensor.motion", "presence"),
                    models.EntityProfile('light.kitchen', 'light', 'Cucina', 'on', area_id='kitchen', role='lighting', attributes={'area_name':'Cucina','last_reported':NOW.isoformat()})]
        note = {'domain':'other','statement':'In Cucina qualcuno può rimanere immobile.'}
        self.assertEqual(policy.relevant_knowledge([note], 'lighting', 'room', profiles), [])
        self.assertEqual(policy.relevant_knowledge([note], 'lighting', 'kitchen', profiles), [note])
        note['statement'] = 'In Salotto nessuno rimane immobile.'
        light = next(d for d in evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=[note]) if d.category == "lighting" and d.area_id=='room')
        self.assertNotEqual(light.status, models.DecisionStatus.SUPPRESSED)

    def test_unlabelled_energy_ids_and_unimplemented_climate_are_traceable(self):
        pv = sensor('sensor.pv', 'generic', '1200', 'W')
        mapped, audit = policy.prepare_profiles([pv], [{'domain':'other','statement':'FV reale: sensor.pv'}])
        self.assertEqual(mapped[0].role, 'solar_power')
        self.assertEqual(audit[0]['status'], 'applied')
        profiles = [sensor('climate.room','climate','heat'), sensor('sensor.t','temperature','18','°C')]
        note = {'knowledge_id':'comfort', 'domain':'other','statement':'In Salotto preferiamo comfort intorno a 21 gradi.'}
        climate = next(d for d in evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=[note]) if d.category=='climate' and d.title=='Comfort da definire')
        self.assertEqual(climate.evidence['knowledge_context'][0]['knowledge_id'], 'comfort')
        self.assertIn('Resta da verificare', climate.evidence['knowledge_followup'])

    def test_progress_is_evidence_not_autonomous_activation(self):
        data = {"knowledge": [{"knowledge_id": "k"}], "last_replay": {"status": "ready", "decisions": 12}}
        current = {"profiles": {"sensor.t": sensor("sensor.t", "temperature", "20", "°C").as_dict()},
                   "history": {"status": "ready"}, "thermal_models": {"room": {"confidence": .8}},
                   "migration_readiness": {"climate": {"status": "candidate_for_manual_migration"}},
                   "questions": [], "kpis": {"feedback": {"quality_score": .9, "samples": 20}}}
        status = progress.progress_status(data, current, NOW)
        self.assertEqual(status["verified"], 8)
        self.assertLess(status["verified_percent"], 100)
        self.assertFalse(status["operational"])
        self.assertIsNone(status["real_efficiency_percent"])
        self.assertEqual(status["feedback_quality_percent"], 90)
        current["profiles"]["sensor.t"]["state"] = "unavailable"
        self.assertFalse(progress.progress_status(data, current, NOW)["checks"][1]["verified"])

    def test_explicit_mapping_units_conflicts_and_manual_override(self):
        pv = sensor("sensor.pv", "generic", "1200", "W")
        memory = [{"knowledge_id": "k1", "domain": "energy", "text": "Potenza FV reale `sensor.pv`."}]
        profiles, audit = policy.prepare_profiles([pv], memory)
        self.assertEqual(profiles[0].role, "solar_power")
        self.assertEqual(pv.role, "generic")
        self.assertEqual(audit[0]["status"], "applied")
        profiles, audit = policy.prepare_profiles([pv], memory, {"sensor.pv": {"role": "load_power"}})
        self.assertEqual(profiles[0].role, "generic")
        self.assertEqual(audit[0]["status"], "needs_review")
        pv.unit = "kWh"
        self.assertEqual(policy.prepare_profiles([pv], memory)[0][0].role, "generic")
        pv.unit = "W"
        memory.append({"domain": "energy", "text": "Consumo totale `sensor.pv`."})
        self.assertEqual(policy.prepare_profiles([pv], memory)[1][0]["status"], "conflict")

    def test_light_constraint_changes_shadow_proposal(self):
        profiles = [sensor("light.room", "lighting", "on"), sensor("binary_sensor.motion", "presence")]
        memory = [{"knowledge_id": "k1", "category": "lighting", "area_id": "Salotto", "text": "Qualcuno può rimanere immobile sul divano."}]
        decisions = evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=memory)
        light = next(d for d in decisions if d.category == "lighting")
        self.assertEqual(light.status, models.DecisionStatus.SUPPRESSED)
        self.assertNotIn("Avrei spento", light.proposed_action)
        self.assertEqual(light.evidence["knowledge_context"][0]["application"], "constraint_applied")
        memory[0]["status"] = "superseded"
        light = next(d for d in evaluate(Engine(), profiles, {}, [], {}, [], NOW, knowledge=memory) if d.category == "lighting")
        self.assertEqual(light.proposed_action, "Avrei spento la luce")

    def test_adjacent_sensor_labels_do_not_contaminate_mappings(self):
        profiles = [sensor("sensor.pv", "generic", "1000", "W"), sensor("sensor.load", "generic", "300", "W"),
                    sensor("sensor.soc", "generic", "50", "%"), sensor("sensor.grid", "generic", "0", "W")]
        knowledge = [{"domain": "energy", "text": "`sensor.pv` per FV reale, `sensor.load` per i carichi, `sensor.soc` per SOC. Rete: `sensor.grid`."}]
        result, audit = policy.prepare_profiles(profiles, knowledge)
        self.assertEqual([p.role for p in result], ["solar_power", "load_power", "battery", "grid_power"])
        self.assertTrue(all(row["status"] == "applied" for row in audit))

    def test_dynamic_water_blocks_fixed_target_question(self):
        memory = [{"knowledge_id": "k", "domain": "hot_water", "text": "Il boiler non deve avere un target fisso."}]
        decisions = evaluate(Engine(), [sensor("sensor.boiler", "hot_water", "50", "°C")], {}, [], {}, [], NOW, knowledge=memory)
        decision = next(d for d in decisions if d.category == "hot_water")
        self.assertEqual(decision.status, models.DecisionStatus.SUPPRESSED)
        self.assertIsNone(decision.evidence["question"])
        self.assertNotIn("target_c", decision.evidence)

    def test_report_preserves_full_learning_and_explains_context(self):
        data = {"knowledge": [{"knowledge_id": "k", "category": "lighting", "text": "Una nota"}],
                "learning": {"sensor.t": {"samples": 42}}, "questions": [{"status": "answered"}],
                "memory_versions": [{"snapshot_id": "s", "memory": {"knowledge": []}}]}
        before = deepcopy(data)
        current = {"evaluated_at": NOW.isoformat(), "latest_decisions": [{"evidence": {"knowledge_context": [{"knowledge_id": "k", "application": "context_only"}]}}]}
        result = report.learning_report(data, current, "1.5.0", NOW)
        self.assertEqual(data, before)
        self.assertEqual(result["memory_and_learning"]["learning"]["sensor.t"]["samples"], 42)
        self.assertEqual(result["assessment"]["knowledge_audit"][0]["application"], "context_only")
        self.assertFalse(result["real_actuation_enabled"])
        self.assertNotIn("memory", result["memory_and_learning"]["memory_versions"][0])

    def test_rules_are_not_verified_just_because_they_are_saved(self):
        memory = {"knowledge": [{"knowledge_id": "r", "kind": "rule", "statement": "Solo quando sono a casa"}]}
        audit = report.knowledge_audit(memory, {})
        self.assertTrue(audit[0]["operational_verification_pending"])
        current = {"latest_decisions": [{"evidence": {"knowledge_context": [{"knowledge_id": "r", "application": "context_only"}]}}]}
        self.assertTrue(report.knowledge_audit(memory, current)[0]["operational_verification_pending"])
        current["latest_decisions"][0]["evidence"]["knowledge_context"][0]["application"] = "constraint_applied"
        self.assertFalse(report.knowledge_audit(memory, current)[0]["operational_verification_pending"])
