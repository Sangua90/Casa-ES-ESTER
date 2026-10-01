# Aggiungere informazioni senza sostituire la memoria

In **INSEGNA → Aggiungi conoscenze da file**, scegli uno o più file,
controlla l'elenco dei file selezionati e premi **CARICA**. La barra mostra il
trasferimento; al 100% attendi la validazione in Home Assistant. Poi controlla
i punti nell'anteprima e premi **CONFERMA E RICORDA**.
Non usare **Importa memoria**, che serve a ripristinare un backup.

I file vengono inviati al backend Home Assistant tramite upload autenticato,
riservato agli amministratori. Il caricamento conserva i documenti nella proposta
persistente e salva subito tutti gli originali nella memoria locale
`knowledge_documents`, identificati dall'impronta del contenuto, senza usare il
nome come percorso su disco. Le proposte in attesa sono limitate alle ultime 20.
La raccolta conserva fino a 1000 contenuti distinti e mostra nomi, dimensioni,
data, conoscenze collegate e stato. Un file salvato non è ancora conoscenza attiva:
premi VEDI ANTEPRIMA E CONFERMA anche dopo aver riaperto la pagina.
I file restano nella raccolta se scarti l'anteprima; per riproporre un'anteprima
scartata o non più nelle ultime 20, carica nuovamente il file.
AGGIUNGI ALTRI FILE permette di selezionare il gruppo successivo.
Gli originali sono conservati nello storage locale, mentre l'esportazione portabile
della memoria contiene le conoscenze estratte con la loro fonte.
Il caricamento non invia documenti al provider AI. Le informazioni confermate entrano nella conoscenza
usata come contesto dal provider AI configurato durante gli insegnamenti successivi.
Non vengono eseguite automazioni né modificate preferenze numeriche o mappature.
Non tutte le note sono già utilizzate dai motori decisionali deterministici.

Puoi caricare TXT o Markdown UTF-8, separando le informazioni con una riga vuota.
Ogni paragrafo viene conservato per intero come informazione nella categoria Altro.
Per categorie specifiche usa JSON:

```json
{
  "format": "ester-knowledge-v1",
  "items": [
    {
      "domain": "lighting",
      "kind": "habit",
      "statement": "Le luci esterne servono quando rientriamo dopo il tramonto."
    },
    {
      "domain": "climate",
      "kind": "exception",
      "statement": "Quando ci sono ospiti, gli orari abituali possono cambiare."
    }
  ]
}
```

Campi: `statement` obbligatorio; `domain`, `kind` e `area_id` facoltativi.
Non inventare gli identificativi delle stanze: ometti `area_id` se non lo conosci.
Argomenti: presence, climate, lighting, hot_water, energy, ventilation, security,
appliances, rooms, other. Tipi: preference, habit, rule, exception, temporary,
constraint, fact, goal. Il tipo è un'etichetta descrittiva, non un comando.

Limiti: 5 file per caricamento, 32 KB per file e 64 KB totali, 100 informazioni
per caricamento, 1000 caratteri per informazione. Un file non valido annulla
l'intera anteprima. Nessun testo viene tagliato silenziosamente.

I duplicati con stesso testo normalizzato, argomento e stanza sono ignorati anche
tra caricamenti diversi. Testi diversi, anche contraddittori, rimangono distinti:
non sostituiamo automaticamente informazioni precedenti. Nome e impronta del file
sono conservati per risalire alla fonte. Se non c'è spazio entro il limite di
1000 conoscenze, l'aggiunta viene rifiutata senza cancellare quelle esistenti.

File omonimi con contenuto diverso possono essere caricati insieme. Ricaricare
lo stesso file, anche rinominato, non duplica le informazioni. Informazioni nuove
in un file con nome già usato vengono aggiunte dopo conferma. Un errore conserva
la selezione per riprovare; una disconnessione non aggiunge conoscenze attive.
Gli originali e le conoscenze confermate rimangono dopo il riavvio.

Per una nuova chat: «Trasforma le mie descrizioni in uno o più file JSON
ester-knowledge-v1 seguendo docs/KNOWLEDGE_FILES.md del repository
Sangua90/Casa-ES-ESTER. Conserva condizioni ed eccezioni. Non inventare dettagli,
non generare un backup e non sostituire preferenze esistenti.»
