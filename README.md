# E.S.T.E.R.
**Everything Seems Totally Easy, Right? — V1.4 Pre-Autonomy Shadow**

E.S.T.E.R. osserva Home Assistant, costruisce un modello delle stanze e registra proposte spiegabili. **Non contiene un esecutore, non chiama servizi dei dispositivi e non può abilitare l'attuazione.**

## Cosa fa
- Scopre entità, aree e dispositivi; permette correzioni locali della classificazione.
- Legge 24 ore di storico Recorder e 7 giorni di statistiche orarie quando disponibili, senza modificare il database.
- Apprende trend e modelli locali: risposta termica delle stanze, efficacia ventilazione, comportamento ACS e probabilità d'uso degli spazi.
- Valuta clima, PDC vs gas, FV/consumi/rete/batteria/fasi, ACS, ventilazione, irrigazione, luci, presenza e antifurto in Shadow.
- Registra confidence, rischio, impatto, motivazioni, evidenze, alternative e osservazioni successive. Le osservazioni successive **non** dimostrano l'effetto di una proposta mai eseguita.
- Conserva preferenze, contesti a scadenza, profili persistenti d’uso previsto degli spazi e feedback. Supporta vacanza, ospiti, malattia e lavoro da casa.
- Espone sensori diagnostici, un campo risposta interattivo, servizi amministrativi e una dashboard HUD.
- Funziona localmente senza AI. Gemini è opzionale: interpreta linguaggio naturale quando il parser locale non basta e spiega decisioni; non calcola la strategia e non controlla dispositivi.

## Installazione e aggiornamento dalla v0.1
Versione di riferimento: **Home Assistant Core 2026.9.4** (Linux, Python >=3.14.2). Non è necessario aggiornare Python separatamente in HA OS.

1. Apri **HACS → E.S.T.E.R. → Aggiorna** e scegli la versione stabile più recente. Se il repository non è ancora presente, aggiungi `https://github.com/Sangua90/Casa-ES-ESTER` in **HACS → menu → Repository personalizzati**, tipo **Integrazione**, poi scarica E.S.T.E.R.
2. HACS scarica e sostituisce automaticamente i file; non servono ZIP o copie manuali.
3. Riavvia Home Assistant. Se E.S.T.E.R. era già configurata, conserva la configurazione: la memoria v0.1 resta leggibile.
4. Per una nuova installazione: **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → E.S.T.E.R.**
5. Assegna le aree in HA, consulta le domande e correggi i ruoli dove necessario. Non tutte le installazioni possiedono i sensori necessari a tutti i motori.

Non creare una seconda integrazione. Non inserire la chiave Gemini in YAML o nel repository.

Le nuove versioni vengono pubblicate automaticamente da GitHub dopo i test su `main`, quando cambia la versione del manifest. HACS rileva le release e gestisce gli aggiornamenti. L'installazione dell'aggiornamento e il riavvio seguono le impostazioni della tua istanza: il repository non abilita aggiornamenti o riavvii automatici di Home Assistant.

## Primo utilizzo
Gli esempi usano ID fittizi: sostituiscili con quelli della tua installazione. Esegui le azioni da **Strumenti per sviluppatori → Azioni**.

Correggere un contatore FV (la stessa azione con `load_power` identifica il consumo totale):
```yaml
action: ester.classify_entity
data:
  entity_id: sensor.potenza_fotovoltaico
  role: solar_power
```

Impostare il comfort di un'area, in °C:
```yaml
action: ester.set_preference
data:
  key: comfort:studio
  value: 21
```

Contesto temporaneo; senza date dura 24 ore:
```yaml
action: ester.add_context
data:
  label: Lavoro da casa
  mode: work_from_home
  areas:
    - studio
```
Per insegnare invece una routine stabile, usa un profilo d'uso previsto:
```yaml
action: ester.set_usage_profile
data:
  area_id: salotto
  label: Salotto weekend sera
  weekdays: [5, 6]
  start_time: "18:00"
  end_time: "23:30"
  expected_occupancy: 0.9
  comfort_c: 21
```
I giorni sono 0=lunedì … 6=domenica. Il servizio restituisce un `profile_id`, che puoi riutilizzare per aggiornare il profilo o passare a `ester.remove_usage_profile`. Le routine sono aspettative, non presenza reale: contesti temporanei come vacanza hanno priorità nelle decisioni Shadow.

