## E.S.T.E.R. 1.6.0 — Cervello, memoria condivisa ed esperienze

- CERVELLO è la pagina iniziale: domande, file, insegnamenti, note aggiornabili, memoria conservata e previsioni nello stesso punto. Il menu principale contiene Cervello, Decisioni e CORE; le sezioni specialistiche sono nei dettagli.
- Memoria di lavoro comune per valutazioni correnti, replay e scenari. Note a scadenza, aggiornamenti con storico, valori operativi di comfort/costo energia, provenienza nelle decisioni e gestione dei conflitti.
- JSON v2 consente effetti espliciti e validati; TXT, Markdown e JSON v1 restano compatibili. Raccolta e ricevute distinguono file conservati e conoscenze attive.
- Le domande di comfort già coperte dalla memoria si risolvono; una nota temporanea scaduta può riaprire il dubbio.
- Riscontri Corretta/Parziale/Sbagliata alimentano una memoria duratura delle esperienze. I precedenti vengono confrontati con situazioni simili; le proposte con fiducia alta restano candidati da verificare.
- Crescita descritta da conteggi reali, modelli, esperienze e tempi misurati. Ricerca del contesto AI nell'intera memoria valida, con budget, senza taglio alle ultime 40 note.

La pagina mostra anche quando un'informazione è solo contesto. Non interpreta
automaticamente ogni frase come una regola e non dimostra intelligenza superiore
o risparmio reale. Previsioni e proposte restano locali e dipendono dai dati.
Shadow Mode invariato, nessuna attuazione fisica. [Dettagli](CERVELLO.md).
Aggiorna da HACS, riavvia Home Assistant e ricarica il pannello E.S.T.E.R.

## E.S.T.E.R. 1.5.3 — Memoria nelle decisioni correnti

- Le note confermate in Altro (TXT, Markdown e testo libero) vengono collegate agli argomenti pertinenti senza riscrivere la memoria.
- Riferimenti espliciti ai sensori energetici utilizzabili anche dalle note non etichettate.
- Informazioni sulla presenza immobile in una stanza possono sospendere una proposta di spegnimento, con controlli su stanza e negazioni.
- Le decisioni mostrano la memoria considerata e il dubbio residuo quando la nota resta solo contesto.
- La pagina Decisioni si aggiorna con le nuove valutazioni senza ricostruire il menu o perdere i dettagli aperti.

Questo migliora il collegamento memoria/valutazione, ma non è un interprete generale
di ogni abitudine o eccezione. Una nota di comfort non diventa automaticamente un
setpoint stagionale; restano necessari preferenze strutturate e dati verificati.
Shadow Mode invariato, senza attuazioni o nuove chiamate AI automatiche.
Aggiorna da HACS, riavvia Home Assistant e ricarica E.S.T.E.R.

## E.S.T.E.R. 1.5.2 — CORE compatto su iPhone

- CORE mantiene il nucleo Jarvis, la barra di preparazione e solo le ultime due decisioni, ordinate per data.
- Rimossi da CORE Insegna e Previsione casa; le altre pagine rimangono disponibili.
- Schede compatte con stanza, proposta, confidence e motivazione apribile al tocco; collegamento Vedi tutte.
- Barra sempre visibile anche in attesa della prima valutazione, con requisiti verificati e dettagli su cosa manca. Non è un conto alla rovescia alla fine dello Shadow Mode.
- Aggiornamento delle ultime decisioni senza ricostruire il nucleo animato.
- Versione nel collegamento del pannello per evitare di riutilizzare la grafica in cache dopo l'aggiornamento.
- Shadow Mode permanente e protezione della memoria invariati.

Aggiornare da HACS e riavviare Home Assistant.

## E.S.T.E.R. 1.5.1 — File di note e salvataggio semplice

- Insegna contiene Note per E.S.T.E.R. e un modello JSON da far compilare a ChatGPT.
- Per i file: CARICA, controllo automatico del formato e SALVA NELLA MEMORIA. Il contenuto non viene mostrato. I file pendenti possono essere salvati direttamente dalla raccolta anche dopo aver riaperto il pannello.
- Le risposte alle domande seguono lo stesso flusso, senza anteprima del contenuto. La validazione resta atomica e il salvataggio separato.
- Domande e richieste raccoglie lacune, associazioni ambigue, regole da verificare e strumenti amministrativi. Configurazione diventa un riepilogo consultabile.
- Il file delle domande comprende anche lacune della conoscenza e audit delle regole, come contesto informativo per ChatGPT.
- Ogni conoscenza attiva compare nell'audit: una regola salvata o usata solo come contesto rimane da verificare. La checklist comprende questa verifica, dati mancanti, domande differite e tutti i modelli disponibili.
- Protezione memoria: due copie locali complete con integrità verificata, recupero automatico e salvataggio prima dei backup nativi Home Assistant. Nessuna cancellazione delle conoscenze più vecchie per limiti numerici. Guida: docs/MEMORY_BACKUP.md.
- Nessun controllo reale: la checklist non certifica la piena preparazione operativa, gli ottimizzatori completi e la conversione generalizzata delle regole restano da sviluppare. Efficienza reale non misurabile in Shadow Mode.

