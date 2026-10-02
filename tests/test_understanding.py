"""Teaching changes forecasts only after confirmation; alternatives respect physics."""
from datetime import timedelta
from copy import deepcopy
import importlib
import unittest
from zoneinfo import ZoneInfo

from test_core import NOW, profile, policies, Engine, usage

teaching = importlib.import_module("ester_core.teaching")
language = importlib.import_module("ester_core.language")
brain = importlib.import_module("ester_core.brain")
deliberation = importlib.import_module("ester_core.deliberation")
files = importlib.import_module("ester_core.knowledge_files")

ROOMS = {"room":{"name":"Studio"}, "guest":{"name":"Studio ospiti"}}


class UnderstandingTests(unittest.TestCase):
    def test_two_facts_become_confirmed_preference_and_expected_use(self):
        proposal = language.validate_teaching(teaching.compile_message(
            "In studio preferisco 21 °C; in studio lavoro dalle 9 alle 18 nei feriali", ROOMS, NOW), "originale", ROOMS)
        store = {"knowledge":[]}
        profiles = [profile("temperature", "18"), profile("climate", "heat", domain="climate")]
        preview = brain.working_memory(store, profiles, NOW)
        self.assertEqual(preview["usage_profiles"], [])
        self.assertNotIn("comfort:room", preview["preferences"])
        language.store_teaching_items(store, proposal, NOW)
        result = policies.evaluate(Engine(), profiles, {}, [], {}, [], NOW, memory=store)
        decision = next(d for d in result if d.evidence.get("target_c")==21)
        self.assertEqual(decision.evidence["expected_use"]["expected_occupancy"], 1)
        self.assertTrue(decision.evidence["brain_routines"])
        self.assertEqual(store.get("preferences", {}), {})
        self.assertEqual(decision.outcome["type"], "not_executed")

    def test_incomplete_or_conditional_facts_never_invent_a_schedule(self):
        for sentence in ("In studio lavoro fino alle 18", "In studio lavoro dalle 9 alle 18",
                         "Se viene Marco in studio lavoro dalle 9 alle 18 nei feriali"):
            row = teaching.compile_message(sentence, ROOMS, NOW)["items"][0]
            self.assertNotIn("routine", row, sentence)
            self.assertTrue(row["clarifications"], sentence)
        for sentence in ("Non voglio 21 gradi in studio", "Se siamo in casa voglio 21 gradi in studio",
                         "Preferisco -21 gradi in studio"):
            row = teaching.compile_message(sentence, ROOMS, NOW)["items"][0]
            self.assertNotIn("effect", row)

    def test_room_aliases_avoid_prefix_confusion(self):
        row = teaching.compile_message("Preferisco 22 gradi nello Studio ospiti", ROOMS, NOW)["items"][0]
        self.assertEqual(row["area_id"], "guest")
        ambiguous = teaching.compile_message("Studio e Studio ospiti: voglio 22 gradi", ROOMS, NOW)["items"][0]
        self.assertNotIn("effect", ambiguous)

    def test_dates_and_overnight_use_expire_at_the_actual_end(self):
        zone = ZoneInfo("Europe/Rome")
        row = teaching.compile_message("Oggi in studio lavoro dalle 22 alle 2", ROOMS, NOW, zone)["items"][0]
        self.assertEqual(row["routine"]["weekdays"], [NOW.astimezone(zone).weekday()])
        from datetime import datetime
        end = datetime.fromisoformat(row["expires_at"])
        self.assertEqual(end.hour, 2)
        self.assertEqual(end.date(), NOW.astimezone(zone).date()+timedelta(days=1))
        tomorrow = teaching.compile_message("Domani preferisco 22 gradi in studio", ROOMS, NOW, zone)["items"][0]
        self.assertEqual(brain.validity(tomorrow, NOW), "scheduled")
        self.assertEqual(brain.validity(tomorrow, NOW+timedelta(days=3)), "expired")

    def test_price_and_weekday_ranges_are_explicit(self):
        row = teaching.compile_message("Pago energia 0,31 €/kWh", ROOMS, NOW)["items"][0]
        self.assertEqual(row["effect"]["value"], .31)
        for text in ("Pago energia -0,31 €/kWh", "Pago 0,2 e 0,3 euro/kWh in studio"):
            self.assertNotIn("effect", teaching.compile_message(text, ROOMS, NOW)["items"][0])
        routine = teaching.compile_message("In studio lavoro dalle 9 alle 18 dal martedì al giovedì", ROOMS, NOW)["items"][0]["routine"]
        self.assertEqual(routine["weekdays"], [1,2,3])

    def test_provider_and_json_cannot_introduce_commands_or_unknown_rooms(self):
        with self.assertRaises(ValueError):
            language.validate_teaching({"items":[{"statement":"Comfort", "area_id":"unknown", "effect":{"type":"comfort", "value":21}}]}, "test", ROOMS)
        with self.assertRaises(ValueError):
            teaching.validate_routine({"start_time":"09:00","end_time":"18:00","weekdays":[True],"expected_occupancy":1}, "room")
        with self.assertRaises(ValueError):
            teaching.validate_routine({"service":"light.turn_on"}, "room")
        import json
        content=json.dumps({"format":"ester-knowledge-v2","items":[{"statement":"Uso studio", "area_id":"room",
            "routine":{"start_time":"09:00","end_time":"18:00","weekdays":[1],"expected_occupancy":1,"comfort_c":22}}]})
        self.assertEqual(files.parse_documents([{"name":"casa.json","content":content}])[0]["routine"]["comfort_c"], 22)

    def test_retracted_parent_excludes_derived_memory(self):
        original = {"knowledge_id":"raw","statement":"In studio preferisco 21 gradi","status":"active"}
        child = {**teaching.compile_item(original, ROOMS, NOW), "knowledge_id":"op","derived_from":"raw"}
        data={"knowledge":[original, child]}
        profiles=[profile("temperature")]
        self.assertEqual(brain.working_memory(data, profiles, NOW)["preferences"]["comfort:room"], 21)
        original["status"]="retracted"
        self.assertNotIn("comfort:room", brain.working_memory(data, profiles, NOW)["preferences"])

    def test_ancestor_retirement_and_cycles_exclude_all_derived_values(self):
        source = {"knowledge_id":"root", "statement":"Fonte", "status":"retracted"}
        parent = {"knowledge_id":"parent", "statement":"Chiarimento", "derived_from":"root"}
        child = {"knowledge_id":"child", "statement":"Comfort", "derived_from":"parent", "area_id":"room",
                 "effect":{"type":"comfort","value":21}}
        frame = brain.working_memory({"knowledge":[source,parent,child]}, [profile("temperature")], NOW)
        self.assertNotIn("comfort:room", frame["preferences"])
        self.assertEqual(brain.retrieval_context({"knowledge":[source,parent,child]}, "Comfort", NOW)["memory_available"], 0)
        source.update(status="active", derived_from="child")
        self.assertNotIn("comfort:room", brain.working_memory({"knowledge":[source,parent,child]}, [profile("temperature")], NOW)["preferences"])

    def test_routine_times_are_canonical_and_absence_is_not_future_occupancy(self):
        routine = teaching.validate_routine({"start_time":"9:00", "end_time":"18:00", "weekdays":[0], "expected_occupancy":0}, "room")
        self.assertEqual(routine["start_time"], "09:00")
        row = {"knowledge_id":"absence", "statement":"Assenza", "area_id":"room", "routine":{
            "start_time":"12:45", "end_time":"18:00", "weekdays":[NOW.weekday()], "expected_occupancy":0,"comfort_c":21}}
        result = policies.evaluate(Engine(), [profile("temperature","18"),profile("climate","heat",domain="climate")],
            {}, [], {}, [], NOW, memory={"knowledge":[row]}, thermal_models={"room":{"active_rate_c_per_h":2,"passive_rate_c_per_h":-.2}})
        self.assertFalse(any(d.evidence.get("comparison") for d in result))

    def test_scheduled_comfort_does_not_become_an_all_day_preference(self):
        row = teaching.compile_message("In studio lavoro dalle 9 alle 18 nei feriali e preferisco 21 gradi", ROOMS, NOW)["items"][0]
        self.assertNotIn("effect", row)
        self.assertEqual(row["routine"]["comfort_c"], 21)
        incomplete = teaching.compile_message("In studio lavoro dalle 9 alle 18 e preferisco 21 gradi", ROOMS, NOW)["items"][0]
        self.assertNotIn("effect", incomplete)
        self.assertNotIn("routine", incomplete)

    def test_routine_with_comfort_can_predict_without_a_global_target(self):
        row={"knowledge_id":"r1","statement":"Uso studio", "area_id":"room","routine":{
            "start_time":"12:45","end_time":"18:00","weekdays":[NOW.weekday()],"expected_occupancy":1,"comfort_c":21}}
        result=policies.evaluate(Engine(), [profile("temperature","18"), profile("climate","heat",domain="climate")],
            {}, [], {}, [], NOW, memory={"knowledge":[row]}, thermal_models={"room":{"active_rate_c_per_h":2,"passive_rate_c_per_h":-.2,"confidence":.8}})
        proposal=next(d for d in result if d.title=="Uso stanza previsto")
        self.assertEqual(proposal.evidence["target_c"],21)
        self.assertTrue(proposal.evidence["brain_routines"])

    def test_overlapping_current_routine_targets_require_clarification(self):
        rows=[{"knowledge_id":str(n),"statement":"Uso studio", "area_id":"room","routine":{
            "start_time":"09:00","end_time":"18:00","weekdays":[NOW.weekday()],"expected_occupancy":1,"comfort_c":n}} for n in (21,24)]
        result=policies.evaluate(Engine(), [profile("temperature","18"), profile("climate","heat",domain="climate")],
            {}, [], {}, [], NOW, memory={"knowledge":rows})
        proposal=next(d for d in result if d.evidence.get("routine_conflicts"))
        self.assertEqual(proposal.status.value, "needs_input")

    def test_calendar_lookup_handles_weekend_boundary_and_full_days(self):
        friday=NOW.replace(day=25,hour=23,minute=30)  # Friday 2026-09-25.
        routines=[{"profile_id":"r1","area_id":"room","weekdays":[5],"start_time":"00:15","end_time":"02:00","expected_occupancy":1},
                  {"profile_id":"all","area_id":"guest","weekdays":[5],"start_time":"12:00","end_time":"12:00","expected_occupancy":1}]
        result=usage.usage_snapshot(routines,friday,friday.tzinfo)
        self.assertEqual(result["room"]["upcoming"][0]["minutes_until"],45)
        self.assertEqual(result["guest"]["upcoming"][0]["minutes_until"],30)


