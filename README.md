# Appunti Lezioni

Programma per Windows che, mentre scorre una videolezione, registra l'audio del PC, lo trascrive in locale (Whisper) e a fine lezione fa scrivere a Claude gli appunti in Word, nello stile scelto. Ogni corso ha la sua **dispensa a capitoli**, che si aggiorna da sola, e ogni lezione può avere i suoi **materiali** (slide, PDF, PowerPoint, Word, foto), usati per correggere nomi e termini.

## Installazione
1. Scarica l'ultima release e scompattala in `Documenti\appunti_lezioni`.
2. Doppio clic su `installa.bat`: installa Python e le librerie, crea i collegamenti e fa una prova automatica.
3. Apri **Appunti Lezioni** dal Desktop e inserisci la chiave API di Claude nelle Impostazioni.

## Aggiornamenti
Il programma controlla le release di questo repository una volta al giorno e propone "Aggiorna ora". Prima di installare, la nuova versione viene verificata; la versione precedente resta disponibile in Impostazioni → "Torna alla versione precedente". Appunti, dispense, materiali e impostazioni non vengono mai toccati.

## File
| File | Contenuto |
|---|---|
| `app.py` | Interfaccia (customtkinter) |
| `core.py` | Configurazione, registrazione audio, trascrizione, chiamata a Claude, Word |
| `corsi.py` | Lezioni, materiali, dispensa |
| `materiali.py` | Lettura di PDF/PPTX/DOCX/foto, termini chiave per Whisper |
| `sistema.py` | Funzioni Windows: avvio automatico, collegamenti, isolamento audio |
| `aggiornamenti.py` | Aggiornamenti dalle release GitHub |
| `autotest.py` | Prova automatica con voce sintetica |

La chiave API e i dati restano solo sul PC (`%APPDATA%\AppuntiLezioni` e `Documenti\Appunti lezioni`).
