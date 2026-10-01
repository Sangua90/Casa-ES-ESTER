"""Real HA authentication, multipart upload, persistence, and mobile browser flow."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


@unittest.skipUnless(importlib.util.find_spec("homeassistant"), "Requires Home Assistant")
class KnowledgeUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp.test_utils import TestClient, TestServer
        from homeassistant.auth import auth_manager_from_config
        from homeassistant.components.http.server import HomeAssistantHTTP
        from homeassistant.config_entries import ConfigEntryState
        from homeassistant.core import HomeAssistant
        from custom_components.ester.knowledge_upload import KnowledgeUploadView
        from custom_components.ester.services import register_services
        from custom_components.ester.storage import EsterStorage
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        from homeassistant.helpers import device_registry
        device_registry.async_setup(self.hass)
        await device_registry.async_load(self.hass)
        self.hass.auth = await auth_manager_from_config(self.hass, [], [])
        self.admin = await self.hass.auth.async_create_user("Upload admin")
        self.member = await self.hass.auth.async_create_user("Member")
        refresh = await self.hass.auth.async_create_refresh_token(self.admin, client_id="http://localhost/")
        self.token = self.hass.auth.async_create_access_token(refresh)
        self.store = EsterStorage(self.hass)
        await self.store.async_load()
        self.runtime = SimpleNamespace(storage=self.store, async_request_refresh=AsyncMock())
        entry = SimpleNamespace(runtime_data=self.runtime, state=ConfigEntryState.LOADED)
        self.hass.config_entries = SimpleNamespace(async_entries=lambda domain: [entry], async_shutdown=AsyncMock())
        register_services(self.hass)
        self.http = HomeAssistantHTTP(self.hass, None, None, None, ["127.0.0.1"], 0, [], "modern")
        self.hass.http = self.http
        await self.http.async_initialize(cors_origins=[], use_x_forwarded_for=False,
                                        login_threshold=-1, is_ban_enabled=False, use_x_frame_options=True)
        self.http.register_view(KnowledgeUploadView())
        self.client = TestClient(TestServer(self.http.app))

    async def asyncTearDown(self):
        await self.client.close()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def upload(self, files, token=None):
        from aiohttp import FormData
        await self.client.start_server()
        body = FormData()
        for name, content in files:
            body.add_field("files", content, filename=name, content_type="application/octet-stream")
        return await self.client.post("/api/ester/knowledge/upload", data=body,
                                      headers={"Authorization": f"Bearer {token or self.token}"})

    async def confirm(self, proposal):
        from homeassistant.core import Context
        return await self.hass.services.async_call("ester", "confirm_teaching",
            {"proposal_id": proposal["proposal_id"]}, blocking=True, return_response=True,
            context=Context(user_id=self.admin.id))

    async def test_upload_confirm_restart_and_same_names(self):
        from custom_components.ester.storage import EsterStorage
        batch = [("casa.txt", b"Prima informazione"), ("casa.txt", b"Seconda informazione")]
        # The complete upload and confirmation can only call ESTER internal services.
        original = self.hass.services.async_call
        async def internal_only(domain, *args, **kwargs):
            self.assertEqual(domain, "ester")
            return await original(domain, *args, **kwargs)
        with patch.object(type(self.hass.services), "async_call", side_effect=internal_only):
            response = await self.upload(batch)
            self.assertEqual(response.status, 200, await response.text())
            proposal = (await response.json())["proposal"]
            self.assertFalse(proposal["device_action"])
            self.assertEqual(self.store.data["knowledge"], [])
            restored = EsterStorage(self.hass)
            await restored.async_load()
            self.assertEqual(len(restored.data["pending_teachings"][-1]["documents"]), 2)
            self.assertEqual((await self.confirm(proposal))["saved"], 2)
            self.assertEqual(len(self.store.data["knowledge_documents"]), 2)
            for files in (batch, [("rinominato.txt", b"Prima informazione")]):
                proposal = (await (await self.upload(files)).json())["proposal"]
                self.assertEqual((await self.confirm(proposal))["saved"], 0)
            proposal = (await (await self.upload([("casa.txt", b"Terza informazione")])).json())["proposal"]
            self.assertEqual((await self.confirm(proposal))["saved"], 1)
            await restored.async_load()
            self.assertEqual(len(restored.data["knowledge"]), 3)
            self.assertEqual(len(restored.data["knowledge_documents"]), 3)

    async def test_rejections_are_atomic_and_admin_only(self):
        from copy import deepcopy
        before = deepcopy(self.store.data)
        for batch in ([('bad.txt', b'\xff')], [('big.txt', b'x' * 32001)],
                      [('ok.txt', b'Valid'), ('bad.json', b'{}')],
                      [('a.txt', b'Valid')] * 6, [('empty.txt', b'')],
                      [('file.pdf', b'PDF')],
                      [('a.txt', (b'x' * 999 + b'\n\n') * 31)] * 3):
            response = await self.upload(batch)
            self.assertEqual(response.status, 400, await response.text())
            self.assertEqual(self.store.data, before)
        response = await self.upload([('a.txt', b'Valid')], token='invalid')
        self.assertEqual(response.status, 401)
        refresh = await self.hass.auth.async_create_refresh_token(self.member, client_id="http://localhost/")
        token = self.hass.auth.async_create_access_token(refresh)
        response = await self.upload([('a.txt', b'Valid')], token=token)
        self.assertEqual(response.status, 403)
        with patch.object(self.store, 'async_save', side_effect=OSError('Disk full')):
            response = await self.upload([('a.txt', b'Valid')])
        self.assertEqual(response.status, 500)
        # Failed writes restore pending proposals as well as active knowledge.
        self.assertEqual(self.store.data.get('pending_teachings', []), before.get('pending_teachings', []))
        self.assertEqual(self.store.data['knowledge'], before['knowledge'])
        proposal = (await (await self.upload([('a.txt', b'Valid')])).json())['proposal']
        before_confirm = deepcopy(self.store.data)
        with patch.object(self.store, 'async_save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError):
                await self.confirm(proposal)
        self.assertEqual(self.store.data, before_confirm)
        self.assertEqual((await self.confirm(proposal))['saved'], 1)

    @unittest.skipUnless(os.environ.get("ESTER_BROWSER_TEST"), "Opt-in WebKit mobile E2E")
    async def test_iphone_browser_upload_and_confirm(self):
        from aiohttp import web
        from homeassistant.core import Context
        from playwright.async_api import async_playwright
        source = Path('custom_components/ester/frontend/ester-panel.js').read_text()
        async def page(request):
            return web.Response(text='<meta name="viewport" content="width=device-width,initial-scale=1"><ester-panel></ester-panel><script src="/test-panel.js"></script>', content_type='text/html')
        async def script(request):
            return web.Response(text=source, content_type='text/javascript')
        async def service(request):
            data = await request.json()
            result = await self.hass.services.async_call('ester', data['service'], data['service_data'],
                blocking=True, return_response=True, context=Context(user_id=self.admin.id))
            return web.json_response({'response': result})
        self.http.app.router.add_get('/test', page)
        self.http.app.router.add_get('/test-panel.js', script)
        self.http.app.router.add_post('/test-service', service)
        await self.client.start_server()
        async with async_playwright() as playwright:
            browser = await playwright.webkit.launch()
            context = await browser.new_context(**playwright.devices['iPhone 13'])
            page = await context.new_page()
            await page.goto(str(self.client.make_url('/test')))
            await page.evaluate('''token => {
              const panel = document.querySelector('ester-panel');
              panel._tab = 'teach';
              panel.hass = {states:{}, auth:{accessToken:token,expired:false},
                hassUrl:path=>new URL('/'+path,location.origin).href,
                callWS:async data=>(await fetch('/test-service',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})).json(),
                callService:async()=>{}};
              panel.render();
            }''', self.token)
            await page.locator('#knowledge-files').set_input_files([
                {'name':'casa.txt','mimeType':'text/plain','buffer':b'Prima informazione'},
                {'name':'casa.txt','mimeType':'text/plain','buffer':b'Seconda informazione'}])
            self.assertEqual(await page.locator('.upload-files li').count(), 2)
            await page.locator('#knowledge-files-upload').click()
            await page.locator('#teach-confirm').wait_for()
            self.assertIn('2 file caricati', await page.locator('#knowledge-upload-status').inner_text())
            self.assertEqual(self.store.data['knowledge'], [])
            self.assertEqual(await page.locator('#knowledge-upload-progress').evaluate('(el)=>el.value'), 100)
            self.assertTrue(await page.locator('#knowledge-files-upload').is_disabled())
            self.assertTrue(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            if os.environ.get('ESTER_SCREENSHOT'):
                await page.screenshot(path=os.environ['ESTER_SCREENSHOT'], full_page=True)
            await page.locator('#teach-confirm').click()
            await page.wait_for_function("document.querySelector('ester-panel')._teachDraft === null")
            self.assertEqual(len(self.store.data['knowledge']), 2)
            await page.locator('#knowledge-files').set_input_files([
                {'name':'bad.json','mimeType':'application/json','buffer':b'{}'}])
            await page.locator('#knowledge-files-upload').click()
            await page.wait_for_function("document.querySelector('ester-panel')._uploadStatus.includes('File non caricati')")
            self.assertEqual(await page.locator('.upload-files li').count(), 1)
            self.assertFalse(await page.locator('#knowledge-files-upload').is_disabled())
            self.assertEqual(len(self.store.data['knowledge']), 2)
            await page.locator('#knowledge-files').set_input_files([
                {'name':'casa.txt','mimeType':'text/plain','buffer':b'Terza informazione'}])
            await page.route('**/api/ester/knowledge/upload', lambda route: route.abort())
            await page.locator('#knowledge-files-upload').click()
            await page.wait_for_function("document.querySelector('ester-panel')._uploadStatus.includes('Connessione interrotta')")
            await page.unroute('**/api/ester/knowledge/upload')
            await page.locator('#knowledge-files-upload').click()
            await page.locator('#teach-confirm').wait_for()
            await page.locator('#teach-confirm').click()
            await page.wait_for_function("document.querySelector('ester-panel')._teachDraft === null")
            self.assertEqual(len(self.store.data['knowledge']), 3)
            self.assertTrue(await page.evaluate('''() => {
              const panel = document.querySelector('ester-panel');
              const nav = panel.shadowRoot.querySelector('nav');
              nav.scrollLeft = 150; const before = nav.scrollLeft;
              panel.hass = {...panel._hass};
              return nav.scrollLeft === before && before > 0;
            }'''))
            await browser.close()
