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
  const live = Object.create(Panel.prototype);
  let replacements = 0, content = '';
  const container = {querySelectorAll:()=>[], get innerHTML(){return content;}, set innerHTML(value){content=value;replacements++;}};
  live._tab = 'decisions';
  live.shadowRoot = {querySelector:selector=>selector==='#current-decisions'?container:null};
  live.render = ()=>{throw Error('Decision refresh must preserve the menu');};
  live._hass = {states:{'sensor.e_s_t_e_r_shadow_decisions':{attributes:{latest:[{title:'Proposta aggiornata'}]}}}};
  live.groupedDecisionCards = ()=>live.latest()[0].title;
  live.refreshDataOnly(); live.refreshDataOnly();
  assert.equal(content, 'Proposta aggiornata'); assert.equal(replacements, 1);
  live._hass.states['sensor.e_s_t_e_r_shadow_decisions'].attributes.latest=[{title:'Memoria applicata'}];
  live.refreshDataOnly();
  assert.equal(content, 'Memoria applicata'); assert.equal(replacements, 2);
  const exchange = Object.create(Panel.prototype);
  let calls = [];
  exchange.render = () => {};
  exchange.shadowRoot = {querySelector: () => ({files:[{size:20,text:async()=>'{"questions":[]}' }]})};
  exchange._hass = {callWS: async request => {calls.push(request);return {response:{items:[{question:'Comfort?',answer:'21 gradi',interpretation:{summary:'Comfort: 21 °C'}}]}};}};
  await exchange.questionFileAction('preview');
  assert.equal(calls[0].service_data.confirm, false);
  assert.ok(exchange.questionFileControls().includes('SALVA RISPOSTE NELLA MEMORIA'));
  assert.ok(!exchange.questionFileControls().includes('Comfort: 21'));
  await exchange.questionFileAction('confirm');
  assert.equal(calls[1].service_data.confirm, true);
  assert.equal(calls[1].service_data.file_json, calls[0].service_data.file_json);
  assert.equal(exchange._questionImport, null);
  let downloaded, clicked = 0;
  context.Blob = Blob;
  context.URL = {createObjectURL: blob => {downloaded=blob;return 'blob:test';},revokeObjectURL() {}};
  context.document = {createElement: () => ({click() {clicked++;}})};
  context.window.document = context.document;
  context.setTimeout = callback => callback();
  exchange._hass = {callWS: async request => {
    assert.equal(request.service, 'export_learning_report');
    return {response:{format:'ester-learning-report-v1',real_actuation_enabled:false}};
  }};
  await exchange.exportLearningReport();
  assert.equal(clicked, 1);
  assert.equal(JSON.parse(await downloaded.text()).format, 'ester-learning-report-v1');
  exchange.downloadNotesTemplate();
  assert.equal(JSON.parse(await downloaded.text()).format, 'ester-knowledge-v1');
  display._teachDraft = {source:'knowledge_files',items:[{statement:'PRIVATE FILE CONTENT'}]};
  const notesView = display.teachView();
  assert.ok(notesView.includes('SALVA NELLA MEMORIA'));
  assert.ok(!notesView.includes('PRIVATE FILE CONTENT'));
  assert.ok(!display.configView().includes('id="class-save"'));
  assert.ok(display.configView(true).includes('id="class-save"'));
  display._tab = 'overview';
  display._hass.states['sensor.e_s_t_e_r_summary'].attributes.progress = {verified_percent:40,verified:4,total:10,checks:[]};
  assert.ok(display.progressView().includes('value="40"'));
  delete display._hass.states['sensor.e_s_t_e_r_summary'].attributes.progress;
  assert.ok(display.progressView().includes('In valutazione'));
  assert.ok(display.progressView().includes('<progress'));
  display._hass.states['sensor.e_s_t_e_r_shadow_decisions'] = {attributes:{latest:[{...older,title:'Old decision'}, {...newer,title:'Latest decision'}, {...otherRoom,title:'Middle decision',created_at:'2026-10-01T08:30:00Z'}]}};
  const coreCards = display.coreDecisionView();
  assert.equal((coreCards.match(/<article /g) || []).length, 2);
  assert.ok(coreCards.indexOf('Latest decision') < coreCards.indexOf('Middle decision'));
  assert.ok(!coreCards.includes('Old decision'));
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
