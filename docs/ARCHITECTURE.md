# Architettura V1 Shadow Mode

## Confine operativo
Discovery → Recorder opzionale → modello/learning → motori deterministici → registro e sensori.
Non esiste alcun esecutore. Le soglie low 0.60, medium 0.80, high 0.93, critical 0.99 distinguono una proposta sufficientemente supportata da una domanda; non autorizzano azioni.

I servizi scrivono esclusivamente memoria E.S.T.E.R. e sono amministrativi. Le correzioni di classificazione non modificano il registro HA. I moduli AI ricevono un riepilogo esplicitamente richiesto, senza oggetti HomeAssistant o accesso ai servizi.

## Dati e limiti
- Aggiornamento ogni 5 minuti; osservazione degli stati attuali senza listener per ogni variazione.
- Recorder: finestra 24 ore, refresh ogni 30 minuti, batch 20 entità, massimo 100 entità ordinate per ID, selezionate per ruoli utili all'apprendimento. Il riepilogo espone il troncamento.
- Conservazione di massimo 1.000 punti storici per entità; la query può leggere più righe prima del campionamento. Su database molto trafficati la finestra deve restare contenuta.
- Statistiche: fino a 7 giorni, periodo hour, solo entità con state_class appropriata. Le statistiche mantengono i metadati/valori del Recorder, non vengono sommate a contatori istantanei.
- Memoria live: massimo 500 entità, 300 campioni ciascuna, finestra 24 ore. Il confronto termico avviene in °C, quello di potenza in W; unità mancanti o non compatibili sono escluse.
- Regressione sull'ultimo episodio senza valori unknown/NaN e senza intervalli oltre due ore; almeno tre campioni e mezz'ora. È una tendenza, non un modello causale.
- Occupazione per ora locale: durata pesata, almeno 15 minuti osservati per cella; intervalli oltre due ore restano ignoti. Le frequenze derivano dalle ultime 24 ore, non sono previsioni settimanali.
- Sensori non aggiornati da oltre due ore sono trattati conservativamente come non affidabili anche se lo stato potrebbe essere ancora valido.
- Store HA versione 1, compatibile con la memoria iniziale. Lock condiviso tra valutazione e servizi; snapshot copiato al salvataggio.
- Registro: massimo 500 decisioni; massimo 500 feedback e 100 contesti. Deduplicazione della stessa proposta per sei ore; rivalutazione corrente esposta nei sensori, evidenza originaria conservata nel registro.
- Dopo 30 minuti il registro annota lo stato osservato successivamente, senza attribuire causalità alla proposta.
- Domande correnti nel sensore, prime 20 in attributi; ultime cinque decisioni in attributi. Il registro completo recente si consulta con get_summary. Attributi estesi esclusi dal Recorder.

## Moduli
- home.py: numeri finiti, unità, ruoli, contesti attivi, trend e stanze.
- discovery.py: stato HA e registri entità/dispositivi/aree; esclude l'integrazione stessa.
- history.py: letture opzionali sul thread executor del Recorder, degradazione allo stato live in caso di errore.
- policies.py: motori locali senza import Home Assistant.
- decision_engine.py: confidence e soglie rischio. I fattori sono registrati nelle evidenze; feedback negativo riduce il punteggio.
- coordinator.py: orchestration, journal e outcome; nessuna chiamata servizi.
- storage.py: persistenza interna.
- services.py: otto servizi con validazione.
- ai/: contratto astratto e adapter Gemini, disabilitato per default.
- sensor.py: sei sensori senza controlli.

## Motori
| Motore | Comportamento V1 |
|---|---|
| Clima | Confronto temperatura ambiente e comfort esplicito in stanza occupata; domanda per dati mancanti; vacanza richiede limiti concordati. |
| Energia | Una sorgente FV e una di consumo totale associate esplicitamente, confronto W senza doppio conteggio; accumulo solo se associato dall'utente. Richiede perimetro contatori e vincoli. |
| ACS | Trend temperatura e richiesta di programma sanitario/fasce d'uso; nessuna soglia sanitaria inventata. |
| Ventilazione | Umidità >65% genera valutazione; richiede condizioni esterne e rumore prima di scegliere ventilazione/deumidificazione. |
| Irrigazione | Soglia terreno configurabile e domande su pioggia/vincoli; senza sensori chiede associazione. |
| Luci | Segnala luci con assenza di movimento; ospiti, malattia e lavoro da casa richiedono comfort protetto. |
| Presenza | Stato sensori e frequenze d'uso per ora locale, senza identificazione persone. |
| Sicurezza | Segnali attivi o dati non affidabili richiedono verifica; nessun disarmo, sblocco o silenziamento. |

I modi su aree specifiche non cambiano le regole delle altre stanze. Le note libere restano memoria e non vengono trasformate automaticamente in policy. Le domande si risolvono correggendo associazioni/preferenze/sensori; il feedback valuta la proposta ma non sostituisce un dato mancante.

## API di riferimento verificate
Release di riferimento: Home Assistant **2026.9.4**, 29 settembre 2026.
- [Recorder history](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/recorder/history/__init__.py): get_significant_states con risposta State non compressa e attributi.
- [Recorder statistics](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/recorder/statistics.py): statistics_during_period(hass, start, end, ids, period, units, types).
- [Recorder helper](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/recorder.py): get_instance e async_add_executor_job.
- [Admin services](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/service.py): async_register_admin_service e risposte.
- [Config entries](https://developers.home-assistant.io/docs/config_entries_index/): runtime_data, forwarding sensori, unload e listener opzioni.
- [Gemini generateContent](https://ai.google.dev/gemini-api/docs/text-generation): REST con chiave in header e nessun function calling.

Le firme Recorder interne possono cambiare in future release: gli errori riducono la disponibilità dei dati, senza abilitare controlli. La CI esegue il motore e smoke test contro la release indicata; non sostituisce il collaudo sulla casa reale.
