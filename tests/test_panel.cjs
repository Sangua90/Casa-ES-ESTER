const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
let Panel, recognition;
class Speech {
  constructor() { recognition = this; }
  start() {}
  stop() { this.onend(); }
  abort() { this.onend(); }
}
const context = {HTMLElement: class {}, customElements: {define: (_, cls) => { Panel = cls; }},
  window: {SpeechRecognition: Speech}, CSS: {escape: x => x}};
vm.runInNewContext(readFileSync('custom_components/ester/frontend/ester-panel.js', 'utf8'), context);
(async () => {
  const display = Object.create(Panel.prototype);
  const older = {category:'climate',area_id:'salotto',title:'Comfort',entity_ids:['climate.room'],created_at:'2026-10-01T08:00:00Z'};
  const newer = {...older,created_at:'2026-10-01T09:00:00Z'};
  const otherRoom = {...older,area_id:'bagno'};
  const original = [newer, otherRoom, older];
  const latest = display.currentDecisions(original);
  assert.equal(latest.length, 2);
  assert.equal(latest.find(x=>x.area_id==='salotto'), newer);
  assert.equal(original.length, 3);
  display._hass = {states:{'sensor.e_s_t_e_r_summary':{attributes:{rooms:{bagno:{name:'Bagno primo piano'}}}}}};
  assert.equal(display.roomName('bagno'), 'Bagno primo piano');
  assert.equal(display.roomName(null), 'Casa / stanza non indicata');
  const exchange = Object.create(Panel.prototype);
  let calls = [];
  exchange.render = () => {};
  exchange.shadowRoot = {querySelector: () => ({files:[{size:20,text:async()=>'{"questions":[]}' }]})};
  exchange._hass = {callWS: async request => {calls.push(request);return {response:{items:[{question:'Comfort?',answer:'21 gradi',interpretation:{summary:'Comfort: 21 °C'}}]}};}};
  await exchange.questionFileAction('preview');
  assert.equal(calls[0].service_data.confirm, false);
  assert.ok(exchange.questionFileControls().includes('CONFERMA IMPORTAZIONE'));
  await exchange.questionFileAction('confirm');
  assert.equal(calls[1].service_data.confirm, true);
  assert.equal(calls[1].service_data.file_json, calls[0].service_data.file_json);
  assert.equal(exchange._questionImport, null);
  let downloaded, clicked = 0;
  context.Blob = Blob;
  context.URL = {createObjectURL: blob => {downloaded=blob;return 'blob:test';},revokeObjectURL() {}};
  context.document = {createElement: () => ({click() {clicked++;}})};
  context.setTimeout = callback => callback();
  exchange._hass = {callWS: async request => {
    assert.equal(request.service, 'export_learning_report');
    return {response:{format:'ester-learning-report-v1',real_actuation_enabled:false}};
  }};
  await exchange.exportLearningReport();
  assert.equal(clicked, 1);
  assert.equal(JSON.parse(await downloaded.text()).format, 'ester-learning-report-v1');
  display._hass.states['sensor.e_s_t_e_r_shadow_decisions'] = {attributes:{latest:[]}};
  display._hass.states['sensor.e_s_t_e_r_summary'].attributes.decision_history = [older];
  assert.equal(display.realDecisions().length, 0);
  for (const id of ['teach', 'answer-test']) {
    const field = {value: 'Testo precedente'};
    const notice = {setAttribute() {}, textContent: ''};
    const panel = Object.create(Panel.prototype);
    panel._hass = {language: 'it'};
    panel.shadowRoot = {querySelector: selector => selector === '.notice' ? notice : field};
    panel.render = () => { throw Error('Speech must not replace the input'); };
    panel.answer = () => { throw Error('Speech must not submit automatically'); };
    await panel.startSpeech(id);
    const first = [{transcript: 'prima frase'}]; first.isFinal = true;
    const second = [{transcript: 'seconda frase'}]; second.isFinal = true;
    recognition.onresult({resultIndex: 0, results: [first]});
    recognition.onresult({resultIndex: 1, results: [first, second]});
    assert.equal(field.value, 'Testo precedente prima frase seconda frase');
    await panel.startSpeech(id);
    assert.equal(panel._recognition, null);
    assert.match(notice.textContent, /Controlla il testo/);
    await panel.startSpeech(id);
    recognition.onerror({error: 'not-allowed'});
    recognition.onend();
    assert.match(notice.textContent, /negato/);
    assert.equal(field.value, 'Testo precedente prima frase seconda frase');
  }
  console.log('Voice transcription regression checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
