"""Behavioral checks for the shared, time-aware Shadow memory."""
from copy import deepcopy
from datetime import timedelta
import importlib
import unittest

from test_core import NOW, profile, Engine, policies, scenario

brain = importlib.import_module("ester_core.brain")
files = importlib.import_module("ester_core.knowledge_files")
experiences = importlib.import_module("ester_core.experiences")


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [profile("temperature", "18"), profile("climate", "heat", domain="climate"),
                         profile("presence", "on", unit=None, domain="binary_sensor")]
        self.note = {"knowledge_id": "n1", "statement": "Comfort temporaneo", "source": "brain_note",
                     "status": "active", "area_id": "room", "domain": "climate",
                     "starts_at": (NOW-timedelta(hours=1)).isoformat(), "expires_at": (NOW+timedelta(hours=1)).isoformat(),
                     "effect": {"type": "comfort", "value": 23}}
        self.data = {"preferences": {"comfort:room": 20}, "brain_notes": [self.note], "knowledge": []}

    def decisions(self, data):
        return policies.evaluate(Engine(None), self.profiles, {}, [], data.get("preferences", {}), [], NOW, memory=data)

    def test_note_changes_real_decision_and_expiry_restores_base(self):
        before = deepcopy(self.data)
        decision = next(d for d in self.decisions(self.data) if d.evidence.get("target_c"))
        self.assertEqual(decision.evidence["target_c"], 23)
        self.assertEqual(decision.evidence["brain_preferences"][0]["knowledge_id"], "n1")
        expired = brain.working_memory(self.data, self.profiles, NOW+timedelta(hours=2))
        self.assertEqual(expired["preferences"]["comfort:room"], 20)
        self.assertEqual(expired["counts"]["expired"], 1)
        self.assertEqual(self.data, before)

    def test_conflict_blocks_affected_decision_only(self):
        self.data["brain_notes"].append({**self.note, "knowledge_id": "n2", "effect": {"type": "comfort", "value": 21}})
        decisions = self.decisions(self.data)
        affected = [d for d in decisions if d.evidence.get("brain_conflicts")]
        self.assertTrue(affected)
        self.assertTrue(all(d.status.value == "needs_input" for d in affected))
        self.assertTrue(all(not d.evidence.get("brain_conflicts") for d in decisions if d.category != "climate"))

    def test_all_season_note_overrides_seasonal_answer_until_expiry(self):
        self.data['preferences']['seasonal_comfort:winter:room'] = 21
        decision = next(d for d in self.decisions(self.data) if d.evidence.get('target_c'))
        self.assertEqual(decision.evidence['target_c'], 23)
        later = brain.working_memory(self.data, self.profiles, NOW+timedelta(hours=2))
        self.assertEqual(later['preferences']['seasonal_comfort:winter:room'], 21)

    def test_structured_file_is_used_without_changing_original_preferences(self):
        import json
        content = json.dumps({"format": "ester-knowledge-v2", "items": [{"statement": "Stare bene a 22 gradi",
            "domain": "climate", "kind": "preference", "area_id": "room", "effect": {"type": "comfort", "value": 22}}]})
        rows = files.parse_documents([{"name": "casa.json", "content": content}])
        data = {"knowledge": [{**r, "status": "active", "knowledge_id": "file1"} for r in rows]}
        decision = next(d for d in self.decisions(data) if d.evidence.get("target_c"))
        self.assertEqual(decision.evidence["target_c"], 22)
        self.assertEqual(decision.evidence["brain_preferences"][0]["source_file"], "casa.json")
        self.assertNotIn("preferences", data)

    def test_temporary_comfort_resolves_question_and_expiry_reopens(self):
        questions = [{"category": "climate", "area_id": "room", "prompt": "Quale temperatura di comfort desideri?", "status": "open"}]
        data = {"brain_notes": [self.note]}
        brain.reconcile_questions(questions, brain.working_memory(data, self.profiles, NOW), NOW)
        self.assertEqual(questions[0]["status"], "resolved_by_memory")
        later = NOW+timedelta(hours=2)
        brain.reconcile_questions(questions, brain.working_memory(data, self.profiles, later), later)
        self.assertEqual(questions[0]["status"], "open")

    def test_scenario_changes_shared_note_without_mutation(self):
        original = deepcopy(self.data)
        result = scenario.simulate_scenario(engine=Engine(None), profiles=self.profiles, data=self.data, now=NOW,
                                           local_tz=NOW.tzinfo, comfort_delta_c=1)
        self.assertTrue(any(d.get("evidence", {}).get("target_c") == 24 for d in result["decisions"]))
        self.assertEqual(self.data, original)

    def test_retrieval_considers_old_memory_and_excludes_expired(self):
        rows = [{"statement": "Nota generica " + str(i)} for i in range(100)]
        rows.insert(0, {"statement": "Antifurto: in vacanza tenere protetto il perimetro"})
        rows.append({"statement": "Antifurto precedente", "expires_at": (NOW-timedelta(hours=1)).isoformat()})
        retrieved = brain.retrieval_context({"knowledge": rows}, "antifurto vacanza", NOW, budget=100)
        self.assertIn("perimetro", retrieved["existing_knowledge"][0]["statement"])
        self.assertEqual(retrieved["memory_available"], 101)
        self.assertLess(retrieved["memory_retrieved"], 101)

    def test_invalid_effect_cannot_become_device_command(self):
        with self.assertRaises(ValueError):
            brain.validate_effect({"type": "service", "value": 1, "service": "light.turn_on"})
        with self.assertRaises(ValueError):
            brain.validate_effect({"type": "energy_price", "value": float("nan")})

    def test_experience_requires_feedback_before_reuse_and_rechecks_conditions(self):
        decision = next(d for d in self.decisions(self.data) if d.evidence.get("target_c"))
        payload = decision.as_dict()
        payload["confidence"] = .95
        data = {}
        experiences.remember(data, payload, NOW)
        self.assertEqual(data["brain_experiences"][0]["validation"], "unverified_prediction")
        self.assertEqual(experiences.similar_cases(data, decision), [])
        payload["feedback"] = {"rating": "correct"}
        experiences.remember(data, payload, NOW)
        self.assertEqual(len(data["brain_experiences"]), 1)
        self.assertEqual(experiences.similar_cases(data, decision)[0]["rating"], "correct")
        decision.evidence["observations"]["binary_sensor.presence"]["state"] = "off"
        self.assertEqual(experiences.similar_cases(data, decision), [])
        payload["feedback"] = {"rating": "wrong"}
        experiences.remember(data, payload, NOW)
        self.assertEqual(data["brain_experiences"][0]["rating"], "wrong")
