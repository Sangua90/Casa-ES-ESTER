## E.S.T.E.R. 1.4.0 — Pre-Autonomy Shadow

Questa release completa il livello di validazione prima dell'autonomia, mantenendo **zero attuazione reale**.

### Validazione
- Replay Recorder da 1 a 30 giorni, con checkpoint e statistiche su decisioni/confidence/rischio.
- What-if per modalità casa, comfort e costo energia senza persistenza.
- KPI Shadow, confidence media, feedback quality, domande e anomalie.
- Autonomy Health per energia, clima, sicurezza, ACS e ventilazione.

### Decisione
- Planner multi-obiettivo whole-home.
- Pesi regolabili: sicurezza, comfort, costo, energia, usura apparati, confidence.
- Priorità decisione separata dalla readiness all'esecuzione.
- Confidence calibrata con feedback per dominio.
- Forecast giornaliero locale e stagionalità automatica.
- Errore di previsione osservabile quando disponibile; nessuna causalità inventata.

### Interfaccia
- Centro E.S.T.E.R. laterale con CORE, DECISIONI, DOMANDE, ENERGIA, APPRENDIMENTO, VALIDAZIONE, MIGRAZIONE e CONFIG.
- Storico decisioni filtrabile.
- Editor routine d'uso casa.
- Editor carichi energetici gestiti.
- Wizard classificazione entità e dati mancanti.
- Replay e scenari avviabili dal pannello.
- Snapshot e rollback direttamente dal pannello.
- Export/import JSON della memoria.

### Sicurezza
- Le automazioni legacy restano attive.
- Casa ES Energy Manager non viene disattivato automaticamente.
- Nessuna automazione viene rimossa automaticamente.
- Nessun servizio HA di attuazione viene chiamato.
- L'executor reale non esiste in questa release.

**L'unico salto architetturale ancora escluso è la futura rimozione controllata dello Shadow Mode.**

Richiede Home Assistant 2026.9.4 o successivo.
