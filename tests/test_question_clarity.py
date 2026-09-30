"""Regression checks for understandable questions and unknown answers."""
from test_core import questions, NOW
import unittest


class QuestionClarityTests(unittest.TestCase):
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
