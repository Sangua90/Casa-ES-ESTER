# Aggiungere informazioni senza sostituire la memoria

In **INSEGNA → Aggiungi conoscenze da file**, scegli uno o più file,
premi **MOSTRA ANTEPRIMA**, controlla i punti e premi **CONFERMA E RICORDA**.
Non usare **Importa memoria**, che serve a ripristinare un backup.

La lettura dei file è locale. Le informazioni confermate entrano nella conoscenza
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

Per una nuova chat: «Trasforma le mie descrizioni in uno o più file JSON
ester-knowledge-v1 seguendo docs/KNOWLEDGE_FILES.md del repository
Sangua90/Casa-ES-ESTER. Conserva condizioni ed eccezioni. Non inventare dettagli,
non generare un backup e non sostituire preferenze esistenti.»
