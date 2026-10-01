"""Regression checks for understandable questions and unknown answers."""
from test_core import questions, NOW
import unittest


class QuestionClarityTests(unittest.TestCase):
    def test_old_questions_refresh_without_losing_answers(self):
        old = {"question_id": "old", "category": "energy", "prompt": "Usa classify_entity", "status": "open"}
        answered = {"question_id": "done", "category": "climate", "status": "answered", "answer": "21 °C"}
        questions.merge_questions([old, answered], [], NOW)
        self.assertNotIn("classify_entity", old["display_prompt"])
        self.assertIn("Non lo so", old["quick_answers"])
        self.assertEqual(answered["answer"], "21 °C")
        self.assertEqual(answered["status"], "answered")

    def test_seasonal_question_retires_legacy_comfort_only(self):
        old = {"question_id": "old", "category": "climate", "area_id": "salotto", "title": "Comfort da definire", "prompt": "Quale comfort?", "status": "open"}
        sensor = {"question_id": "sensor", "category": "climate", "area_id": "salotto", "title": "Sensore", "prompt": "Quale sensore?", "status": "open"}
        decision = {"decision_id": "d", "category": "climate", "area_id": "salotto", "title": "Comfort da definire", "reasoning": "", "confidence": .4, "risk": "low", "evidence": {"question": "Quale comfort (winter)?", "comfort_season": "winter", "season_source": "calendar"}}
        _, new = questions.merge_questions([old, sensor], [decision], NOW)
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(sensor["status"], "open")
        self.assertIn("20 °C", new[0]["display_prompt"])

    def test_seasonal_suggestion_only_learns_on_confirmation(self):
        for season, degrees in (("winter", 20), ("summer", 26), ("shoulder", 20)):
            decision = {"decision_id": "d", "category": "climate", "area_id": "salotto",
                        "title": "Comfort", "reasoning": "", "confidence": .4, "risk": "low",
                        "evidence": {"question": "Quale comfort?", "comfort_season": season, "season_source": "calendar"}}
            q = questions.question_from_decision(decision, NOW)
            self.assertIn(f"{degrees} °C", q["display_prompt"])
            data = {"questions": [q], "preferences": {"comfort:altra_stanza": 21}}
            questions.apply_answer(data, q["question_id"], f"{degrees} °C", NOW)
            self.assertEqual(data["preferences"][f"seasonal_comfort:{season}:salotto"], degrees)
            self.assertNotIn("comfort:salotto", data["preferences"])
            self.assertEqual(data["preferences"]["comfort:altra_stanza"], 21)

    def test_sensor_question_is_not_a_comfort_preference(self):
        q = {"category": "climate", "area_id": "salotto",
             "prompt": "Quale sensore misura la temperatura ambiente?"}
        shown = questions._friendly_question(q, q["prompt"])
        self.assertIn("sensore", shown["display_prompt"])
        self.assertNotIn("21 °C", shown["quick_answers"])
        self.assertEqual(questions.interpret_answer(q, "Termometro 21 °C")["kind"], "knowledge_note")

    def test_unknown_does_not_train_memory(self):
        q = {"question_id": "one", "category": "climate", "area_id": "salotto", "status": "open"}
        data = {"questions": [q]}
        result = questions.apply_answer(data, "one", "Non lo so", NOW)
        self.assertEqual(result["kind"], "deferred")
        self.assertEqual(q["status"], "deferred")
        self.assertNotIn("preferences", data)
        self.assertNotIn("knowledge", data)

    def test_boiler_does_not_offer_arbitrary_temperatures(self):
        shown = questions._friendly_question({"category": "hot_water"}, "Temperatura ACS?")
        self.assertEqual(shown["quick_answers"], ["Non lo so"])
        self.assertIn("impostato", shown["display_prompt"])
