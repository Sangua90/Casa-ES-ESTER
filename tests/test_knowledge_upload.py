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
        from homeassistant.helpers import device_registry, area_registry, entity_registry
        device_registry.async_setup(self.hass)
        await device_registry.async_load(self.hass)
        await area_registry.async_load(self.hass)
        await entity_registry.async_load(self.hass)
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

    async def test_brain_note_failure_and_experience_persistence(self):
        from homeassistant.core import Context
        from homeassistant.exceptions import HomeAssistantError
        from unittest.mock import patch
        self.store.data['decisions'] = [{'decision_id':'case1','category':'lighting','area_id':'room',
            'entity_ids':['light.room'],'title':'Luce','proposed_action':'Mantieni accesa','confidence':.9,
            'created_at':'2026-10-02T10:00:00+00:00','status':'shadow','evidence':{'observations':{'light.room':{'state':'on'}}}}]
        await self.hass.services.async_call('ester','add_feedback',{'decision_id':'case1','rating':'correct'},
            blocking=True,context=Context(user_id=self.admin.id))
        restored=type(self.store)(self.hass)
        await restored.async_load()
        self.assertEqual(restored.data['brain_experiences'][0]['rating'],'correct')
        with patch.object(self.store,'async_save',side_effect=OSError('disk failed')):
            with self.assertRaises((OSError,HomeAssistantError)):
                await self.hass.services.async_call('ester','save_brain_note',{'statement':'Non salvata'},
                    blocking=True,return_response=True,context=Context(user_id=self.admin.id))
        self.assertEqual(self.store.data['brain_notes'],[])

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
            collection_response = await self.client.get('/api/ester/knowledge/upload', headers={'Authorization': f'Bearer {self.token}'})
            collection = await collection_response.json()
            self.assertEqual(collection['count'], 2)
            self.assertTrue(all(f['status'] == 'pending' for f in collection['files']))
            self.assertNotIn('content', json.dumps(collection))
            restored = EsterStorage(self.hass)
            await restored.async_load()
            self.assertEqual(len(restored.data["pending_teachings"][-1]["documents"]), 2)
            self.assertEqual(len(restored.data['knowledge_documents']), 2)
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
            collection = await (await self.client.get('/api/ester/knowledge/upload', headers={'Authorization': f'Bearer {self.token}'})).json()
            self.assertEqual(collection['count'], 3)
            self.assertTrue(all(f['status'] == 'confirmed' for f in collection['files']))
            self.assertIn('rinominato.txt', collection['files'][0]['names'])

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
        response = await self.client.get('/api/ester/knowledge/upload', headers={'Authorization': f'Bearer {token}'})
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
                blocking=True, return_response=data.get('return_response', False), context=Context(user_id=self.admin.id))
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
                hassUrl:path=>new URL(path,location.origin).href,
                callWS:async data=>(await fetch('/test-service',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})).json(),
                callService:async(domain,service,service_data)=>(await fetch('/test-service',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({domain,service,service_data})})).json()};
              panel.render();
            }''', self.token)
            await page.wait_for_function("document.querySelector('ester-panel')._fileCollection !== null")
            await page.locator('#teach').fill('Nota ancora da inviare')
            await page.locator('#knowledge-files').set_input_files([
                {'name':'casa.txt','mimeType':'text/plain','buffer':b'Prima informazione'},
                {'name':'casa.txt','mimeType':'text/plain','buffer':b'Seconda informazione'}])
            self.assertEqual(await page.locator('.upload-files li').count(), 2)
            self.assertEqual(await page.locator('#teach').input_value(), 'Nota ancora da inviare')
            await page.locator('#knowledge-files-upload').click()
            await page.locator('#teach-confirm').wait_for()
            self.assertIn('2 file salvati e conservati', await page.locator('#knowledge-upload-status').inner_text())
            self.assertIn('Raccolta file conservati in memoria · 2', await page.locator('#knowledge-collection').inner_text())
            self.assertFalse(await page.locator('#knowledge-files-add-more').is_disabled())
            self.assertEqual(self.store.data['knowledge'], [])
            self.assertEqual(await page.locator('#knowledge-upload-progress').evaluate('(el)=>el.value'), 100)
            self.assertTrue(await page.locator('#knowledge-files-upload').is_disabled())
            self.assertTrue(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            if os.environ.get('ESTER_SCREENSHOT'):
                await page.screenshot(path=os.environ['ESTER_SCREENSHOT'], full_page=True)
            # A new panel recovers uploaded files and pending proposals from real HA storage.
            await page.evaluate('''() => {
              const old = document.querySelector('ester-panel');
              const hass = old._hass;
              const panel = document.createElement('ester-panel'); old.replaceWith(panel);
              panel._tab = 'teach'; panel.hass = hass; panel.render();
            }''')
            await page.locator('[data-file-proposal]').wait_for()
            self.assertIn('Raccolta file conservati in memoria · 2', await page.locator('#knowledge-collection').inner_text())
            await page.locator('[data-file-proposal]').click()
            await page.wait_for_function("document.querySelector('ester-panel')._teachDraft === null && !document.querySelector('ester-panel')._busy")
            self.assertEqual(len(self.store.data['knowledge']), 2)
            await page.locator('#knowledge-files').set_input_files([
                {'name':'bad.json','mimeType':'application/json','buffer':b'{}'}])
            await page.locator('#knowledge-files-upload').click()
            await page.wait_for_function("document.querySelector('ester-panel')._uploadStatus.includes('Caricamento non confermato')")
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
            await page.wait_for_function("document.querySelector('ester-panel')._teachDraft === null && !document.querySelector('ester-panel')._busy")
            self.assertEqual(len(self.store.data['knowledge']), 3)
            self.assertTrue(await page.evaluate('''() => {
              const panel = document.querySelector('ester-panel');
              panel._advanced=true; panel.render();
              const nav = panel.shadowRoot.querySelector('nav');
              nav.scrollLeft = 150; const before = nav.scrollLeft;
              panel.hass = {...panel._hass};
              return nav.scrollLeft === before && before > 0;
            }'''))
            await page.evaluate('''() => {
              const panel=document.querySelector('ester-panel');
              panel._tab='brain'; panel._advanced=false; panel.render();
            }''')
            await page.wait_for_function("document.querySelector('ester-panel')._brain !== null")
            self.assertEqual(await page.locator('nav [data-tab]').count(), 3)
            await page.locator('summary').filter(has_text='INFORMAZIONI CHE CAMBIANO NEL TEMPO').click()
            await page.locator('#brain-note').fill('Tariffa temporanea confermata')
            await page.locator('#brain-domain').select_option('energy')
            await page.locator('#brain-effect').select_option('energy_price')
            await page.locator('#brain-value').fill('0.31')
            await page.evaluate("document.querySelector('ester-panel').hass={...document.querySelector('ester-panel')._hass}")
            self.assertEqual(await page.locator('#brain-note').input_value(), 'Tariffa temporanea confermata')
            await page.locator('#brain-note-save').click()
            await page.wait_for_function("document.querySelector('ester-panel')._brain.preferences.energy_price_eur_kwh === 0.31")
            await page.locator('summary').filter(has_text='INFORMAZIONI CHE CAMBIANO NEL TEMPO').click()
            self.assertEqual(await page.locator('#brain-note').input_value(), '')
            restored = type(self.store)(self.hass)
            await restored.async_load()
            self.assertEqual(restored.data['brain_notes'][0]['effect']['value'], .31)
            self.assertEqual(len(restored.data['knowledge_documents']), 3)
            await page.locator('summary').filter(has_text='MEMORIA CONSERVATA').click()
            await page.locator('[data-brain-edit]').click()
            await page.locator('#brain-value').fill('0.29')
            await page.locator('#brain-note-save').click()
            await page.wait_for_function("document.querySelector('ester-panel')._brain.preferences.energy_price_eur_kwh === 0.29")
            self.assertEqual(self.store.data['brain_notes'][0]['status'], 'superseded')
            await page.locator('summary').filter(has_text='MEMORIA CONSERVATA').click()
            await page.locator('[data-brain-retract]').click()
            await page.wait_for_function("!('energy_price_eur_kwh' in document.querySelector('ester-panel')._brain.preferences)")
            if os.environ.get('ESTER_BRAIN_SCREENSHOT'):
                await page.screenshot(path=os.environ['ESTER_BRAIN_SCREENSHOT'], full_page=True)
            self.assertTrue(await page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            await page.evaluate('''() => {
              const panel = document.querySelector('ester-panel');
              panel._tab = 'overview'; panel._notice = '';
              const latest = [1,3,2].map(i=>({category:'lighting',area_id:'salotto',title:'Proposta '+i,proposed_action:'Mantenere la luce accesa',reasoning:'Presenza rilevata',confidence:.7,created_at:'2026-10-02T10:0'+i+':00Z'}));
              panel._hass.states={'sensor.e_s_t_e_r_summary':{attributes:{rooms:{salotto:{name:'Salotto'}},progress:{verified_percent:40,verified:4,total:10,checks:[]}}},'sensor.e_s_t_e_r_shadow_decisions':{state:'3',attributes:{latest}}};
              panel.render();
            }''')
            self.assertEqual(await page.locator('.core-decision').count(), 2)
            self.assertEqual(await page.locator('.core-progress progress').get_attribute('value'), '40')
            self.assertFalse(await page.get_by_text('PREVISIONE CASA', exact=True).count())
            self.assertTrue(await page.evaluate('''() => {
              const root=document.querySelector('ester-panel').shadowRoot;
              return document.documentElement.scrollWidth <= innerWidth && root.querySelector('#core-latest').getBoundingClientRect().bottom <= 740;
            }'''))
            await page.get_by_role('button', name='Vedi tutte', exact=True).click()
            self.assertTrue(await page.locator('.decision-explainer').is_visible())
            await browser.close()