Le date esplicite richiedono il fuso orario, ad esempio `2026-10-01T18:00:00+02:00`. `areas: []` indica tutta la casa. I modi sono `normal`, `vacation`, `guests`, `illness`, `work_from_home`. Per terminare prima usa `ester.remove_context` con `event_id`.

`ester.get_summary` restituisce stanze, contesti, stato Recorder e ultime decisioni, con `limit` da 1 a 100. La risposta contiene gli ID per feedback e spiegazioni:
```yaml
action: ester.add_feedback
data:
  decision_id: ID_DALLA_DECISIONE
  rating: wrong
  comment: La stanza era occupata da una persona ferma
```
Valutazioni: `correct`, `wrong`, `partial`. Un secondo feedback sulla stessa decisione sostituisce il precedente. Il feedback negativo riduce la confidence della categoria; non crea automaticamente nuove regole operative.

## Domande e apprendimento
Le decisioni con informazioni mancanti entrano nella **Question Inbox**. Il sensore Questions espone le domande aperte e l'entità `text.e_s_t_e_r_answer_current_question` permette di rispondere direttamente dalla dashboard alla domanda più vecchia.

Una risposta chiara come “Preferisco 21 gradi” a una domanda di comfort diventa una preferenza strutturata. Una risposta più ambigua viene conservata come conoscenza con fonte utente, senza creare automaticamente una regola. Sono disponibili anche `ester.answer_question` e `ester.dismiss_question`.

## Dashboard e notifiche
[Dashboard Lovelace di esempio](examples/dashboard.yaml): aggiungi una dashboard manuale e incolla il contenuto nell'editor YAML. Adatta gli ID ai sei sensori presenti nella pagina del dispositivo E.S.T.E.R.; i nomi possono dipendere dalla versione precedente e dalle personalizzazioni.

I sensori mostrano stato Shadow, entità osservate, dimensione del registro, domande correnti e riepilogo. Il riepilogo completo è disponibile tramite `ester.get_summary`.

Gli eventi `ester_decision`, `ester_question` e `ester_feedback` sono predisposti per automazioni di notifica. Non viene installata né attivata alcuna automazione: [esempio solo notifica](examples/notification.yaml). Non collegare questi eventi a comandi sui dispositivi se vuoi mantenere l'intero sistema in Shadow Mode.

## Conversazione e Assist
La V1.3 espone un agente conversazionale Home Assistant **E.S.T.E.R.**. Puoi selezionarlo nella pipeline Assist. Testo e voce passano allo stesso router: prima interpretazione locale, poi Gemini solo se abilitato e necessario. L'agente non espone feature di controllo Home Assistant.

Puoi anche scrivere direttamente nell'entità `text.e_s_t_e_r_teach_e_s_t_e_r` oppure usare `ester.interpret_message`.

## Gemini opzionale
Nelle opzioni dell'integrazione scegli `gemini`, inserisci la chiave API e il nome di un modello disponibile nel tuo account. Gemini viene chiamato solo dopo un messaggio esplicito dell'utente quando l'interpretazione locale non è sufficientemente sicura, oppure da `ester.explain_decision`. Per il linguaggio riceve il testo e un contesto ridotto (ID aree ammessi e titoli di alcune domande aperte); per le spiegazioni riceve categoria, titolo, proposta, motivazione, confidence e rischio. Non vengono inviati inventario completo, ID entità, note dei contesti o attributi grezzi.

Nessuna chiamata periodica. Le spiegazioni hanno un limite di una richiesta al minuto; le interpretazioni avvengono solo quando invii una frase. Timeout Gemini 25 secondi. Errori del provider non fermano l'osservazione. Selezionando `disabled`, la chiave viene rimossa dalle opzioni correnti e le spiegazioni restano locali. Eventuali backup precedenti mantengono le proprie copie.

L'interfaccia astratta è in `ai/base.py`; il punto di sostituzione è `ai/factory.py`. L'AI produce solo testo, mai strumenti eseguibili né modifiche automatiche ai contesti.

## Limiti dichiarati
La V1.3 implementa modelli empirici locali e planner deterministici. **Non** è ancora un modello termico fisico calibrato né un previsore FV proprietario: usa dati e forecast disponibili in Home Assistant e richiede validazione Shadow prima dell'autonomia. Confidence e impatto sono euristiche, non probabilità calibrate o risparmi misurati.

