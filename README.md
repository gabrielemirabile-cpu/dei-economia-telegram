# Avvisi Economia (L-33) → Telegram

Bot che pubblica su un gruppo o canale Telegram i nuovi avvisi del **Corso di laurea in Economia (L-33)**
dell'Università di Catania, con testo completo, data, categoria e allegati.

Gira gratis su **GitHub Actions** ogni 5 minuti, 24 ore su 24, senza PC acceso, senza AI e senza servizi a pagamento.

## Come funziona

1. Ogni 5 minuti legge le due pagine già filtrate per Economia dal sito del Dipartimento:
   - https://www.dei.unict.it/corsi/l-33/avvisi (avvisi del corso)
   - https://www.dei.unict.it/corsi/l-33/avvisi-docente (avvisi dei docenti)
2. Confronta gli avvisi con `seen.json` (quelli già inviati). Lo stesso avviso presente in entrambe le pagine
   viene riconosciuto dall'id interno del sito (`/node/12345`) e inviato una volta sola.
3. Per ogni avviso nuovo apre la pagina, estrae il testo completo e i link (PDF di bandi, ecc.) e lo manda su Telegram.
4. Salva `seen.json` nel repository, così non reinvia mai due volte la stessa notizia.
5. Alla **prima esecuzione** non invia nulla: segna come già visti gli avvisi presenti, per non inondare il gruppo.
   Da lì in poi invia solo le novità.

Formato del messaggio:

```
📌 Seduta di laurea straordinaria AA 26/27
Sabato, 3 Ottobre, 2026 · Altro (didattica) · Avvisi del corso

Clicca qui per leggere l'avviso.

🔗 Leggi sul sito
📎 Avviso dicembre aa2627.pdf
```

## Installazione (circa 15 minuti)

### 1. Crea il bot Telegram
1. Su Telegram apri **@BotFather**, scrivi `/newbot`, scegli nome e username.
2. BotFather ti dà un **token** (tipo `123456789:AAH...`). Tienilo segreto.

### 2. Aggiungi il bot al gruppo o canale
- **Gruppo**: aggiungi il bot come membro. Se non riesce a leggere i messaggi non importa, deve solo scrivere.
- **Canale**: aggiungi il bot come **amministratore** con il permesso "Pubblica messaggi".

### 3. Trova l'id della chat
- Canale pubblico: basta `@nomecanale`.
- Gruppo o canale privato: scrivi un messaggio nel gruppo (o pubblica un post nel canale), poi apri nel browser
  `https://api.telegram.org/bot<TOKEN>/getUpdates` e cerca `"chat":{"id":-100...}`. L'id è quel numero negativo.
  Se non vedi nulla, rimuovi e riaggiungi il bot e riprova.

### 4. Crea il repository su GitHub
1. Su GitHub crea un repository **pubblico** (i repository pubblici hanno minuti di Actions illimitati e gratuiti;
   con uno privato i 2.000 minuti mensili gratuiti non bastano per un controllo ogni 5 minuti).
   Il token non finisce nel codice, quindi il repo pubblico non è un problema.
2. Carica tutti i file di questa cartella (anche la cartella nascosta `.github`).

   Da terminale, dentro questa cartella:
   ```bash
   git init && git add -A && git commit -m "Bot avvisi Economia" && git branch -M main
   git remote add origin https://github.com/<tuo-utente>/<nome-repo>.git
   git push -u origin main
   ```

### 5. Imposta i segreti
Nel repository: **Settings → Secrets and variables → Actions → New repository secret**. Crea:

| Nome | Valore |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | il token di BotFather |
| `TELEGRAM_CHAT_ID` | l'id del gruppo/canale (es. `-1001234567890` o `@nomecanale`) |
| `ADMIN_CHAT_ID` | (facoltativo) il tuo id personale: ricevi un messaggio se lo scraping fallisce |

Per il tuo id personale: scrivi al bot in privato, poi guarda `getUpdates` come sopra (id positivo).

### 6. Attiva e prova
1. Scheda **Actions** del repository → se chiede conferma, abilita i workflow.
2. Apri il workflow "Avvisi Economia → Telegram" → **Run workflow**. La prima esecuzione segna gli avvisi
   esistenti come già visti e non invia nulla (vedi log).
3. Da quel momento parte da solo ogni 5 minuti. Al prossimo avviso pubblicato sul sito arriva il messaggio.

## Provare l'invio subito (senza aspettare un avviso nuovo)

Dalla scheda **Actions** → "Avvisi Economia → Telegram" → **Run workflow** → nel campo *resend* metti ad esempio `2`:
invia i 2 avvisi più recenti nel gruppo anche se già visti, senza toccare `seen.json`.

Oppure in locale, con Python 3.9 o superiore:

```bash
pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python bot.py --resend 3
```

Invia i 3 avvisi più recenti anche se già visti, senza toccare `seen.json`.
Con `--dry-run` stampa i messaggi a schermo senza inviare nulla:

```bash
python bot.py --dry-run --resend 3
```

## Replicare sul canale di un'altra persona

Basta un secondo repository (o un fork) con i propri segreti `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
Lo stesso bot può pubblicare su più canali, ma ogni repository tiene il proprio `seen.json`.

Per un **altro corso di laurea** cambia le due URL in `SOURCES` dentro `bot.py` (es. `l-18` al posto di `l-33`).

## Test automatici

```bash
pip install -r requirements.txt pytest
python -m pytest tests
```

I test usano copie delle pagine del sito salvate in `tests/fixtures`, quindi non dipendono dalla rete.

## Cose da sapere

- **Ritardi**: il cron di GitHub può partire con qualche minuto di ritardo nelle ore di punta. Per avvisi universitari è irrilevante.
- **Se il sito cambia struttura**: il bot smette di trovare avvisi, l'esecuzione risulta fallita (rossa) nella scheda Actions
  e, se hai impostato `ADMIN_CHAT_ID`, ricevi un messaggio di errore. Vanno aggiornati i selettori in `parse_list` o `parse_article`.
- **Inattività**: GitHub disattiva i workflow programmati se il repository non ha attività per 60 giorni. Il bot stesso
  fa un commit a ogni avviso nuovo, quindi in pratica non succede. Se dovesse succedere, nella scheda Actions compare
  un pulsante per riattivarlo.
- **Limiti Telegram**: massimo 4096 caratteri a messaggio. Gli avvisi più lunghi vengono tagliati con "[…]" e resta
  sempre il link "Leggi sul sito". Il bot aspetta 1 secondo tra un messaggio e l'altro per rispettare i limiti dei canali.
- **Carico sul sito**: 2 richieste ogni 5 minuti, più una per ogni avviso nuovo. Trascurabile.
