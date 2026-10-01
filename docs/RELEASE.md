## E.S.T.E.R. 1.4.7 — Domande e risposte da file

- Esporta tutte le domande aperte in un JSON da spiegare e compilare con ChatGPT.
- Importa le risposte con anteprima e conferma; checkpoint prima dell'apprendimento.
- Lascia aperte le risposte vuote, rinvia «Non lo so», chiude le domande obsolete.
- Rifiuta interamente file con risposte cambiate, già chiuse, sconosciute o duplicate.
- Archivia domande su aree eliminate e nasconde le relative proposte e modelli correnti.
- Non confonde sensori offline con sensori eliminati.
- «Dati non affidabili» è una diagnosi tecnica, non una domanda a cui rispondere.
- Shadow Mode permanente: nessuna attuazione e nessun invio a Gemini durante l'importazione.

Guida: docs/QUESTION_FILES.md. Aggiorna da HACS, riavvia Home Assistant e ricarica
la pagina E.S.T.E.R. La pulizia avviene alla successiva valutazione.

## E.S.T.E.R. 1.4.6 — Aggiornamento domande salvate

Le domande aperte ricevono le spiegazioni aggiornate anche quando la proposta
originale non viene più generata. Le vecchie domande generiche sul comfort
vengono archiviate quando è disponibile quella stagionale per la stessa stanza.
Le risposte già date sono conservate. Schede più leggibili, con spaziatura e testo
più grandi. Il nuovo testo appare dopo riavvio e successiva valutazione.

- Layout a una o due colonne con contrasto e dimensioni leggibili.
- Nome della stanza in evidenza nelle proposte e nelle domande.
- Proposte ripetute raggruppate nella vista senza cancellare il registro.
- Spiegazioni richiudibili e pulsante per passare alle domande.
- Configurazione avanzata e backup richiudibili con istruzioni per iniziare.
- Insegna non mostra dieci schede vuote; guida il primo insegnamento.
- Tutte le domande aperte sono accessibili: eliminato il limite invisibile di 20.
- Anteprima del pannello con soli dati dimostrativi in examples/panel-preview.html.

### Include il caricamento file 1.4.5

In INSEGNA puoi caricare più file TXT, Markdown o JSON ester-knowledge-v1.
Anteprima e conferma aggiungono le informazioni senza sostituire quelle esistenti.
Duplicati ignorati, fonte conservata e nessuna esecuzione delle automazioni descritte.
Vedi docs/KNOWLEDGE_FILES.md per il formato e i limiti.

### Include le correzioni 1.4.4

- Domande più chiare e dettagli tecnici richiudibili.
- Comfort proposto: 20 °C per riscaldamento/mezza stagione, 26 °C per raffrescamento. Punti di partenza modificabili, salvati solo dopo conferma e separati per stagione.
- La stagione segue la modalità heat/cool dell'impianto, altrimenti il calendario locale.
- «Non lo so» rinvia di sette giorni senza insegnare preferenze.
- Corretto un errore di sintassi del pannello nella 1.4.3.
- Corretti i pulsanti PARLA: trascrizione nel campo visibile, frasi accumulate, errori espliciti e controllo del testo prima dell'invio.
- Shadow Mode permanente: nessuna azione sui dispositivi.

Aggiornare da HACS e riavviare Home Assistant, poi ricaricare E.S.T.E.R. Le domande pertinenti vengono aggiornate alla successiva valutazione.

Usare DOMANDE per le preferenze guidate e INSEGNA per descrivere abitudini e verificare le proposte prima di salvarle. Le risposte libere alle domande restano note: non tutte diventano regole usate dai motori. Gemini e voce richiedono configurazione e non sono stati verificati dal vivo per questa release.

Richiede Home Assistant 2026.9.4 o successivo.