Nessuna diagnosi sanitaria/impiantistica, modifica dei cicli antilegionella, gestione certificata di allarmi o identificazione delle persone. Una stanza senza movimento non viene dichiarata vuota. Dati mancanti o vecchi generano domande, non certezze.

[Architettura, limiti e API verificate](docs/ARCHITECTURE.md) · [Verifica dopo l'installazione](docs/VALIDATION.md)

## Test
```text
python -m unittest discover -s tests -v
```
I test puri funzionano anche senza Home Assistant. I test d'integrazione richiedono Linux/Python 3.14 e Home Assistant 2026.9.4, installati da GitHub Actions. Nessun test accede ai dispositivi della casa o usa credenziali AI reali.


## Come migliorare E.S.T.E.R.
Il nuovo box nella dashboard e il sensore Data suggestions mostrano dati mancanti per stanza, utilità, priorità e tipo di sensore utile. Prima suggeriscono di ripristinare sensori non disponibili o associare entità senza area; hardware nuovo è una possibilità solo dopo queste verifiche. Copre temperatura, umidità, presenza e umidità del terreno in base ai dispositivi osservati. Ogni suggerimento ha un decision_id per la spiegazione locale o Gemini opzionale. Nessun prodotto specifico o acquisto automatico.


## E.S.T.E.R. HUD
La V1.3 include `examples/dashboard.yaml` con viste CORE, QUESTIONS, LEARNING, ENERGY e MIGRATION, più `examples/ester_hud_theme.yaml` per il tema scuro/ciano. Il pulsante microfono usa l'azione Assist nativa di Home Assistant; il campo risposta testuale è interno a E.S.T.E.R. e non controlla dispositivi.


## Migrazione da automazioni ed Energy Manager
E.S.T.E.R. inventaria in sola lettura le automazioni Home Assistant e le raggruppa per energia, sicurezza, luci, clima, ventilazione, presenza e irrigazione. La pagina MIGRATION confronta il numero di decisioni Shadow, domande aperte e feedback.

Lo stato `candidate_for_manual_migration` significa solo che una categoria può essere valutata per una disattivazione manuale delle vecchie automazioni. **E.S.T.E.R. non le disabilita automaticamente.**

Il planner energia V1.3 è indipendente da Casa ES Energy Manager e può essere istruito con ruoli espliciti per FV, carico, rete, SOC e fasi, più carichi flessibili. Finché resta Shadow, Energy Manager e le automazioni attuali possono continuare a gestire fisicamente la casa mentre E.S.T.E.R. confronta le proprie decisioni.


## Centro di controllo laterale
La V1.3 registra una vera voce **E.S.T.E.R.** nel menu laterale di Home Assistant tramite un custom panel nativo. Non richiede di creare manualmente una dashboard Lovelace.

Il centro di controllo include:
- **CORE**: stato Shadow, nodi osservati, decisioni, domande e canale “Teach E.S.T.E.R.”;
- **DECISIONI**: proposta, motivazione, confidence e rischio;
- **DOMANDE**: Question Inbox con risposta diretta;
- **ENERGIA**: strategia energetica locale, FV, casa, SOC, surplus e decisioni sui carichi;
- **APPRENDIMENTO**: modelli termici, ventilazione, ACS e occupazione;
- **MIGRAZIONE**: stato delle automazioni legacy e prontezza alla sostituzione manuale.

Il pannello è amministrativo e non abilita attuazione reale.


## V1.4 — validazione pre-autonomia
La V1.4 mantiene **Shadow Mode obbligatorio** ma aggiunge il livello di controllo necessario prima di una futura esecuzione reale:

- replay storico Recorder da 1 a 30 giorni;
- planner multi-obiettivo con pesi configurabili per sicurezza, comfort, costo, energia, usura e confidence;
- separazione tra priorità della decisione ed execution readiness;
- confidence calibrata dai feedback reali per dominio;
- errore osservabile delle previsioni quando misurabile, senza attribuire causalità in Shadow;
- KPI Shadow e health gate per dominio;
- rilevamento conservativo di sensori indisponibili/bloccati;
- contesto stagionale automatico;
- forecast locale della giornata;
- simulazioni what-if senza persistenza;
- storico decisioni filtrabile;
- editor visuale di routine, carichi, classificazioni e pesi;
- snapshot, rollback, export e import della memoria;
- wizard dei dati mancanti.

Il sistema non contiene ancora alcun executor reale. La futura rimozione dello Shadow resta un passaggio separato.
