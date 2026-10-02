# Il nucleo di memoria e ragionamento

CERVELLO è la pagina iniziale. Riunisce domande, file, insegnamenti,
note aggiornabili, esperienze e previsioni. Le altre sezioni specialistiche
sono accessibili da Dettagli tecnici; Decisioni e CORE restano nel menu principale.

## Memoria che entra nelle valutazioni

Dalla 1.7 il racconto `In studio preferisco 21 gradi; in studio lavoro dalle 9
alle 18 nei feriali` propone un comfort e un'abitudine separati. Il parser locale
riconosce nomi/ID delle stanze, temperature esplicite, prezzo in euro/kWh, intervalli
orari e giorni dichiarati. Non completa campi mancanti né trasforma una negazione
o condizione in una regola generale. Un'abitudine indica presenza dichiarata,
non una probabilità misurata. L'anteprima precede sempre la conferma.

**File e insegnamenti → Analizza le informazioni già conservate** prepara
interpretazioni delle fonti precedenti senza attivarle subito. I riferimenti
relativi oggi/domani delle vecchie fonti usano la data originale, non quella
dell'analisi. Gli insegnamenti incompleti si possono completare con un nuovo
racconto collegato alla fonte. Puoi ritirare i valori interpretati; originali e
storico restano conservati e le interpretazioni discendenti non sopravvivono
al ritiro o alla scadenza della fonte. JSON v2 supporta anche `routine` con
`start_time`, `end_time`, `weekdays` (0=lunedì), `expected_occupancy` e
`comfort_c` facoltativo. Informazioni contraddittorie richiedono chiarimento.

Le proposte climatiche mostrano il confronto fra attesa, climatizzazione ora
e anticipazione dell'uso previsto. Usano tassi termici locali e, quando disponibili,
potenza e prezzo configurati. Le stime descrivono energia aggiuntiva e costo
condizionato della climatizzazione elettrica; non confrontano ogni impianto o
ottimizzano tutta la casa. Il modello lineare rispetta il tempo disponibile:
se il target non è raggiungibile lo dichiara. Il comfort ha precedenza nella
fattibilità; i pesi comfort/costo/energia ordinano le alternative ammissibili.
Il punteggio relativo non è una probabilità di successo.

Una potenza o tariffa mancante resta sconosciuta. L'uso del surplus FV osservato
per un intervento immediato assume che rimanga costante: l'ipotesi è visibile e
non viene estesa alle partenze future. Non è una previsione di produzione.
La fiducia di una scelta modellata non può superare la fiducia del modello.
I vincoli fisici e della memoria continuano a bloccare le proposte interessate.
Gli orari futuri vengono cercati direttamente nel calendario, senza interrogare
un modello AI a ogni valutazione. Shadow Mode rimane attivo.

Il motore locale usa una memoria di lavoro comune per valutazioni correnti,
replay e scenari. Filtra la validità temporale, risolve preferenze e contesti,
poi confronta questi dati con sensori, abitudini e modelli termici/di presenza.
Non interroga un provider AI a ogni ciclo: la valutazione ordinaria resta locale.
La durata mostrata comprende anche la lettura dello storico e non è una promessa
di latenza sulla propria installazione. I cicli ordinari restano ogni cinque minuti;
il salvataggio di informazioni e riscontri richiede una nuova valutazione.

Le informazioni libere sono conservate e collegate agli argomenti delle proposte.
Non ogni frase diventa una regola operativa: il pannello distingue contesto,
valore strutturato, conflitto e informazione da verificare. I vincoli già supportati
dal motore continuano a essere applicati. Le chiamate opzionali di interpretazione
AI cercano informazioni nell'intera memoria valida, ordinate per pertinenza,
con un limite di contesto dichiarato; non selezionano soltanto le ultime 40 note.

Le risposte strutturate già confermate hanno priorità sui valori dei file.
Una nota operativa aggiornata può sovrascriverle durante la propria validità.
Due note operative attive incompatibili bloccano le proposte coinvolte e generano
un chiarimento. Aggiornare una nota conserva la precedente come superata;
ritirarla o lasciarla scadere la esclude dalle nuove valutazioni.
Una domanda di comfort con un valore già disponibile viene risolta dalla memoria;
se quel valore temporaneo scade e non esiste un'alternativa, la domanda riapre.

