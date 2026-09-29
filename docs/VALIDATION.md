# Collaudo V1

## Automazione
La workflow GitHub installa Home Assistant 2026.9.4 su Python 3.14/Linux, verifica sintassi e nomi non definiti ed esegue unittest.
I test coprono unità, classificazione, scadenze/fuso, regressione con lacune, presenza pesata, motori, vincoli dati mancanti, feedback e assenza di chiamate di attuazione.
Gli smoke test usano HomeAssistant reale per registri, stati, servizi e storage; le query Recorder sono simulate per verificare normalizzazione e firme API senza accedere al database dell'utente.
Non vengono effettuate richieste Gemini reali.

## Dopo l'installazione nella casa
1. Verificare che Status sia shadow e real_actuation_enabled sia false.
2. Verificare le sei entità del dispositivo e adattare gli ID nella dashboard.
3. Consultare ester.get_summary: controllo aree, history.status e presenza di domande.
4. Se Recorder è assente/esclude entità, verificare che E.S.T.E.R. continui ad aggiornarsi con dati live.
5. Associare esplicitamente FV/consumo/accumulo; verificare unità e perimetro dei contatori prima di interpretare un surplus.
6. Aggiungere un contesto breve, verificarne l'effetto e la scadenza; provare la rimozione.
7. Dare feedback usando un ID reale e verificare la persistenza dopo un riavvio.
8. Verificare che contatori, luci, valvole, setpoint e allarmi non siano stati modificati da E.S.T.E.R.
9. Solo se desiderato, configurare Gemini e richiedere una spiegazione. Disabilitarlo e verificare il fallback locale.

Un esito positivo dei test software non dimostra accuratezza delle previsioni nella casa: questa versione produce trend descrittivi e proposte da validare.
