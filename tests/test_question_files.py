from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType("ester_core")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/ester")]
sys.modules.setdefault("ester_core", package)
files = importlib.import_module("ester_core.question_files")
questions = importlib.import_module("ester_core.questions")
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


class QuestionFilesTests(unittest.TestCase):
    def test_new_answers_and_teaching_never_drop_older_knowledge(self):
        language = importlib.import_module("ester_core.language")
        old = [{"knowledge_id": str(i), "text": "memoria precedente"} for i in range(1001)]
        data = {"knowledge": deepcopy(old), "questions": [{"question_id": "note", "status": "open", "category": "other", "prompt": "Come usi la casa?"}]}
        questions.apply_answer(data, "note", "Normalmente lavoro da casa", NOW)
        language.store_teaching_items(data, {"items": [{"statement": "Una nuova nota", "domain": "other", "kind": "fact"}]}, NOW)
        self.assertEqual(data["knowledge"][:1001], old)
        self.assertEqual(len(data["knowledge"]), 1003)

    def setUp(self):
        self.data = {"questions": [{"question_id": "q1", "status": "open", "category": "climate",
                                  "area_id": "studio", "prompt": "Comfort?", "comfort_season": "winter",
                                  "title": "Comfort", "entity_ids": ["sensor.t"]}], "preferences": {"existing": 1}}
        self.document = files.export_questions(self.data, {"studio": {"name": "Studio"}}, NOW)

    def test_preview_then_apply_preserves_memory(self):
        self.document["questions"][0]["answer"] = "21 gradi"
        before = deepcopy(self.data)
        plan = files.preview_answers(self.data, self.document)
        self.assertEqual(self.data, before)
        self.assertEqual(plan[0]["interpretation"]["value"], 21)
        files.import_answers(self.data, self.document, NOW)
        self.assertEqual(self.data["preferences"], {"existing": 1, "seasonal_comfort:winter:studio": 21})
        with self.assertRaises(ValueError):
            files.import_answers(self.data, self.document, NOW)

    def test_empty_defer_and_obsolete(self):
        self.assertEqual(files.import_answers(self.data, self.document, NOW), [])
        self.document["questions"][0]["action"] = "defer"
        files.import_answers(self.data, self.document, NOW)
        self.assertEqual(self.data["questions"][0]["status"], "deferred")
        self.assertNotIn("knowledge", self.data)
        self.setUp()
        self.document["questions"][0]["action"] = "obsolete"
        files.import_answers(self.data, self.document, NOW)
        self.assertEqual(self.data["questions"][0]["status"], "obsolete")
        decision = {**self.data["questions"][0], "decision_id": "d", "reasoning": "", "risk": "low", "confidence": .4, "evidence": {"question": "Comfort?"}}
        _, created = questions.merge_questions(self.data["questions"], [decision], NOW+timedelta(days=30))
        self.assertEqual(created, [])

    def test_invalid_batch_is_atomic(self):
        self.document["questions"][0]["answer"] = "21 gradi"
        bad = deepcopy(self.document["questions"][0]); bad["question_id"] = "unknown"
        self.document["questions"].append(bad)
        before = deepcopy(self.data)
        with self.assertRaises(ValueError):
            files.import_answers(self.data, self.document, NOW)
        self.assertEqual(self.data, before)
        self.document["questions"].pop()
        self.data["questions"][0]["prompt"] = "Nuova domanda"
        with self.assertRaises(ValueError):
            files.preview_answers(self.data, self.document)

    def test_removed_room_and_registered_offline_sensor(self):
        questions.retire_removed_questions(self.data["questions"], {"studio"}, {"sensor.t"}, NOW)
        self.assertEqual(self.data["questions"][0]["status"], "open")
        questions.retire_removed_questions(self.data["questions"], set(), {"sensor.t"}, NOW)
        self.assertEqual(self.data["questions"][0]["status"], "removed_reference")

    def test_technical_health_is_not_a_question(self):
        q = {"status": "open", "category": "operational_safety", "title": "Dati non affidabili"}
        questions.merge_questions([q], [], NOW)
        self.assertEqual(q["status"], "technical_check")
        self.assertIsNone(questions.question_from_decision(q, NOW))
