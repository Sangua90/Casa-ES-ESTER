# Rapporto completo di memoria e apprendimento

Apri **Apprendimento** oppure **Config**, premi **SCARICA RAPPORTO COMPLETO**
e carica `ester-rapporto-apprendimento.json` nella chat in cui vuoi analizzarlo.
Non occorrono screenshot o il backup configurazione per le informazioni incluse.
Non è un file da importare: serve a valutare la situazione.

Il rapporto contiene versione, ultima valutazione, inventario completo corrente,
memoria, preferenze, classificazioni, routine, documenti caricati, domande anche
chiuse, feedback, registro decisioni conservato, campioni e modelli termici,
umidità/ventilazione, ACS e presenza, stato Recorder, anomalie, KPI, risultati
di replay e scenari quando disponibili. Le versioni della memoria sono elencate
come metadati; le copie annidate dei vecchi backup non vengono duplicate.
Sono i dati conservati da E.S.T.E.R., non l'intero database storico Home Assistant.

`assessment.knowledge_audit` distingue per ogni conoscenza:

- `mapping_applied`: identificativo energetico associato per la valutazione.
- `constraint_applied`: ha sospeso una proposta incompatibile.
- `context_only`: appare come riferimento, ma non è una regola implementata.
- `stored_not_used_in_current_evaluation`: conservata, non usata nella valutazione corrente.

La mappatura riporta conflitti, unità incompatibili e sensori non trovati. Non
modifica i registri Home Assistant o le classificazioni manuali. Solo gli ID
espliciti dei sensori FV reale, carichi, rete, SOC e potenza batteria possono
essere riconosciuti; nomi approssimativi e stime FV non diventano misure reali.
Associazioni ambigue rimangono da verificare.

I vincoli attualmente implementati riguardano il rischio di persone ferme nelle
valutazioni di spegnimento luci, la richiesta di ACS senza target fisso e le
modalità incompatibili quando è descritto un multisplit. Sono controlli
conservativi: ACS dinamica e identificazione dei gruppi multisplit non sono
ottimizzatori completi. Per un multisplit non ancora mappato, la presenza di
heat/cool differenti provoca una sospensione prudenziale da verificare.
Gli altri racconti restano contesto, senza generare codice o servizi eseguibili.
Le note confermate nella categoria Altro vengono ora riconosciute per argomento
anche senza etichette JSON, con riferimenti al file di origine nelle decisioni.
Le stanze nominate nel testo vengono confrontate con le aree disponibili; un
paragrafo che mescola più stanze non viene trasferito automaticamente a una sola.
Questo riconoscimento usa termini espliciti, non un interprete generale di tutte
le condizioni. Le note in anteprima continuano a essere escluse.
Nessun valore di confidence viene aumentato per la sola presenza di una nota.

Apri **Memoria considerata** nelle proposte per vedere i riferimenti e capire
se hanno applicato un vincolo o sono soltanto contesto. La stessa logica opera
negli scenari e nel replay. Le conoscenze in anteprima non vengono usate finché
non confermi. Lo scope temporaneo delle vecchie risposte viene conservato;
senza una scadenza esplicita non viene inventata una durata.

L'export non include le opzioni della Config Entry, le credenziali Gemini o i
token Home Assistant. Include però i testi e i documenti che hai insegnato:
eventuali dati privati scritti da te possono comparire nel rapporto. Il download
è locale e non invia dati a un provider AI; la successiva condivisione è una tua scelta.

Non fornisce una percentuale generica di prontezza: conteggi, modelli e risultati
Shadow sono prove diverse. Un esito osservato non dimostra l'effetto causale
di un'azione che E.S.T.E.R. non ha eseguito. Nessun rapporto abilita l'attuazione:
questa versione rimane permanentemente in Shadow Mode.

## Barra e sezioni

CORE e Apprendimento mostrano la percentuale dei sette requisiti espliciti
verificati nella checklist. Tutti hanno lo stesso peso: è un conteggio, non
una probabilità di successo, una percentuale di intelligenza o una stima dei
giorni mancanti. Espandi la lista per vedere le condizioni. Anche zero domande
aperte non completa la checklist. Il requisito del controllo reale resta
non verificato in questa versione e richiede sviluppo, test e autorizzazione:
la barra non abilita mai i dispositivi.

La qualità secondo i feedback è mostrata separatamente, con il numero di
valutazioni. L'efficienza reale resta non misurabile: occorreranno azioni reali,
consumi misurati e una baseline appropriata, non la sola confidence.

Le operazioni quotidiane sono raccolte in **Domande e richieste** (scarica
il file, rispondi con ChatGPT, importa con anteprima e conferma) e **Insegna**
(CARICA conserva i documenti; CONFERMA E RICORDA attiva le conoscenze).
Le altre pagine mostrano dati e percentuali con il loro significato; i comandi
di simulazione e configurazione rimangono nei dettagli/impostazioni avanzati.
L'export delle domande include anche il contesto diagnostico delle lacune e
dei sensori. Le risposte importabili rimangono quelle con question_id e
fingerprint: il contesto diagnostico non si trasforma in una regola.
