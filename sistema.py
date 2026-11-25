"""
Appunti Lezioni – funzioni legate a macOS: app in ~/Applications, apertura all'accesso, programma di
cattura audio (ScreenCaptureKit), permessi, notifiche, PDF, istanza unica, apertura file.

Questa versione funziona solo su macOS. L'errore all'importazione su altri sistemi fa fallire la
verifica degli aggiornamenti su un vecchio PC Windows, che resta così alla versione 3.x.
(Per provare il codice su Linux: APPUNTI_TEST=1.)
"""

import hashlib
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

if sys.platform != "darwin" and not os.environ.get("APPUNTI_TEST"):
    raise ImportError("Questa versione di Appunti Lezioni funziona solo su macOS.")

from core import APP_DIR, APP_NOME, APP_VERSIONE, log

PORTA_ISTANZA = 47651
BUNDLE_ID = "it.appuntilezioni.app"
APP_BUNDLE = Path(os.environ.get("APPUNTI_APP") or Path.home() / "Applications" / f"{APP_NOME}.app")
BIN = APP_DIR / "bin"
HELPER = BIN / "cattura-audio"
SORGENTE_HELPER = APP_DIR / "cattura_audio.swift"
SORGENTE_APP = APP_DIR / "avvio_app.swift"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "it.appuntilezioni.avvio.plist"
PANNELLO_PERMESSO = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
MSG_STRUMENTI = ("Mancano gli Strumenti da riga di comando di Xcode (servono a preparare il programma). "
                 "Apri il Terminale, scrivi:  xcode-select --install  e premi Invio, poi riapri il programma.")


def apri(path):
    subprocess.Popen(["/usr/bin/open", str(path)])


def comando_avvio(nascosto=False):
    """Comando per (ri)avviare il programma: tramite l'app, così macOS mantiene i permessi."""
    extra = ["--nascosto"] if nascosto else []
    if APP_BUNDLE.exists():
        return ["/usr/bin/open", "-n", str(APP_BUNDLE), "--args"] + extra
    return [sys.executable, str(APP_DIR / "app.py")] + extra


