# Domande e risposte con ChatGPT

Nella pagina **Domande**, premi **Scarica tutte le domande**. Il file JSON
contiene tutte le domande aperte, stanza, motivazione, osservazioni e suggerimenti.
Puoi caricarlo in una normale chat ChatGPT e chiedere:

> Raggruppa e spiegami queste domande con parole semplici. Raccogli le mie
> risposte senza inventare informazioni. Alla fine restituisci il file JSON
> nello stesso formato, mantenendo question_id e fingerprint.

Carica il file restituito in **Domande → File di risposte → Mostra anteprima**.
Leggi le risposte e cosa verrà salvato, poi premi **Conferma importazione**.
L'anteprima non modifica nulla. La conferma crea un checkpoint e aggiorna solo
la memoria: nessuna chiamata ai dispositivi e nessuna richiesta a Gemini.
Caricare il file in ChatGPT è una tua scelta: contiene informazioni sulla casa.

## Formato

Il documento conserva `format: "ester-question-exchange-v1"` e l'array `questions`.
Non cambiare gli identificativi o le impronte delle domande. Modifica soltanto:

- `answer`: risposta testuale, massimo 2000 caratteri. `null` lascia aperta la domanda.
- `action: "answer"`: apprende la risposta con la stessa interpretazione delle risposte nel pannello.
- `action: "defer"`: registra «Non lo so», senza imparare una preferenza; rinvia la domanda di sette giorni.
- `action: "obsolete"`: chiude questa domanda come non pertinente e impedisce di riproporla identica. Non cancella o esclude sensori o aree.

Le risposte libere diventano note; solo le preferenze riconosciute dal parser
locale diventano valori strutturati. L'anteprima mostra questa distinzione.
Le note non diventano automazioni eseguibili. Non sostituisce il backup memoria
e non usa il formato `ester-knowledge-v1` della pagina Insegna.

Limiti: 300 domande e file massimo 1 MB. Se una risposta riguarda una domanda
chiusa, modificata o sconosciuta, oppure contiene identificativi duplicati,
l'intera importazione viene rifiutata senza apprendere risposte parziali.
Scarica un nuovo file e trasferisci solo le risposte ancora pertinenti.

## Riferimenti eliminati

Alla valutazione, le domande aperte collegate ad aree eliminate da Home Assistant
o esclusivamente a entità non più registrate né presenti vengono archiviate.
Le proposte e i modelli delle aree eliminate non compaiono nella vista corrente;
la memoria e il registro originali restano conservati. Le classificazioni manuali
non possono ricreare un'area eliminata. Un sensore registrato ma indisponibile
rimane riconosciuto: offline non significa eliminato.
«Dati non affidabili» rimane una diagnosi, senza chiedere all'utente di verificare
frequenze o raggiungibilità dei sensori.
