"""
Prova automatica di Appunti Lezioni: usa una voce sintetica di Windows per verificare
registrazione, trascrizione, salvataggio continuo, isolamento dell'audio, chiave API e appunti.
Il risultato finisce in autotest_risultato.txt nella cartella del programma.
"""

import datetime as dt
import difflib
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
import traceback
from pathlib import Path

import core
from core import log

TESTO_PROVA = (
    "Oggi parliamo del contratto nel diritto privato. Secondo l'articolo 1321 del codice civile, "
    "il contratto è l'accordo di due o più parti per costituire, regolare o estinguere tra loro "
    "un rapporto giuridico patrimoniale. Gli elementi essenziali del contratto sono l'accordo delle parti, "
    "la causa, l'oggetto e la forma, quando è prescritta dalla legge sotto pena di nullità. "
    "La prossima volta vedremo la differenza tra nullità e annullabilità."
)
TESTO_ISOLAMENTO = ("Questa frase non dovrebbe essere registrata, perché il programma silenzia tutto "
                    "ciò che non è il browser. Continuo a parlare ancora per qualche secondo per la prova.")

PS_PARLA = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'it*' } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Volume = 100
$s.Speak([IO.File]::ReadAllText($args[0], [Text.Encoding]::UTF8))
"""


def parla(testo, attesa=True):
    td = Path(tempfile.mkdtemp())
    (td / "t.txt").write_text(testo, encoding="utf-8")
    (td / "p.ps1").write_text(PS_PARLA, encoding="utf-8-sig")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(td / "p.ps1"), str(td / "t.txt")]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    if attesa:
        p.wait(timeout=180)
    return p


def _parole(t):
    return re.findall(r"\w+", t.lower())


def esegui():
    risultati = []

    def ok(nome, esito, dettaglio=""):
        risultati.append((nome, esito, dettaglio))
        log(f"{'OK ' if esito else 'NO '} {nome} {('- ' + dettaglio) if dettaglio else ''}")

    log("=" * 60)
    log(f"AUTOTEST v2 – Python {platform.python_version()} – {platform.platform()} – {os.cpu_count()} CPU")
    cfg = core.load_config()

    try:
        import anthropic, customtkinter, docx, faster_whisper, pystray, pycaw, pyaudiowpatch  # noqa: F401
        ok("Librerie installate", True, f"faster-whisper {faster_whisper.__version__}, "
                                        f"customtkinter {customtkinter.__version__}")
    except Exception as e:
        ok("Librerie installate", False, repr(e))
        return _riassunto(risultati)

    try:
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        lb = core.trova_loopback(pa, pyaudio)
        pa.terminate()
        ok("Cattura dell'audio del PC", True, lb["name"])
    except Exception as e:
        ok("Cattura dell'audio del PC", False, repr(e))
        return _riassunto(risultati)

    try:
        tr = core.Trascrittore(cfg["qualita_trascrizione"])
        ok("Modello di trascrizione", True, f"{cfg['qualita_trascrizione']} ({core.MODELLI[cfg['qualita_trascrizione']]})")
    except Exception as e:
        ok("Modello di trascrizione", False, repr(e))
        return _riassunto(risultati)

    # Registrazione + trascrizione + salvataggio continuo
    testo = ""
    try:
        s = core.Sessione(dict(cfg, secondi_per_blocco=15), "Prova automatica", "Lezione di prova", tr,
                          termini=["Codice civile", "nullità", "annullabilità"])
        s.registratore.avvia()
        log("Riproduco una voce di prova dalle casse…")
        parla(TESTO_PROVA)
        time.sleep(2)
        testo = s.termina()
        su_disco = s.file_testo.read_text(encoding="utf-8")
        recuperabile = any(x["id"] == s.id for x in core.sessioni_incompiute())
        ok("Salvataggio continuo su disco", su_disco.strip() == testo.strip() and recuperabile and bool(testo),
           f"{len(su_disco.split())} parole salvate durante la registrazione")
        s.chiudi()
        senza_marcatori = re.sub(r"\[min \d+\]", " ", testo)
        sim = difflib.SequenceMatcher(None, _parole(TESTO_PROVA), _parole(senza_marcatori)).ratio()
        log(f"Trascrizione: {testo!r}")
        ok("Trascrizione fedele", sim >= 0.75, f"somiglianza col testo originale {sim:.0%}")
        if s.secondi_audio:
            rtf = s.secondi_calcolo / s.secondi_audio
            ok("Velocità di trascrizione", rtf < 0.8, f"{rtf:.2f} s di calcolo per secondo di lezione")
    except Exception as e:
        log(traceback.format_exc())
        ok("Registrazione e trascrizione", False, repr(e))

    # Isolamento: un programma che non è un browser (PowerShell) deve essere silenziato
    try:
        import sistema
        reg = core.Registratore(cfg, lambda *a: None)
        reg.avvia()
        iso = sistema.IsolamentoAudio()
        iso.avvia()
        p = parla(TESTO_ISOLAMENTO, attesa=False)
        campioni, t0 = [], time.time()
        while p.poll() is None and time.time() - t0 < 60:
            if time.time() - t0 > 4.5:      # dopo la prima scansione (ogni 3 s)
                campioni.append(reg.livello_attuale())
            time.sleep(0.2)
        silenziati = sorted(iso.silenziati)
        iso.ferma()
        reg.ferma()
        picco = max(campioni) if campioni else 1.0
        ok("Solo audio del browser", picco < 0.003 and "powershell.exe" in silenziati,
           f"livello di un programma non-browser durante la registrazione: {picco:.4f}; silenziati: {silenziati}")
        ripristinati = not (core.DATI / "silenziati.json").exists()
        ok("Audio degli altri programmi riattivato", ripristinati)
    except Exception as e:
        log(traceback.format_exc())
        ok("Solo audio del browser", False, repr(e))

    # Chiave e appunti
    chiave = cfg.get("chiave_api_anthropic", "")
    if not chiave:
        ok("Chiave API", False, "non inserita")
    else:
        valida, msg = core.verifica_chiave(chiave)
        ok("Chiave API", valida, msg)
        if valida and testo:
            try:
                import corsi
                import materiali
                cartella_mat = Path(tempfile.mkdtemp())
                slide = cartella_mat / "Slide contratto.txt"
                slide.write_text("Il contratto (art. 1321 c.c.)\nRequisiti essenziali (art. 1325 c.c.): "
                                 "accordo, causa, oggetto, forma.\nNullità (art. 1418 c.c.) e annullabilità "
                                 "(art. 1425 c.c.).\nRiferimento: Galgano, Diritto privato, 2020.", encoding="utf-8")
                from PIL import Image, ImageDraw
                foto = cartella_mat / "Lavagna.png"
                img = Image.new("RGB", (900, 300), "white")
                ImageDraw.Draw(img).text((30, 120), "Contratto = accordo + causa + oggetto + forma", fill="black")
                img.save(foto)
                termini = materiali.termini_chiave(materiali.testo(slide))
                ok("Termini estratti dai materiali", bool(termini), ", ".join(termini[:10]))
                lid = "autotest-" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
                corsi.nuova_lezione(cfg, "Prova automatica", "Lezione di prova – Il contratto", lid, dt.datetime.now())
                corsi.aggiungi_materiale(cfg, "Prova automatica", lid, slide, minuto=0)
                corsi.aggiungi_materiale(cfg, "Prova automatica", lid, foto, minuto=1)
                corsi.salva_trascrizione(cfg, "Prova automatica", lid, testo)
                p = corsi.crea_appunti_lezione(cfg, "Prova automatica", lid)
                lez = corsi.lezione(cfg, "Prova automatica", lid)
                ok("Appunti con Claude e materiali", p.exists(), str(p))
                ok("Glossario della lezione", bool(lez.get("glossario")),
                   ", ".join(g["termine"] for g in lez.get("glossario", [])[:6]))
                disp = corsi.percorso_dispensa(cfg, "Prova automatica")
                ok("Dispensa del corso", disp.exists(), str(disp))
            except Exception as e:
                log(traceback.format_exc())
                ok("Appunti con Claude e materiali", False, core.messaggio_errore(e))
    return _riassunto(risultati)


def _riassunto(risultati):
    righe = ["RISULTATO AUTOTEST " + dt.datetime.now().strftime("%Y-%m-%d %H:%M")]
    for nome, esito, dettaglio in risultati:
        righe.append(f"[{'OK' if esito else 'NO'}] {nome}: {dettaglio}")
    testo = "\n".join(righe)
    (core.APP_DIR / "autotest_risultato.txt").write_text(testo, encoding="utf-8")
    log("\n" + testo)
    return all(e for _, e, _ in risultati)
