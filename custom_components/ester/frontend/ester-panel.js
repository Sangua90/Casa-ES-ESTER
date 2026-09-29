class EsterPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._hass = null;
    this._busy = false;
    this._tab = "overview";
  }

  set hass(value) {
    this._hass = value;
    this.render();
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    this.render();
  }

  state(id) {
    return this._hass?.states?.[id];
  }

  esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  pct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? Math.round(n * 100) + "%" : "—";
  }

  latest() {
    return this.state("sensor.e_s_t_e_r_shadow_decisions")?.attributes?.latest || [];
  }

  questions() {
    return this.state("sensor.e_s_t_e_r_questions")?.attributes?.items || [];
  }

  summary() {
    return this.state("sensor.e_s_t_e_r_summary")?.attributes || {};
  }

  migration() {
    return this.summary().migration_readiness || {};
  }

  async call(domain, service, data={}) {
    if (!this._hass || this._busy) return;
    this._busy = true;
    this.render();
    try {
      await this._hass.callService(domain, service, data);
    } finally {
      this._busy = false;
      this.render();
    }
  }

  async teach() {
    const el = this.shadowRoot?.querySelector("#teach");
    const message = el?.value?.trim();
    if (!message) return;
    await this.call("ester", "interpret_message", {message});
    if (el) el.value = "";
  }

  async answer(questionId) {
    const el = this.shadowRoot?.querySelector("#answer-" + CSS.escape(questionId));
    const answer = el?.value?.trim();
    if (!answer) return;
    await this.call("ester", "answer_question", {question_id: questionId, answer});
  }

  decisionCards() {
    const items = this.latest().slice().reverse().slice(0, 12);
    if (!items.length) return '<div class="empty">Nessuna decisione Shadow disponibile.</div>';
    return items.map(d => `
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
        <div class="meta"><span>RISCHIO ${this.esc((d.risk || "—").toUpperCase())}</span><span>SHADOW</span></div>
      </article>
    `).join("");
  }

  questionCards() {
    const items = this.questions().slice(0, 10);
    if (!items.length) return '<div class="empty">Nessuna domanda aperta.</div>';
    return items.map(q => `
      <article class="question">
        <div class="eyebrow">INPUT REQUIRED · ${this.pct(q.confidence)}</div>
        <h3>${this.esc(q.title)}</h3>
        <p>${this.esc(q.prompt)}</p>
        <div class="answer-row">
          <input id="answer-${this.esc(q.question_id)}" placeholder="Scrivi la risposta..." />
          <button data-answer="${this.esc(q.question_id)}">INVIA</button>
        </div>
      </article>
    `).join("");
  }

  energyCard() {
    const d = this.latest().slice().reverse().find(x => x.category === "energy");
    if (!d) return '<div class="empty">Il planner energia non ha ancora una decisione completa.</div>';
    const p = d.evidence?.energy_plan || {};
    return `
      <article class="energy-core">
        <div class="orb"><div class="orb-core"></div></div>
        <div class="energy-data">
          <div class="eyebrow">LOCAL ENERGY CORE</div>
          <h2>${this.esc((p.strategy || "learning").replaceAll("_", " ").toUpperCase())}</h2>
          <div class="metrics">
            <div><b>${this.esc(p.pv_w ?? "—")}</b><span>FV W</span></div>
            <div><b>${this.esc(p.load_w ?? "—")}</b><span>CASA W</span></div>
            <div><b>${this.esc(p.battery_soc ?? "—")}%</b><span>SOC</span></div>
            <div><b>${this.esc(p.instant_surplus_w ?? "—")}</b><span>SURPLUS W</span></div>
          </div>
          <p>${this.esc(d.reasoning)}</p>
        </div>
      </article>
    `;
  }

  migrationCards() {
    const items = Object.entries(this.migration());
    if (!items.length) return '<div class="empty">Nessuna automazione legacy classificata.</div>';
    return items.map(([name, x]) => `
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
      ["THERMAL", s.thermal_models || {}],
      ["VENTILATION", s.ventilation_models || {}],
      ["HOT WATER", s.hot_water_models || {}],
      ["OCCUPANCY", s.occupancy_models || {}],
    ];
    return groups.map(([label, data]) => `
      <article class="model">
        <div class="eyebrow">${label}</div>
        <h3>${Object.keys(data).length} modelli</h3>
        <pre>${this.esc(JSON.stringify(data, null, 2)).slice(0, 1400)}</pre>
      </article>
    `).join("");
  }

  bind() {
    this.shadowRoot?.querySelectorAll("[data-tab]").forEach(el => {
      el.onclick = () => { this._tab = el.dataset.tab; this.render(); };
    });
    const teach = this.shadowRoot?.querySelector("#teach-send");
    if (teach) teach.onclick = () => this.teach();
    this.shadowRoot?.querySelectorAll("[data-answer]").forEach(el => {
      el.onclick = () => this.answer(el.dataset.answer);
    });
  }

  render() {
    if (!this.shadowRoot) return;
    const status = this.state("sensor.e_s_t_e_r_status")?.state || "loading";
    const decisionCount = this.state("sensor.e_s_t_e_r_shadow_decisions")?.state || "0";
    const questionCount = this.state("sensor.e_s_t_e_r_questions")?.state || "0";
    const observed = this.state("sensor.e_s_t_e_r_observed_entities")?.state || "0";

    const tabs = [
      ["overview","CORE"],
      ["decisions","DECISIONI"],
      ["questions","DOMANDE"],
      ["energy","ENERGIA"],
      ["learning","APPRENDIMENTO"],
      ["migration","MIGRAZIONE"],
    ];

    let body = "";
    if (this._tab === "overview") {
      body = `
        <section class="hero">
          <div class="jarvis">
            <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>
            <div class="core-dot"></div>
          </div>
          <div>
            <div class="eyebrow">EVERYTHING SEEMS TOTALLY EASY, RIGHT?</div>
            <h1>E.S.T.E.R.</h1>
            <p class="lead">Home Intelligence Core · Shadow Mode</p>
            <div class="statusline"><span class="pulse"></span>${this.esc(status.toUpperCase())} · REAL ACTUATION DISABLED</div>
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
          <div class="teach-row"><textarea id="teach" placeholder="Es. Questo weekend siamo via. Ester oggi è a casa. La palestra la uso alle 19..."></textarea><button id="teach-send">${this._busy ? "..." : "INVIA"}</button></div>
        </section>
        <h2 class="section-title">LIVE DECISION FEED</h2>
        <section class="grid">${this.decisionCards()}</section>
      `;
    } else if (this._tab === "decisions") {
      body = '<h2 class="section-title">DECISIONI SHADOW</h2><section class="grid">' + this.decisionCards() + '</section>';
    } else if (this._tab === "questions") {
      body = '<h2 class="section-title">QUESTION INBOX</h2><section class="grid">' + this.questionCards() + '</section>';
    } else if (this._tab === "energy") {
      body = '<h2 class="section-title">ENERGY MANAGER INTEGRATO</h2>' + this.energyCard() + '<h2 class="section-title">ULTIME DECISIONI ENERGIA</h2><section class="grid">' + this.latest().filter(x=>x.category==="energy").slice().reverse().slice(0,8).map(d=>`<article class="decision"><div class="decision-head"><h3>${this.esc(d.title)}</h3><div class="confidence">${this.pct(d.confidence)}</div></div><p>${this.esc(d.reasoning)}</p><div class="proposal">${this.esc(d.proposed_action)}</div></article>`).join("") + '</section>';
    } else if (this._tab === "learning") {
      body = '<h2 class="section-title">MODELLI APPRESI</h2><section class="grid">' + this.learningCards() + '</section>';
    } else if (this._tab === "migration") {
      body = '<h2 class="section-title">MIGRAZIONE AUTOMAZIONI</h2><section class="grid">' + this.migrationCards() + '</section>';
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;min-height:100vh;background:radial-gradient(circle at 50% -10%,#0c4251 0,#071820 32%,#03080d 68%);color:#dffaff;font-family:Inter,Roboto,sans-serif}
        *{box-sizing:border-box}.shell{max-width:1600px;margin:auto;padding:18px 22px 50px}
        nav{display:flex;gap:8px;overflow:auto;padding:6px 0 18px;position:sticky;top:0;z-index:5;background:linear-gradient(#03080df2,#03080dd9 75%,transparent)}
        nav button,.teach button,.answer-row button{border:1px solid #19d9ff55;background:#071b24;color:#7feeff;padding:10px 14px;border-radius:7px;letter-spacing:.08em;cursor:pointer}
        nav button.active{background:#0b3443;box-shadow:0 0 18px #00cfff40;border-color:#38e7ff}
        .hero{min-height:300px;display:flex;align-items:center;justify-content:center;gap:60px;border:1px solid #1cc9e32e;background:linear-gradient(135deg,#06151db8,#03101766);border-radius:16px;box-shadow:inset 0 0 50px #00cfff0d,0 15px 50px #0008}
        h1{font-size:clamp(54px,9vw,130px);letter-spacing:.16em;margin:2px 0;color:#e8fdff;text-shadow:0 0 14px #75eeff,0 0 50px #0acfea60}
        h2.section-title{font-size:15px;letter-spacing:.18em;color:#63eaff;margin:30px 0 12px}.lead{font-size:18px;color:#8dbbc6}
        .eyebrow{font-size:11px;letter-spacing:.18em;color:#4acde8;text-transform:uppercase}.statusline{font-family:monospace;color:#6ff7d0}.pulse{display:inline-block;width:8px;height:8px;background:#60ffd5;border-radius:50%;box-shadow:0 0 12px #60ffd5;margin-right:8px}
        .jarvis{width:220px;height:220px;position:relative;border-radius:50%;display:grid;place-items:center}.ring{position:absolute;border:1px solid #48eaff;border-radius:50%;box-shadow:0 0 22px #00d9ff55,inset 0 0 18px #00d9ff33}.r1{inset:4%;animation:spin 14s linear infinite}.r2{inset:18%;border-style:dashed;animation:spin 9s linear reverse infinite}.r3{inset:32%;animation:pulseRing 2s ease-in-out infinite}.core-dot{width:44px;height:44px;border-radius:50%;background:#c7fbff;box-shadow:0 0 18px #fff,0 0 55px #00eaff,0 0 110px #00d9ff}
        @keyframes spin{to{transform:rotate(360deg)}}@keyframes pulseRing{50%{transform:scale(1.08);opacity:.55}}
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.stats>div,.metrics>div{padding:18px;border:1px solid #16d8ff35;background:#06151d9e;border-radius:10px}.stats b,.metrics b{display:block;font-size:28px;color:#d9fbff}.stats span,.metrics span{font-size:10px;letter-spacing:.14em;color:#55bdd0}
        .teach{border:1px solid #1eddfc40;background:#041219c8;border-radius:12px;padding:15px}.teach-row{display:flex;gap:10px;margin-top:8px}.teach textarea{flex:1;min-height:70px;border:1px solid #25dffc44;background:#02090e;color:#dcfbff;border-radius:8px;padding:12px;resize:vertical}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:13px}.decision,.question,.migration,.model,.energy-core{border:1px solid #1eddfc32;background:linear-gradient(145deg,#071923e8,#031017e8);border-radius:12px;padding:16px;box-shadow:inset 0 0 28px #00d9ff08}
        .decision-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.decision h3,.question h3,.migration h3,.model h3{margin:5px 0 10px;color:#e9fdff}.confidence{font-family:monospace;font-size:25px;color:#68efff}.meter{height:3px;background:#0e2a34;margin:8px 0 14px}.meter span{display:block;height:100%;background:#53edff;box-shadow:0 0 10px #2ae8ff}.decision p,.question p,.energy-core p{color:#9dc5cf;line-height:1.5}.proposal{padding:10px 12px;background:#06222c;border-left:2px solid #50e9ff;color:#c8f8ff;margin-top:12px}.meta{display:flex;justify-content:space-between;color:#4fa3b3;font-family:monospace;font-size:10px;margin-top:13px}
        .answer-row{display:flex;gap:8px}.answer-row input{flex:1;background:#02090e;border:1px solid #28dcf44d;color:#dffaff;border-radius:7px;padding:10px}.energy-core{display:flex;align-items:center;gap:35px}.orb{width:150px;height:150px;border-radius:50%;border:1px solid #4dedff;display:grid;place-items:center;box-shadow:0 0 30px #00d9ff45,inset 0 0 35px #00d9ff25;flex:0 0 auto}.orb-core{width:48px;height:48px;border-radius:50%;background:#c9fbff;box-shadow:0 0 50px #16e5ff}.energy-data{flex:1}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.metrics.compact b{font-size:19px}.status{font-family:monospace;color:#6ff6cb}.model pre{white-space:pre-wrap;max-height:310px;overflow:auto;color:#7eb9c5;font-size:11px}.empty{padding:30px;color:#6c9da8;border:1px dashed #1bd5ef35;border-radius:10px}
        @media(max-width:800px){.shell{padding:10px}.hero{min-height:240px;gap:20px;padding:18px}.jarvis{width:115px;height:115px}h1{font-size:42px}.stats{grid-template-columns:repeat(2,1fr)}.energy-core{display:block}.orb{margin:0 auto 20px}.metrics{grid-template-columns:repeat(2,1fr)}.teach-row,.answer-row{flex-direction:column}}
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
