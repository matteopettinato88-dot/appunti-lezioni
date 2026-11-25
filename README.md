# Appunti Lezioni

Programma per **macOS** che, mentre scorre una videolezione, registra l'audio del Mac, lo trascrive in locale (Whisper) e a fine lezione fa scrivere a Claude gli appunti in Word, nello stile scelto. Ogni corso ha la sua **dispensa a capitoli**, che si aggiorna da sola, e ogni lezione può avere i suoi **materiali** (slide, PDF, PowerPoint, Word, foto), usati per correggere nomi e termini.

Dalla versione 4 il programma funziona solo su Mac (macOS 13 Ventura o successivo).

## Installazione
Apri il **Terminale** (⌘ Spazio, «Terminale») e incolla:

```
curl -fsSL https://raw.githubusercontent.com/matteopettinato88-dot/appunti-lezioni/main/installa.sh | bash
```

Lo script installa, se mancano, gli Strumenti da riga di comando di Apple e Python 3.14 (chiede la password del Mac), poi il programma, le librerie e l'app **Appunti Lezioni** in Applicazioni, e fa una prova automatica.

Al primo uso macOS chiede alcuni permessi:
- **Registrazione schermo e audio di sistema**: serve per registrare l'audio della lezione (lo schermo non viene registrato). Si attiva in Impostazioni di Sistema → Privacy e sicurezza, poi si riapre il programma.
- **Cartella Documenti**: lì vengono salvati gli appunti.

Per rifare solo la prova automatica: `curl -fsSL …/installa.sh | bash -s prova`.

## Uso
Apri **Appunti Lezioni** da Launchpad o Spotlight e inserisci la chiave API di Claude nelle Impostazioni. Chiudere la finestra non chiude il programma: si riapre con un clic sull'icona nel Dock; per uscire ⌘Q.

Con «Registra solo la lezione» viene registrato solo l'audio di browser (Safari, Chrome, Firefox, Edge, Arc…) e app di videoconferenza (Zoom, Teams, Webex…): musica, notifiche e altri suoni restano fuori.

## Aggiornamenti
Il programma legge `versione.json` da questo repository una volta al giorno e, se trova un numero più alto, propone "Aggiorna ora". Per pubblicare una versione: aggiornare `APP_VERSIONE` in `core.py` e `versione.json` (numero e novità), poi caricare su `main`. Prima di installare, la nuova versione viene verificata; la versione precedente resta disponibile in Impostazioni → "Torna alla versione precedente". Appunti, dispense, materiali e impostazioni non vengono mai toccati.

## File
| File | Contenuto |
|---|---|
| `app.py` | Interfaccia (customtkinter) |
| `core.py` | Configurazione, registrazione audio, trascrizione, chiamata a Claude, Word |
| `corsi.py` | Lezioni, materiali, dispensa |
| `materiali.py` | Lettura di PDF/PPTX/DOCX/foto, termini chiave per Whisper |
| `sistema.py` | Funzioni macOS: app, apertura all'accesso, permessi, notifiche, PDF |
| `cattura_audio.swift` | Cattura dell'audio del Mac con ScreenCaptureKit (compilato sul Mac) |
| `avvio_app.swift` | Eseguibile di Appunti Lezioni.app, che avvia il programma Python |
| `aggiornamenti.py` | Aggiornamenti dal repository GitHub |
| `autotest.py` | Prova automatica con la voce sintetica del Mac |
| `installa.sh` | Installazione |

Il programma sta in `~/Library/Application Support/AppuntiLezioni/programma`; configurazione, chiave API e registro in `~/Library/Application Support/AppuntiLezioni`; appunti e dispense in `Documenti/Appunti lezioni`.