class AlternativeTests(unittest.TestCase):
    def compare(self, current=18,target=21,horizon=120, passive=.8,active=2,power=2,price=.25,pv=None,prefs=None):
        model={"passive_rate_c_per_h":passive,"active_rate_c_per_h":active,"confidence":.8}
        options=deliberation.climate_candidates(current_c=current,target_c=target,minutes_until_use=horizon,model=model,
            estimated_power_kw=power,energy_price_eur_kwh=price,pv_surplus_kw=pv)
        return deliberation.compare_alternatives(options,target,prefs,model)

    def test_wait_is_selected_when_passive_evolution_meets_comfort(self):
        comparison=self.compare(current=21,target=21,passive=0)
        self.assertEqual(comparison["selected_strategy"],"wait")

    def test_later_start_can_use_less_energy_with_equal_comfort(self):
        comparison=self.compare()
        self.assertEqual(comparison["selected_strategy"],"precondition")
        now=next(c for c in comparison["candidates"] if c["strategy"]=="condition_now")
        later=next(c for c in comparison["candidates"] if c["strategy"]=="precondition")
        self.assertLess(later["estimated_energy_kwh"],now["estimated_energy_kwh"])
        self.assertTrue(later["meets_comfort"])

    def test_observed_solar_can_change_choice_but_is_declared_conditional(self):
        comparison=self.compare(pv=2)
        self.assertEqual(comparison["selected_strategy"],"condition_now")
        selected=next(c for c in comparison["candidates"] if c["selected"])
        self.assertTrue(selected["solar_assumption"])
        self.assertTrue(any("non da una previsione" in u for u in comparison["uncertainties"]))
        energy_first=self.compare(pv=2,prefs={"objective_weight:cost":0,"objective_weight:energy":1})
        self.assertEqual(energy_first["selected_strategy"],"precondition")

    def test_unreachable_deadline_never_fabricates_target_temperature(self):
        comparison=self.compare(current=17,target=20,horizon=45,passive=-.2)
        self.assertFalse(any(c["meets_comfort"] for c in comparison["candidates"]))
        self.assertLess(max(c["predicted_temp_at_use"] for c in comparison["candidates"]),20)
        self.assertTrue(any("Nessuna alternativa" in u for u in comparison["uncertainties"]))

    def test_unknown_costs_and_energy_remain_unknown(self):
        comparison=self.compare(power=None,price=None)
        active=next(c for c in comparison["candidates"] if c["strategy"]=="condition_now")
        self.assertIsNone(active["estimated_cost_eur"])
        self.assertIsNone(active["estimated_energy_kwh"])
        self.assertFalse(comparison["causal_savings_measured"])

    def test_cooling_and_future_drift_use_the_correct_direction(self):
        comparison=self.compare(current=28,target=24,passive=.2,active=-3)
        self.assertTrue(any(c["meets_comfort"] for c in comparison["candidates"]))
        drift=self.compare(current=21,target=21,passive=-1,active=2)
        self.assertEqual(drift["selected_strategy"],"precondition")

    def test_comparison_is_read_only_and_invalid_model_does_not_win(self):
        model={"passive_rate_c_per_h":-.2,"active_rate_c_per_h":float("nan")}
        original=deepcopy(model)
        candidates=deliberation.climate_candidates(current_c=18,target_c=21,minutes_until_use=60,model=model)
        comparison=deliberation.compare_alternatives(candidates,21,{},model)
        self.assertIsNone(comparison["selected_strategy"])
        self.assertEqual(model.keys(),original.keys())
