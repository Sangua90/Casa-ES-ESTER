# Protezione della memoria E.S.T.E.R.

La memoria completa viene salvata tramite lo Store nativo di Home Assistant in
`/config/.storage/ester.storage`: note confermate, documenti originali, file ancora
da confermare, preferenze, domande, risposte, campioni, modelli e registri conservati.
Gli aggiornamenti dell'integrazione non rimuovono questi file.

Un backup Home Assistant che include la configurazione contiene anche questa
memoria. Il supporto nativo `backup.py` forza il salvataggio prima del backup.
La chiave Gemini resta nella configurazione Home Assistant, non nei rapporti JSON.

E.S.T.E.R. mantiene inoltre due generazioni complete in
`/config/.storage/ester.memory_backup`, con SHA-256 verificato durante il recupero.
Le copie vengono aggiornate dopo cambiamenti delle conoscenze/configurazioni/domande,
almeno ogni 24 ore mentre l'integrazione salva, e prima dei backup Home Assistant.
Se la memoria principale manca o è illeggibile, viene recuperata la prima copia
verificabile. Se sono presenti copie ma nessuna è valida, l'avvio fallisce senza
salvare una memoria vuota. Gli errori della copia locale sono visibili in Config.

Le copie locali proteggono da alcuni errori del file; non da guasti del disco,
furto o perdita dell'intera installazione. In Impostazioni → Sistema → Backup,
configura backup automatici con la configurazione inclusa e almeno una destinazione
esterna (cloud, NAS o altro dispositivo). Conserva anche il kit di emergenza della
cifratura. E.S.T.E.R. non può confermare che il tuo backup remoto funzioni senza
accedere alla tua installazione e verificare un ripristino.

Per ripristinare tutto, usa il normale ripristino del backup Home Assistant:
al successivo avvio E.S.T.E.R. ricarica la memoria dai file ripristinati.
Per una copia consultabile aggiuntiva, scarica il rapporto completo da Apprendimento.
Quel rapporto è diagnostico: non va caricato come file di note.

Nessuna cancellazione automatica delle conoscenze per limiti numerici; i limiti
del caricamento rifiutano nuove aggiunte senza cancellare le precedenti. Restano
limiti di conservazione per registri delle decisioni, feedback e campioni: questo
non è un archivio illimitato di ogni evento storico.

Riferimenti ufficiali:
- https://www.home-assistant.io/common-tasks/general/#backups
- https://developers.home-assistant.io/docs/core/platform/backup/
