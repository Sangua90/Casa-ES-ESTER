# E.S.T.E.R.
**Everything Seems Totally Easy, Right? — V1 Shadow Mode**

E.S.T.E.R. osserva Home Assistant, costruisce un modello delle stanze e registra proposte spiegabili. **Non contiene un esecutore, non chiama servizi dei dispositivi e non può abilitare l'attuazione.**

## Cosa fa
- Scopre entità, aree e dispositivi; permette correzioni locali della classificazione.
- Legge 24 ore di storico Recorder e 7 giorni di statistiche orarie quando disponibili, senza modificare il database.
- Apprende trend descrittivi di temperatura, umidità, ACS e frequenze d'uso delle stanze.
- Valuta clima, FV/consumi/batteria, ACS, ventilazione/deumidificazione, irrigazione, luci, presenza e segnali di sicurezza.
- Registra confidence, rischio, impatto, motivazioni, evidenze, alternative e osservazioni successive. Le osservazioni successive **non** dimostrano l'effetto di una proposta mai eseguita.
- Conserva preferenze, contesti a scadenza e feedback. Supporta vacanza, ospiti, malattia e lavoro da casa.
- Espone sei sensori, otto servizi amministrativi e una dashboard di esempio.
- Funziona localmente senza AI. Gemini è opzionale, sostituibile e usato solo quando richiedi una spiegazione.

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

## Dashboard e notifiche
[Dashboard Lovelace di esempio](examples/dashboard.yaml): aggiungi una dashboard manuale e incolla il contenuto nell'editor YAML. Adatta gli ID ai sei sensori presenti nella pagina del dispositivo E.S.T.E.R.; i nomi possono dipendere dalla versione precedente e dalle personalizzazioni.

I sensori mostrano stato Shadow, entità osservate, dimensione del registro, domande correnti e riepilogo. Il riepilogo completo è disponibile tramite `ester.get_summary`.

Gli eventi `ester_decision`, `ester_question` e `ester_feedback` sono predisposti per automazioni di notifica. Non viene installata né attivata alcuna automazione: [esempio solo notifica](examples/notification.yaml). Non collegare questi eventi a comandi sui dispositivi se vuoi mantenere l'intero sistema in Shadow Mode.

## Gemini opzionale
Nelle opzioni dell'integrazione scegli `gemini`, inserisci la chiave API e il nome di un modello disponibile nel tuo account. Poi chiama `ester.explain_decision` con un `decision_id`. Vengono inviati a Google categoria, titolo, proposta, motivazione (incluse eventuali misure citate), confidence e rischio. Non vengono inviati inventario completo, ID entità, note dei contesti o attributi grezzi.

Nessuna chiamata periodica: massimo una richiesta al minuto, timeout 25 secondi. Errori del provider non fermano l'osservazione. Selezionando `disabled`, la chiave viene rimossa dalle opzioni correnti e le spiegazioni restano locali. Eventuali backup precedenti mantengono le proprie copie.

L'interfaccia astratta è in `ai/base.py`; il punto di sostituzione è `ai/factory.py`. L'AI produce solo testo, mai strumenti eseguibili né modifiche automatiche ai contesti.

## Limiti dichiarati
Questa V1 implementa apprendimento statistico descrittivo e regole conservative, **non** un modello termico fisico calibrato, un previsore FV o un ottimizzatore economico. Confidence e impatto sono euristiche, non probabilità calibrate o risparmi misurati.

Nessuna diagnosi sanitaria/impiantistica, modifica dei cicli antilegionella, gestione certificata di allarmi o identificazione delle persone. Una stanza senza movimento non viene dichiarata vuota. Dati mancanti o vecchi generano domande, non certezze.

[Architettura, limiti e API verificate](docs/ARCHITECTURE.md) · [Verifica dopo l'installazione](docs/VALIDATION.md)

## Test
```text
python -m unittest discover -s tests -v
```
I test puri funzionano anche senza Home Assistant. I test d'integrazione richiedono Linux/Python 3.14 e Home Assistant 2026.9.4, installati da GitHub Actions. Nessun test accede ai dispositivi della casa o usa credenziali AI reali.


## Come migliorare E.S.T.E.R.
Il nuovo box nella dashboard e il sensore Data suggestions mostrano dati mancanti per stanza, utilità, priorità e tipo di sensore utile. Prima suggeriscono di ripristinare sensori non disponibili o associare entità senza area; hardware nuovo è una possibilità solo dopo queste verifiche. Copre temperatura, umidità, presenza e umidità del terreno in base ai dispositivi osservati. Ogni suggerimento ha un decision_id per la spiegazione locale o Gemini opzionale. Nessun prodotto specifico o acquisto automatico.