Aggiornare da HACS, riavviare Home Assistant e ricaricare il pannello.

## E.S.T.E.R. 1.5.0 — Rapporto completo e memoria nelle valutazioni Shadow

- In Apprendimento e Config: SCARICA RAPPORTO COMPLETO con memoria, inventario, modelli, campioni, domande, feedback, esiti Shadow e audit delle conoscenze.
- Il rapporto distingue memoria salvata, contesto considerato, associazioni applicate e vincoli che hanno sospeso una proposta. Non inventa una percentuale di prontezza.
- Usa gli identificativi energetici espliciti nelle memorie confermate solo con unità compatibili, senza ambiguità e senza sovrascrivere classificazioni manuali.
- Sospende lo spegnimento basato sull'assenza di movimento quando la memoria segnala persone ferme o addormentate.
- Sospende il piano ACS fisso se la memoria richiede ACS adattiva; non inventa un target. L'ottimizzatore dinamico completo resta da sviluppare.
- Richiede verifica del gruppo multisplit quando la memoria segnala incompatibilità e sono osservate modalità heat/cool diverse.
- Memoria considerata visibile nelle proposte; applicata anche in scenari e replay. Risposte raggruppate nel dominio corretto in Insegna.
- CORE e Apprendimento mostrano una barra dei requisiti verificati con elenco di ciò che manca, qualità dei feedback separata ed efficienza reale non ancora misurabile. Nessuna attivazione automatica.
- Operazioni quotidiane in Domande e richieste e Insegna; simulazioni nei dettagli tecnici.
- Shadow Mode permanente: nessuna attuazione, nessun invio AI nell'esportazione.

Guida: docs/LEARNING_REPORT.md. Aggiornare da HACS, riavviare Home Assistant e ricaricare il pannello.

## E.S.T.E.R. 1.4.9 — Raccolta file e salvataggio visibile

- CARICA conserva subito i documenti in Home Assistant; il 100% appare solo dopo la conferma del backend.
- Raccolta persistente con numero, nomi, dimensioni, data e stato di ciascun file.
- Anteprime da confermare recuperabili anche dopo riapertura della pagina.
- AGGIUNGI ALTRI FILE consente caricamenti successivi senza perdere la raccolta.
- Duplicati identificati dal contenuto; nomi alternativi conservati, file omonimi distinti.
- Testo non inviato e posizione del menu conservati durante aggiornamenti della raccolta.
- Nessuna attuazione: le conoscenze diventano attive solo dopo CONFERMA E RICORDA.

Verifiche: upload HTTP autenticato, salvataggio prima della conferma, riapertura
del pannello e recupero anteprima in WebKit con profilo iPhone 13, errori e retry.
Nessuna verifica sull'impianto domestico o su iPhone fisico.
Aggiorna da HACS, riavvia Home Assistant e ricarica E.S.T.E.R.

## E.S.T.E.R. 1.4.8 — Caricamento reale in INSEGNA

- Selezione di uno o più file, elenco visibile e pulsante CARICA.
- Upload multipart autenticato in Home Assistant, progresso e messaggi di errore.
- Documenti persistenti, anteprima e conferma nella pipeline di conoscenza esistente.
- File omonimi senza sovrascritture; ricaricamenti senza conoscenze duplicate.
- Selezione conservata dopo errori e menu mobile stabile durante aggiornamenti HA.
- Shadow Mode invariato: nessuna attuazione fisica e nessun invio AI durante upload.

Verificato su Home Assistant 2026.9.4 con upload HTTP, autenticazione, conferma,
ricaricamento dello storage e browser WebKit con profilo iPhone 13.
La verifica non è stata eseguita sull'impianto domestico né su un iPhone fisico.
Aggiorna da HACS, riavvia Home Assistant e ricarica E.S.T.E.R.
Formati e limiti: docs/KNOWLEDGE_FILES.md.

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