## File e valori espliciti

Si possono caricare più file in ogni invio e aggiungerne altri dopo.
L'archivio conserva i contenuti prima della conferma delle conoscenze:
ricevuta del file e attivazione nella memoria sono due stati distinti.
Il nome non è l'identità: lo stesso contenuto viene deduplicato,
mentre contenuti diversi con lo stesso nome rimangono distinti.

TXT, Markdown e JSON v1 rimangono compatibili. JSON v2 permette di aggiungere
un effetto operativo verificabile. Esempio con valori puramente illustrativi,
da sostituire con quelli reali e con l'identificativo effettivo della stanza:

```json
{
  "format": "ester-knowledge-v2",
  "items": [
    {
      "statement": "Preferenza di comfort invernale della stanza",
      "domain": "climate",
      "kind": "preference",
      "area_id": "IDENTIFICATIVO_STANZA",
      "effect": {"type": "comfort", "value": 21, "season": "winter"}
    },
    {
      "statement": "Prezzo corrente dell'energia acquistata",
      "domain": "energy",
      "kind": "preference",
      "area_id": "",
      "effect": {"type": "energy_price", "value": 0.25}
    }
  ]
}
```

Comfort: stanza obbligatoria, 5–35 °C, stagione all/winter/summer/shoulder.
Costo energia: casa intera, 0–10 €/kWh. Sono valori di valutazione,
non comandi al termostato o ai dispositivi. L'anteprima mostra gli effetti.
I file non vengono trasformati arbitrariamente in automazioni eseguibili.
Per informazioni temporanee usare il modulo delle note: 1 ora, 24 ore,
7 giorni oppure persistenza fino al successivo aggiornamento manuale.

## Esperienze riutilizzabili

Ogni proposta può ricevere un riscontro Corretta/Parziale/Sbagliata.
Il nucleo conserva il caso e le condizioni, separatamente dal registro delle
proposte. Ripetere il riscontro sullo stesso caso aggiorna la valutazione,
senza moltiplicarne il peso. Le proposte con fiducia almeno 85% possono essere
conservate come candidati non verificati; non sono recuperate come successi.

Il confronto cerca casi valutati dalla persona con stesso argomento, stanza,
titolo, dispositivi, situazioni, stagione e obiettivo. Richiede le stesse
osservazioni e unità: gli stati categorici devono coincidere; i numeri possono
differire al massimo del 10% o di un'unità. Mostra fino a tre precedenti,
inclusi errori e risultati parziali. La soluzione corrente viene ricalcolata:
il caso passato non sostituisce i dati nuovi e non aumenta automaticamente
la fiducia. La somiglianza è un criterio semplice, non una garanzia statistica.
Non viene attribuito un successo causale a una proposta mai eseguita.

Note ed esperienze vengono incluse nella memoria persistente, nelle copie locali
verificate e nelle versioni esportabili. Limiti: 1000 note storiche e 2000 casi;
al limite si conserva la storia valutata e si eliminano soltanto candidati
non verificati per fare spazio. Non c'è una crescita illimitata.

## Crescita visibile e limiti

Il pannello mostra quantità effettive: tasselli attivi, file conservati,
risposte, preferenze, abitudini, note scadute, conflitti, modelli ed esperienze.
Mostra inoltre l'ultima valutazione e l'uso della memoria nelle proposte.
Queste misure descrivono memoria e attività: non sono un QI o una promessa
di superiorità sulle decisioni umane. Le previsioni dipendono dallo storico
e dalle associazioni dei sensori; il risparmio reale deve essere misurato.

Shadow Mode rimane invariato: nessuna attuazione fisica e nessun esecutore.

## Verifica

Test su Home Assistant reale: memoria su disco, riavvio, errori di scrittura,
comfort che modifica la proposta, conflitti che restano needs_input anche dopo
calibrazione, riscontri conservati. Test puri: scadenze, riapertura dei dubbi,
scenari senza mutazioni, JSON v2, ricerca su informazioni vecchie, similarità.
Browser WebKit iPhone: caricamento multiplo, errori/retry, conferma, raccolta,
pagina Cervello, salvataggio/aggiornamento/ritiro note, form preservati durante
gli aggiornamenti e assenza di overflow orizzontale.
