## E.S.T.E.R. 1.3.0 — Pre-Final Shadow

Versione pensata per portare il cervello di E.S.T.E.R. vicino alla futura modalità autonoma, mantenendo **zero attuazione reale**.

- Agente conversazionale nativo Home Assistant selezionabile in Assist.
- Parser locale + Gemini opzionale per interpretare preferenze, contesti, routine e note.
- Gemini non decide dispositivi: i calcoli restano locali e deterministici.
- Modello termico empirico per stanza e pre-climatizzazione predittiva.
- Modello di occupazione per giorno/ora combinato con routine dichiarate.
- Apprendimento dell'efficacia della ventilazione.
- Modello ACS locale di calo/recupero.
- Confronto economico PDC/gas con tariffe e COP configurabili.
- Planner energia locale con FV, carico, rete, SOC, target batteria, riserva, limiti inverter/fasi e forecast.
- Carichi flessibili con potenza, durata, priorità, SOC minimo e interrompibilità.
- Outcome learning e calibrazione da feedback.
- Inventario automazioni legacy e stato di prontezza alla migrazione per categoria.
- Planner Shadow per luci e antifurto.
- Export della memoria E.S.T.E.R.
- Centro di controllo nativo nel menu laterale di Home Assistant, stile JARVIS, con CORE, DECISIONI, DOMANDE, ENERGIA, APPRENDIMENTO e MIGRAZIONE.
- Gestione carichi energia con fase, priorità, SOC minimo, finestre orarie, tempi minimi ON/OFF, massimo avvii e non-interrompibilità.

Le automazioni esistenti e Casa ES Energy Manager **non vengono modificati o disattivati**. La migrazione resta manuale e progressiva.

**Ultimo passo futuro:** introdurre un executor controllato e togliere Shadow per domini validati. Questa release non contiene tale executor.

Richiede Home Assistant 2026.9.4 o successivo.
