"""
Appunti Lezioni – aggiornamenti dal repository GitHub.

Come funziona:
  1. controlla() legge versione.json dal repository GitHub (pubblico, senza password).
  2. installa() scarica la nuova versione in una cartella temporanea e la VERIFICA prima di toccare
     nulla: compila tutti i file e prova a importare i moduli con il Python del programma.
  3. Solo se la verifica passa: copia di sicurezza della versione attuale in _versione_precedente,
     sostituzione dei file del programma, installazione delle librerie se requirements.txt è cambiato.
  4. ripristina_precedente() rimette la copia di sicurezza (pulsante in Impostazioni).

Non vengono mai toccati: appunti, dispense, materiali, configurazione e chiave API
(stanno in Documenti\\Appunti lezioni e in %APPDATA%\\AppuntiLezioni).
"""

import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import core
from core import APP_DIR, log

ESTENSIONI = {".py", ".bat", ".txt", ".md"}
ESCLUSI = {"config.json", "autotest_risultato.txt", "installazione.log", "appunti_lezioni.log"}
BACKUP = APP_DIR / "_versione_precedente"
UA = {"User-Agent": "AppuntiLezioni", "Accept": "application/vnd.github+json"}


def versione_tupla(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3]) or (0,)


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def controlla(repo, ramo="main"):
    """
    Legge versione.json dal repository GitHub. Restituisce None se non ci sono novità, altrimenti
    {versione, note, url_zip, pagina}. Solleva eccezioni in caso di problemi di rete.
    """
    if not repo:
        raise RuntimeError("Aggiornamenti non ancora configurati.")
    dati = json.loads(_get(f"https://raw.githubusercontent.com/{repo}/{ramo}/versione.json"))
    versione = str(dati.get("versione", "")).lstrip("vV")
    if versione_tupla(versione) <= versione_tupla(core.APP_VERSIONE):
        return None
    note = dati.get("note", "")
    if isinstance(note, list):
        note = "\n".join(f"- {n}" for n in note)
    return {"versione": versione, "note": note.strip(),
            "url_zip": f"https://github.com/{repo}/archive/refs/heads/{ramo}.zip",
            "pagina": f"https://github.com/{repo}"}


def _file_programma(cartella):
    return [p for p in Path(cartella).iterdir()
            if p.is_file() and p.suffix.lower() in ESTENSIONI and p.name not in ESCLUSI]


def _python_programma():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        exe = exe.with_name("python.exe")
    return str(exe)


def _nascosto():
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def installa(info, avanzamento=lambda msg: None):
    """Scarica, verifica e installa la nuova versione. Restituisce la nuova versione."""
    avanzamento("Scarico la nuova versione…")
    contenuto = _get(info["url_zip"], timeout=120)
    tmp = Path(tempfile.mkdtemp(prefix="aggiornamento_"))
    with zipfile.ZipFile(io.BytesIO(contenuto)) as z:
        z.extractall(tmp)
    radice = next((p.parent for p in tmp.rglob("app.py")), None)
    if radice is None:
        raise RuntimeError("Il pacchetto scaricato non contiene il programma.")
    nuovi = _file_programma(radice)

    avanzamento("Controllo che la nuova versione funzioni…")
    prova = subprocess.run(
        [_python_programma(), "-c",
         "import sys, py_compile, glob; sys.path.insert(0, sys.argv[1]);"
         "[py_compile.compile(f, doraise=True) for f in glob.glob(sys.argv[1] + '/*.py')];"
         "import core, corsi, materiali, sistema, app; print(core.APP_VERSIONE)", str(radice)],
        capture_output=True, text=True, timeout=180, cwd=str(radice), **_nascosto())
    if prova.returncode != 0:
        log("Verifica aggiornamento fallita:\n" + prova.stdout + prova.stderr)
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("La nuova versione non ha superato il controllo: l'aggiornamento è stato annullato "
                           "e il programma resta com'è.")

    req_nuovo = (radice / "requirements.txt").read_text(encoding="utf-8") if (radice / "requirements.txt").exists() else ""
    req_attuale = (APP_DIR / "requirements.txt").read_text(encoding="utf-8") if (APP_DIR / "requirements.txt").exists() else ""

    avanzamento("Salvo una copia della versione attuale…")
    if BACKUP.exists():
        shutil.rmtree(BACKUP, ignore_errors=True)
    BACKUP.mkdir()
    for p in _file_programma(APP_DIR):
        shutil.copy2(p, BACKUP / p.name)
    (BACKUP / "VERSIONE").write_text(core.APP_VERSIONE, encoding="utf-8")

    if req_nuovo.strip() != req_attuale.strip():
        avanzamento("Installo le nuove librerie (qualche minuto)…")
        r = subprocess.run([_python_programma(), "-m", "pip", "install", "-r", str(radice / "requirements.txt")],
                           capture_output=True, text=True, timeout=1800, **_nascosto())
        if r.returncode != 0:
            log("pip install fallito:\n" + r.stdout[-3000:] + r.stderr[-3000:])
            raise RuntimeError("Non sono riuscito a installare le librerie della nuova versione. "
                               "Il programma resta com'è.")

    avanzamento("Installo la nuova versione…")
    for p in nuovi:
        shutil.copy2(p, APP_DIR / p.name)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"Aggiornato dalla versione {core.APP_VERSIONE} alla {info['versione']}.")
    return info["versione"]


def versione_precedente():
    v = BACKUP / "VERSIONE"
    return v.read_text(encoding="utf-8").strip() if v.exists() else None


def ripristina_precedente():
    if not versione_precedente():
        raise RuntimeError("Non c'è una versione precedente da ripristinare.")
    for p in _file_programma(BACKUP):
        shutil.copy2(p, APP_DIR / p.name)
    v = versione_precedente()
    log(f"Ripristinata la versione precedente ({v}).")
    return v


def riavvia(argomenti=()):
    """Avvia una nuova istanza del programma (la vecchia deve chiudersi subito dopo)."""
    import sistema
    cmd = sistema.comando_avvio() + list(argomenti)
    subprocess.Popen(cmd, cwd=str(APP_DIR), close_fds=True, **_nascosto())