def notifica(titolo, testo):
    def q(t):
        return '"' + str(t).replace("\\", "\\\\").replace('"', '\\"') + '"'
    try:
        subprocess.Popen(["/usr/bin/osascript", "-e", f"display notification {q(testo)} with title {q(titolo)}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Compilazione dei programmi Swift (cattura audio e app)
# ----------------------------------------------------------------------------

def _impronta(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _swiftc(sorgente, destinazione):
    if not Path("/usr/bin/xcrun").exists() or subprocess.run(
            ["/usr/bin/xcode-select", "-p"], capture_output=True).returncode != 0:
        raise RuntimeError(MSG_STRUMENTI)
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    tmp = destinazione.with_name(destinazione.name + ".nuovo")
    r = subprocess.run(["/usr/bin/xcrun", "swiftc", "-O", str(sorgente), "-o", str(tmp)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        log(f"Compilazione di {sorgente.name} fallita:\n{r.stdout}\n{r.stderr}")
        raise RuntimeError(f"Non riesco a preparare {sorgente.name}: dettagli nel registro.\n"
                           + (r.stderr.strip().splitlines() or [""])[-1])
    os.replace(tmp, destinazione)


def compila_helper(forza=False):
    """Compila cattura-audio se manca o se il sorgente è cambiato (es. dopo un aggiornamento)."""
    impronta = BIN / "cattura-audio.sha256"
    attuale = _impronta(SORGENTE_HELPER)
    if not forza and HELPER.exists() and impronta.exists() and impronta.read_text().strip() == attuale:
        return False
    log("Preparo il programma di cattura audio…")
    _swiftc(SORGENTE_HELPER, HELPER)
    impronta.write_text(attuale)
    log("Programma di cattura audio pronto.")
    return True


def helper_audio():
    compila_helper()
    return HELPER


def permesso_audio():
    """True se macOS permette di registrare l'audio (Registrazione schermo e audio di sistema)."""
    try:
        return subprocess.run([str(helper_audio()), "--verifica"], capture_output=True, timeout=30).returncode == 0
    except Exception as e:
        log(f"Verifica del permesso non riuscita: {e}")
        return False


def chiedi_permesso_audio():
    """Mostra la richiesta di macOS (compare solo la prima volta) e apre le Impostazioni giuste."""
    try:
        subprocess.run([str(helper_audio()), "--chiedi"], capture_output=True, timeout=60)
    except Exception:
        pass


def apri_impostazioni_permesso():
    subprocess.Popen(["/usr/bin/open", PANNELLO_PERMESSO])


def assicura_permesso_audio():
    import core
    if not permesso_audio():
        chiedi_permesso_audio()
        raise core.PermessoMancante(core.MSG_PERMESSO)


# ----------------------------------------------------------------------------
# L'app "Appunti Lezioni" in ~/Applications (Launchpad, Spotlight, Dock)
# ----------------------------------------------------------------------------

def crea_app(icona_png, destinazione=None):
    """Crea (o aggiorna) Appunti Lezioni.app. Restituisce il percorso."""
    from PIL import Image

    app = Path(destinazione) if destinazione else Path.home() / "Applications" / f"{APP_NOME}.app"
    tmp = Path(tempfile.mkdtemp(prefix="app_")) / app.name
    macos = tmp / "Contents" / "MacOS"
    risorse = tmp / "Contents" / "Resources"
    macos.mkdir(parents=True)
    risorse.mkdir(parents=True)
    _swiftc(SORGENTE_APP, macos / APP_NOME)
    Image.open(icona_png).convert("RGBA").resize((1024, 1024)).save(risorse / "icona.icns")
    info = {
        "CFBundleName": APP_NOME,
        "CFBundleDisplayName": APP_NOME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": APP_NOME,
        "CFBundleIconFile": "icona",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": APP_VERSIONE,
        "CFBundleVersion": APP_VERSIONE,
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "AppuntiProgramma": str(APP_DIR),
        "NSAppleEventsUsageDescription": "Serve per esportare la dispensa in PDF con Word o Pages.",
        "NSDocumentsFolderUsageDescription": "Gli appunti vengono salvati nella cartella Documenti.",
        "NSDesktopFolderUsageDescription": "Per allegare alle lezioni materiali che si trovano sulla Scrivania.",
        "NSDownloadsFolderUsageDescription": "Per allegare alle lezioni materiali scaricati.",
        "NSAudioCaptureUsageDescription": "Per trascrivere l'audio delle videolezioni.",
        "NSScreenCaptureUsageDescription": "Per registrare l'audio delle videolezioni (lo schermo non viene registrato).",
    }
    with open(tmp / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(tmp)],
                   capture_output=True, text=True)
    app.parent.mkdir(parents=True, exist_ok=True)
    if app.exists():
        shutil.rmtree(app)
    shutil.move(str(tmp), str(app))
    shutil.rmtree(tmp.parent, ignore_errors=True)
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
                    "/Support/lsregister", "-f", str(app)], capture_output=True)
    log(f"App creata: {app}")
    return app


# ----------------------------------------------------------------------------
# Apertura all'accesso al Mac
# ----------------------------------------------------------------------------

def avvio_automatico_attivo():
    return LAUNCH_AGENT.exists()


def imposta_avvio_automatico(attivo):
    if attivo:
        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump({"Label": "it.appuntilezioni.avvio",
                           "ProgramArguments": ["/usr/bin/open", "-g", str(APP_BUNDLE), "--args", "--nascosto"],
                           "RunAtLoad": True}, f)
    else:
        try:
            LAUNCH_AGENT.unlink()
        except OSError:
            pass
    log(f"Apertura all'accesso: {'attiva' if attivo else 'disattivata'}")


# ----------------------------------------------------------------------------
# PDF della dispensa (con Microsoft Word se c'è, altrimenti con Pages)
# ----------------------------------------------------------------------------

def _as(t):
    return '"' + str(t).replace("\\", "\\\\").replace('"', '\\"') + '"'


def esporta_pdf(docx_path):
    docx_path = Path(docx_path).resolve()
    pdf = docx_path.with_suffix(".pdf")
    script_word = f"""
tell application "Microsoft Word"
    open POSIX file {_as(docx_path)}
    set d to active document
    save as d file name {_as(pdf)} file format format PDF
    close d saving no
end tell"""
    script_pages = f"""
tell application "Pages"
    set d to open POSIX file {_as(docx_path)}
    export d to POSIX file {_as(pdf)} as PDF
    close d saving no
end tell"""
    tentativi = []
    if Path("/Applications/Microsoft Word.app").exists():
        tentativi.append(("Word", script_word))
    if Path("/Applications/Pages.app").exists():
        tentativi.append(("Pages", script_pages))
    if not tentativi:
        raise RuntimeError("Per creare il PDF serve Pages (gratuito sull'App Store) o Microsoft Word.")
    errori = []
    for nome, script in tentativi:
        try:
            pdf.unlink()
        except OSError:
            pass
        r = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and pdf.exists():
            return pdf
        errori.append(f"{nome}: {r.stderr.strip()}")
    raise RuntimeError("PDF non creato. " + " | ".join(errori))


# ----------------------------------------------------------------------------
# Istanza unica: un secondo avvio porta in primo piano la finestra già aperta
# ----------------------------------------------------------------------------

class IstanzaUnica:
    def __init__(self, on_mostra):
        self.on_mostra = on_mostra
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.bind(("127.0.0.1", PORTA_ISTANZA))
        except OSError:
            self.sock.close()
            self.sock = None
            return
        self.sock.listen(2)
        threading.Thread(target=self._ascolta, daemon=True).start()

    @property
    def prima(self):
        return self.sock is not None

    def _ascolta(self):
        while True:
            try:
                c, _ = self.sock.accept()
                if c.recv(16) == b"MOSTRA":
                    self.on_mostra()
                c.close()
            except OSError:
                break

    @staticmethod
    def chiedi_di_mostrare():
        try:
            with socket.create_connection(("127.0.0.1", PORTA_ISTANZA), timeout=2) as s:
                s.sendall(b"MOSTRA")
            return True
        except OSError:
            return False
