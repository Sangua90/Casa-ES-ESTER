class EsterPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._hass = null;
    this._busy = false;
    this._tab = "overview";
    this._decisionCategory = "all";
    this._advanced = false;
    this._notice = "";
    this._teachDraft = null;
    this._neuralFrame = 0;
    this._neuralResize = null;
    this._neuralStartedAt = 0;
    this._neuralNodes = [];
    this._neuralEdges = [];
    this._neuralImpulses = [];
  }

  set hass(value) { this._hass = value; this.render(); }
  set panel(value) { this._panel = value; }
  connectedCallback() { this.render(); }
  disconnectedCallback() { this.stopNeuralCore(); }

  state(id) { return this._hass?.states?.[id]; }
  summary() { return this.state("sensor.e_s_t_e_r_summary")?.attributes || {}; }
  latest() { return this.state("sensor.e_s_t_e_r_shadow_decisions")?.attributes?.latest || []; }
  history() { return this.summary().decision_history || this.latest(); }
  isTrueDecision(d) {
    if (!d || d.category === "model") return false;
    const title = String(d.title || "").toLowerCase();
    const action = String(d.proposed_action || "").toLowerCase();
    const technical = ["da completare","associare almeno","configurazione","dati mancanti","contatori energetici","raccolta dati"];
    return !technical.some(x => title.includes(x) || action.includes(x));
  }
  realDecisions() { return this.history().filter(d => this.isTrueDecision(d)); }
  friendlyGap(g) {
    const raw = [g?.missing_data, g?.title, g?.benefit, g?.next_step].filter(Boolean).join(" ").toLowerCase();
    const area = g?.area_name || g?.area_id || "casa";
    if (raw.includes("solar") || raw.includes("fv") || raw.includes("fotovolta")) return {
      title:"Non so ancora quale sensore misura il fotovoltaico",
      why:"Mi serve per capire quanta energia stai producendo e se c'è surplus realmente disponibile.",
      action:"Indica l'entità che rappresenta la potenza FV istantanea.",
      area
    };
    if (raw.includes("load") || raw.includes("consumo") || raw.includes("casa")) return {
      title:"Non so ancora quale sensore misura il consumo totale della casa",
      why:"Mi serve per distinguere ciò che consuma la casa da ciò che viene caricato in batteria o preso dalla rete.",
      action:"Indica l'entità che rappresenta il consumo totale istantaneo.",
      area
    };
    if (raw.includes("grid") || raw.includes("rete") || raw.includes("import")) return {
      title:"Non so ancora quale sensore rappresenta la rete elettrica",
      why:"Mi serve per sapere quando stai prelevando energia e quanto margine hai prima del limite del contatore.",
      action:"Indica l'entità della potenza rete/import.",
      area
    };
    if (raw.includes("battery") || raw.includes("batter") || raw.includes("soc")) return {
      title:"Mi manca un riferimento affidabile per la batteria",
      why:"Mi serve per rispettare riserva, target di carica e disponibilità energetica reale.",
      action:"Indica il sensore SOC e, se disponibile, la potenza batteria.",
      area
    };
    if (raw.includes("temperature") || raw.includes("temperatura")) return {
      title:"Mi manca una temperatura utile per questa zona",
      why:"Senza una misura affidabile non posso imparare quanto velocemente la stanza si scalda o si raffredda.",
      action:"Indica il sensore temperatura corretto per l'area.",
      area
    };
    if (raw.includes("presence") || raw.includes("presenza") || raw.includes("occup")) return {
      title:"Non ho abbastanza informazioni sulla presenza",
      why:"Mi serve per evitare decisioni sbagliate su luci, clima e antifurto quando qualcuno è in casa ma non si muove.",
      action:"Indica i sensori di presenza più affidabili per questa area.",
      area
    };
    return {
      title:g?.missing_data || g?.title || "Mi manca un'informazione",
      why:g?.benefit || "Questo dato mi serve per rendere le decisioni più affidabili.",
      action:g?.next_step || "Completa la configurazione richiesta.",
      area
    };
  }
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
    return this.teachText(message);
  }

  async teachText(message) {
    if (!message || !this._hass || this._busy) return;
    this._busy = true;
    this._notice = "Sto capendo quello che mi hai raccontato…";
    this.render();
    try {
      const result = await this._hass.callWS({
        type:"call_service", domain:"ester", service:"interpret_message",
        service_data:{message, preview:true}, return_response:true
      });
      this._teachDraft = result?.response || result || null;
      this._notice = this._teachDraft?.summary || "Controlla quello che ho capito prima di salvarlo.";
    } catch (err) {
      this._notice = "Non sono riuscita a interpretare il messaggio: " + (err?.message || "errore");
    } finally {
      this._busy = false;
      this.render();
    }
  }

  async confirmTeach() {
    const token = this._teachDraft?.proposal_id;
    if (!token || !this._hass || this._busy) return;
    this._busy = true; this._notice = "Sto salvando le conoscenze confermate…"; this.render();
    try {
      const result = await this._hass.callWS({
        type:"call_service", domain:"ester", service:"confirm_teaching",
        service_data:{proposal_id:token}, return_response:true
      });
      const response = result?.response || result || {};
      this._teachDraft = null;
      this._notice = response?.summary || "Conoscenze salvate.";
      await this._hass.callService("ester","evaluate",{});
    } catch (err) {
      this._notice = "Non ho salvato nulla: " + (err?.message || "errore");
    } finally { this._busy=false; this.render(); }
  }

  async discardTeach() {
    const token = this._teachDraft?.proposal_id;
    if (token && this._hass) {
      try { await this._hass.callService("ester","discard_teaching",{proposal_id:token}); } catch (_) {}
    }
    this._teachDraft=null; this._notice="Proposta scartata. Non ho modificato la memoria."; this.render();
  }

  async answer(questionId, quickAnswer=null) {
    const el = this.shadowRoot?.querySelector("#answer-" + CSS.escape(questionId));
    const answer = (quickAnswer ?? el?.value)?.trim();
    if (!answer || !this._hass || this._busy) return;
    this._busy = true;
    this._notice = "Sto registrando la risposta…";
    this.render();
    try {
      const result = await this._hass.callWS({
        type:"call_service",
        domain:"ester",
        service:"answer_question",
        service_data:{question_id:questionId, answer},
        return_response:true
      });
      const response = result?.response || result || {};
      this._notice = response?.interpretation?.summary
        ? "Capito: " + response.interpretation.summary
        : "Risposta registrata.";
      await this._hass.callService("ester","evaluate",{});
    } catch (err) {
      this._notice = "Risposta non registrata: " + (err?.message || "errore");
    } finally {
      this._busy = false;
      this.render();
    }
  }

  async startSpeech(targetId) {
    const target = this.shadowRoot?.querySelector("#" + CSS.escape(targetId));
    if (!target || !this._hass) return;

    const questionId = targetId.startsWith("answer-") ? targetId.slice(7) : null;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.lang = (this._hass.language || "it").startsWith("it") ? "it-IT" : (this._hass.language || "it-IT");
      recognition.interimResults = true;
      recognition.continuous = targetId === "teach";
      this._notice = "Ti ascolto…";
      this.render();

      recognition.onresult = async (event) => {
        let text = "";
        let final = false;
        for (let i=event.resultIndex;i<event.results.length;i++) {
          text += event.results[i][0].transcript;
          final = final || event.results[i].isFinal;
        }
        target.value = text.trim();
        if (final && text.trim()) {
          if (questionId) await this.answer(questionId, text.trim());
          else if (targetId === "teach") {
            const combined = text.trim();
            target.dataset.finalText = combined;
            target.value = combined;
            this._notice = "Ti ascolto… puoi continuare a parlare. Premi CAPIRE quando hai finito.";
          } else {
            this._notice = "Ho sentito: «" + text.trim() + "»";
            await this.call("ester","interpret_message",{message:text.trim()});
          }
        }
      };
      recognition.onerror = () => {
        this._notice = "Il browser non riesce ad accedere al microfono. Prova dall'app Home Assistant con Assist.";
        this.render();
      };
      recognition.start();
      return;
    }

    if (this._hass.auth?.external?.config?.hasAssist) {
      if (questionId) {
        await this._hass.callService("ester","select_voice_question",{question_id:questionId});
      }
      this._hass.auth.external.fireMessage({
        type:"assist/show",
        payload:{pipeline_id:"preferred",start_listening:true}
      });
      this._notice = questionId
        ? "Parla: la prossima frase verrà usata come risposta a questa domanda."
        : "Parla con E.S.T.E.R. tramite Assist.";
      this.render();
      return;
    }

    this._notice = "Microfono non disponibile in questo browser. Nell'app Home Assistant puoi usare Assist.";
    this.render();
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

  confidenceLabel(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "ANCORA DA VALUTARE";
    if (n >= .9) return "MOLTO SICURA";
    if (n >= .8) return "SICURA";
    if (n >= .65) return "ABBASTANZA SICURA";
    if (n >= .5) return "INCERTA";
    return "POCO SICURA";
  }

  confidenceMeaning(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "Non ho ancora abbastanza dati.";
    if (n >= .9) return "Ho molti dati coerenti per questa scelta.";
    if (n >= .8) return "I dati disponibili supportano bene questa scelta.";
    if (n >= .65) return "La scelta è plausibile, ma voglio ancora verificarla.";
    if (n >= .5) return "Ci sono ancora elementi che possono cambiare la decisione.";
    return "Non userei ancora questa decisione in automatico.";
  }

  migrationMeaning(status) {
    const s = String(status || "observe");
    if (s === "candidate_for_manual_migration") return "QUASI PRONTA DA SOSTITUIRE";
    if (s === "validate") return "DA CONTROLLARE ANCORA";
    if (s === "needs_validation") return "NON ANCORA AFFIDABILE";
    if (s === "needs_data") return "MANCANO DATI";
    return "CONTINUA A OSSERVARE";
  }

  categoryLabel(category) {
    const labels = {
      energy:"ENERGIA", climate:"CLIMA", hot_water:"ACQUA CALDA", ventilation:"VENTILAZIONE",
      lighting:"LUCI", security:"SICUREZZA", operational_safety:"SICUREZZA OPERATIVA",
      presence:"PRESENZA", irrigation:"IRRIGAZIONE", model:"MODELLO", input:"ALTRO"
    };
    return labels[category] || String(category || "ALTRO").replaceAll("_"," ").toUpperCase();
  }

  groupedDecisionCards(items=null) {
    let list = (items || this.realDecisions()).slice();
    if (!items && this._decisionCategory !== "all") list = list.filter(x=>x.category===this._decisionCategory);
    const groups = {};
    for (const d of list) {
      const key = d.category || "other";
      (groups[key] ||= []).push(d);
    }
    const order = ["energy","climate","hot_water","ventilation","lighting","security","operational_safety","presence","irrigation","other"];
    return order.filter(k=>groups[k]?.length).map(k=>`
      <section class="domain-group">
        <div class="domain-head">
          <div>
            <span>DOMINIO</span>
            <h3>${this.esc(this.categoryLabel(k))}</h3>
          </div>
          <b>${groups[k].length}</b>
        </div>
        <div class="grid">${this.decisionCards(groups[k])}</div>
      </section>`).join("") || '<div class="empty">Nessuna decisione Shadow disponibile.</div>';
  }

  decisionCards(items=null) {
    let list = (items || this.realDecisions()).slice().reverse();
    if (!items && this._decisionCategory !== "all") list = list.filter(x=>x.category===this._decisionCategory);
    list = list.slice(0, 100);
    if (!list.length) return '<div class="empty">Non ci sono ancora decisioni vere da mostrare.</div>';
    return list.map(d => {
      const objective = d.evidence?.objective_score?.score;
      const readiness = d.evidence?.objective_score?.execution_readiness;
      return `
      <article class="decision true-decision">
        <div class="decision-head">
          <div>
            <div class="eyebrow">${this.esc(this.categoryLabel(d.category))}</div>
            <h3>${this.esc(d.title)}</h3>
          </div>
          <div class="simple-confidence">
            <b>${this.esc(this.confidenceLabel(d.confidence))}</b>
            <span>${this.pct(d.confidence)}</span>
          </div>
        </div>
        <div class="decision-section primary"><span>E.S.T.E.R. AVREBBE FATTO</span><strong>${this.esc(d.proposed_action)}</strong></div>
        <div class="decision-section"><span>PERCHÉ</span><p>${this.esc(d.reasoning)}</p></div>
        <div class="plain-explain">${this.esc(this.confidenceMeaning(d.confidence))}</div>
        ${this._advanced ? `
          <details class="tech-details" open>
            <summary>DETTAGLI TECNICI</summary>
            <div class="meta">
              <span>RISCHIO ${this.esc((d.risk || "—").toUpperCase())}</span>
              <span>PRIORITÀ ${objective == null ? "—" : this.pct(objective)}</span>
              <span>READINESS ${readiness == null ? "—" : this.pct(readiness)}</span>
            </div>
          </details>` : ''}
      </article>`;
    }).join("");
  }

  groupedQuestionCards() {
    const items = this.questions().slice(0, 50);
    if (!items.length) return '<div class="empty">Nessuna domanda aperta. E.S.T.E.R. non ha bisogno di chiarimenti in questo momento.</div>';
    const groups = {};
    for (const q of items) {
      const key = q.category || "other";
      (groups[key] ||= []).push(q);
    }
    const order = ["energy","climate","hot_water","ventilation","lighting","security","operational_safety","presence","irrigation","other"];
    return order.filter(k=>groups[k]?.length).map(k=>`
      <section class="domain-group question-domain">
        <div class="domain-head">
          <div>
            <span>DOMANDE</span>
            <h3>${this.esc(this.categoryLabel(k))}</h3>
          </div>
          <b>${groups[k].length}</b>
        </div>
        <div class="question-stack">${this.questionCards(groups[k])}</div>
      </section>`).join("");
  }

  questionCards(itemsArg=null) {
    const items = (itemsArg || this.questions()).slice(0, 50);
    if (!items.length) return '<div class="empty">Nessuna domanda aperta.</div>';
    return items.map((q,index) => {
      const title = q.display_title || q.title || "Mi serve un'informazione";
      const prompt = q.display_prompt || q.prompt || "";
      const observed = q.observed || q.reasoning || "";
      const why = q.why_asking || "La risposta mi serve per ridurre le ipotesi.";
      const hint = q.answer_hint || "Puoi rispondere con parole normali.";
      const quick = q.quick_answers || [];
      return `
      <article class="question-panel">
        <div class="question-index">Q${String(index+1).padStart(2,"0")}</div>
        <div class="question-main">
          <div class="eyebrow">${this.esc((q.category || "input").toUpperCase())} · CONFIDENCE ${this.pct(q.confidence)} · RISCHIO ${this.esc((q.risk || "—").toUpperCase())}</div>
          <h2>${this.esc(title)}</h2>
          <div class="question-prompt">${this.esc(prompt)}</div>
          <div class="question-context">
            <div><span>COSA HO OSSERVATO</span><p>${this.esc(observed)}</p></div>
            <div><span>PERCHÉ TE LO CHIEDO</span><p>${this.esc(why)}</p></div>
          </div>
          <div class="hint">${this.esc(hint)}</div>
          ${quick.length ? '<div class="quick-row">'+quick.map(x=>`<button class="quick" data-quick-q="${this.esc(q.question_id)}" data-quick-answer="${this.esc(x)}">${this.esc(x)}</button>`).join("")+'</div>' : ''}
          <div class="answer-console">
            <input id="answer-${this.esc(q.question_id)}" placeholder="Rispondi qui oppure usa il microfono…" />
            <button class="mic" data-voice-q="${this.esc(q.question_id)}" title="Rispondi a voce">◉ PARLA</button>
            <button class="send" data-answer="${this.esc(q.question_id)}">INVIA</button>
          </div>
        </div>
      </article>`;
    }).join("");
  }

  viewHeader(code, title, subtitle, metric="SHADOW", metricLabel="MODE") {
    return `
      <section class="view-hud-head">
        <div class="mini-reactor">
          <div class="mini-ring a"></div><div class="mini-ring b"></div><div class="mini-ring c"></div>
          <div class="mini-core"></div>
        </div>
        <div class="view-copy">
          <div class="hud-label">${this.esc(code)}</div>
          <h1 class="view-title">${this.esc(title)}</h1>
          <p>${this.esc(subtitle)}</p>
        </div>
        <div class="view-metric">
          <span>${this.esc(metricLabel)}</span>
          <b>${this.esc(metric)}</b>
          <i></i>
        </div>
      </section>`;
  }

  hudGauge(label, value, detail="") {
    const n = Number(value);
    const pct = Number.isFinite(n) ? Math.max(0,Math.min(100,Math.round(n*100))) : 0;
    return `<div class="hud-gauge" style="--pct:${pct}">
      <div class="gauge-face"><b>${Number.isFinite(n)?pct+"%":"—"}</b><span>${this.esc(label)}</span></div>
      ${detail ? '<small>'+this.esc(detail)+'</small>' : ''}
    </div>`;
  }

  energyCard() {
    const d = this.latest().slice().reverse().find(x => x.category === "energy");
    if (!d) return '<div class="empty">E.S.T.E.R. sta ancora raccogliendo i dati necessari per il piano energia.</div>';
    const p = d.evidence?.energy_plan || {};
    const managed = d.evidence?.managed_load_plan || [];
    const surplus = Number(p.instant_surplus_w);
    const summary = Number.isFinite(surplus)
      ? (surplus > 300 ? "In questo momento hai energia disponibile oltre al consumo della casa." :
         surplus < 50 ? "In questo momento non c'è un surplus FV significativo." :
         "Il bilancio energetico è quasi in equilibrio.")
      : "Sto ancora completando il bilancio energetico.";
    return `
      <article class="energy-core hud-panel">
        <div class="energy-reactor"><div class="energy-ring er1"></div><div class="energy-ring er2"></div><div class="energy-core-dot"></div><span>${this.esc(p.battery_soc ?? "—")}%</span></div>
        <div class="energy-data">
          <div class="eyebrow">SITUAZIONE ENERGIA</div>
          <h2>${this.esc(summary)}</h2>
          <div class="metrics human-metrics">
            <div><b>${this.esc(p.pv_w ?? "—")} W</b><span>STA PRODUCENDO IL FV</span></div>
            <div><b>${this.esc(p.load_w ?? "—")} W</b><span>STA USANDO LA CASA</span></div>
            <div><b>${this.esc(p.battery_soc ?? "—")}%</b><span>BATTERIA DISPONIBILE</span></div>
            <div><b>${this.esc(p.instant_surplus_w ?? "—")} W</b><span>ENERGIA IN PIÙ</span></div>
          </div>
          <div class="decision-section primary"><span>E.S.T.E.R. AVREBBE FATTO</span><strong>${this.esc(d.proposed_action)}</strong></div>
          <div class="decision-section"><span>PERCHÉ</span><p>${this.esc(d.reasoning)}</p></div>
          ${this._advanced ? `<details class="tech-details" open><summary>DETTAGLI TECNICI</summary><pre>${this.esc(JSON.stringify({energy_plan:p,managed_loads:managed},null,2)).slice(0,4000)}</pre></details>` : ''}
        </div>
      </article>
      ${managed.length ? '<h2 class="section-title">CARICHI CHE E.S.T.E.R. STA VALUTANDO</h2><section class="grid">' + managed.slice(0,20).map(x=>`
        <article class="decision">
          <div class="eyebrow">${this.esc(x.name)}</div>
          <div class="decision-section primary"><span>COSA FAREBBE</span><strong>${this.esc((x.shadow_action || "").replaceAll("_"," "))}</strong></div>
          <p>${this.esc(x.shadow_reason)}</p>
          ${this._advanced ? '<div class="meta"><span>'+this.esc(x.power_w)+' W</span><span>'+this.esc(x.estimated_energy_kwh)+' kWh</span><span>'+this.esc(x.phase||"")+'</span></div>' : ''}
        </article>`).join("") + '</section>' : ''}
    `;
  }

  migrationCards() {
    const items = Object.entries(this.migration());
    if (!items.length) return '<div class="empty">Non ho ancora automazioni legacy da confrontare.</div>';
    return items.map(([name,x]) => `
      <article class="migration hud-panel">
        <div class="panel-orbit"><div class="panel-ring"></div><b>${this.esc(x.shadow_decisions_checked ?? 0)}</b><span>PROVE</span></div>
        <div class="panel-body">
          <div class="eyebrow">${this.esc(this.categoryLabel(name))}</div>
          <h3>${this.esc(this.migrationMeaning(x.status))}</h3>
          <p>${x.status==="candidate_for_manual_migration"
              ? "E.S.T.E.R. ha già abbastanza confronti per valutare una sostituzione manuale."
              : "Per ora terrei attive le automazioni esistenti mentre E.S.T.E.R. continua a confrontarsi con loro."}</p>
          <div class="plain-explain">Automazioni attuali: ${this.esc(x.legacy_automations ?? 0)} · Domande ancora aperte: ${this.esc(x.open_questions ?? 0)}</div>
          ${this._advanced ? `<details class="tech-details" open><summary>DETTAGLI TECNICI</summary><pre>${this.esc(JSON.stringify(x,null,2))}</pre></details>` : ''}
        </div>
      </article>`).join("");
  }

  learningCards() {
    const s = this.summary();
    const groups = [
      ["CLIMA STANZE",s.thermal_models||{},"quanto velocemente si scaldano o raffreddano le stanze"],
      ["VENTILAZIONE",s.ventilation_models||{},"quanto serve davvero accendere le ventole"],
      ["ACQUA CALDA",s.hot_water_models||{},"come cala e recupera la temperatura del boiler"],
      ["PRESENZA",s.occupancy_models||{},"quando è probabile che gli ambienti vengano usati"]
    ];
    return groups.map(([label,data,desc]) => {
      const vals = Object.values(data).map(x=>Number(x?.confidence)).filter(Number.isFinite);
      const avg = vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
      const enough = avg != null && avg >= .65;
      return `
        <article class="model hud-panel">
          <div class="panel-orbit"><div class="panel-ring"></div><b>${enough?"OK":"…"}</b><span>${enough?"DATI SUFFICIENTI":"STO IMPARANDO"}</span></div>
          <div class="panel-body">
            <div class="eyebrow">${this.esc(label)}</div>
            <h3>${enough ? "Ho già una base utile" : "Mi servono ancora osservazioni"}</h3>
            <p>Sto imparando ${this.esc(desc)}.</p>
            <div class="plain-explain">${avg==null?"Non ho ancora abbastanza esempi.":this.confidenceMeaning(avg)}</div>
            ${this._advanced ? `<details class="tech-details" open><summary>DETTAGLI TECNICI</summary><pre>${this.esc(JSON.stringify(data,null,2)).slice(0,3000)}</pre></details>` : ''}
          </div>
        </article>`;
    }).join("");
  }

  validationView() {
    const s = this.summary();
    const k = s.kpis || {};
    const h = s.autonomy_health || {};
    const replay = s.last_replay || {};
    const scenario = s.last_scenario || {};
    const anomalies = s.anomalies || [];
    const ready = !!h.overall_ready_for_executor;
    return `
      ${this.viewHeader("VALIDATION / 06","VALIDAZIONE","Qui vedi in parole semplici se E.S.T.E.R. ha già imparato abbastanza.", ready?"QUASI PRONTA":"NON ANCORA","STATO")}
      <article class="health ${ready?"ok":"warn"}">
        <div class="decision-section primary"><span>POSSO TOGLIERE SHADOW?</span><strong>${ready?"I DATI SONO ABBASTANZA SOLIDI PER LA VALIDAZIONE FINALE":"NO, CONTINUEREI ANCORA IN SHADOW"}</strong></div>
        <p>${ready
            ? "I domini principali hanno dati e feedback sufficienti. L'esecuzione reale comunque non è ancora attiva."
            : "Ci sono ancora aree che devono essere osservate o confermate prima di affidare azioni reali a E.S.T.E.R."}</p>
        <div class="plain-explain">${(h.blocking_reasons||[]).length ? "Da completare: "+this.esc((h.blocking_reasons||[]).map(x=>this.categoryLabel(x)).join(", ")) : "Nessun blocco principale rilevato."}</div>
      </article>

      <h2 class="section-title">COME STA ANDANDO</h2>
      <section class="simple-status-grid">
        <div><b>${this.esc(k.decisions ?? 0)}</b><span>decisioni osservate</span></div>
        <div><b>${k.avg_confidence == null ? "—" : this.pct(k.avg_confidence)}</b><span>sicurezza media</span></div>
        <div><b>${k.feedback?.quality_score == null ? "—" : this.pct(k.feedback.quality_score)}</b><span>feedback positivi</span></div>
        <div><b>${this.esc(k.open_questions ?? 0)}</b><span>domande ancora aperte</span></div>
      </section>

      <h2 class="section-title">PROVA SULLO STORICO</h2>
      <article class="control">
        <p>Puoi farle rileggere il passato per vedere cosa avrebbe deciso, senza aspettare settimane.</p>
        <div class="button-row"><button data-replay="7">ULTIMA SETTIMANA</button><button data-replay="30">ULTIMO MESE</button><button data-replay="56">ULTIME 8 SETTIMANE</button></div>
        ${replay.checkpoints ? `<div class="plain-explain">Ultima prova: ${this.esc(replay.decisions)} decisioni simulate · sicurezza media ${this.pct(replay.avg_checkpoint_confidence)} · ${this.esc(replay.needs_input)} casi in cui avrebbe chiesto aiuto.</div>` : ''}
        ${this._advanced ? `<details class="tech-details"><summary>DETTAGLI TECNICI REPLAY</summary><pre>${this.esc(JSON.stringify(replay,null,2)).slice(0,3500)}</pre></details>` : ''}
      </article>

      <h2 class="section-title">SIMULA UNA GIORNATA DIVERSA</h2>
      <article class="control">
        <p>Serve per vedere come cambierebbero le decisioni se foste in vacanza, aveste ospiti o cambiasse il costo dell'energia.</p>
        <div class="button-row"><button data-scenario="normal">GIORNATA NORMALE</button><button data-scenario="vacation">VACANZA</button><button data-scenario="guests">OSPITI</button><button data-scenario="illness">MALATTIA</button><button data-scenario="work_from_home">CASA/LAVORO</button></div>
        ${scenario.mode ? `<div class="plain-explain">Ultima simulazione: ${this.esc(scenario.mode)} · ${this.esc(scenario.decision_count)} decisioni previste.</div>` : ''}
      </article>

      <h2 class="section-title">COSE DA CONTROLLARE</h2>
      <section class="grid">${anomalies.length ? anomalies.slice(0,20).map(a=>`
        <article class="decision"><div class="eyebrow">${this.esc(a.entity_id)}</div><h3>${this.esc(a.message)}</h3><p>Questo dato potrebbe ridurre l'affidabilità delle decisioni finché non viene verificato.</p></article>`).join("") : '<div class="empty">Non vedo problemi importanti nei sensori osservati.</div>'}</section>
    `;
  }

  forecastCard() {
    const f = this.summary().daily_forecast || {};
    const uses = f.next_uses || [];
    return `
      <article class="control forecast-simple">
        <div class="eyebrow">OGGI</div>
        <h3>${uses.length ? "Ecco cosa mi aspetto nelle prossime ore" : "Non ho utilizzi particolari previsti"}</h3>
        <p>${f.energy_strategy ? "Per l'energia la strategia prevista è: "+this.esc(String(f.energy_strategy).replaceAll("_"," "))+"." : "Sto ancora costruendo il piano energia della giornata."}</p>
        ${uses.length ? '<div class="timeline">'+uses.slice(0,8).map(u=>`<div><b>${this.esc(u.area_id)}</b><span>${this.esc(u.label || "uso previsto")} · tra ${this.esc(u.minutes_until)} min${u.comfort_c==null?"":" · "+this.esc(u.comfort_c)+" °C"}</span></div>`).join("")+'</div>' : ''}
        ${this._advanced ? `<details class="tech-details"><summary>DETTAGLI TECNICI</summary><pre>${this.esc(JSON.stringify(f,null,2)).slice(0,2500)}</pre></details>` : ''}
      </article>`;
  }

  teachView() {
    const s=this.summary();
    const knowledge=s.knowledge_items || [];
    const coverage=s.knowledge_coverage || {};
    const gaps=s.knowledge_gaps || [];
    const proposal=this._teachDraft;
    const domains=["presence","climate","lighting","hot_water","energy","ventilation","security","appliances","rooms","other"];
    const labels={presence:"PRESENZA / FAMIGLIA",climate:"CLIMA",lighting:"LUCI",hot_water:"ACQUA CALDA",energy:"ENERGIA / FV / BATTERIA",ventilation:"VENTILAZIONE",security:"SICUREZZA",appliances:"ELETTRODOMESTICI",rooms:"STANZE",other:"ALTRO"};
    const grouped={}; for(const k of knowledge){(grouped[k.domain||"other"] ||= []).push(k);}
    return `
      ${this.viewHeader("TEACH / 04","INSEGNA","Raccontami liberamente come vivete la casa. Ti mostro cosa ho capito prima di ricordarlo.",String(knowledge.length),"CONOSCENZE")}
      <section class="command-deck teach-main">
        <div class="command-head"><span>VOCE / TESTO</span><b>RACCONTA A E.S.T.E.R.</b></div>
        <p>Non devi usare parole precise. Puoi parlare di più cose insieme: luci, clima, orari, persone, eccezioni e priorità.</p>
        <div class="command-input"><textarea id="teach" placeholder="Per esempio: «La sera in salotto vogliamo circa 21 gradi. Se non c'è nessuno non serve scaldarlo. Le luci esterne servono quando rientriamo col buio…»"></textarea><button class="mic-btn big-mic" data-mic="teach">◉ PARLA</button><button id="teach-send">${this._busy?"...":"CAPIRE"}</button></div>
      </section>
      ${proposal ? `<h2 class="section-title">QUELLO CHE HO CAPITO</h2><article class="control teach-review"><p>${this.esc(proposal.summary||"Controlla questi punti.")}</p><div class="knowledge-list">${(proposal.items||[]).map(x=>`<div class="knowledge-row"><b>${this.esc(labels[x.domain]||this.categoryLabel(x.domain))}</b><span>${this.esc(x.statement)}</span><small>${this.esc((x.kind||"informazione").replaceAll("_"," "))} · ${this.pct(x.confidence)}</small></div>`).join("")||'<div class="empty">Non ho estratto informazioni affidabili.</div>'}</div><div class="button-row"><button id="teach-confirm">CONFERMA E RICORDA</button><button id="teach-discard">SCARTA</button></div><p class="hint">Finché non confermi, la memoria di E.S.T.E.R. non cambia.</p></article>` : ""}
      <h2 class="section-title">COSA SO GIÀ</h2>
      <section class="grid">${domains.map(d=>{const items=grouped[d]||[];const cv=coverage[d]||{};return `<article class="control knowledge-domain"><div class="eyebrow">${labels[d]}</div><h3>${items.length ? "Sto imparando" : "Da insegnare"}</h3><p>${this.esc(cv.meaning|| (items.length ? "Ho già alcune informazioni su questo argomento." : "Non mi hai ancora raccontato abbastanza di questo argomento."))}</p>${items.slice(-5).map(x=>`<div class="knowledge-mini">${this.esc(x.statement||x.text||"")}</div>`).join("")}</article>`}).join("")}</section>
      <h2 class="section-title">COSA MI MANCA</h2>
      <section class="grid">${gaps.length?gaps.map(g=>`<article class="decision data-gap"><div class="eyebrow">${this.esc(labels[g.domain]||"CASA")}</div><h3>${this.esc(g.title)}</h3><p>${this.esc(g.why)}</p></article>`).join(""):'<div class="empty">Non vedo lacune importanti da chiederti adesso.</div>'}</section>
    `;
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
      ${this.viewHeader("CONFIG / 08","CONFIGURAZIONE","Routine, carichi, mappature, pesi decisionali e memoria.","ADMIN","ACCESS")}
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
        ${gaps.length ? gaps.slice(0,30).map(g=>{ const f=this.friendlyGap(g); return `
          <article class="decision data-gap">
            <div class="eyebrow">DATO MANCANTE · ${this.esc(String(f.area).toUpperCase())}</div>
            <h3>${this.esc(f.title)}</h3>
            <div class="decision-section"><span>PERCHÉ MI SERVE</span><p>${this.esc(f.why)}</p></div>
            <div class="decision-section"><span>COSA DEVI INDICARMI</span><strong>${this.esc(f.action)}</strong></div>
          </article>`; }).join("") : '<div class="empty">Non vedo dati mancanti importanti in questo momento.</div>'}
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
    const modeToggle = this.shadowRoot?.querySelector("#mode-toggle");
    if (modeToggle) modeToggle.onclick = () => { this._advanced = !this._advanced; this.render(); };
    const teach = this.shadowRoot?.querySelector("#teach-send");
    if (teach) teach.onclick = () => this.teach();
    const teachConfirm = this.shadowRoot?.querySelector("#teach-confirm");
    if (teachConfirm) teachConfirm.onclick = () => this.confirmTeach();
    const teachDiscard = this.shadowRoot?.querySelector("#teach-discard");
    if (teachDiscard) teachDiscard.onclick = () => this.discardTeach();
    this.shadowRoot?.querySelectorAll("[data-answer]").forEach(el => el.onclick=()=>this.answer(el.dataset.answer));
    this.shadowRoot?.querySelectorAll("[data-voice-q]").forEach(el => el.onclick=()=>this.speakQuestion(el.dataset.voiceQ));
    this.shadowRoot?.querySelectorAll("[data-quick-q]").forEach(el => el.onclick=()=>this.answer(el.dataset.quickQ, el.dataset.quickAnswer));
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

  stopNeuralCore() {
    if (this._neuralFrame) cancelAnimationFrame(this._neuralFrame);
    this._neuralFrame = 0;
    if (this._neuralResize) {
      window.removeEventListener("resize", this._neuralResize);
      this._neuralResize = null;
    }
  }

  neuralProfile(mode) {
    const profiles = {
      observing:{speed:.35, energy:.34, impulses:3, jitter:.7, glow:.65},
      waiting:{speed:.18, energy:.22, impulses:1, jitter:.35, glow:.48},
      thinking:{speed:.78, energy:.72, impulses:8, jitter:1.6, glow:1},
      replay:{speed:1.3, energy:1, impulses:14, jitter:2.2, glow:1.25},
      alert:{speed:1.05, energy:.95, impulses:11, jitter:2.8, glow:1.35},
    };
    return profiles[mode] || profiles.observing;
  }

  buildNeuralNetwork() {
    const nodes = [];
    const rings = 7;
    const perRing = [14,20,26,32,34,28,20];
    for (let r=0; r<rings; r++) {
      const radius = .12 + r * .055;
      const count = perRing[r];
      for (let i=0; i<count; i++) {
        const a = (i / count) * Math.PI * 2 + (r%2 ? .11 : 0);
        const warp = 1 + Math.sin(a*3 + r*.7)*.09 + Math.cos(a*5-r)*.04;
        nodes.push({
          a,
          r:radius*warp,
          phase:Math.random()*Math.PI*2,
          size:.55+Math.random()*1.6,
          drift:(Math.random()-.5)*.004,
          ring:r,
        });
      }
    }
    for (let i=0;i<34;i++) {
      nodes.push({
        a:Math.random()*Math.PI*2,
        r:.05+Math.random()*.16,
        phase:Math.random()*Math.PI*2,
        size:.8+Math.random()*2,
        drift:(Math.random()-.5)*.006,
        ring:-1,
      });
    }

    const edges=[];
    for (let i=0;i<nodes.length;i++) {
      const a=nodes[i];
      const candidates=[];
      for (let j=0;j<nodes.length;j++) {
        if(i===j) continue;
        const b=nodes[j];
        let da=Math.abs(a.a-b.a); da=Math.min(da,Math.PI*2-da);
        const dr=Math.abs(a.r-b.r);
        const score=da*1.8+dr*9;
        if(score<.72) candidates.push([score,j]);
      }
      candidates.sort((x,y)=>x[0]-y[0]);
      const n=2+(i%3===0?1:0);
      for(const [,j] of candidates.slice(0,n)) {
        const x=Math.min(i,j), y=Math.max(i,j);
        if(!edges.some(e=>e[0]===x&&e[1]===y)) edges.push([x,y,Math.random()*Math.PI*2]);
      }
    }
    this._neuralNodes=nodes;
    this._neuralEdges=edges;
    this._neuralImpulses=[];
  }

  startNeuralCore() {
    this.stopNeuralCore();
    const canvas=this.shadowRoot?.querySelector("#neural-core");
    if(!canvas || this._tab!=="overview") return;
    if(!this._neuralNodes.length) this.buildNeuralNetwork();

    const resize=()=>{
      const rect=canvas.getBoundingClientRect();
      const dpr=Math.min(2,window.devicePixelRatio||1);
      const w=Math.max(1,Math.round(rect.width*dpr));
      const h=Math.max(1,Math.round(rect.height*dpr));
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    };
    this._neuralResize=resize;
    window.addEventListener("resize",resize,{passive:true});
    resize();
    this._neuralStartedAt=performance.now();

    const draw=(now)=>{
      if(!canvas.isConnected || this._tab!=="overview"){this.stopNeuralCore();return;}
      resize();
      const ctx=canvas.getContext("2d");
      if(!ctx){this.stopNeuralCore();return;}
      const dpr=Math.min(2,window.devicePixelRatio||1);
      const w=canvas.width/dpr,h=canvas.height/dpr;
      ctx.setTransform(dpr,0,0,dpr,0,0);
      ctx.clearRect(0,0,w,h);

      const thought=this.thoughtState();
      const p=this.neuralProfile(thought.mode);
      const t=(now-this._neuralStartedAt)/1000;
      const cx=w/2, cy=h/2;
      const base=Math.min(w,h)*.9;
      const breathing=1+Math.sin(t*(.8+p.speed))*.018*p.energy;

      ctx.save();
      ctx.globalCompositeOperation="lighter";

      const halo=ctx.createRadialGradient(cx,cy,0,cx,cy,base*.48);
      halo.addColorStop(0,"rgba(185,253,255,.16)");
      halo.addColorStop(.18,`rgba(67,233,255,${.10*p.glow})`);
      halo.addColorStop(.55,`rgba(0,215,255,${.045*p.glow})`);
      halo.addColorStop(1,"rgba(0,120,160,0)");
      ctx.fillStyle=halo;ctx.beginPath();ctx.arc(cx,cy,base*.49,0,Math.PI*2);ctx.fill();

      const pts=this._neuralNodes.map((n,idx)=>{
        const spin=t*(.035+p.speed*.025)*(n.r>.28?1:-.65);
        const pulse=Math.sin(t*(1.1+p.speed)+n.phase)*(.006+.008*p.energy);
        const noise=Math.sin(t*(1.7+p.speed)+idx*.73+n.phase)*n.drift*p.jitter;
        const rr=(n.r+pulse+noise)*base*breathing;
        const aa=n.a+spin+Math.sin(t*.7+n.phase)*.006*p.jitter;
        const squash=.79 + .05*Math.sin(t*.42);
        return {x:cx+Math.cos(aa)*rr,y:cy+Math.sin(aa)*rr*squash,n};
      });

      for(const [ia,ib,phase] of this._neuralEdges){
        const a=pts[ia], b=pts[ib];
        const flicker=.12+.28*(.5+.5*Math.sin(t*(1.8+p.speed*2)+phase));
        ctx.strokeStyle=`rgba(64,235,255,${flicker*p.glow})`;
        ctx.lineWidth=.45+.65*p.energy;
        ctx.beginPath();
        const mx=(a.x+b.x)/2 + Math.sin(t*.8+phase)*5*p.energy;
        const my=(a.y+b.y)/2 + Math.cos(t*.7+phase)*5*p.energy;
        ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo(mx,my,b.x,b.y);ctx.stroke();
      }

      for(let i=0;i<pts.length;i++){
        const q=pts[i];
        const flick=.45+.55*(.5+.5*Math.sin(t*(1.3+p.speed)+q.n.phase));
        const r=q.n.size*(.65+p.energy*.5);
        ctx.shadowBlur=5+7*p.glow;ctx.shadowColor="rgba(67,238,255,.9)";
        ctx.fillStyle=`rgba(178,251,255,${.32+.55*flick})`;
        ctx.beginPath();ctx.arc(q.x,q.y,r,0,Math.PI*2);ctx.fill();
      }
      ctx.shadowBlur=0;

      const desired=p.impulses;
      while(this._neuralImpulses.length<desired){
        const edgeIndex=Math.floor(Math.random()*this._neuralEdges.length);
        this._neuralImpulses.push({edgeIndex,u:Math.random(),speed:.12+Math.random()*.22,life:.7+Math.random()*.7});
      }
      while(this._neuralImpulses.length>desired) this._neuralImpulses.pop();
      for(const imp of this._neuralImpulses){
        imp.u=(imp.u+imp.speed*(.35+p.speed)*.016)%1;
        const [ia,ib]=this._neuralEdges[imp.edgeIndex%this._neuralEdges.length];
        const a=pts[ia],b=pts[ib],u=imp.u;
        const x=a.x+(b.x-a.x)*u, y=a.y+(b.y-a.y)*u;
        const rg=ctx.createRadialGradient(x,y,0,x,y,9+8*p.energy);
        rg.addColorStop(0,"rgba(255,255,255,1)");
        rg.addColorStop(.18,"rgba(146,250,255,.95)");
        rg.addColorStop(1,"rgba(0,220,255,0)");
        ctx.fillStyle=rg;ctx.beginPath();ctx.arc(x,y,10+8*p.energy,0,Math.PI*2);ctx.fill();
      }

      const corePulse=.88+.12*Math.sin(t*(1.7+p.speed*1.8));
      const coreR=base*(.055+.018*p.energy)*corePulse;
      const core=ctx.createRadialGradient(cx,cy,0,cx,cy,coreR*3.4);
      core.addColorStop(0,"rgba(255,255,255,.98)");
      core.addColorStop(.13,"rgba(158,252,255,.95)");
      core.addColorStop(.4,`rgba(32,225,255,${.7*p.glow})`);
      core.addColorStop(1,"rgba(0,130,175,0)");
      ctx.fillStyle=core;ctx.beginPath();ctx.arc(cx,cy,coreR*3.4,0,Math.PI*2);ctx.fill();

      for(let k=0;k<3;k++){
        const rr=base*(.37+k*.045 + Math.sin(t*(.55+k*.12))* .006);
        ctx.strokeStyle=`rgba(78,235,255,${(.11-k*.02)*p.glow})`;
        ctx.lineWidth=.6;
        ctx.setLineDash([2+k,8+k*3]);
        ctx.lineDashOffset=-t*(7+k*4)*p.speed;
        ctx.beginPath();ctx.ellipse(cx,cy,rr,rr*.79,0,0,Math.PI*2);ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.restore();

      this._neuralFrame=requestAnimationFrame(draw);
    };
    this._neuralFrame=requestAnimationFrame(draw);
  }

  thoughtState() {
    const s = this.summary();
    const q = Number(this.state("sensor.e_s_t_e_r_questions")?.state || 0);
    const replay = s.last_replay || {};
    const anomalies = s.anomalies || [];
    const decisions = this.latest();
    const newest = decisions[decisions.length-1];

    if (replay.status === "running") return {mode:"replay",label:"RILEGGO IL PASSATO",detail:"Sto confrontando lo storico con ciò che avrei deciso oggi.",pulse:"fast"};
    if (anomalies.length) return {mode:"alert",label:"STO VERIFICANDO",detail:"Ho trovato dati che meritano controllo.",pulse:"alert"};
    if (q > 0) return {mode:"waiting",label:"MI MANCA UN'INFORMAZIONE",detail:"Sto aspettando una tua risposta per decidere meglio.",pulse:"slow"};
    if (newest) return {mode:"thinking",label:"STO RAGIONANDO",detail:"Sto confrontando stato attuale, abitudini, costi e sicurezza.",pulse:"normal"};
    return {mode:"observing",label:"STO OSSERVANDO",detail:"Raccolgo dati e imparo il comportamento della casa.",pulse:"slow"};
  }

  render() {
    if (!this.shadowRoot) return;
    this.stopNeuralCore();
    const s = this.summary();
    const status = this.state("sensor.e_s_t_e_r_status")?.state || "loading";
    const decisionCount = this.state("sensor.e_s_t_e_r_shadow_decisions")?.state || "0";
    const questionCount = this.state("sensor.e_s_t_e_r_questions")?.state || "0";
    const observed = this.state("sensor.e_s_t_e_r_observed_entities")?.state || "0";
    const health = s.autonomy_health || {};
    const thought = this.thoughtState();

    const tabs = [
      ["overview","CORE"],["decisions","DECISIONI"],["questions","DOMANDE"],["teach","INSEGNA"],
      ["energy","ENERGIA"],["learning","APPRENDIMENTO"],["validation","VALIDAZIONE"],
      ["migration","MIGRAZIONE"],["config","CONFIG"]
    ];

    let body = "";
    if (this._tab === "overview") {
      body = `
        <section class="jarvis-stage">
          <div class="hud-grid"></div>
          <div class="telemetry left">
            <div class="hud-label">SYSTEM / 01</div>
            <div class="hud-value">${this.esc(status.toUpperCase())}</div>
            <div class="hud-line"></div>
            <div class="tele-row"><span>STATO</span><b>${this.esc(thought.label)}</b></div>
            <div class="tele-row"><span>DECISIONI</span><b>${this.esc(decisionCount)}</b></div>
            <div class="tele-row"><span>DOMANDE</span><b>${this.esc(questionCount)}</b></div>
            <div class="tele-row"><span>ATTUAZIONI</span><b>0</b></div>
          </div>

          <div class="jarvis neural-canvas-core" data-mode="${this.esc(thought.mode)}">
            <canvas id="neural-core" aria-label="${this.esc(thought.label)}"></canvas>
            <div class="neural-reticle nr1"></div>
            <div class="neural-reticle nr2"></div>
            <div class="neural-caption">
              <strong>${this.esc(thought.label)}</strong>
              <span>${this.esc(thought.detail)}</span>
            </div>
          </div>

          <div class="telemetry right">
            <div class="hud-label">CASA / ADESSO</div>
            <div class="hud-value">${this.esc((s.season?.season || "—").toUpperCase())}</div>
            <div class="hud-line"></div>
            <div class="tele-row"><span>AUTONOMIA</span><b>${health.overall_ready_for_executor ? "PRONTA" : "NON PRONTA"}</b></div>
            <div class="tele-row"><span>SICUREZZA</span><b>${this.pct(s.kpis?.avg_confidence)}</b></div>
            <div class="tele-row"><span>RISCONTRI</span><b>${this.pct(s.kpis?.feedback?.quality_score)}</b></div>
            <div class="tele-row"><span>MODALITÀ</span><b>SHADOW</b></div>
          </div>
        </section>

        <section class="identity-strip">
          <div>
            <span>EVERYTHING SEEMS TOTALLY EASY, RIGHT?</span>
            <strong>E.S.T.E.R.</strong>
          </div>
          <div class="live-chip"><i></i> SHADOW ATTIVO · NESSUNA AZIONE REALE</div>
        </section>

        <section class="command-deck">
          <div class="command-head"><span>CONOSCENZA CASA</span><b>INSEGNA A E.S.T.E.R.</b></div>
          <p>Per raccontarmi come vivete la casa, cosa preferite e le eccezioni, usa la sezione INSEGNA. Prima di ricordare qualcosa ti farò sempre controllare cosa ho capito.</p>
          <button data-tab="teach">APRI INSEGNA</button>
        </section>
        <h2 class="section-title">PREVISIONE CASA</h2>
        ${this.forecastCard()}
        <h2 class="section-title">ULTIME DECISIONI</h2>
        ${this.groupedDecisionCards(this.realDecisions().slice(-12))}
      `;
    } else if (this._tab === "decisions") {
      const cats = ["all","energy","climate","hot_water","ventilation","lighting","security","presence","irrigation","operational_safety"];
      body = this.viewHeader("DECISION / 02","DECISIONI","Le scelte che E.S.T.E.R. avrebbe eseguito, ordinate per dominio.",this.pct(s.kpis?.avg_confidence),"CONFIDENCE")+'<h2 class="section-title">DECISIONI CHE E.S.T.E.R. AVREBBE PRESO</h2><article class="control decision-explainer"><p>Le decisioni sono raggruppate per tipo, così puoi leggere subito Energia, Clima, Sicurezza, Luci e gli altri domini separatamente.</p><label>Filtro dominio<select id="decision-filter">'+cats.map(x=>'<option value="'+x+'" '+(this._decisionCategory===x?'selected':'')+'>'+this.categoryLabel(x)+'</option>').join("")+'</select></label></article>'+this.groupedDecisionCards();
    } else if (this._tab === "questions") {
      body = this.viewHeader("QUESTIONS / 03","DOMANDE","Informazioni che E.S.T.E.R. ti chiede per ridurre l'incertezza.",String(questionCount),"APERTE")+'<h2 class="section-title">QUESTION INBOX · DIMMI QUELLO CHE MANCA</h2><article class="control"><p>Le domande sono raggruppate per argomento, così puoi rispondere prima a Energia, Clima, Sicurezza o agli altri gruppi senza mescolare tutto.</p></article>'+this.groupedQuestionCards();
    } else if (this._tab === "teach") {
      body = this.teachView();
    } else if (this._tab === "energy") {
      body = this.viewHeader("ENERGY / 04","ENERGIA","Planner integrato FV, rete, batteria, limiti e carichi flessibili.",this.esc((s.daily_forecast?.energy_strategy||"LEARNING").replaceAll("_"," ").toUpperCase()),"STRATEGY")+'<h2 class="section-title">ENERGY MANAGER INTEGRATO</h2>'+this.energyCard()+
        '<h2 class="section-title">ULTIME DECISIONI ENERGIA</h2>'+
        this.groupedDecisionCards(this.realDecisions().filter(x=>x.category==="energy"));
    } else if (this._tab === "learning") {
      body = this.viewHeader("LEARNING / 05","APPRENDIMENTO","Modelli locali costruiti dallo storico reale della casa.",String((Object.keys(s.thermal_models||{}).length+Object.keys(s.occupancy_models||{}).length+Object.keys(s.hot_water_models||{}).length+Object.keys(s.ventilation_models||{}).length)),"MODELLI")+'<h2 class="section-title">MODELLI APPRESI</h2><section class="grid">'+this.learningCards()+'</section>';
    } else if (this._tab === "validation") {
      body = this.validationView();
    } else if (this._tab === "migration") {
      body = this.viewHeader("MIGRATION / 07","MIGRAZIONE","Confronto tra logiche legacy e comportamento Shadow E.S.T.E.R.",String(Object.keys(this.migration()).length),"DOMINI")+'<h2 class="section-title">MIGRAZIONE AUTOMAZIONI</h2><section class="grid">'+this.migrationCards()+'</section>';
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
.jarvis-stage{min-height:430px;position:relative;display:grid;grid-template-columns:minmax(210px,1fr) minmax(300px,460px) minmax(210px,1fr);align-items:center;gap:26px;overflow:hidden;border-top:1px solid #64eaff3a;border-bottom:1px solid #64eaff24;background:radial-gradient(circle at 50% 50%,#0b52602b 0,transparent 45%),linear-gradient(90deg,transparent,#04121999 18%,#021017d9 50%,#04121999 82%,transparent);box-shadow:inset 0 0 120px #00d9ff0b}
        .jarvis-stage:before,.jarvis-stage:after{content:"";position:absolute;top:9%;bottom:9%;width:1px;background:linear-gradient(transparent,#5aefff88,transparent);box-shadow:0 0 12px #00dcff}.jarvis-stage:before{left:5%}.jarvis-stage:after{right:5%}
        .hud-grid{position:absolute;inset:0;background-image:linear-gradient(#35dff708 1px,transparent 1px),linear-gradient(90deg,#35dff708 1px,transparent 1px);background-size:30px 30px;mask-image:radial-gradient(circle at center,#000 10%,transparent 75%)}
        .jarvis{width:min(34vw,430px);height:min(34vw,430px);min-width:320px;min-height:320px;position:relative;border-radius:50%;display:grid;place-items:center;margin:auto;filter:drop-shadow(0 0 34px #00d9ff30)}.ring{position:absolute;border:1px solid #48eaff;border-radius:50%;box-shadow:0 0 18px #00d9ff38,inset 0 0 18px #00d9ff20}.r0{inset:0;border-style:dotted;opacity:.42;animation:spin 31s linear reverse infinite}.r1{inset:8%;border-width:2px;border-left-color:transparent;border-bottom-color:#48eaff28;animation:spin 16s linear infinite}.r2{inset:23%;border-style:dashed;animation:spin 10s linear reverse infinite}.r3{inset:37%;border-width:2px;animation:pulseRing 2.4s ease-in-out infinite}.tick-ring{position:absolute;inset:13%;border-radius:50%;background:repeating-conic-gradient(#5cecff 0 1deg,transparent 1deg 6deg);mask:radial-gradient(circle,transparent 0 43%,#000 44% 48%,transparent 49%);opacity:.58;animation:spin 44s linear infinite}.neural-canvas-core{position:relative;isolation:isolate}.neural-canvas-core canvas{position:absolute;inset:1%;width:98%;height:98%;display:block;filter:drop-shadow(0 0 14px #00dfff55)}.neural-canvas-core:before{content:"";position:absolute;inset:7%;border-radius:50%;background:radial-gradient(circle,transparent 0 45%,#00eaff08 58%,transparent 72%);box-shadow:inset 0 0 70px #00eaff10;pointer-events:none}.neural-reticle{position:absolute;border-radius:50%;pointer-events:none}.nr1{inset:4%;border:1px solid #4ceaff4f;border-left-color:transparent;border-right-color:transparent;animation:spin 26s linear infinite}.nr2{inset:15%;border:1px dashed #4ceaff32;animation:spin 17s linear reverse infinite}.neural-caption{position:absolute;left:-5%;right:-5%;bottom:4%;text-align:center;display:grid;gap:5px;pointer-events:none}.neural-caption strong{font:400 12px monospace;letter-spacing:.22em;color:#d8fdff;text-shadow:0 0 14px #00dfff}.neural-caption span{font:9px/1.4 monospace;color:#67acb8;letter-spacing:.025em}.thought-field{display:none!important}.scan-line{position:absolute;width:46%;height:1px;background:linear-gradient(90deg,transparent,#7af5ff,transparent);transform-origin:100% 50%;left:4%;top:50%;animation:spin 4.5s linear infinite}.core-caption{position:absolute;bottom:12%;font:9px monospace;letter-spacing:.26em;color:#58b8c5}
        .telemetry{position:relative;z-index:2;padding:18px 20px;background:linear-gradient(90deg,#031018b5,transparent 94%);clip-path:polygon(0 0,92% 0,100% 14%,100% 86%,92% 100%,0 100%)}.telemetry.right{background:linear-gradient(270deg,#031018b5,transparent 94%);text-align:right;clip-path:polygon(8% 0,100% 0,100% 100%,8% 100%,0 86%,0 14%)}.hud-label{font:9px monospace;letter-spacing:.26em;color:#3fa8b8}.hud-value{font:300 27px monospace;letter-spacing:.08em;color:#c9fbff;margin:7px 0;text-shadow:0 0 14px #55eaff55}.hud-line{height:1px;background:linear-gradient(90deg,#48eaff,transparent);margin:10px 0 14px}.right .hud-line{background:linear-gradient(270deg,#48eaff,transparent)}.tele-row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #37dff216;font:10px monospace;color:#559aa7}.right .tele-row{flex-direction:row-reverse}.tele-row b{font-weight:400;color:#d2fbff}
        .identity-strip{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;padding:14px 4px 20px}.identity-strip span{display:block;font:9px monospace;letter-spacing:.2em;color:#4eb5c4}.identity-strip strong{display:block;font:300 clamp(36px,5vw,70px)/1 monospace;letter-spacing:.18em;color:#eaffff;text-shadow:0 0 18px #4eeaff55}.live-chip{font:10px monospace;color:#6ce6c5}.live-chip i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#62ffd2;box-shadow:0 0 12px #62ffd2;margin-right:7px}
        .command-deck{position:relative;margin:4px 0 24px;padding:14px 18px;border-top:1px solid #3ce8ff3d;border-bottom:1px solid #3ce8ff20;background:linear-gradient(90deg,transparent,#04171ea8 10%,#04171ea8 90%,transparent)}.command-head{display:flex;justify-content:space-between;gap:20px;margin-bottom:9px}.command-head span{font:9px monospace;letter-spacing:.22em;color:#4faebe}.command-head b{font:400 12px monospace;letter-spacing:.17em;color:#8af1ff}.command-input{display:grid;grid-template-columns:1fr auto auto;gap:8px}.command-input textarea{min-height:62px;background:#01090dbb;border:1px solid #2adcf044;color:#e5fdff;padding:12px;resize:vertical}
        h1{font-size:clamp(54px,9vw,130px);letter-spacing:.16em;margin:2px 0;color:#e8fdff;text-shadow:0 0 14px #75eeff,0 0 50px #0acfea60}
        h2.section-title{font-size:12px;font-weight:400;letter-spacing:.26em;color:#63eaff;margin:30px 0 12px;text-transform:uppercase}.lead{font-size:18px;color:#8dbbc6}
        .eyebrow{font-size:10px;letter-spacing:.2em;color:#4acde8;text-transform:uppercase}.statusline{font-family:monospace;color:#6ff7d0;margin:6px 0}.pulse{display:inline-block;width:8px;height:8px;background:#60ffd5;border-radius:50%;box-shadow:0 0 12px #60ffd5;margin-right:8px}
        @keyframes spin{to{transform:rotate(360deg)}}@keyframes pulseRing{50%{transform:scale(1.08);opacity:.55}}
        .plain-explain{margin:12px 0;padding:10px 12px;border-left:2px solid #46e8ff66;background:#03151b99;color:#9bc7cf;line-height:1.45}.decision-section.primary strong{font-size:19px;color:#ecffff}.simple-confidence{text-align:right}.simple-confidence b{display:block;font:400 11px monospace;letter-spacing:.08em;color:#bdfaff}.simple-confidence span{display:block;font:300 28px monospace;color:#61eaff;text-shadow:0 0 12px #00dfff44}.tech-details{margin-top:12px;border-top:1px solid #38dff229;padding-top:10px}.tech-details summary{cursor:pointer;font:9px monospace;letter-spacing:.15em;color:#57b6c5}.simple-status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0 20px}.simple-status-grid>div{padding:15px 16px;border-top:1px solid #43e8ff42;border-bottom:1px solid #43e8ff1d;background:linear-gradient(90deg,transparent,#04151ca6 10%,#04151ca6 90%,transparent)}.simple-status-grid b{display:block;font:300 25px monospace;color:#d3fdff}.simple-status-grid span{font-size:10px;color:#73aeb8}.mode-toggle{margin-left:auto!important;border-color:#4ceaff77!important}.human-metrics span{line-height:1.25}.forecast-simple h3{font-size:20px;font-weight:400;color:#dffcff}
        .view-hud-head{position:relative;display:grid;grid-template-columns:110px 1fr minmax(150px,240px);align-items:center;gap:20px;min-height:150px;margin:4px 0 24px;padding:18px 24px;border-top:1px solid #50ecff45;border-bottom:1px solid #50ecff22;background:linear-gradient(90deg,transparent,#041820c4 10%,#041820c4 90%,transparent);overflow:hidden}
        .view-hud-head:before{content:"";position:absolute;inset:0;background-image:linear-gradient(#35dff708 1px,transparent 1px),linear-gradient(90deg,#35dff708 1px,transparent 1px);background-size:22px 22px;mask-image:linear-gradient(90deg,transparent,#000 15%,#000 85%,transparent)}
        .mini-reactor{position:relative;width:86px;height:86px;border-radius:50%;display:grid;place-items:center}.mini-ring{position:absolute;border:1px solid #54eaff;border-radius:50%;box-shadow:0 0 12px #00dfff38}.mini-ring.a{inset:0;border-style:dashed;animation:spin 14s linear infinite}.mini-ring.b{inset:17%;animation:spin 7s linear reverse infinite}.mini-ring.c{inset:32%;border-style:dotted}.mini-core{width:22px;height:22px;border-radius:50%;background:#c8fcff;box-shadow:0 0 15px #fff,0 0 38px #00eaff}
        .view-copy{position:relative;z-index:1}.view-copy p{margin:6px 0;color:#79aeb8}.view-title{margin:3px 0;font:300 clamp(28px,4vw,52px)/1 monospace;letter-spacing:.12em;color:#e8fdff;text-shadow:0 0 16px #49eaff55}.view-metric{position:relative;z-index:1;text-align:right;border-right:1px solid #54eaff55;padding-right:14px}.view-metric span{display:block;font:8px monospace;letter-spacing:.22em;color:#4caaba}.view-metric b{display:block;margin:5px 0;font:300 24px monospace;color:#c9fbff}.view-metric i{display:block;margin-left:auto;width:70%;height:1px;background:linear-gradient(90deg,transparent,#52eaff)}
        .hud-panel,.control,.health,.decision,.question-panel,.migration,.model,.energy-core{position:relative;border:0!important;border-top:1px solid #4eeaff40!important;border-bottom:1px solid #4eeaff1e!important;background:linear-gradient(90deg,transparent,#04161dc4 7%,#04161dc4 93%,transparent)!important;border-radius:0!important;clip-path:polygon(0 9px,9px 0,100% 0,100% calc(100% - 9px),calc(100% - 9px) 100%,0 100%);box-shadow:none!important}
        .hud-panel:before,.control:before,.health:before,.decision:before,.question-panel:before{content:"";position:absolute;left:0;top:22%;bottom:22%;width:2px;background:#51ecff;box-shadow:0 0 10px #00dfff88}
        .panel-orbit{position:relative;width:112px;height:112px;min-width:112px;border-radius:50%;display:grid;place-items:center;align-content:center}.panel-orbit .panel-ring{position:absolute;inset:5px;border:1px dashed #4ceaff99;border-radius:50%;animation:spin 16s linear infinite;box-shadow:0 0 15px #00dfff25}.panel-orbit:after{content:"";position:absolute;inset:24px;border:1px solid #4ceaff55;border-radius:50%}.panel-orbit b{font:300 24px monospace;color:#d5fdff;z-index:1}.panel-orbit span{font:7px monospace;letter-spacing:.16em;color:#55aeba;z-index:1}.panel-body{flex:1;min-width:0}.model,.migration{display:flex;gap:20px;align-items:center}.model h3,.migration h3{font:400 20px monospace;letter-spacing:.08em}.model details{margin-top:12px;color:#629da8}.model summary{cursor:pointer;font:9px monospace;letter-spacing:.14em;color:#55b8c8}.signal-line{height:2px;background:#0a2b34;margin:14px 0}.signal-line span{display:block;height:100%;background:#54ebff;box-shadow:0 0 10px #54ebff}
        .tele-list{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.tele-list>div{padding:8px 10px;border-top:1px solid #40eaff2e;background:#03121980}.tele-list span{display:block;font:8px monospace;letter-spacing:.12em;color:#579ba7}.tele-list b{font:300 18px monospace;color:#c7faff}
        .energy-reactor{position:relative;width:160px;height:160px;min-width:160px;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 35px #00dfff22}.energy-ring{position:absolute;border-radius:50%;border:1px solid #51ecff}.er1{inset:4%;border-style:dashed;animation:spin 13s linear infinite}.er2{inset:22%;border-width:2px;animation:spin 7s linear reverse infinite}.energy-core-dot{width:54px;height:54px;border-radius:50%;background:radial-gradient(circle,#d8ffff 0 8%,#55eaff 10%,#073b46 30%,#021014 65%);box-shadow:0 0 18px #fff,0 0 55px #00eaff}.energy-reactor>span{position:absolute;bottom:14px;font:10px monospace;color:#79eaf8}
        .hud-gauge{position:relative;width:120px;height:120px;border-radius:50%;background:conic-gradient(#56eaff calc(var(--pct)*1%),#0b2a33 0);padding:3px;box-shadow:0 0 20px #00dfff22}.hud-gauge:after{content:"";position:absolute;inset:7px;border-radius:50%;background:#031016}.gauge-face{position:absolute;inset:0;z-index:2;display:grid;place-items:center;align-content:center}.gauge-face b{font:300 25px monospace;color:#e3feff}.gauge-face span{font:7px monospace;letter-spacing:.15em;color:#5eabb7}.hud-gauge small{position:absolute;top:100%;left:0;right:0;text-align:center;color:#659ba5}
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.stats>div,.metrics>div{padding:18px;border:1px solid #16d8ff35;background:#06151d9e;border-radius:10px}.stats b,.metrics b{display:block;font-size:28px;color:#d9fbff}.stats span,.metrics span{font-size:10px;letter-spacing:.14em;color:#55bdd0}
        .teach,.control,.health{border:1px solid #1eddfc40;background:#041219c8;border-radius:12px;padding:15px}.teach-row,.answer-row,.button-row{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}
        textarea,input,select{width:100%;border:1px solid #25dffc44;background:#02090e;color:#dcfbff;border-radius:8px;padding:11px}.teach textarea,.control textarea{min-height:85px;resize:vertical}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.decision,.question,.migration,.model,.energy-core{position:relative;border:0;border-top:1px solid #63eaff42;border-bottom:1px solid #63eaff1f;background:linear-gradient(90deg,transparent,#05161dbd 7%,#05161dbd 93%,transparent);clip-path:polygon(0 10px,10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%);padding:18px 20px;box-shadow:none}.decision:before,.question:before,.migration:before,.model:before{content:"";position:absolute;left:14px;top:0;width:70px;height:1px;background:#74efff;box-shadow:0 0 8px #26e7ff}
        .decision-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.confidence-block{text-align:right;font-family:monospace}.confidence-block span{display:block;font-size:8px;letter-spacing:.18em;color:#4eaabb}.confidence-block b{font-size:28px;font-weight:400;color:#c9fbff;text-shadow:0 0 12px #4eeaff55}.decision-section{margin:14px 0;padding-left:13px;border-left:1px solid #45e9ff55}.decision-section span{display:block;font-size:9px;letter-spacing:.17em;color:#4cb4c4;margin-bottom:5px}.decision-section strong{font-size:17px;font-weight:400;color:#dcfbff}.decision-section p{margin:0;color:#91c0c8;line-height:1.45}.decision-explainer{margin-bottom:14px}.decision h3,.question h3,.migration h3,.model h3{margin:5px 0 10px;color:#e9fdff}.confidence{font-family:monospace;font-size:25px;color:#68efff}.meter{height:3px;background:#0e2a34;margin:8px 0 14px}.meter span{display:block;height:100%;background:#53edff;box-shadow:0 0 10px #2ae8ff}.decision p,.question p,.energy-core p,.control p,.health p{color:#9dc5cf;line-height:1.5}.proposal{padding:10px 12px;background:#06222c;border-left:2px solid #50e9ff;color:#c8f8ff;margin-top:12px}.meta{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;color:#4fa3b3;font-family:monospace;font-size:10px;margin-top:13px}
        .answer-row input{flex:1;min-width:180px}.mic-btn{border-radius:999px;border-color:#69f2ff;box-shadow:0 0 14px #00d9ff44;background:radial-gradient(circle,#0b3444,#041018)}.big-mic{min-width:112px}.quick-row{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}.quick{padding:7px 10px;font-size:11px}.question-focus{display:grid;grid-template-columns:120px 1fr;gap:18px;align-items:start}.question-radar{position:relative;width:108px;height:108px;border-radius:50%;border:1px solid #69efff99;display:grid;place-items:center;background:radial-gradient(circle,#0bdcff24 0,#031018 58%,transparent 59%);box-shadow:0 0 25px #00dcff22,inset 0 0 25px #00dcff18}.radar-ring{position:absolute;border:1px solid #43e8ff66;border-radius:50%}.rr1{inset:12%;border-style:dashed;animation:spin 9s linear infinite}.rr2{inset:28%;animation:spin 5s linear reverse infinite}.radar-value{font:700 20px monospace;color:#c9fbff;text-shadow:0 0 12px #56eaff}.question-block{margin:10px 0;padding:9px 12px;border-left:2px solid #28dff2;background:linear-gradient(90deg,#09202a88,transparent)}.question-block span{display:block;font-size:9px;letter-spacing:.18em;color:#49c6dc}.question-block p{margin:5px 0}.question-block.ask{border-left-color:#fff}.question-block.why{border-left-color:#6ff7d0}.hint{font-size:12px;color:#7db5c0;font-style:italic;margin:8px 0}.energy-core{display:flex;align-items:center;gap:35px}.orb{width:150px;height:150px;border-radius:50%;border:1px solid #4dedff;display:grid;place-items:center;box-shadow:0 0 30px #00d9ff45,inset 0 0 35px #00d9ff25;flex:0 0 auto}.orb-core{width:48px;height:48px;border-radius:50%;background:#c9fbff;box-shadow:0 0 50px #16e5ff}.energy-data{flex:1}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.metrics.compact b{font-size:19px}.status{font-family:monospace;color:#6ff6cb}.model pre{white-space:pre-wrap;max-height:310px;overflow:auto;color:#7eb9c5;font-size:11px}.empty{padding:30px;color:#6c9da8;border:1px dashed #1bd5ef35;border-radius:10px}
        .health.ok{border-color:#5dffc16b}.health.warn{border-color:#ffc95d59}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:10px 0}.form-grid.one{grid-template-columns:1fr auto}.form-grid label{font-size:11px;color:#68c9da;letter-spacing:.08em}.form-grid label input,.form-grid label select{margin-top:5px}.timeline{display:grid;gap:7px;margin-top:12px}.timeline div{display:flex;justify-content:space-between;gap:15px;padding:9px;border-bottom:1px solid #1cdff322}.timeline span{color:#7bbcca;font-size:12px}
        @media(max-width:800px){
          :host{overflow-x:hidden}
          .shell{width:100%;max-width:100vw;padding:8px 10px 34px;overflow-x:hidden}
          .mobile-nav-wrap{position:sticky;top:0;z-index:20;margin:0 -10px 12px;padding:7px 10px 9px;background:linear-gradient(#03080d 72%,#03080de8 88%,transparent)}
          nav{position:relative;top:auto;z-index:auto;display:flex;flex-wrap:nowrap;gap:7px;width:100%;max-width:100%;overflow-x:auto;overflow-y:hidden;padding:2px 1px 8px;scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;touch-action:pan-x;scrollbar-width:none;background:none}
          nav::-webkit-scrollbar{display:none}
          nav button{flex:0 0 auto;min-width:max-content;padding:9px 12px;font-size:11px;white-space:nowrap;scroll-snap-align:center}
          nav button.active{position:relative}
          .mode-toggle{display:block;width:100%;margin:2px 0 0!important;padding:8px 10px;font-size:10px}
          .view-hud-head{grid-template-columns:58px minmax(0,1fr)!important;min-height:auto!important;padding:10px!important;gap:9px}
          .view-hud-head>div,.question-main,.model>div,.migration>div,.telemetry,.card,.panel{min-width:0}
          .view-hud-head h1,.view-hud-head h2,.section-title,.question-main h2{overflow-wrap:anywhere;word-break:normal}
          .view-hud-head h1{font-size:24px!important;letter-spacing:.06em}
          .view-hud-head p,.question-prompt,.question-context,.decision-copy,.tele-list,.timeline{overflow-wrap:anywhere}
          .view-metric{grid-column:1/-1!important;text-align:left!important;border-right:0!important;border-left:1px solid #54eaff55;padding:7px 0 7px 9px!important}
          .mini-reactor{width:52px!important;height:52px!important}
          .jarvis-stage{display:flex!important;flex-direction:column;justify-content:flex-start;min-height:0!important;gap:8px;padding:10px 0 14px;overflow:visible!important}
          .jarvis-stage:before,.jarvis-stage:after{display:none}
          .jarvis{order:1;width:min(86vw,330px)!important;height:min(86vw,330px)!important;min-width:0!important;min-height:0!important;flex:0 0 auto}
          .telemetry{position:relative!important;inset:auto!important;width:100%!important;order:2;padding:10px!important}
          .telemetry.right{order:3}
          .neural-caption{left:2%!important;right:2%!important;bottom:5%!important}
          .neural-caption strong{font-size:11px!important;letter-spacing:.12em!important}
          .neural-caption span{font-size:9px!important;line-height:1.35!important;padding:0 12px}
          .identity-strip{display:flex!important;align-items:flex-start!important;flex-direction:column!important;gap:8px}
          .simple-status-grid,.stats,.metrics{grid-template-columns:1fr!important}
          .grid,.tele-list,.question-context,.answer-console,.question-focus,.question-panel,.command-input,.form-grid,.form-grid.one{grid-template-columns:1fr!important}
          .question-panel{padding:12px!important}
          .question-index{display:none!important}
          .question-main h2{font-size:20px!important;line-height:1.15}
          .question-prompt{font-size:16px!important;line-height:1.4}
          .model,.migration{align-items:flex-start;flex-direction:column!important}
          .panel-orbit{width:70px!important;height:70px!important;min-width:70px!important}
          .energy-core{display:block!important}
          .energy-reactor{width:116px!important;height:116px!important;min-width:116px!important;margin:0 auto 12px}
          .orb{margin:0 auto 16px}
          .teach-row,.answer-row{grid-template-columns:1fr!important;flex-direction:column!important}
          .timeline div{display:grid!important;grid-template-columns:1fr!important;gap:4px!important}
          .telemetry{clip-path:none!important;border:1px solid #37dff225;background:#031018cc!important;border-radius:10px;text-align:left!important}
          .telemetry.right{text-align:left!important}
          .right .tele-row{flex-direction:row!important}
          .hud-value{font-size:20px!important;margin:4px 0!important}
          .hud-line{margin:6px 0 8px!important}
          .tele-row{font-size:11px!important;padding:6px 0!important}
          .identity-strip{padding:10px 4px 14px!important}
          .identity-strip span{font-size:8px!important;letter-spacing:.12em!important}
          .identity-strip strong{font-size:34px!important;letter-spacing:.12em!important}
          .live-chip{font-size:9px!important;line-height:1.4}
          .command-deck{padding:12px 8px!important;margin-bottom:16px!important}
          .command-head{flex-direction:column!important;gap:3px!important}
          .command-input textarea{min-height:82px;font-size:16px}
          .knowledge-row{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid #1cdff322}.knowledge-row span,.knowledge-mini{overflow-wrap:anywhere}.knowledge-row small{color:#68aebb}.knowledge-mini{padding:8px 0;color:#a9d2d9;border-bottom:1px solid #1cdff31a}
          h2.section-title{margin:20px 0 10px!important;font-size:11px!important;letter-spacing:.16em!important}
          input,select,textarea,button{max-width:100%}
          pre,.code,.technical{max-width:100%;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere}
        }
      </style>
      <div class="shell">
        ${this._notice ? '<div class="notice">'+this.esc(this._notice)+'</div>' : ''}
        <div class="mobile-nav-wrap"><nav id="ester-nav">${tabs.map(([id,label])=>`<button data-tab="${id}" class="${this._tab===id?"active":""}">${label}</button>`).join("")}</nav><button id="mode-toggle" class="mode-toggle">${this._advanced?"MODALITÀ SEMPLICE":"DETTAGLI TECNICI"}</button></div>
        ${body}
      </div>
    `;
    this.bind();
    if (this._tab === "overview") requestAnimationFrame(()=>this.startNeuralCore());
  }
}
customElements.define("ester-panel", EsterPanel);
