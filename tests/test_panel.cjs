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
