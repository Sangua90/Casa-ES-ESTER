class EsterPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._hass = null;
    this._busy = false;
    this._tab = "overview";
    this._decisionCategory = "all";
  }

  set hass(value) { this._hass = value; this.render(); }
  set panel(value) { this._panel = value; }
  connectedCallback() { this.render(); }

  state(id) { return this._hass?.states?.[id]; }
  summary() { return this.state("sensor.e_s_t_e_r_summary")?.attributes || {}; }
  latest() { return this.state("sensor.e_s_t_e_r_shadow_decisions")?.attributes?.latest || []; }
  history() { return this.summary().decision_history || this.latest(); }
  questions() { return this.state("sensor.e_s_t_e_r_questions")?.attributes?.items || []; }
  migration() { return this.summary().migration_readiness || {}; }
  prefs() { return this.summary().preferences || {}; }

  esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  pct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? Math.round(n * 100) + "%" : "—";
  }

  async call(domain, service, data={}) {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this.render();
    try { await this._hass.callService(domain, service, data); }
    finally { this._busy = false; this.render(); }
  }

  async teach() {
    const el = this.shadowRoot?.querySelector("#teach");
    const message = el?.value?.trim();
    if (!message) return;
    await this.call("ester", "interpret_message", {message});
  }

  async answer(questionId, quickAnswer=null) {
    const el = this.shadowRoot?.querySelector("#answer-" + CSS.escape(questionId));
    const answer = (quickAnswer ?? el?.value)?.trim();
    if (!answer) return;
    await this.call("ester", "answer_question", {question_id: questionId, answer});
  }

  async startSpeech(targetId) {
    const target = this.shadowRoot?.querySelector("#" + CSS.escape(targetId));
    if (!target) return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.lang = (this._hass?.language || "it").startsWith("it") ? "it-IT" : (this._hass?.language || "it-IT");
      recognition.interimResults = true;
      recognition.continuous = false;
      target.placeholder = "Sto ascoltando...";
      recognition.onresult = (event) => {
        let text = "";
        for (let i=event.resultIndex;i<event.results.length;i++) text += event.results[i][0].transcript;
        target.value = text.trim();
      };
      recognition.onerror = () => { target.placeholder = "Microfono non disponibile: scrivi oppure usa Assist"; };
      recognition.onend = () => { if (!target.value) target.placeholder = "Scrivi o usa il microfono..."; };
      recognition.start();
      return;
    }
    if (this._hass?.auth?.external?.config?.hasAssist) {
      if (targetId.startsWith("answer-")) {
        const question_id = targetId.slice(7);
        await this._hass.callService("ester", "select_voice_question", {question_id});
      }
      this._hass.auth.external.fireMessage({
        type:"assist/show",
        payload:{pipeline_id:"preferred",start_listening:true}
      });
      return;
    }
    target.placeholder = "Il browser non supporta la dettatura. Usa Assist o scrivi la risposta.";
  }

  async replay(days) {
    await this.call("ester", "run_replay", {days:Number(days), step_minutes:30});
  }

  async scenario(mode) {
    const delta = Number(this.shadowRoot?.querySelector("#scenario-comfort")?.value || 0);
    const price = Number(this.shadowRoot?.querySelector("#scenario-price")?.value || 1);
    await this.call("ester", "simulate_scenario", {
      mode, comfort_delta_c:delta, energy_price_multiplier:price
    });
  }

  async saveWeight(name) {
    const value = Number(this.shadowRoot?.querySelector("#weight-" + name)?.value);
    if (!Number.isFinite(value)) return;
    await this.call("ester", "set_preference", {key:"objective_weight:" + name, value});
  }

  async classify() {
    const entity_id = this.shadowRoot?.querySelector("#class-entity")?.value?.trim();
    const role = this.shadowRoot?.querySelector("#class-role")?.value?.trim();
    const area_id = this.shadowRoot?.querySelector("#class-area")?.value?.trim();
    if (!entity_id || !role) return;
    const data = {entity_id, role};
    if (area_id) data.area_id = area_id;
    await this.call("ester", "classify_entity", data);
  }

  async snapshot() {
    const label = this.shadowRoot?.querySelector("#snapshot-label")?.value?.trim() || "Snapshot manuale";
    await this.call("ester", "snapshot_memory", {label, reason:"Creato dal centro di controllo"});
  }

  async rollback(snapshotId) {
    await this.call("ester", "rollback_memory", {snapshot_id:snapshotId});
  }

  async exportMemory() {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this.render();
    try {
      const result = await this._hass.callWS({
        type:"call_service", domain:"ester", service:"export_memory",
        service_data:{}, return_response:true
      });
      const payload = result?.response || result;
      this._memoryExport = JSON.stringify(payload, null, 2);
    } finally {
      this._busy = false;
      this.render();
    }
  }

  async importMemory() {
    const memory_json = this.shadowRoot?.querySelector("#memory-import")?.value?.trim();
    if (!memory_json) return;
    await this.call("ester", "import_memory", {memory_json});
  }

  async saveRoutine() {
    const area_id = this.shadowRoot?.querySelector("#routine-area")?.value?.trim();
    const label = this.shadowRoot?.querySelector("#routine-label")?.value?.trim();
    const weekdays = (this.shadowRoot?.querySelector("#routine-days")?.value || "")
      .split(",").map(x=>Number(x.trim())).filter(x=>Number.isInteger(x) && x>=0 && x<=6);
    const start_time = this.shadowRoot?.querySelector("#routine-start")?.value;
    const end_time = this.shadowRoot?.querySelector("#routine-end")?.value;
    const expected_occupancy = Number(this.shadowRoot?.querySelector("#routine-occ")?.value);
    const comfort = this.shadowRoot?.querySelector("#routine-comfort")?.value;
    if (!area_id || !label || !weekdays.length || !start_time || !end_time || !Number.isFinite(expected_occupancy)) return;
    const data = {area_id,label,weekdays,start_time,end_time,expected_occupancy};
    if (comfort !== "") data.comfort_c = Number(comfort);
    await this.call("ester","set_usage_profile",data);
  }

  async removeRoutine(profile_id) {
    await this.call("ester","remove_usage_profile",{profile_id});
  }

  async saveLoad() {
    const name = this.shadowRoot?.querySelector("#load-name")?.value?.trim();
    const entity_id = this.shadowRoot?.querySelector("#load-entity")?.value?.trim();
    const power_w = Number(this.shadowRoot?.querySelector("#load-power")?.value);
    const duration_minutes = Number(this.shadowRoot?.querySelector("#load-duration")?.value || 60);
    const priority = Number(this.shadowRoot?.querySelector("#load-priority")?.value || 50);
    const min_soc = Number(this.shadowRoot?.querySelector("#load-soc")?.value || 0);
    const phase = this.shadowRoot?.querySelector("#load-phase")?.value || "unknown";
    const min_on_minutes = Number(this.shadowRoot?.querySelector("#load-min-on")?.value || 0);
    const min_off_minutes = Number(this.shadowRoot?.querySelector("#load-min-off")?.value || 0);
    if (!name || !entity_id || !Number.isFinite(power_w)) return;
    await this.call("ester","set_flexible_load",{
      name,entity_id,power_w,duration_minutes,priority,min_soc,phase,min_on_minutes,min_off_minutes,
      interruptible:true,non_interruptible:false
    });
  }

  async removeLoad(load_id) {
    await this.call("ester","remove_flexible_load",{load_id});
  }

  decisionCards(items=null) {
    let list = (items || this.history()).slice().reverse();
    if (!items && this._decisionCategory !== "all") list = list.filter(x=>x.category===this._decisionCategory);
    list = list.slice(0, 100);
    if (!list.length) return '<div class="empty">Nessuna decisione Shadow disponibile.</div>';
    return list.map(d => {
      const objective = d.evidence?.objective_score?.score;
      return `
      <article class="decision">
        <div class="decision-head">
          <div>
            <div class="eyebrow">${this.esc(d.category || "decision")}</div>
            <h3>${this.esc(d.title)}</h3>
          </div>
          <div class="confidence">${this.pct(d.confidence)}</div>
        </div>
        <div class="meter"><span style="width:${Math.max(0, Math.min(100, Number(d.confidence || 0) * 100))}%"></span></div>
        <p>${this.esc(d.reasoning)}</p>
        <div class="proposal">${this.esc(d.proposed_action)}</div>
        <div class="meta">
          <span>RISCHIO ${this.esc((d.risk || "—").toUpperCase())}</span>
          <span>GLOBAL SCORE ${objective == null ? "—" : this.pct(objective)}</span>
          <span>SHADOW</span>
        </div>
      </article>`;
    }).join("");
  }

  questionCards() {
    const items = this.questions().slice(0, 20);
    if (!items.length) return '<div class="empty">Nessuna domanda aperta.</div>';
    return items.map(q => {
      const quick = q.quick_answers || [];
      return `
      <article class="question question-focus">
        <div class="question-radar">
          <div class="radar-ring rr1"></div><div class="radar-ring rr2"></div>
          <div class="radar-value">${this.pct(q.confidence)}</div>
        </div>
        <div class="question-main">
          <div class="eyebrow">${this.esc((q.category || "INPUT").toUpperCase())} · RISCHIO ${this.esc((q.risk || "—").toUpperCase())}</div>
          <h3>${this.esc(q.display_title || q.title)}</h3>
          <div class="question-block observed"><span>COSA HO VISTO</span><p>${this.esc(q.observed || q.reasoning || "Sto raccogliendo dati dalla casa.")}</p></div>
          <div class="question-block ask"><span>COSA MI MANCA</span><p>${this.esc(q.display_prompt || q.prompt)}</p></div>
          <div class="question-block why"><span>PERCHÉ TE LO CHIEDO</span><p>${this.esc(q.why_asking || "La risposta aumenta la sicurezza della decisione.")}</p></div>
          <div class="hint">${this.esc(q.answer_hint || "Puoi rispondere con parole normali.")}</div>
          ${quick.length ? '<div class="quick-row">'+quick.map(a=>`<button class="quick" data-quick-question="${this.esc(q.question_id)}" data-quick-answer="${this.esc(a)}">${this.esc(a)}</button>`).join("")+'</div>' : ''}
          <div class="answer-row">
            <input id="answer-${this.esc(q.question_id)}" placeholder="Scrivi o detta la risposta..." />
            <button class="mic-btn" data-mic="answer-${this.esc(q.question_id)}" title="Parla">◉ MIC</button>
            <button data-answer="${this.esc(q.question_id)}">CONFERMA</button>
          </div>
        </div>
      </article>
    `}).join("");
  }

  energyCard() {
    const d = this.latest().slice().reverse().find(x => x.category === "energy");
    if (!d) return '<div class="empty">Il planner energia non ha ancora una decisione completa.</div>';
    const p = d.evidence?.energy_plan || {};
    const managed = d.evidence?.managed_load_plan || [];
    return `
      <article class="energy-core">
        <div class="orb"><div class="orb-core"></div></div>
        <div class="energy-data">
          <div class="eyebrow">LOCAL ENERGY CORE</div>
          <h2>${this.esc((p.strategy || "learning").replaceAll("_"," ").toUpperCase())}</h2>
          <div class="metrics">
            <div><b>${this.esc(p.pv_w ?? "—")}</b><span>FV W</span></div>
            <div><b>${this.esc(p.load_w ?? "—")}</b><span>CASA W</span></div>
            <div><b>${this.esc(p.battery_soc ?? "—")}%</b><span>SOC</span></div>
            <div><b>${this.esc(p.instant_surplus_w ?? "—")}</b><span>SURPLUS W</span></div>
          </div>
          <p>${this.esc(d.reasoning)}</p>
          <div class="meta"><span>CARICHI GESTITI ${managed.length}</span><span>COMANDI REALI 0</span></div>
        </div>
      </article>
      ${managed.length ? '<h2 class="section-title">PIANO CARICHI</h2><section class="grid">' + managed.slice(0,20).map(x=>`
        <article class="decision">
          <div class="eyebrow">${this.esc(x.phase || "unknown")} · PRIORITÀ ${this.esc(x.priority)}</div>
          <h3>${this.esc(x.name)}</h3>
          <div class="proposal">${this.esc((x.shadow_action || "").replaceAll("_"," ").toUpperCase())}</div>
          <p>${this.esc(x.shadow_reason)}</p>
          <div class="meta"><span>${this.esc(x.power_w)} W</span><span>${this.esc(x.estimated_energy_kwh)} kWh</span></div>
        </article>`).join("") + '</section>' : ''}
    `;
  }

  migrationCards() {
    const items = Object.entries(this.migration());
    if (!items.length) return '<div class="empty">Nessuna automazione legacy classificata.</div>';
    return items.map(([name,x]) => `
      <article class="migration">
        <div class="decision-head">
          <div><div class="eyebrow">LEGACY DOMAIN</div><h3>${this.esc(name.toUpperCase())}</h3></div>
          <span class="status">${this.esc(x.status || "observe")}</span>
        </div>
        <div class="metrics compact">
          <div><b>${this.esc(x.legacy_automations ?? 0)}</b><span>AUTOMAZIONI</span></div>
          <div><b>${this.esc(x.shadow_decisions_checked ?? 0)}</b><span>DECISIONI</span></div>
          <div><b>${this.esc(x.open_questions ?? 0)}</b><span>DOMANDE</span></div>
          <div><b>${x.empirical_feedback_score == null ? "—" : this.pct(x.empirical_feedback_score)}</b><span>FEEDBACK</span></div>
        </div>
        <div class="meta"><span>DISATTIVAZIONE AUTOMATICA</span><span>NO</span></div>
      </article>
    `).join("");
  }

  learningCards() {
    const s = this.summary();
    const groups = [
      ["THERMAL",s.thermal_models||{}],["VENTILATION",s.ventilation_models||{}],
      ["HOT WATER",s.hot_water_models||{}],["OCCUPANCY",s.occupancy_models||{}]
    ];
    return groups.map(([label,data]) => `
      <article class="model">
        <div class="eyebrow">${label}</div>
        <h3>${Object.keys(data).length} modelli</h3>
        <pre>${this.esc(JSON.stringify(data,null,2)).slice(0,1800)}</pre>
      </article>
    `).join("");
  }

  validationView() {
    const s = this.summary();
    const k = s.kpis || {};
    const h = s.autonomy_health || {};
    const replay = s.last_replay || {};
    const scenario = s.last_scenario || {};
    const anomalies = s.anomalies || [];
    return `
      <h2 class="section-title">AUTONOMY HEALTH</h2>
      <article class="health ${h.overall_ready_for_executor ? "ok" : "warn"}">
        <div class="decision-head">
          <div>
            <div class="eyebrow">PRE-AUTONOMY GATE</div>
            <h2>${h.overall_ready_for_executor ? "READY FOR FINAL VALIDATION" : "SHADOW STILL REQUIRED"}</h2>
          </div>
          <div class="confidence">${h.feedback_quality == null ? "—" : this.pct(h.feedback_quality)}</div>
        </div>
        <p>Blocchi: ${this.esc((h.blocking_reasons || []).join(", ") || "nessuno")}</p>
        <div class="meta"><span>EXECUTOR PRESENTE</span><span>NO</span></div>
      </article>

      <h2 class="section-title">KPI SHADOW</h2>
      <section class="stats">
        <div><b>${this.esc(k.decisions ?? 0)}</b><span>DECISIONI</span></div>
        <div><b>${k.avg_confidence == null ? "—" : this.pct(k.avg_confidence)}</b><span>CONFIDENCE MEDIA</span></div>
        <div><b>${k.feedback?.quality_score == null ? "—" : this.pct(k.feedback.quality_score)}</b><span>QUALITÀ FEEDBACK</span></div>
        <div><b>${this.esc(k.open_questions ?? 0)}</b><span>DOMANDE APERTE</span></div>
      </section>

      <h2 class="section-title">REPLAY STORICO</h2>
      <article class="control">
        <p>Rigioca Recorder con il motore Shadow attuale. Non modifica dispositivi né storico.</p>
        <div class="button-row">
          <button data-replay="7">REPLAY 7 GIORNI</button>
          <button data-replay="30">REPLAY 30 GIORNI</button>
        </div>
        <div class="metrics compact">
          <div><b>${this.esc(replay.checkpoints ?? "—")}</b><span>CHECKPOINT</span></div>
          <div><b>${this.esc(replay.decisions ?? "—")}</b><span>DECISIONI</span></div>
          <div><b>${replay.avg_checkpoint_confidence == null ? "—" : this.pct(replay.avg_checkpoint_confidence)}</b><span>CONFIDENCE</span></div>
          <div><b>${this.esc(replay.needs_input ?? "—")}</b><span>INPUT NECESSARI</span></div>
        </div>
      </article>

      <h2 class="section-title">WHAT-IF</h2>
      <article class="control">
        <div class="form-grid">
          <label>Delta comfort °C<input id="scenario-comfort" type="number" step="0.5" value="0"></label>
          <label>Moltiplicatore costo energia<input id="scenario-price" type="number" step="0.1" value="1"></label>
        </div>
        <div class="button-row">
          <button data-scenario="normal">NORMALE</button>
          <button data-scenario="vacation">VACANZA</button>
          <button data-scenario="guests">OSPITI</button>
          <button data-scenario="illness">MALATTIA</button>
          <button data-scenario="work_from_home">CASA/LAVORO</button>
        </div>
        <p>Ultimo scenario: ${this.esc(scenario.mode || "—")} · ${this.esc(scenario.decision_count ?? "—")} decisioni</p>
      </article>

      <h2 class="section-title">ANOMALIE</h2>
      <section class="grid">
        ${anomalies.length ? anomalies.slice(0,30).map(a=>`
          <article class="decision">
            <div class="eyebrow">${this.esc(a.severity)} · ${this.esc(a.kind)}</div>
            <h3>${this.esc(a.entity_id)}</h3>
            <p>${this.esc(a.message)}</p>
          </article>`).join("") : '<div class="empty">Nessuna anomalia rilevata.</div>'}
      </section>
    `;
  }

  forecastCard() {
    const f = this.summary().daily_forecast || {};
    const uses = f.next_uses || [];
    return `
      <article class="control">
        <div class="eyebrow">DAILY HOME FORECAST</div>
        <h3>${this.esc((f.season || "—").toUpperCase())} · ${this.pct(f.avg_recent_confidence)}</h3>
        <p>Strategia energia: <b>${this.esc((f.energy_strategy || "—").replaceAll("_"," "))}</b> · Domande aperte: ${this.esc(f.open_questions ?? 0)} · Anomalie: ${this.esc(f.anomalies ?? 0)}</p>
        ${uses.length ? '<div class="timeline">'+uses.slice(0,8).map(u=>`<div><b>${this.esc(u.area_id)}</b><span>${this.esc(u.label || "")} · tra ${this.esc(u.minutes_until)} min · ${u.comfort_c == null ? "—" : this.esc(u.comfort_c)+" °C"}</span></div>`).join("")+'</div>' : '<div class="empty">Nessun uso stanza previsto nelle prossime ore.</div>'}
      </article>`;
  }

  configView() {
    const weights = ["safety","comfort","cost","energy","equipment","confidence"];
    const defaults = {safety:1,comfort:.75,cost:.6,energy:.65,equipment:.55,confidence:.9};
    const prefs = this.prefs();
    const versions = this.summary().memory_versions || [];
    const routines = this.summary().usage_profile_items || [];
    const loads = this.summary().flexible_loads || [];
    const gaps = this.state("sensor.e_s_t_e_r_data_suggestions")?.attributes?.items || [];
    return `
      <h2 class="section-title">PESI MULTI-OBIETTIVO</h2>
      <section class="grid">
        ${weights.map(w=>`
          <article class="control">
            <div class="eyebrow">${w.toUpperCase()}</div>
            <div class="form-grid one">
              <input id="weight-${w}" type="number" min="0" max="1" step="0.05" value="${this.esc(prefs["objective_weight:"+w] ?? defaults[w])}">
              <button data-weight="${w}">SALVA</button>
            </div>
          </article>`).join("")}
      </section>

      <h2 class="section-title">ROUTINE USO CASA</h2>
      <article class="control">
        <div class="form-grid">
          <label>Area ID<input id="routine-area" placeholder="salotto"></label>
          <label>Nome<input id="routine-label" placeholder="Salotto sera"></label>
          <label>Giorni 0-6<input id="routine-days" placeholder="0,1,2,3,4"></label>
          <label>Inizio<input id="routine-start" type="time"></label>
          <label>Fine<input id="routine-end" type="time"></label>
          <label>Probabilità uso<input id="routine-occ" type="number" min="0" max="1" step="0.05" value="0.9"></label>
          <label>Comfort °C<input id="routine-comfort" type="number" min="5" max="35" step="0.5"></label>
        </div>
        <button id="routine-save">AGGIUNGI ROUTINE</button>
      </article>
      <section class="grid">
        ${routines.length ? routines.map(r=>`
          <article class="migration"><div class="eyebrow">${this.esc(r.area_id)} · ${this.esc((r.weekdays||[]).join(","))}</div>
          <h3>${this.esc(r.label)}</h3><p>${this.esc(r.start_time)}–${this.esc(r.end_time)} · uso ${this.pct(r.expected_occupancy)} · comfort ${r.comfort_c ?? "—"} °C</p>
          <button data-remove-routine="${this.esc(r.profile_id)}">RIMUOVI</button></article>`).join("") : '<div class="empty">Nessuna routine configurata.</div>'}
      </section>

      <h2 class="section-title">CARICHI ENERGETICI GESTITI</h2>
      <article class="control">
        <div class="form-grid">
          <label>Nome<input id="load-name" placeholder="Boiler"></label>
          <label>Entity ID<input id="load-entity" placeholder="switch.boiler"></label>
          <label>Potenza W<input id="load-power" type="number" min="0"></label>
          <label>Durata min<input id="load-duration" type="number" min="1" value="60"></label>
          <label>Priorità 1-100<input id="load-priority" type="number" min="1" max="100" value="50"></label>
          <label>SOC minimo<input id="load-soc" type="number" min="0" max="100" value="0"></label>
          <label>Fase<select id="load-phase"><option>unknown</option><option>l1</option><option>l2</option><option>l3</option><option>three_phase</option></select></label>
          <label>Min ON min<input id="load-min-on" type="number" min="0" value="0"></label>
          <label>Min OFF min<input id="load-min-off" type="number" min="0" value="0"></label>
        </div>
        <button id="load-save">AGGIUNGI CARICO</button>
      </article>
      <section class="grid">
        ${loads.length ? loads.map(l=>`
          <article class="migration"><div class="eyebrow">${this.esc(l.phase)} · PRIORITÀ ${this.esc(l.priority)}</div>
          <h3>${this.esc(l.name)}</h3><p>${this.esc(l.entity_id)} · ${this.esc(l.power_w)} W · SOC min ${this.esc(l.min_soc)}%</p>
          <button data-remove-load="${this.esc(l.load_id)}">RIMUOVI</button></article>`).join("") : '<div class="empty">Nessun carico configurato.</div>'}
      </section>

      <h2 class="section-title">MAPPATURA ENTITÀ</h2>
      <article class="control">
        <div class="form-grid">
          <label>Entity ID<input id="class-entity" placeholder="sensor.xxx"></label>
          <label>Ruolo<input id="class-role" placeholder="solar_power, load_power, temperature..."></label>
          <label>Area ID<input id="class-area" placeholder="opzionale"></label>
        </div>
        <button id="class-save">SALVA CLASSIFICAZIONE</button>
      </article>

      <h2 class="section-title">DATI MANCANTI / WIZARD</h2>
      <section class="grid">
        ${gaps.length ? gaps.slice(0,30).map(g=>`
          <article class="decision"><div class="eyebrow">${this.esc(g.area_name || g.area_id || "casa")}</div>
          <h3>${this.esc(g.missing_data || g.title)}</h3><p>${this.esc(g.benefit)}</p><div class="proposal">${this.esc(g.next_step)}</div></article>`).join("") : '<div class="empty">Nessuna lacuna dati rilevata.</div>'}
      </section>

      <h2 class="section-title">VERSIONI MEMORIA</h2>
      <article class="control">
        <div class="form-grid one"><input id="snapshot-label" placeholder="Nome snapshot"><button id="snapshot-create">CREA SNAPSHOT</button></div>
      </article>
      <section class="grid">
        ${versions.length ? versions.slice().reverse().map(v=>`
          <article class="migration">
            <div class="eyebrow">${this.esc(v.created_at || "")}</div>
            <h3>${this.esc(v.label)}</h3>
            <p>${this.esc(v.reason)}</p>
            <button data-rollback="${this.esc(v.snapshot_id)}">RIPRISTINA</button>
          </article>`).join("") : '<div class="empty">Nessuno snapshot disponibile.</div>'}
      </section>

      <h2 class="section-title">BACKUP / IMPORT MEMORIA</h2>
      <article class="control">
        <div class="button-row"><button id="memory-export">ESPORTA JSON</button></div>
        <textarea readonly placeholder="Il backup JSON comparirà qui...">${this.esc(this._memoryExport || "")}</textarea>
        <textarea id="memory-import" placeholder='Incolla qui un backup JSON E.S.T.E.R.'></textarea>
        <button id="memory-import-send">IMPORTA CON SNAPSHOT PREVENTIVO</button>
      </article>
    `;
  }

  bind() {
    this.shadowRoot?.querySelectorAll("[data-tab]").forEach(el => {
      el.onclick = () => { this._tab = el.dataset.tab; this.render(); };
    });
    const teach = this.shadowRoot?.querySelector("#teach-send");
    if (teach) teach.onclick = () => this.teach();
    this.shadowRoot?.querySelectorAll("[data-answer]").forEach(el => el.onclick=()=>this.answer(el.dataset.answer));
    this.shadowRoot?.querySelectorAll("[data-quick-question]").forEach(el => el.onclick=()=>this.answer(el.dataset.quickQuestion, el.dataset.quickAnswer));
    this.shadowRoot?.querySelectorAll("[data-mic]").forEach(el => el.onclick=()=>this.startSpeech(el.dataset.mic));
    this.shadowRoot?.querySelectorAll("[data-replay]").forEach(el => el.onclick=()=>this.replay(el.dataset.replay));
    this.shadowRoot?.querySelectorAll("[data-scenario]").forEach(el => el.onclick=()=>this.scenario(el.dataset.scenario));
    this.shadowRoot?.querySelectorAll("[data-weight]").forEach(el => el.onclick=()=>this.saveWeight(el.dataset.weight));
    this.shadowRoot?.querySelectorAll("[data-rollback]").forEach(el => el.onclick=()=>this.rollback(el.dataset.rollback));
    const classify = this.shadowRoot?.querySelector("#class-save");
    if (classify) classify.onclick=()=>this.classify();
    const snapshot = this.shadowRoot?.querySelector("#snapshot-create");
    if (snapshot) snapshot.onclick=()=>this.snapshot();
    const memoryExport = this.shadowRoot?.querySelector("#memory-export");
    if (memoryExport) memoryExport.onclick=()=>this.exportMemory();
    const memoryImport = this.shadowRoot?.querySelector("#memory-import-send");
    if (memoryImport) memoryImport.onclick=()=>this.importMemory();
    const routineSave = this.shadowRoot?.querySelector("#routine-save");
    if (routineSave) routineSave.onclick=()=>this.saveRoutine();
    this.shadowRoot?.querySelectorAll("[data-remove-routine]").forEach(el=>el.onclick=()=>this.removeRoutine(el.dataset.removeRoutine));
    const loadSave = this.shadowRoot?.querySelector("#load-save");
    if (loadSave) loadSave.onclick=()=>this.saveLoad();
    this.shadowRoot?.querySelectorAll("[data-remove-load]").forEach(el=>el.onclick=()=>this.removeLoad(el.dataset.removeLoad));
    const filter = this.shadowRoot?.querySelector("#decision-filter");
    if (filter) filter.onchange=()=>{this._decisionCategory=filter.value;this.render();};
  }

  render() {
    if (!this.shadowRoot) return;
    const s = this.summary();
    const status = this.state("sensor.e_s_t_e_r_status")?.state || "loading";
    const decisionCount = this.state("sensor.e_s_t_e_r_shadow_decisions")?.state || "0";
    const questionCount = this.state("sensor.e_s_t_e_r_questions")?.state || "0";
    const observed = this.state("sensor.e_s_t_e_r_observed_entities")?.state || "0";
    const health = s.autonomy_health || {};

    const tabs = [
      ["overview","CORE"],["decisions","DECISIONI"],["questions","DOMANDE"],
      ["energy","ENERGIA"],["learning","APPRENDIMENTO"],["validation","VALIDAZIONE"],
      ["migration","MIGRAZIONE"],["config","CONFIG"]
    ];

    let body = "";
    if (this._tab === "overview") {
      body = `
        <section class="hero jarvis-stage">
          <div class="hud-grid"></div>
          <div class="jarvis">
            <div class="ring r0"></div><div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>
            <div class="tick-ring"></div>
            <div class="core-dot"></div>
            <div class="scan-line"></div>
          </div>
          <div class="hero-data">
            <div class="eyebrow">EVERYTHING SEEMS TOTALLY EASY, RIGHT?</div>
            <h1>E.S.T.E.R.</h1>
            <p class="lead">Home Intelligence Core · Pre-Autonomy Shadow</p>
            <div class="statusline"><span class="pulse"></span>${this.esc(status.toUpperCase())} · REAL ACTUATION DISABLED</div>
            <div class="statusline">SEASON ${this.esc((s.season?.season || "—").toUpperCase())} · AUTONOMY GATE ${health.overall_ready_for_executor ? "READY" : "BLOCKED"}</div>
          </div>
        </section>
        <section class="stats">
          <div><b>${this.esc(decisionCount)}</b><span>DECISIONI</span></div>
          <div><b>${this.esc(questionCount)}</b><span>DOMANDE</span></div>
          <div><b>${this.esc(observed)}</b><span>NODI OSSERVATI</span></div>
          <div><b>0</b><span>COMANDI REALI</span></div>
        </section>
        <section class="teach">
          <div class="eyebrow">TEACH E.S.T.E.R.</div>
          <div class="teach-row">
            <textarea id="teach" placeholder="Parla o scrivi: «Questo weekend siamo via», «Ester oggi è a casa», «La palestra la uso alle 19»..."></textarea>
            <button class="mic-btn big-mic" data-mic="teach">◉ PARLA</button>
            <button id="teach-send">${this._busy ? "..." : "INVIA"}</button>
          </div>
        </section>
        <h2 class="section-title">FORECAST CASA</h2>
        ${this.forecastCard()}
        <h2 class="section-title">LIVE DECISION FEED</h2>
        <section class="grid">${this.decisionCards(this.latest())}</section>
      `;
    } else if (this._tab === "decisions") {
      const cats = ["all","energy","climate","hot_water","ventilation","lighting","security","presence","irrigation","operational_safety","model"];
      body = '<h2 class="section-title">STORICO DECISIONI SHADOW</h2><article class="control"><label>Filtro dominio<select id="decision-filter">'+cats.map(x=>'<option value="'+x+'" '+(this._decisionCategory===x?'selected':'')+'>'+x+'</option>').join("")+'</select></label></article><section class="grid">'+this.decisionCards()+'</section>';
    } else if (this._tab === "questions") {
      body = '<h2 class="section-title">QUESTION INBOX</h2><section class="grid">'+this.questionCards()+'</section>';
    } else if (this._tab === "energy") {
      body = '<h2 class="section-title">ENERGY MANAGER INTEGRATO</h2>'+this.energyCard()+
        '<h2 class="section-title">ULTIME DECISIONI ENERGIA</h2><section class="grid">'+
        this.decisionCards(this.latest().filter(x=>x.category==="energy"))+'</section>';
    } else if (this._tab === "learning") {
      body = '<h2 class="section-title">MODELLI APPRESI</h2><section class="grid">'+this.learningCards()+'</section>';
    } else if (this._tab === "validation") {
      body = this.validationView();
    } else if (this._tab === "migration") {
      body = '<h2 class="section-title">MIGRAZIONE AUTOMAZIONI</h2><section class="grid">'+this.migrationCards()+'</section>';
    } else if (this._tab === "config") {
      body = this.configView();
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;min-height:100vh;background:radial-gradient(circle at 50% -10%,#0c4251 0,#071820 32%,#03080d 68%);color:#dffaff;font-family:Inter,Roboto,sans-serif}
        *{box-sizing:border-box}.shell{max-width:1700px;margin:auto;padding:18px 22px 50px}
        nav{display:flex;gap:8px;overflow:auto;padding:6px 0 18px;position:sticky;top:0;z-index:5;background:linear-gradient(#03080df2,#03080dd9 75%,transparent)}
        button{border:1px solid #19d9ff55;background:#071b24;color:#7feeff;padding:10px 14px;border-radius:7px;letter-spacing:.06em;cursor:pointer}
        button:hover{background:#0b3443;box-shadow:0 0 15px #00cfff30}nav button.active{background:#0b3443;box-shadow:0 0 18px #00cfff40;border-color:#38e7ff}
.hero{min-height:360px;display:flex;align-items:center;justify-content:center;gap:72px;border-top:1px solid #64eaff40;border-bottom:1px solid #64eaff2e;background:linear-gradient(90deg,transparent,#061b24a8 20%,#031117d9 50%,#061b24a8 80%,transparent);position:relative;overflow:hidden;box-shadow:inset 0 0 90px #00d9ff0c}.jarvis-stage:before,.jarvis-stage:after{content:"";position:absolute;top:12%;bottom:12%;width:1px;background:linear-gradient(transparent,#5aefff99,transparent);box-shadow:0 0 12px #00dcff}.jarvis-stage:before{left:6%}.jarvis-stage:after{right:6%}.hud-grid{position:absolute;inset:0;background-image:linear-gradient(#35dff70a 1px,transparent 1px),linear-gradient(90deg,#35dff70a 1px,transparent 1px);background-size:28px 28px;mask-image:radial-gradient(circle at center,#000 20%,transparent 72%)}
        h1{font-size:clamp(54px,9vw,130px);letter-spacing:.16em;margin:2px 0;color:#e8fdff;text-shadow:0 0 14px #75eeff,0 0 50px #0acfea60}
        h2.section-title{font-size:15px;letter-spacing:.18em;color:#63eaff;margin:30px 0 12px}.lead{font-size:18px;color:#8dbbc6}
        .eyebrow{font-size:11px;letter-spacing:.18em;color:#4acde8;text-transform:uppercase}.statusline{font-family:monospace;color:#6ff7d0;margin:6px 0}.pulse{display:inline-block;width:8px;height:8px;background:#60ffd5;border-radius:50%;box-shadow:0 0 12px #60ffd5;margin-right:8px}
        .jarvis{width:290px;height:290px;position:relative;border-radius:50%;display:grid;place-items:center;filter:drop-shadow(0 0 26px #00d9ff33)}.ring{position:absolute;border:1px solid #48eaff;border-radius:50%;box-shadow:0 0 18px #00d9ff40,inset 0 0 18px #00d9ff28}.r0{inset:0;border-style:dotted;opacity:.45;animation:spin 25s linear reverse infinite}.r1{inset:8%;border-width:2px;border-left-color:transparent;border-bottom-color:#48eaff33;animation:spin 14s linear infinite}.r2{inset:23%;border-style:dashed;animation:spin 9s linear reverse infinite}.r3{inset:37%;border-width:2px;animation:pulseRing 2s ease-in-out infinite}.tick-ring{position:absolute;inset:14%;border-radius:50%;background:repeating-conic-gradient(#5cecff 0 1deg,transparent 1deg 7deg);mask:radial-gradient(circle,transparent 0 43%,#000 44% 48%,transparent 49%);opacity:.62;animation:spin 40s linear infinite}.core-dot{width:54px;height:54px;border-radius:50%;background:radial-gradient(circle,#fff 0 12%,#9ef8ff 18%,#25dff5 40%,#063e4d 65%,transparent 68%);box-shadow:0 0 20px #fff,0 0 55px #00eaff,0 0 120px #00d9ff}.scan-line{position:absolute;width:46%;height:1px;background:linear-gradient(90deg,transparent,#7af5ff,transparent);transform-origin:100% 50%;left:4%;top:50%;animation:spin 4s linear infinite}.hero-data{position:relative;z-index:2}
        @keyframes spin{to{transform:rotate(360deg)}}@keyframes pulseRing{50%{transform:scale(1.08);opacity:.55}}
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.stats>div,.metrics>div{padding:18px;border:1px solid #16d8ff35;background:#06151d9e;border-radius:10px}.stats b,.metrics b{display:block;font-size:28px;color:#d9fbff}.stats span,.metrics span{font-size:10px;letter-spacing:.14em;color:#55bdd0}
        .teach,.control,.health{border:1px solid #1eddfc40;background:#041219c8;border-radius:12px;padding:15px}.teach-row,.answer-row,.button-row{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}
        textarea,input,select{width:100%;border:1px solid #25dffc44;background:#02090e;color:#dcfbff;border-radius:8px;padding:11px}.teach textarea,.control textarea{min-height:85px;resize:vertical}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.decision,.question,.migration,.model,.energy-core{position:relative;border:1px solid #63eaff42;background:linear-gradient(155deg,#07151bd9,#03080dd9);clip-path:polygon(0 12px,12px 0,calc(100% - 28px) 0,100% 28px,100% 100%,28px 100%,0 calc(100% - 28px));padding:18px;box-shadow:inset 0 0 38px #00d9ff0b}.decision:before,.question:before,.migration:before,.model:before{content:"";position:absolute;left:14px;top:0;width:70px;height:1px;background:#74efff;box-shadow:0 0 8px #26e7ff}
        .decision-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.decision h3,.question h3,.migration h3,.model h3{margin:5px 0 10px;color:#e9fdff}.confidence{font-family:monospace;font-size:25px;color:#68efff}.meter{height:3px;background:#0e2a34;margin:8px 0 14px}.meter span{display:block;height:100%;background:#53edff;box-shadow:0 0 10px #2ae8ff}.decision p,.question p,.energy-core p,.control p,.health p{color:#9dc5cf;line-height:1.5}.proposal{padding:10px 12px;background:#06222c;border-left:2px solid #50e9ff;color:#c8f8ff;margin-top:12px}.meta{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;color:#4fa3b3;font-family:monospace;font-size:10px;margin-top:13px}
        .answer-row input{flex:1;min-width:180px}.mic-btn{border-radius:999px;border-color:#69f2ff;box-shadow:0 0 14px #00d9ff44;background:radial-gradient(circle,#0b3444,#041018)}.big-mic{min-width:112px}.quick-row{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}.quick{padding:7px 10px;font-size:11px}.question-focus{display:grid;grid-template-columns:120px 1fr;gap:18px;align-items:start}.question-radar{position:relative;width:108px;height:108px;border-radius:50%;border:1px solid #69efff99;display:grid;place-items:center;background:radial-gradient(circle,#0bdcff24 0,#031018 58%,transparent 59%);box-shadow:0 0 25px #00dcff22,inset 0 0 25px #00dcff18}.radar-ring{position:absolute;border:1px solid #43e8ff66;border-radius:50%}.rr1{inset:12%;border-style:dashed;animation:spin 9s linear infinite}.rr2{inset:28%;animation:spin 5s linear reverse infinite}.radar-value{font:700 20px monospace;color:#c9fbff;text-shadow:0 0 12px #56eaff}.question-block{margin:10px 0;padding:9px 12px;border-left:2px solid #28dff2;background:linear-gradient(90deg,#09202a88,transparent)}.question-block span{display:block;font-size:9px;letter-spacing:.18em;color:#49c6dc}.question-block p{margin:5px 0}.question-block.ask{border-left-color:#fff}.question-block.why{border-left-color:#6ff7d0}.hint{font-size:12px;color:#7db5c0;font-style:italic;margin:8px 0}.energy-core{display:flex;align-items:center;gap:35px}.orb{width:150px;height:150px;border-radius:50%;border:1px solid #4dedff;display:grid;place-items:center;box-shadow:0 0 30px #00d9ff45,inset 0 0 35px #00d9ff25;flex:0 0 auto}.orb-core{width:48px;height:48px;border-radius:50%;background:#c9fbff;box-shadow:0 0 50px #16e5ff}.energy-data{flex:1}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.metrics.compact b{font-size:19px}.status{font-family:monospace;color:#6ff6cb}.model pre{white-space:pre-wrap;max-height:310px;overflow:auto;color:#7eb9c5;font-size:11px}.empty{padding:30px;color:#6c9da8;border:1px dashed #1bd5ef35;border-radius:10px}
        .health.ok{border-color:#5dffc16b}.health.warn{border-color:#ffc95d59}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:10px 0}.form-grid.one{grid-template-columns:1fr auto}.form-grid label{font-size:11px;color:#68c9da;letter-spacing:.08em}.form-grid label input,.form-grid label select{margin-top:5px}.timeline{display:grid;gap:7px;margin-top:12px}.timeline div{display:flex;justify-content:space-between;gap:15px;padding:9px;border-bottom:1px solid #1cdff322}.timeline span{color:#7bbcca;font-size:12px}
        @media(max-width:800px){.shell{padding:10px}.question-focus{grid-template-columns:1fr}.question-radar{width:82px;height:82px}.hero{min-height:310px;gap:18px;padding:18px;flex-direction:column}.jarvis{width:175px;height:175px}h1{font-size:42px}.stats{grid-template-columns:repeat(2,1fr)}.energy-core{display:block}.orb{margin:0 auto 20px}.metrics{grid-template-columns:repeat(2,1fr)}.teach-row,.answer-row,.form-grid.one{grid-template-columns:1fr;flex-direction:column}}
      </style>
      <div class="shell">
        <nav>${tabs.map(([id,label])=>`<button data-tab="${id}" class="${this._tab===id?"active":""}">${label}</button>`).join("")}</nav>
        ${body}
      </div>
    `;
    this.bind();
  }
}
customElements.define("ester-panel", EsterPanel);
