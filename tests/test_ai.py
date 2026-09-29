"""Provider boundary tests without credentials or network requests."""
import importlib
import sys
import types
from pathlib import Path
import unittest

package = types.ModuleType("ester_ai_test")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/ester/ai")]
sys.modules.setdefault("ester_ai_test", package)
Gemini = importlib.import_module("ester_ai_test.gemini").GeminiProvider


class Response:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class Session:
    def __init__(self, data):
        self.data = data
        self.request = None

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return Response(self.data)


class AITests(unittest.IsolatedAsyncioTestCase):
    async def test_text_only_no_tools_or_key_in_url(self):
        session = Session({"candidates": [{"content": {"parts": [{"text": "Spiegazione"}]}}]})
        provider = Gemini(session=session, api_key="test-secret", model="test-model")
        response = await provider.async_explain(decision={"category": "climate"}, context={})
        self.assertEqual(response.text, "Spiegazione")
        url, request = session.request
        self.assertNotIn("test-secret", url)
        self.assertEqual(request["headers"]["x-goog-api-key"], "test-secret")
        self.assertNotIn("tools", request["json"])

    async def test_empty_or_blocked_response(self):
        provider = Gemini(session=Session({"candidates": []}), api_key="test", model="test")
        with self.assertRaises(ValueError):
            await provider.async_explain(decision={}, context={})

    async def test_model_cannot_change_request_host(self):
        with self.assertRaises(ValueError):
            Gemini(session=None, api_key="test", model="../other?key=secret")
