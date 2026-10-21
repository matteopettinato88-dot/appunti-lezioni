"""
Appunti Lezioni – funzioni legate a Windows: avvio automatico, collegamenti,
isolamento dell'audio del browser, istanza unica, apertura file.
Su altri sistemi le funzioni non fanno nulla (utile per i test).
"""

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

from core import APP_DIR, APP_NOME, DATI, log

WIN = sys.platform == "win32"
BROWSER = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "opera_gx.exe",
           "vivaldi.exe", "arc.exe", "iexplore.exe", "msedgewebview2.exe",
           # programmi per lezioni in diretta: non vanno mai silenziati
           "zoom.exe", "zoom_vdi.exe", "ms-teams.exe", "teams.exe", "msteams.exe", "webex.exe",
           "ciscocollabhost.exe", "atmgr.exe", "webexmta.exe", "skype.exe", "gotomeeting.exe",
           "g2mcomm.exe", "bbbclient.exe", "meet.exe"}
PORTA_ISTANZA = 47651


def apri(path):
    path = str(path)
    if WIN:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def comando_avvio(nascosto=False):
    pyw = Path(sys.executable)
    if WIN and pyw.name.lower() == "python.exe":
        pyw = pyw.with_name("pythonw.exe")
    args = [str(pyw), str(APP_DIR / "app.py")]
    if nascosto:
        args.append("--nascosto")
    return args


# ----------------------------------------------------------------------------
# Avvio con Windows
# ----------------------------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def avvio_automatico_attivo():
    if not WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, "AppuntiLezioni")
            return True
    except OSError:
        return False


def imposta_avvio_automatico(attivo):
    if not WIN:
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if attivo:
            cmd = " ".join(f'"{a}"' if not a.startswith("--") else a for a in comando_avvio(nascosto=True))
            winreg.SetValueEx(k, "AppuntiLezioni", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "AppuntiLezioni")
            except OSError:
                pass
    log(f"Avvio con Windows: {'attivo' if attivo else 'disattivato'}")


# ----------------------------------------------------------------------------
# Collegamenti su Desktop e menu Start
# ----------------------------------------------------------------------------

def crea_collegamenti(icona):
    if not WIN:
        return []
    exe, script = comando_avvio()[:2]
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
            desktop = Path(buf.value)  # Desktop reale (anche se spostato su OneDrive)
    except Exception:
        pass
    start = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    creati = []
    for cartella in (desktop, start):
        lnk = cartella / f"{APP_NOME}.lnk"
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
            "$s.TargetPath=$env:EXE;$s.Arguments='\"'+$env:SCRIPT+'\"';"
            "$s.WorkingDirectory=$env:WD;$s.IconLocation=$env:ICO;"
            "$s.Description='Trascrive le videolezioni e crea gli appunti';$s.Save()"
        )
        env = dict(os.environ, LNK=str(lnk), EXE=exe, SCRIPT=script, WD=str(APP_DIR), ICO=str(icona))
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           env=env, capture_output=True, text=True, creationflags=0x08000000)
        if r.returncode == 0:
            creati.append(lnk)
        else:
            log(f"Collegamento non creato in {cartella}: {r.stderr.strip()}")
    return creati


# ----------------------------------------------------------------------------
# Solo audio del browser: silenzia temporaneamente gli altri programmi
# ----------------------------------------------------------------------------

_SILENZIATI_FILE = DATI / "silenziati.json"


class IsolamentoAudio:
    """
    Durante la registrazione silenzia i programmi che non sono browser (Spotify, WhatsApp,
    suoni di sistema…) così nella trascrizione finisce solo la lezione. Alla fine li riattiva.
    I programmi silenziati vengono annotati su disco: se il PC si spegne, al riavvio
    dell'app vengono riattivati (ripristina_sospesi).
    """

    def __init__(self):
        self.silenziati = set()      # nomi dei processi (o "suoni di sistema")
        self.attivo = False
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _sessioni():
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetAllSessions()

    @staticmethod
    def _nome(sessione):
        try:
            if sessione.Process is None:
                return "suoni di sistema"
            return sessione.Process.name().lower()
        except Exception:
            return None

    def _passata(self):
        mio = os.getpid()
        for s in self._sessioni():
            nome = self._nome(s)
            if not nome or nome in BROWSER:
                continue
            try:
                if s.Process is not None and s.Process.pid == mio:
                    continue
                vol = s.SimpleAudioVolume
                if not vol.GetMute():
                    vol.SetMute(1, None)
                    if nome not in self.silenziati:
                        log(f"Silenziato durante la registrazione: {nome}")
                    self.silenziati.add(nome)
            except Exception:
                pass
        self._salva()

    def _salva(self):
        try:
            _SILENZIATI_FILE.write_text(json.dumps(sorted(self.silenziati)), encoding="utf-8")
        except OSError:
            pass

    def avvia(self):
        if not WIN:
            return
        try:
            import comtypes
            comtypes.CoInitialize()
            self._passata()
        except Exception as e:
            log(f"Isolamento audio non disponibile: {e}")
            return
        self.attivo = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, daemon=True)
        self._thread.start()

    def _ciclo(self):
        import comtypes
        comtypes.CoInitialize()
        while not self._stop.wait(3):  # i programmi aperti dopo vengono silenziati anch'essi
            try:
                self._passata()
            except Exception:
                pass

    def ferma(self):
        if not self.attivo:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        riattiva(self.silenziati)
        self.silenziati.clear()
        self.attivo = False


def riattiva(nomi):
    if not WIN or not nomi:
        try:
            _SILENZIATI_FILE.unlink()
        except OSError:
            pass
        return
    try:
        import comtypes
        comtypes.CoInitialize()
        for s in IsolamentoAudio._sessioni():
            if IsolamentoAudio._nome(s) in nomi:
                try:
                    s.SimpleAudioVolume.SetMute(0, None)
                except Exception:
                    pass
        log(f"Riattivato l'audio di: {', '.join(sorted(nomi))}")
    except Exception as e:
        log(f"Impossibile riattivare l'audio: {e}")
    try:
        _SILENZIATI_FILE.unlink()
    except OSError:
        pass


def ripristina_sospesi():
    """Se l'app si era chiusa male durante una registrazione, riattiva i programmi rimasti muti."""
    if _SILENZIATI_FILE.exists():
        try:
            riattiva(set(json.loads(_SILENZIATI_FILE.read_text(encoding="utf-8"))))
        except Exception:
            pass


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
