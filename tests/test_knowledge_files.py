"""Additive knowledge must preserve all pre-existing memory."""
import copy
import importlib
import json
import unittest
from test_core import NOW

files = importlib.import_module("ester_core.knowledge_files")


class KnowledgeFileTests(unittest.TestCase):
    def test_append_preserves_memory_and_deduplicates(self):
        old = {"statement": "Luci accese la sera", "domain": "lighting", "status": "active"}
        store = {"knowledge": [old], "preferences": {"comfort:salotto": 21}, "learning": {"samples": 12}}
        before = copy.deepcopy(store)
        content = json.dumps({"format": "ester-knowledge-v1", "items": [
            {"statement": "Luci accese la sera", "domain": "lighting"},
            {"statement": "Luci spente la sera", "domain": "lighting"}]})
        rows = files.parse_documents([{"name": "luci.json", "content": content}])
        self.assertEqual(store, before)
        saved = files.append_documents(store, {"items": rows}, NOW)
        self.assertEqual(len(saved), 1)
        self.assertEqual(store["knowledge"][0], before["knowledge"][0])
        self.assertEqual(store["preferences"], before["preferences"])
        self.assertEqual(store["learning"], before["learning"])
        self.assertEqual(saved[0]["source_file"], "luci.json")
        self.assertEqual(files.append_documents(store, {"items": rows}, NOW), [])

    def test_text_multiple_files_and_duplicate_paragraphs(self):
        rows = files.parse_documents([{"name": "a.txt", "content": "Prima nota\n\nSeconda nota"},
                                     {"name": "b.md", "content": "Prima nota"}])
        self.assertEqual(len(files.additions([], rows)), 2)

    def test_backup_and_replacement_instructions_rejected(self):
        for document in ({"preferences": {"comfort:salotto": 20}},
                         {"format": "ester-knowledge-v1", "items": [{"statement": "Nuovo", "supersedes_hint": "vecchio"}]}):
            with self.assertRaises(ValueError):
                files.parse_documents([{"name": "bad.json", "content": json.dumps(document)}])

    def test_limits_do_not_delete_existing_knowledge(self):
        store = {"knowledge": [{"statement": str(i)} for i in range(1000)]}
        before = copy.deepcopy(store)
        with self.assertRaises(ValueError):
            files.append_documents(store, {"items": [{"statement": "new"}]}, NOW)
        self.assertEqual(store, before)
        with self.assertRaises(ValueError):
            files.parse_documents([{"name": "long.txt", "content": "x" * 1001}])
