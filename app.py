#!/usr/bin/env python3
"""
Appunti Lezioni – l'applicazione con interfaccia.

  pythonw app.py              apre la finestra
  pythonw app.py --nascosto   parte ridotta nella barra delle applicazioni (avvio con Windows)
  python  app.py --installa   crea i collegamenti su Desktop e menu Start
  python  app.py --autotest   prova automatica completa (vedi autotest.py)
"""

import datetime as dt
import queue
import sys
import threading
import traceback
import uuid
from pathlib import Path

import core
import corsi
import materiali
from core import log

COLORI = {
    "caricamento": "#8a8f98", "pronto": "#2f6fdf", "registra": "#d93636",
    "pausa": "#e0a412", "elabora": "#ec7a08", "errore": "#6b6f76",
}
TESTI_STATO = {
    "caricamento": "Preparazione…", "pronto": "Pronto", "registra": "Sto registrando",
    "pausa": "In pausa", "elabora": "Sto scrivendo gli appunti…", "errore": "Problema",
}
QUALITA_ETICHETTE = {"veloce": "Veloce", "standard": "Standard", "preciso": "Preciso"}
STOP_OPZIONI = {"Mai": 0, "5 minuti": 5, "8 minuti": 8, "15 minuti": 15, "30 minuti": 30}
EXTRA_OPZIONI = {"Aggiungili, segnati «(dai materiali)»": "segna", "Ignorali": "ignora"}
GRIGIO = "#5f6670"
TIPI_FILE = [("Materiali", "*.pdf *.pptx *.docx *.txt *.md *.jpg *.jpeg *.png *.webp"),
             ("PDF", "*.pdf"), ("PowerPoint", "*.pptx"), ("Word", "*.docx"),
             ("Foto", "*.jpg *.jpeg *.png *.webp"), ("Tutti i file", "*.*")]


def crea_icona(path, colore="#2f6fdf"):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=colore)
    d.rounded_rectangle((64, 52, 192, 204), radius=14, fill="white")
    for y in (92, 120, 148, 176):
        d.rectangle((86, y, 170, y + 8), fill=colore)
    d.ellipse((150, 150, 214, 214), fill="#d93636", outline="white", width=8)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return img


def icona_tray(stato):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=COLORI.get(stato, COLORI["pronto"]))
    if stato == "registra":
        d.ellipse((22, 22, 42, 42), fill="white")
    elif stato == "pausa":
        d.rectangle((21, 20, 28, 44), fill="white")
        d.rectangle((36, 20, 43, 44), fill="white")
    else:
        d.rectangle((20, 18, 44, 46), fill="white")
        for y in (24, 31, 38):
            d.rectangle((24, y, 40, y + 3), fill=COLORI.get(stato, COLORI["pronto"]))
    return img


def imposta_icona(finestra, ico):
    try:
        finestra.iconbitmap(str(ico))
    except Exception:
        pass


def tempo_fa(ts):
    sec = (dt.datetime.now() - dt.datetime.fromtimestamp(ts)).total_seconds()
    if sec < 3600:
        return f"{max(1, int(sec // 60))} min fa"
    if sec < 86400:
        return f"{int(sec // 3600)} ore fa"
    return f"{int(sec // 86400)} giorni fa"


# ============================================================================
# Finestra «Nuova lezione» (anche per modificare corso e titolo durante la registrazione)
# ============================================================================

class FinestraLezione:
    def __init__(self, app, modifica=None):
        """modifica: None per una nuova lezione, oppure (corso, titolo) da correggere."""
        import customtkinter as ctk

        self.app = app
        self.modifica = modifica
        self.file = []           # materiali scelti (solo nuova lezione)
        self.titolo_toccato = bool(modifica)
        self.risultato = None
        cfg = app.cfg

        w = self.win = ctk.CTkToplevel(app.root)
        w.title("Modifica lezione" if modifica else "Nuova lezione")
        w.geometry("520x" + ("300" if modifica else "480"))
        w.resizable(False, False)
        w.transient(app.root)
        w.after(150, lambda: (w.lift(), w.focus_force()))
        w.after(250, lambda: imposta_icona(w, app.ico))
        w.grid_columnconfigure(0, weight=1)
        bold = ctk.CTkFont(weight="bold")

        ctk.CTkLabel(w, text="Corso", font=bold).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 2))
        self.cmb_corso = ctk.CTkComboBox(w, values=core.elenco_corsi(cfg), height=36,
                                         command=lambda _: self._corso_cambiato())
        self.cmb_corso.grid(row=1, column=0, sticky="ew", padx=20)
        self.cmb_corso.set(modifica[0] if modifica else cfg.get("ultimo_corso", ""))
        self.cmb_corso._entry.bind("<KeyRelease>", lambda e: self._corso_cambiato())

        ctk.CTkLabel(w, text="Titolo della lezione", font=bold).grid(row=2, column=0, sticky="w", padx=20, pady=(14, 2))
        self.ent_titolo = ctk.CTkEntry(w, height=36, placeholder_text="es. Lezione 4 – Genitorialità")
        self.ent_titolo.grid(row=3, column=0, sticky="ew", padx=20)
        self.ent_titolo.bind("<Key>", lambda e: setattr(self, "titolo_toccato", True))
        if modifica:
            self.ent_titolo.insert(0, modifica[1])
        else:
            self._corso_cambiato()

        riga = 4
        if not modifica:
            ctk.CTkLabel(w, text="Materiali (facoltativi)", font=bold).grid(row=4, column=0, sticky="w", padx=20, pady=(14, 0))
            ctk.CTkLabel(w, text="Slide, dispense, appunti tuoi o foto. Potrai aggiungerne altri anche durante la lezione.",
                         text_color=GRIGIO, wraplength=470, justify="left").grid(row=5, column=0, sticky="w", padx=20)
            self.zona = ctk.CTkFrame(w, height=150, border_width=2, border_color="#b8c4d6", fg_color="#f4f7fb",
                                     corner_radius=10)
            self.zona.grid(row=6, column=0, sticky="ew", padx=20, pady=(6, 0))
            self.zona.grid_columnconfigure(0, weight=1)
            self.suggerimento = materiali.ultimo_scaricato(corsi.nomi_materiali_usati(cfg))
            self._disegna_zona()
            app.abilita_drop(w, self._aggiungi_file)
            riga = 7

        b = ctk.CTkFrame(w, fg_color="transparent")
        b.grid(row=riga, column=0, sticky="e", padx=20, pady=18)
        ctk.CTkButton(b, text="Annulla", width=100, fg_color="#8a8f98", hover_color="#6f747c",
                      command=w.destroy).grid(row=0, column=0, padx=6)
        ctk.CTkButton(b, text="Salva" if modifica else "●  Inizia a registrare", width=190,
                      fg_color="#2f6fdf" if modifica else "#d93636",
                      hover_color="#2459b8" if modifica else "#b52b2b", font=bold,
                      command=self._conferma).grid(row=0, column=1)
        w.bind("<Return>", lambda e: self._conferma())
        w.bind("<Escape>", lambda e: w.destroy())
        w.grab_set()

    def _corso_cambiato(self):
        if self.titolo_toccato:
            return
        corso = self.cmb_corso.get().strip()
        self.ent_titolo.delete(0, "end")
        self.ent_titolo.insert(0, corsi.titolo_proposto(self.app.cfg, corso) if corso else "Lezione 1")

    def _disegna_zona(self):
        import customtkinter as ctk
        for c in self.zona.winfo_children():
            c.destroy()
        r = 0
        for p in self.file:
            ctk.CTkLabel(self.zona, text=f"{materiali.icona(p)}  {p.name}", anchor="w"
                         ).grid(row=r, column=0, sticky="w", padx=12, pady=(8 if r == 0 else 2, 0))
            ctk.CTkButton(self.zona, text="✕", width=28, height=24, fg_color="transparent", text_color=GRIGIO,
                          hover_color="#e1e6ee", command=lambda x=p: self._togli(x)
                          ).grid(row=r, column=1, padx=8, pady=(8 if r == 0 else 2, 0))
            r += 1
        if self.suggerimento and self.suggerimento not in self.file:
            s = ctk.CTkFrame(self.zona, fg_color="#e3edfb", corner_radius=8)
            s.grid(row=r, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
            s.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(s, anchor="w", justify="left", wraplength=330,
                         text=f"Ultimo scaricato: {self.suggerimento.name} "
                              f"({tempo_fa(self.suggerimento.stat().st_mtime)})"
                         ).grid(row=0, column=0, sticky="w", padx=10, pady=6)
            ctk.CTkButton(s, text="Usa", width=60, command=lambda: self._aggiungi_file([self.suggerimento])
                          ).grid(row=0, column=1, padx=8)
            r += 1
        testo = "Trascina qui i file" if self.app.dnd else "Nessun materiale"
        if not self.file:
            ctk.CTkLabel(self.zona, text=f"📎  {testo}", text_color=GRIGIO
                         ).grid(row=r, column=0, columnspan=2, pady=(14, 0))
            r += 1
        ctk.CTkButton(self.zona, text="+ Allega", width=110, command=self._scegli
                      ).grid(row=r, column=0, columnspan=2, pady=12)

    def _scegli(self):
        from tkinter import filedialog
        nomi = filedialog.askopenfilenames(parent=self.win, title="Materiali della lezione", filetypes=TIPI_FILE)
        self._aggiungi_file([Path(n) for n in nomi])

    def _aggiungi_file(self, percorsi):
        from tkinter import messagebox
        for p in map(Path, percorsi):
            errore = materiali.controlla(p)
            if errore:
                messagebox.showwarning(core.APP_NOME, errore, parent=self.win)
            elif p not in self.file:
                self.file.append(p)
        self._disegna_zona()

    def _togli(self, p):
        self.file.remove(p)
        self._disegna_zona()

    def _conferma(self):
        from tkinter import messagebox
        corso = self.cmb_corso.get().strip()
        if not corso:
            messagebox.showinfo(core.APP_NOME, "Scrivi o scegli il nome del corso.", parent=self.win)
            return
        corso = core.normalizza_corso(corso, core.elenco_corsi(self.app.cfg))
        titolo = self.ent_titolo.get().strip() or corsi.titolo_proposto(self.app.cfg, corso)
        self.win.grab_release()
        self.win.destroy()
        if self.modifica:
            self.app.applica_modifica(corso, titolo)
        else:
            self.app.inizia_lezione(corso, titolo, self.file)


# ============================================================================
# Finestra «Visualizza dispensa»
# ============================================================================

class FinestraDispensa:
    def __init__(self, app, corso):
        import customtkinter as ctk

        self.app = app
        self.aperte = set()
        w = self.win = ctk.CTkToplevel(app.root)
        w.title("Dispensa")
        w.geometry("640x720")
        w.minsize(560, 480)
        w.after(150, lambda: (w.lift(), w.focus_force()))
        w.after(250, lambda: imposta_icona(w, app.ico))
        w.protocol("WM_DELETE_WINDOW", self.chiudi)
        w.grid_columnconfigure(0, weight=1)
        w.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(w, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        top.grid_columnconfigure(0, weight=1)
        self.cmb = ctk.CTkComboBox(top, values=core.elenco_corsi(app.cfg) or [corso], height=36,
                                   font=ctk.CTkFont(size=16, weight="bold"), command=lambda _: self.aggiorna())
        self.cmb.grid(row=0, column=0, sticky="ew")
        self.cmb.set(corso)

        self.card = ctk.CTkFrame(w, fg_color="#ffffff", border_width=1, border_color="#d5d8dc", corner_radius=12)
        self.card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.card.grid_columnconfigure(0, weight=1)

        self.lista = ctk.CTkScrollableFrame(w, fg_color="transparent")
        self.lista.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self.lista.grid_columnconfigure(0, weight=1)
        app.abilita_drop(w, self._drop)
        if app.lezione_corrente:
            self.aperte.add(app.lezione_corrente["id"])
        self.aggiorna()

    @property
    def corso(self):
        return self.cmb.get().strip()

    def chiudi(self):
        self.app.finestra_dispensa = None
        self.win.destroy()

    def _drop(self, percorsi):
        """Un file trascinato sulla finestra va alla lezione aperta (o a quella in registrazione)."""
        cur = self.app.lezione_corrente
        if cur and cur["corso"] == self.corso:
            self.app.allega(percorsi, self.corso, cur["id"])
        elif len(self.aperte) == 1:
            self.app.allega(percorsi, self.corso, next(iter(self.aperte)))

    def aggiorna(self):
        import customtkinter as ctk
        cfg = self.app.cfg
        corso = self.corso
        self.win.title(f"Dispensa – {corso}")
        for c in self.card.winfo_children():
            c.destroy()
        for c in self.lista.winfo_children():
            c.destroy()
        lez = corsi.lezioni(cfg, corso) if corso else []
        complete = [l for l in lez if l["stato"] == "completa"]
        disp = corsi.percorso_dispensa(cfg, corso) if corso else None

        ctk.CTkLabel(self.card, text="📘  Dispensa del corso", font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        info = f"{len(complete)} lezioni"
        dati = corsi.leggi(cfg, corso) if corso else {}
        if dati.get("dispensa_aggiornata"):
            info += f" · aggiornata il {dt.datetime.fromisoformat(dati['dispensa_aggiornata']):%d/%m %H:%M}"
        elif not complete:
            info = "Si crea da sola quando finisci la prima lezione di questo corso."
        ctk.CTkLabel(self.card, text=info, text_color=GRIGIO, anchor="w").grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))
        if disp and disp.exists():
            ctk.CTkButton(self.card, text="Apri", width=70, command=lambda: self.app.sistema.apri(disp)
                          ).grid(row=0, column=1, rowspan=2, padx=4)
            ctk.CTkButton(self.card, text="PDF", width=60, fg_color="#8a8f98", hover_color="#6f747c",
                          command=self._pdf).grid(row=0, column=2, rowspan=2, padx=(4, 14))

        if not lez:
            ctk.CTkLabel(self.lista, text="Nessuna lezione registrata per questo corso.", text_color=GRIGIO
                         ).grid(row=0, column=0, pady=30)
        for i, l in enumerate(sorted(lez, key=lambda x: (x.get("numero", 0), x["inizio"]), reverse=True)):
            self._riquadro(i, corso, l)

    def _riquadro(self, riga, corso, l):
        import customtkinter as ctk
        cfg = self.app.cfg
        corrente = self.app.lezione_corrente and self.app.lezione_corrente["id"] == l["id"]
        aperta = l["id"] in self.aperte
        f = ctk.CTkFrame(self.lista, fg_color="#ffffff", border_width=1,
                         border_color="#d93636" if corrente else "#d5d8dc", corner_radius=10)
        f.grid(row=riga, column=0, sticky="ew", padx=4, pady=4)
        f.grid_columnconfigure(0, weight=1)

        if corrente:
            stato = "● in registrazione"
        elif l["stato"] == "completa":
            stato = f"{dt.datetime.fromisoformat(l['inizio']):%d/%m}   📝"
        else:
            stato = "da completare"
        nmat = len(l.get("materiali", []))
        testo = f"{'▼' if aperta else '▶'}  {corsi.titolo_capitolo(l)}"
        ctk.CTkButton(f, text=testo, anchor="w", fg_color="transparent", text_color="#1d2127", hover_color="#f0f2f5",
                      font=ctk.CTkFont(weight="bold"), command=lambda: self._apri_chiudi(l["id"])
                      ).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(f, text=stato + (f"   📎{nmat}" if nmat else ""),
                     text_color="#d93636" if corrente else (GRIGIO if l["stato"] == "completa" else "#c06a00")
                     ).grid(row=0, column=1, padx=12)
        if not aperta:
            return

        corpo = ctk.CTkFrame(f, fg_color="transparent")
        corpo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))
        corpo.grid_columnconfigure(0, weight=1)
        r = 0
        if not l.get("materiali"):
            ctk.CTkLabel(corpo, text="Nessun materiale allegato.", text_color=GRIGIO).grid(row=r, column=0, sticky="w")
            r += 1
        for m in l.get("materiali", []):
            quando = f"   min {m['minuto']}" if m.get("minuto") is not None else ""
            ctk.CTkLabel(corpo, text=f"{materiali.icona(m['nome'])}  {m['nome']}{quando}", anchor="w"
                         ).grid(row=r, column=0, sticky="w")
            p = corsi.percorso_materiale(cfg, corso, m)
            ctk.CTkButton(corpo, text="Apri", width=56, height=26, command=lambda x=p: self.app.sistema.apri(x)
                          ).grid(row=r, column=1, padx=4, pady=2)
            ctk.CTkButton(corpo, text="✕", width=28, height=26, fg_color="transparent", text_color=GRIGIO,
                          hover_color="#e1e6ee", command=lambda x=m: self._rimuovi(corso, l, x)
                          ).grid(row=r, column=2, pady=2)
            r += 1

        bot = ctk.CTkFrame(corpo, fg_color="transparent")
        bot.grid(row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))
        b_agg = ctk.CTkButton(bot, text="+ Aggiungi materiale", width=150, height=30)
        b_agg.configure(command=lambda: self.app.menu_aggiungi(b_agg, corso, l["id"]))
        b_agg.grid(row=0, column=0, padx=(0, 6))
        if l.get("appunti") and (corsi.cartella(cfg, corso) / l["appunti"]).exists():
            ctk.CTkButton(bot, text="📝 Apri appunti", width=120, height=30, fg_color="#8a8f98", hover_color="#6f747c",
                          command=lambda: self.app.sistema.apri(corsi.cartella(cfg, corso) / l["appunti"])
                          ).grid(row=0, column=1, padx=6)
        if not corrente and l.get("trascrizione") and (l["stato"] != "completa" or l.get("materiali_modificati")):
            etichetta = "Rigenera appunti" if l["stato"] == "completa" else "Crea appunti"
            ctk.CTkButton(bot, text=etichetta, width=130, height=30, fg_color="#ec7a08", hover_color="#c96706",
                          command=lambda: self.app.crea_appunti_di(corso, l["id"])).grid(row=0, column=2, padx=6)
        if not corrente and l["stato"] != "completa":
            ctk.CTkButton(bot, text="Elimina", width=80, height=30, fg_color="transparent", text_color="#c0392b",
                          hover_color="#f8e1df", command=lambda: self.app.elimina_lezione(corso, l)
                          ).grid(row=0, column=3, padx=6)
        if l.get("materiali_modificati") and l["stato"] == "completa":
            ctk.CTkLabel(corpo, text="Hai cambiato i materiali: rigenera gli appunti per tenerne conto.",
                         text_color="#c06a00").grid(row=r + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _apri_chiudi(self, lid):
        self.aperte.symmetric_difference_update({lid})
        self.aggiorna()

    def _rimuovi(self, corso, l, m):
        from tkinter import messagebox
        if messagebox.askyesno(core.APP_NOME, f"Togliere «{m['nome']}» da questa lezione?", parent=self.win):
            corsi.rimuovi_materiale(self.app.cfg, corso, l["id"], m["file"])
            self.app.dopo_cambio_materiali(corso, l["id"])

    def _pdf(self):
        from tkinter import messagebox
        disp = corsi.percorso_dispensa(self.app.cfg, self.corso)

        def lavoro():
            try:
                pdf = corsi.esporta_pdf(disp)
                self.app.ui_q.put(("apri", pdf))
            except Exception as e:
                log(f"Esportazione PDF fallita: {e}")
                self.app.ui_q.put(("avviso", "Per creare il PDF serve Microsoft Word. In alternativa apri la "
                                             "dispensa e usa File → Esporta → PDF."))
        threading.Thread(target=lavoro, daemon=True).start()
        messagebox.showinfo(core.APP_NOME, "Creo il PDF della dispensa: si aprirà tra qualche secondo.", parent=self.win)


# ============================================================================
# Applicazione
# ============================================================================

class App:
    def __init__(self, nascosto=False):
        import customtkinter as ctk
        import sistema

        self.ctk = ctk
        self.sistema = sistema
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.cfg = core.load_config()
        self.ui_q = queue.Queue()
        self.stato = "caricamento"
        self.dettaglio = "Carico il modello di trascrizione…"
        self.trascrittore = None
        self.ricarica_modello_dopo = False
        self.sessione = None
        self.lezione_corrente = None      # {"corso", "id", "titolo"}
        self.isolamento = None
        self.banner_visibile = False
        self.avvisato_tray = False
        self.notificato_stop = False
        self.tray = None
        self.finestra_dispensa = None
        self._live_provvisorio = False

        try:
            n = corsi.importa_sessioni_interrotte(self.cfg)
            if n:
                log(f"Recuperate {n} registrazioni interrotte.")
        except Exception:
            log(traceback.format_exc())

        self.ico = core.DATI / "icona.ico"
        try:
            crea_icona(self.ico)
        except Exception:
            pass

        self.root = ctk.CTk()
        self.dnd = False
        try:
            from tkinterdnd2 import TkinterDnD
            TkinterDnD._require(self.root)
            self.dnd = True
        except Exception as e:
            log(f"Trascinamento file non disponibile: {e}")
        self.root.title(core.APP_NOME)
        self.root.geometry("620x760")
        self.root.minsize(540, 620)
        try:
            self.root.iconbitmap(str(self.ico))
        except Exception:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.nascondi)

        self.tabs = ctk.CTkTabview(self.root, anchor="nw")
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._scheda_lezione(self.tabs.add("Lezione"))
        self._scheda_appunti(self.tabs.add("Appunti"))
        self._scheda_impostazioni(self.tabs.add("Impostazioni"))
        self.abilita_drop(self.root, self._drop_principale)

        self._avvia_tray()
        sistema.ripristina_sospesi()
        self._aggiorna_stato_ui()
        self.aggiorna_appunti()
        self.root.after(150, self._tick)
        threading.Thread(target=self._carica_modello, daemon=True).start()
        self.root.after(15000, self._controllo_automatico)

        if not self.cfg.get("chiave_api_anthropic"):
            self.tabs.set("Impostazioni")
            self.lbl_verifica.configure(text="Inserisci la chiave API per poter creare gli appunti.",
                                        text_color="#c0392b")
        elif corsi.lezioni_da_completare(self.cfg):
            self.tabs.set("Appunti")
        if nascosto:
            self.root.withdraw()

    # ------------------------------------------------------------------ trascinamento
    def abilita_drop(self, widget, callback):
        if not self.dnd:
            return
        try:
            from tkinterdnd2 import DND_FILES
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", lambda e: (callback([Path(p) for p in widget.tk.splitlist(e.data)]), e.action)[1])
        except Exception as e:
            log(f"Trascinamento non attivato: {e}")

    def _drop_principale(self, percorsi):
        if self.lezione_corrente:
            self.allega(percorsi, self.lezione_corrente["corso"], self.lezione_corrente["id"])
        elif self.stato == "pronto":
            from tkinter import messagebox
            messagebox.showinfo(core.APP_NOME, "Avvia prima una nuova lezione: i materiali si collegano alla lezione.")

    # ------------------------------------------------------------------ UI: scheda Lezione
    def _scheda_lezione(self, tab):
        ctk = self.ctk
        tab.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(tab, corner_radius=12, fg_color="#ffffff", border_width=1, border_color="#d5d8dc")
        card.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 10))
        card.grid_columnconfigure(1, weight=1)
        self.lbl_pallino = ctk.CTkLabel(card, text="●", font=ctk.CTkFont(size=34))
        self.lbl_pallino.grid(row=0, column=0, rowspan=2, padx=(16, 8), pady=12)
        self.lbl_stato = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=20, weight="bold"), anchor="w")
        self.lbl_stato.grid(row=0, column=1, sticky="w", pady=(12, 0))
        self.lbl_dettaglio = ctk.CTkLabel(card, text="", anchor="w", text_color=GRIGIO, justify="left", wraplength=380)
        self.lbl_dettaglio.grid(row=1, column=1, sticky="w", pady=(0, 12))
        self.lbl_timer = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_timer.grid(row=0, column=2, padx=(16, 4))
        self.btn_modifica = ctk.CTkButton(card, text="✏️", width=34, height=28, fg_color="transparent",
                                          hover_color="#eef1f5", text_color="#1d2127", command=self.modifica_lezione)
        self.barra_livello = ctk.CTkProgressBar(card, height=8, progress_color="#d93636")
        self.barra_livello.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 14))
        self.barra_livello.set(0)

        b = ctk.CTkFrame(tab, fg_color="transparent")
        b.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        b.grid_columnconfigure((0, 1, 2), weight=1)
        self.btn_avvia = ctk.CTkButton(b, text="●  Nuova lezione", height=46,
                                       font=ctk.CTkFont(size=15, weight="bold"),
                                       fg_color="#d93636", hover_color="#b52b2b", command=self.avvia)
        self.btn_pausa = ctk.CTkButton(b, text="❚❚  Pausa", height=40, command=self.pausa,
                                       fg_color="#e0a412", hover_color="#c18c0c")
        self.btn_ferma = ctk.CTkButton(b, text="■  Ferma e crea appunti", height=40, command=self.ferma,
                                       fg_color="#2f6fdf", hover_color="#2459b8")

        self.banner = ctk.CTkFrame(tab, fg_color="#fdebd0", corner_radius=10)
        self.banner.grid_columnconfigure(0, weight=1)
        self.lbl_banner = ctk.CTkLabel(self.banner, text="", text_color="#7a4a00", anchor="w", justify="left")
        self.lbl_banner.grid(row=0, column=0, sticky="w", padx=12, pady=10)
        ctk.CTkButton(self.banner, text="Continua a registrare", width=170, command=self._rinvia_stop,
                      fg_color="#ec7a08", hover_color="#c96706").grid(row=0, column=1, padx=10)

        self.banner_agg = ctk.CTkFrame(tab, fg_color="#e3edfb", corner_radius=10)
        self.banner_agg.grid_columnconfigure(0, weight=1)
        self.lbl_agg = ctk.CTkLabel(self.banner_agg, text="", text_color="#1d3f7a", anchor="w", justify="left",
                                    wraplength=330)
        self.lbl_agg.grid(row=0, column=0, rowspan=2, sticky="w", padx=12, pady=10)
        ctk.CTkButton(self.banner_agg, text="Aggiorna ora", width=120, command=self.aggiorna_programma
                      ).grid(row=0, column=1, padx=10, pady=(10, 2))
        ctk.CTkButton(self.banner_agg, text="Più tardi", width=120, fg_color="transparent", text_color="#1d3f7a",
                      hover_color="#d3e1f6", command=lambda: self._mostra_agg(None)
                      ).grid(row=1, column=1, padx=10, pady=(2, 10))
        self.info_agg = None

        # materiali della lezione in corso
        self.frm_mat = ctk.CTkFrame(tab, corner_radius=12, fg_color="#ffffff", border_width=1, border_color="#d5d8dc")
        self.frm_mat.grid_columnconfigure(0, weight=1)

        self.btn_dispensa = ctk.CTkButton(tab, text="📘  Visualizza dispensa", height=34, fg_color="#e9eef6",
                                          text_color="#1d3f7a", hover_color="#dbe4f2", command=self.apri_dispensa)
        self.btn_dispensa.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 8))

        ctk.CTkLabel(tab, text="Ultime frasi trascritte", font=ctk.CTkFont(weight="bold")
                     ).grid(row=5, column=0, sticky="w", padx=4, pady=(4, 2))
        self.txt_live = ctk.CTkTextbox(tab, wrap="word", height=160)
        self.txt_live.grid(row=6, column=0, sticky="nsew", padx=4, pady=(0, 4))
        tab.grid_rowconfigure(6, weight=1)
        self._scrivi_live("Premi «Nuova lezione»: qui compariranno le frasi man mano che vengono trascritte.", reset=True)

    def _disegna_materiali(self):
        ctk = self.ctk
        for c in self.frm_mat.winfo_children():
            c.destroy()
        cur = self.lezione_corrente
        if not cur:
            self.frm_mat.grid_remove()
            return
        self.frm_mat.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 8))
        l = corsi.lezione(self.cfg, cur["corso"], cur["id"]) or {"materiali": []}
        ctk.CTkLabel(self.frm_mat, text="Materiali di questa lezione", font=ctk.CTkFont(weight="bold"), anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        b = ctk.CTkButton(self.frm_mat, text="+ Aggiungi", width=100, height=28)
        b.configure(command=lambda: self.menu_aggiungi(b, cur["corso"], cur["id"]))
        b.grid(row=0, column=1, columnspan=2, padx=12, pady=(10, 4), sticky="e")
        r = 1
        for m in l["materiali"]:
            quando = f"aggiunto al min {m['minuto']}" if m.get("minuto") is not None else ""
            ctk.CTkLabel(self.frm_mat, text=f"{materiali.icona(m['nome'])}  {m['nome']}", anchor="w"
                         ).grid(row=r, column=0, sticky="w", padx=14)
            ctk.CTkLabel(self.frm_mat, text=quando, text_color=GRIGIO).grid(row=r, column=1, padx=6)
            ctk.CTkButton(self.frm_mat, text="✕", width=28, height=24, fg_color="transparent", text_color=GRIGIO,
                          hover_color="#eef1f5",
                          command=lambda x=m: self.rimuovi_materiale(cur["corso"], cur["id"], x)
                          ).grid(row=r, column=2, padx=(0, 10))
            r += 1
        if not l["materiali"]:
            suggerimento = "Trascina qui slide, dispense o foto, oppure usa «+ Aggiungi»." if self.dnd else \
                "Usa «+ Aggiungi» per allegare slide, dispense o foto."
            ctk.CTkLabel(self.frm_mat, text=suggerimento, text_color=GRIGIO
                         ).grid(row=r, column=0, columnspan=3, sticky="w", padx=14)
            r += 1
        ctk.CTkFrame(self.frm_mat, height=8, fg_color="transparent").grid(row=r, column=0)

    # ------------------------------------------------------------------ menu «+ Aggiungi»
    def menu_aggiungi(self, bottone, corso, lezione_id):
        import tkinter as tk
        from tkinter import filedialog

        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 10))

        def scegli():
            nomi = filedialog.askopenfilenames(title="Aggiungi materiale", filetypes=TIPI_FILE)
            if nomi:
                self.allega([Path(n) for n in nomi], corso, lezione_id)
        menu.add_command(label="Scegli file…", command=scegli)
        ultimo = materiali.ultimo_scaricato(corsi.nomi_materiali_usati(self.cfg))
        if ultimo:
            menu.add_command(label=f"Ultimo scaricato: {ultimo.name}",
                             command=lambda: self.allega([ultimo], corso, lezione_id))
        recenti = corsi.materiali_recenti(self.cfg)
        if recenti:
            menu.add_separator()
            menu.add_command(label="Materiali recenti", state="disabled")
            for nome, p in recenti:
                menu.add_command(label=f"   {materiali.icona(nome)} {nome}",
                                 command=lambda x=p: self.allega([x], corso, lezione_id))
        try:
            menu.tk_popup(bottone.winfo_rootx(), bottone.winfo_rooty() + bottone.winfo_height())
        finally:
            menu.grab_release()

    def allega(self, percorsi, corso, lezione_id):
        from tkinter import messagebox
        cur = self.lezione_corrente
        dal_vivo = cur and cur["id"] == lezione_id and self.sessione
        minuto = self.sessione.minuto_attuale() if dal_vivo else None
        errori = []
        for p in percorsi:
            try:
                corsi.aggiungi_materiale(self.cfg, corso, lezione_id, p, minuto=minuto)
            except Exception as e:
                errori.append(str(e))
        if errori:
            messagebox.showwarning(core.APP_NOME, "\n\n".join(errori))
        self.dopo_cambio_materiali(corso, lezione_id)

    def rimuovi_materiale(self, corso, lezione_id, m):
        corsi.rimuovi_materiale(self.cfg, corso, lezione_id, m["file"])
        self.dopo_cambio_materiali(corso, lezione_id)

    def dopo_cambio_materiali(self, corso, lezione_id):
        cur = self.lezione_corrente
        if cur and cur["id"] == lezione_id and self.sessione:
            s = self.sessione
            # aggiorna il vocabolario di Whisper senza bloccare la finestra
            threading.Thread(target=lambda: setattr(
                s, "termini", corsi.termini_lezione(self.cfg, corso, corsi.lezione(self.cfg, corso, lezione_id))),
                daemon=True).start()
        self._disegna_materiali()
        if self.finestra_dispensa:
            self.finestra_dispensa.aggiorna()

    # ------------------------------------------------------------------ UI: scheda Appunti
    def _scheda_appunti(self, tab):
        ctk = self.ctk
        tab.grid_columnconfigure(0, weight=1)
        self.frm_recupero = ctk.CTkFrame(tab, fg_color="#fdebd0", corner_radius=10)
        self.frm_recupero.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 4))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Appunti recenti", font=ctk.CTkFont(size=16, weight="bold")
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(top, text="Apri cartella", width=110, command=self.apri_cartella
                      ).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkButton(top, text="Aggiorna", width=90, fg_color="#8a8f98", hover_color="#6f747c",
                      command=self.aggiorna_appunti).grid(row=0, column=2, padx=(6, 0))
        self.lst_appunti = ctk.CTkScrollableFrame(tab)
        self.lst_appunti.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.lst_appunti.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

    def aggiorna_appunti(self):
        ctk = self.ctk
        for w in self.frm_recupero.winfo_children():
            w.destroy()
        cur_id = self.lezione_corrente["id"] if self.lezione_corrente else None
        da_fare = corsi.lezioni_da_completare(self.cfg, escludi_id=cur_id)
        if da_fare:
            self.frm_recupero.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
            ctk.CTkLabel(self.frm_recupero, text="Lezioni da completare", text_color="#7a4a00",
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(self.frm_recupero, text="Registrate ma senza appunti (programma chiuso, connessione assente…).",
                         text_color="#7a4a00").grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
            for i, (corso, l) in enumerate(da_fare):
                riga = 2 + i
                ctk.CTkLabel(self.frm_recupero, anchor="w", text_color="#4a3000",
                             text=f"{corso} · {corsi.titolo_capitolo(l)} · "
                                  f"{dt.datetime.fromisoformat(l['inizio']):%d/%m %H:%M}"
                             ).grid(row=riga, column=0, sticky="w", padx=12, pady=4)
                if l.get("trascrizione"):
                    ctk.CTkButton(self.frm_recupero, text="Crea appunti", width=110,
                                  command=lambda c=corso, x=l: self.crea_appunti_di(c, x["id"])
                                  ).grid(row=riga, column=1, padx=4)
                ctk.CTkButton(self.frm_recupero, text="Elimina", width=80, fg_color="#8a8f98",
                              hover_color="#6f747c", command=lambda c=corso, x=l: self.elimina_lezione(c, x)
                              ).grid(row=riga, column=2, padx=(4, 12))
        else:
            self.frm_recupero.grid_remove()

        for w in self.lst_appunti.winfo_children():
            w.destroy()
        files = [p for p in core.appunti_recenti(self.cfg) if not p.name.startswith("Dispensa – ")]
        if not files:
            ctk.CTkLabel(self.lst_appunti, text="Nessun appunto ancora: registra la prima lezione!",
                         text_color=GRIGIO).grid(row=0, column=0, pady=20)
        for i, p in enumerate(files):
            data = dt.datetime.fromtimestamp(p.stat().st_mtime)
            ctk.CTkLabel(self.lst_appunti, anchor="w", justify="left",
                         text=f"{p.parent.name}\n{p.stem}", font=ctk.CTkFont(size=12)
                         ).grid(row=i, column=0, sticky="w", padx=6, pady=4)
            ctk.CTkLabel(self.lst_appunti, text=f"{data:%d/%m %H:%M}", text_color=GRIGIO).grid(row=i, column=1, padx=6)
            ctk.CTkButton(self.lst_appunti, text="Apri", width=70, command=lambda x=p: self.sistema.apri(x)
                          ).grid(row=i, column=2, padx=6)
        if self.finestra_dispensa:
            self.finestra_dispensa.aggiorna()

    # ------------------------------------------------------------------ UI: scheda Impostazioni
    def _scheda_impostazioni(self, tab):
        ctk = self.ctk
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        s = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        s.grid(row=0, column=0, sticky="nsew")
        s.grid_columnconfigure(0, weight=1)
        bold = ctk.CTkFont(weight="bold")
        r = 0

        def titolo(testo, aiuto=None):
            nonlocal r
            ctk.CTkLabel(s, text=testo, font=bold, anchor="w").grid(row=r, column=0, sticky="w", pady=(12, 0))
            r += 1
            if aiuto:
                ctk.CTkLabel(s, text=aiuto, text_color=GRIGIO, anchor="w", justify="left", wraplength=520
                             ).grid(row=r, column=0, sticky="w")
                r += 1

        titolo("Chiave API di Claude", "Si crea su platform.claude.com → Chiavi API. Incolla qui la chiave "
                                       "(inizia con sk-ant-).")
        fk = ctk.CTkFrame(s, fg_color="transparent")
        fk.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        fk.grid_columnconfigure(0, weight=1)
        self.ent_chiave = ctk.CTkEntry(fk, show="•", height=34, placeholder_text="sk-ant-…")
        self.ent_chiave.grid(row=0, column=0, sticky="ew")
        self.ent_chiave.insert(0, self.cfg.get("chiave_api_anthropic", ""))
        self.ent_chiave.bind("<FocusOut>", lambda e: self._pulisci_chiave())
        self.ent_chiave.bind("<<Paste>>", lambda e: self.root.after(50, self._pulisci_chiave))
        self.var_mostra = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(fk, text="Mostra", variable=self.var_mostra, width=70,
                        command=lambda: self.ent_chiave.configure(show="" if self.var_mostra.get() else "•")
                        ).grid(row=0, column=1, padx=6)
        self.btn_verifica = ctk.CTkButton(fk, text="Verifica", width=90, command=self.verifica_chiave)
        self.btn_verifica.grid(row=0, column=2)
        self.lbl_verifica = ctk.CTkLabel(s, text="", anchor="w")
        self.lbl_verifica.grid(row=r, column=0, sticky="w"); r += 1

        titolo("Qualità della trascrizione", "Veloce: per PC lenti. Standard: consigliata. "
                                             "Preciso: meno errori su nomi e numeri, ma richiede un PC più potente.")
        self.seg_qualita = ctk.CTkSegmentedButton(s, values=list(QUALITA_ETICHETTE.values()))
        self.seg_qualita.grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        self.seg_qualita.set(QUALITA_ETICHETTE[self.cfg["qualita_trascrizione"]])

        titolo("Contenuti presenti solo nei materiali", "Cosa fare con ciò che è nelle slide o nelle dispense "
                                                         "ma il docente non spiega a lezione.")
        self.opt_extra = ctk.CTkOptionMenu(s, values=list(EXTRA_OPZIONI.keys()), width=300)
        self.opt_extra.grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        self.opt_extra.set(next(k for k, v in EXTRA_OPZIONI.items()
                                if v == self.cfg.get("contenuti_solo_materiali", "segna")))

        titolo("Cartella degli appunti")
        fc = ctk.CTkFrame(s, fg_color="transparent")
        fc.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        fc.grid_columnconfigure(0, weight=1)
        self.ent_cartella = ctk.CTkEntry(fc, height=34)
        self.ent_cartella.grid(row=0, column=0, sticky="ew")
        self.ent_cartella.insert(0, str(core.cartella_appunti(self.cfg)))
        ctk.CTkButton(fc, text="Cambia…", width=90, command=self._scegli_cartella).grid(row=0, column=1, padx=(6, 0))

        titolo("Stop automatico", "Se non arriva audio per questo tempo la lezione viene chiusa e trasformata "
                                  "in appunti. Un minuto prima compare un avviso.")
        self.opt_stop = ctk.CTkOptionMenu(s, values=list(STOP_OPZIONI.keys()))
        self.opt_stop.grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        minuti = int(self.cfg.get("minuti_silenzio_stop_automatico", 8))
        self.opt_stop.set(next((k for k, v in STOP_OPZIONI.items() if v == minuti), f"{minuti} minuti"))

        titolo("Comportamento")
        self.var_solo_browser = ctk.BooleanVar(value=bool(self.cfg.get("solo_browser", True)))
        ctk.CTkSwitch(s, text="Registra solo la lezione (browser, Zoom, Teams): silenzia Spotify, notifiche e il resto",
                      variable=self.var_solo_browser).grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        self.var_apri = ctk.BooleanVar(value=bool(self.cfg.get("apri_appunti_al_termine", True)))
        ctk.CTkSwitch(s, text="Apri gli appunti appena pronti", variable=self.var_apri
                      ).grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1
        self.var_avvio = ctk.BooleanVar(value=self.sistema.avvio_automatico_attivo())
        ctk.CTkSwitch(s, text="Avvia con Windows (parte ridotto vicino all'orologio)", variable=self.var_avvio
                      ).grid(row=r, column=0, sticky="w", pady=(6, 0)); r += 1

        titolo("Come vuoi gli appunti", "Scrivilo a parole: Claude seguirà queste istruzioni.")
        self.txt_stile = ctk.CTkTextbox(s, height=170, wrap="word")
        self.txt_stile.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        self.txt_stile.insert("1.0", self.cfg.get("stile_appunti", ""))

        titolo("Aggiornamenti")
        fa = ctk.CTkFrame(s, fg_color="transparent")
        fa.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        ctk.CTkLabel(fa, text=f"Versione installata: {core.APP_VERSIONE}").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.btn_controlla = ctk.CTkButton(fa, text="Controlla aggiornamenti", width=180,
                                           command=lambda: self.controlla_aggiornamenti(manuale=True))
        self.btn_controlla.grid(row=0, column=1)
        self.lbl_agg_stato = ctk.CTkLabel(s, text="", text_color=GRIGIO, anchor="w")
        self.lbl_agg_stato.grid(row=r, column=0, sticky="w"); r += 1
        import aggiornamenti
        prec = aggiornamenti.versione_precedente()
        if prec:
            ctk.CTkButton(s, text=f"Torna alla versione precedente ({prec})", width=260, fg_color="#8a8f98",
                          hover_color="#6f747c", command=self.torna_indietro).grid(row=r, column=0, sticky="w", pady=(4, 0))
            r += 1

        fs = ctk.CTkFrame(s, fg_color="transparent")
        fs.grid(row=r, column=0, sticky="ew", pady=(14, 8)); r += 1
        ctk.CTkButton(fs, text="Salva impostazioni", height=38, command=self.salva_impostazioni).grid(row=0, column=0)
        self.lbl_salvato = ctk.CTkLabel(fs, text="", text_color="#1e8449")
        self.lbl_salvato.grid(row=0, column=1, padx=10)

    # ------------------------------------------------------------------ tray
    def _avvia_tray(self):
        try:
            import pystray
        except Exception:
            return
        M = pystray.MenuItem
        self.tray = pystray.Icon(
            "appunti_lezioni", icona_tray("caricamento"), core.APP_NOME,
            menu=pystray.Menu(
                M("Mostra finestra", lambda: self.ui_q.put(("mostra",)), default=True),
                M(lambda i: "Ferma e crea appunti" if self.sessione else "Nuova lezione",
                  lambda: self.ui_q.put(("ferma",) if self.sessione else ("avvia_da_tray",))),
                pystray.Menu.SEPARATOR,
                M("Esci", lambda: self.ui_q.put(("esci",))),
            ),
        )
        try:
            self.tray.run_detached()
        except Exception:
            log("Icona nella barra non disponibile:\n" + traceback.format_exc())
            self.tray = None

    def notifica(self, titolo, testo):
        log(f"{titolo}: {testo}")
        if self.tray:
            try:
                self.tray.notify(testo, titolo)
            except Exception:
                pass

    def mostra(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def nascondi(self):
        self.root.withdraw()
        if not self.avvisato_tray:
            self.notifica(core.APP_NOME, "Continuo a funzionare qui vicino all'orologio. "
                                         "Clic sull'icona per riaprire la finestra.")
            self.avvisato_tray = True

    def esci(self):
        from tkinter import messagebox
        if self.sessione or self.stato == "elabora":
            self.mostra()
            if not messagebox.askyesno(core.APP_NOME, "C'è una lezione in corso. Se esci ora, la "
                                       "trascrizione resta salvata e potrai creare gli appunti alla "
                                       "prossima apertura.\n\nUscire comunque?"):
                return
            if self.sessione:
                try:
                    self.sessione.registratore.ferma()
                except Exception:
                    pass
        if self.isolamento:
            self.isolamento.ferma()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    # ------------------------------------------------------------------ ciclo UI
    def _tick(self):
        try:
            while True:
                self._gestisci(self.ui_q.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            log(traceback.format_exc())
        try:
            self._aggiorna_live()
        except Exception:
            log(traceback.format_exc())
        self.root.after(150, self._tick)

    def _gestisci(self, msg):
        from tkinter import messagebox
        tipo = msg[0]
        if tipo == "stato":
            self.stato, self.dettaglio = msg[1], msg[2]
            self._aggiorna_stato_ui()
        elif tipo == "testo":
            self._scrivi_live(msg[1])
        elif tipo == "mostra":
            self.mostra()
        elif tipo == "avvia_da_tray":
            self.mostra()
            self.avvia()
        elif tipo == "ferma":
            self.ferma()
        elif tipo == "esci":
            self.esci()
        elif tipo == "apri":
            self.sistema.apri(msg[1])
        elif tipo == "avviso":
            messagebox.showinfo(core.APP_NOME, msg[1])
        elif tipo == "fatto":
            path = msg[1]
            self.stato, self.dettaglio = "pronto", f"Appunti pronti: {path.name}"
            self._aggiorna_stato_ui()
            self.aggiorna_appunti()
            self.notifica("Appunti pronti", path.name)
            if self.cfg.get("apri_appunti_al_termine"):
                self.sistema.apri(path)
            self._dopo_lavorazione()
        elif tipo == "errore_appunti":
            self.stato, self.dettaglio = "pronto", "Appunti non creati: la lezione è tra quelle da completare"
            self._aggiorna_stato_ui()
            self.aggiorna_appunti()
            self.notifica("Appunti non creati", msg[1])
            self.mostra()
            self.tabs.set("Appunti")
            messagebox.showwarning(core.APP_NOME, f"Non sono riuscito a creare gli appunti:\n\n{msg[1]}\n\n"
                                   "La trascrizione è al sicuro: trovi la lezione nella scheda Appunti, "
                                   "con il pulsante «Crea appunti» per riprovare.")
            self._dopo_lavorazione()
        elif tipo == "vuota":
            self.stato, self.dettaglio = "pronto", "Nessun audio registrato: la lezione era in riproduzione?"
            self._aggiorna_stato_ui()
            self.aggiorna_appunti()
            self.notifica("Nessun audio", self.dettaglio)
            self._dopo_lavorazione()
        elif tipo == "aggiornamento":
            info, manuale = msg[1], msg[2]
            if info:
                self._mostra_agg(info)
                self.lbl_agg_stato.configure(text=f"È disponibile la versione {info['versione']}.")
                if manuale:
                    self.tabs.set("Lezione")
            else:
                self.lbl_agg_stato.configure(text=msg[3] if len(msg) > 3 else "Hai già l'ultima versione.")
            self.btn_controlla.configure(state="normal")
        elif tipo == "aggiornato":
            messagebox.showinfo(core.APP_NOME, f"Aggiornato alla versione {msg[1]}.\n\nIl programma ora si riavvia.")
            self._riavvia()
        elif tipo == "aggiornamento_fallito":
            self.stato, self.dettaglio = "pronto", "Aggiornamento non riuscito: il programma è rimasto com'era."
            self._aggiorna_stato_ui()
            messagebox.showwarning(core.APP_NOME, msg[1])
        elif tipo == "verifica":
            ok, testo = msg[1], msg[2]
            self.btn_verifica.configure(state="normal")
            self.lbl_verifica.configure(text=("✔ " if ok else "✖ ") + testo,
                                        text_color="#1e8449" if ok else "#c0392b")

    def _aggiorna_stato_ui(self):
        colore = COLORI[self.stato]
        self.lbl_pallino.configure(text_color=colore)
        self.lbl_stato.configure(text=TESTI_STATO[self.stato])
        self.lbl_dettaglio.configure(text=self.dettaglio)
        reg = self.stato in ("registra", "pausa")
        if reg:
            self.btn_avvia.grid_remove()
            self.btn_pausa.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            self.btn_ferma.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(4, 0))
            self.btn_pausa.configure(text="▶  Riprendi" if self.stato == "pausa" else "❚❚  Pausa")
            self.btn_modifica.grid(row=1, column=2, padx=(16, 4), sticky="e")
        else:
            self.btn_pausa.grid_remove()
            self.btn_ferma.grid_remove()
            self.btn_modifica.grid_remove()
            self.btn_avvia.grid(row=0, column=0, columnspan=3, sticky="ew")
            self.btn_avvia.configure(state="normal" if self.stato == "pronto" else "disabled")
            self.lbl_timer.configure(text="")
            self.barra_livello.set(0)
        self._disegna_materiali()
        if hasattr(self, "banner_agg"):
            self._mostra_agg(self.info_agg)
        if self.tray:
            try:
                self.tray.icon = icona_tray(self.stato)
                self.tray.title = f"{core.APP_NOME} – {TESTI_STATO[self.stato]}"
                self.tray.update_menu()
            except Exception:
                pass

    def _aggiorna_live(self):
        s = self.sessione
        if not s:
            self._mostra_banner(False)
            return
        reg = s.registratore
        durata = int((dt.datetime.now() - s.inizio).total_seconds())
        self.lbl_timer.configure(text=f"{durata // 3600}:{durata // 60 % 60:02d}:{durata % 60:02d}"
                                 if durata >= 3600 else f"{durata // 60}:{durata % 60:02d}")
        livello = reg.livello_attuale()
        self.barra_livello.set(min(1.0, (livello / 0.15) ** 0.5) if livello > 0 else 0)
        n = len(s.testi)
        parti = "1 parte trascritta" if n == 1 else f"{n} parti trascritte"
        attesa = s.in_ritardo()
        if attesa > 1:
            parti += f" · {attesa} in attesa"
        intestazione = f"{s.corso} · {s.titolo}"
        self.lbl_dettaglio.configure(text=f"{intestazione}\n{'in pausa' if reg.in_pausa else parti}")

        limite = float(self.cfg.get("minuti_silenzio_stop_automatico", 8)) * 60
        if limite > 0 and not reg.in_pausa:
            silenzio = reg.secondi_di_silenzio()
            preavviso = min(60.0, limite / 2)
            if silenzio >= limite:
                log("Silenzio prolungato: stop automatico.")
                self._mostra_banner(False)
                self.ferma()
                return
            if silenzio >= limite - preavviso:
                resto = int(limite - silenzio)
                self.lbl_banner.configure(text=f"Non sento audio da {int(silenzio // 60)} min.\n"
                                               f"Chiudo la lezione e creo gli appunti tra {resto} s.")
                self._mostra_banner(True)
                if not self.notificato_stop:
                    self.notifica("Lezione ferma?", f"Nessun audio: chiudo la lezione tra {resto} secondi. "
                                                    "Apri la finestra per continuare a registrare.")
                    self.notificato_stop = True
                return
        self._mostra_banner(False)

    def _mostra_banner(self, visibile):
        if visibile and not self.banner_visibile:
            self.banner.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 8))
        elif not visibile and self.banner_visibile:
            self.banner.grid_remove()
            self.notificato_stop = False
        self.banner_visibile = visibile

    def _rinvia_stop(self):
        if self.sessione:
            self.sessione.registratore.rinvia_stop()
        self._mostra_banner(False)

    def _scrivi_live(self, testo, reset=False):
        """reset=True mostra un messaggio provvisorio, che sparisce alla prima frase trascritta."""
        self.txt_live.configure(state="normal")
        if reset or self._live_provvisorio:
            self.txt_live.delete("1.0", "end")
        self._live_provvisorio = reset
        self.txt_live.insert("end", testo if reset else testo + "\n\n")
        self.txt_live.see("end")
        self.txt_live.configure(state="disabled")

    # ------------------------------------------------------------------ modello
    def _carica_modello(self):
        qualita = self.cfg["qualita_trascrizione"]
        self.ui_q.put(("stato", "caricamento", "Carico il modello di trascrizione…"))
        try:
            self.trascrittore = core.Trascrittore(qualita, self.cfg.get("lingua", "it"),
                                                  on_stato=lambda m: self.ui_q.put(("stato", "caricamento", m)))
            self.ui_q.put(("stato", "pronto", f"Trascrizione: {QUALITA_ETICHETTE[qualita]}. "
                                              "Premi «Nuova lezione» per iniziare."))
        except Exception as e:
            log(traceback.format_exc())
            self.ui_q.put(("stato", "errore", f"Modello di trascrizione non caricato: {e}"))

    def _dopo_lavorazione(self):
        if self.ricarica_modello_dopo:
            self.ricarica_modello_dopo = False
            self.trascrittore = None
            threading.Thread(target=self._carica_modello, daemon=True).start()

    # ------------------------------------------------------------------ lezione
    def avvia(self):
        from tkinter import messagebox
        if self.stato != "pronto" or self.sessione:
            return
        if not self.cfg.get("chiave_api_anthropic") and not messagebox.askyesno(
                core.APP_NOME, "Manca la chiave API: la lezione verrà registrata e trascritta, ma gli "
                               "appunti potrai crearli solo dopo aver inserito la chiave.\n\nContinuare?"):
            return
        FinestraLezione(self)

    def inizia_lezione(self, corso, titolo, file_materiali):
        from tkinter import messagebox
        cfg = self.cfg
        cfg["corsi"] = [corso] + [c for c in cfg.get("corsi", []) if c.casefold() != corso.casefold()]
        cfg["ultimo_corso"] = corso
        core.save_config(cfg)
        inizio = dt.datetime.now()
        lid = f"{inizio:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        lez = corsi.nuova_lezione(cfg, corso, titolo, lid, inizio)
        errori = []
        for p in file_materiali:
            try:
                corsi.aggiungi_materiale(cfg, corso, lid, p, minuto=0)
            except Exception as e:
                errori.append(str(e))
        lez = corsi.lezione(cfg, corso, lid)
        try:
            self.sessione = core.Sessione(cfg, corso, lez["titolo"], self.trascrittore,
                                          on_testo=lambda t: self.ui_q.put(("testo", t)), lezione_id=lid,
                                          termini=corsi.termini_lezione(cfg, corso, lez))
        except Exception as e:
            log(traceback.format_exc())
            corsi.elimina_lezione(cfg, corso, lid)
            messagebox.showerror(core.APP_NOME, f"Non riesco ad avviare la registrazione:\n\n{e}")
            return
        self.lezione_corrente = {"corso": corso, "id": lid, "titolo": lez["titolo"]}
        if self.var_solo_browser.get():
            self.isolamento = self.sistema.IsolamentoAudio()
            self.isolamento.avvia()
        self.sessione.registratore.avvia()
        self._scrivi_live("In ascolto… fai partire la lezione.", reset=True)
        self.stato, self.dettaglio = "registra", f"{corso} · {lez['titolo']}"
        self._aggiorna_stato_ui()
        if self.finestra_dispensa:
            self.finestra_dispensa.aperte.add(lid)
            self.finestra_dispensa.aggiorna()
        log(f"Registrazione avviata: {corso} – {lez['titolo']} ({len(file_materiali)} materiali)")
        if errori:
            messagebox.showwarning(core.APP_NOME, "\n\n".join(errori))

    def modifica_lezione(self):
        cur = self.lezione_corrente
        if cur:
            FinestraLezione(self, modifica=(cur["corso"], self.sessione.titolo))

    def applica_modifica(self, corso, titolo):
        cur, s = self.lezione_corrente, self.sessione
        if not cur or not s:
            return
        lez = corsi.rinomina_lezione(self.cfg, cur["corso"], cur["id"], corso, titolo)
        cur.update(corso=corso, titolo=lez["titolo"])
        s.corso, s.titolo = corso, lez["titolo"]
        s.salva_meta()
        self.dettaglio = f"{corso} · {lez['titolo']}"
        self._aggiorna_stato_ui()
        if self.finestra_dispensa:
            self.finestra_dispensa.aggiorna()

    def pausa(self):
        if not self.sessione:
            return
        reg = self.sessione.registratore
        reg.pausa(not reg.in_pausa)
        self.stato = "pausa" if reg.in_pausa else "registra"
        self._aggiorna_stato_ui()

    def ferma(self):
        s, cur = self.sessione, self.lezione_corrente
        if not s:
            return
        self.sessione = None
        self.stato, self.dettaglio = "elabora", "Trascrivo gli ultimi minuti…"
        self._aggiorna_stato_ui()
        threading.Thread(target=self._completa, args=(s, cur), daemon=True).start()

    def _completa(self, s, cur):
        try:
            testo = s.termina()
        finally:
            if self.isolamento:
                self.isolamento.ferma()
                self.isolamento = None
        self.lezione_corrente = None
        corso, lid = cur["corso"], cur["id"]
        if not testo.strip():
            corsi.elimina_lezione(self.cfg, corso, lid)
            s.chiudi()
            self.ui_q.put(("vuota",))
            return
        corsi.salva_trascrizione(self.cfg, corso, lid, testo)
        s.chiudi()
        self.ui_q.put(("stato", "elabora", "Claude sta scrivendo gli appunti…"))
        try:
            path = corsi.crea_appunti_lezione(self.cfg, corso, lid)
            self.ui_q.put(("fatto", path))
        except Exception as e:
            log(traceback.format_exc())
            self.ui_q.put(("errore_appunti", core.messaggio_errore(e)))

    def crea_appunti_di(self, corso, lezione_id):
        from tkinter import messagebox
        if self.stato != "pronto":
            messagebox.showinfo(core.APP_NOME, "Aspetta che finisca la lezione in corso.")
            return
        l = corsi.lezione(self.cfg, corso, lezione_id)
        self.stato, self.dettaglio = "elabora", f"Creo gli appunti di {corso} · {l['titolo']}…"
        self._aggiorna_stato_ui()
        self.tabs.set("Lezione")

        def lavoro():
            try:
                self.ui_q.put(("fatto", corsi.crea_appunti_lezione(self.cfg, corso, lezione_id)))
            except Exception as e:
                log(traceback.format_exc())
                self.ui_q.put(("errore_appunti", core.messaggio_errore(e)))
        threading.Thread(target=lavoro, daemon=True).start()

    def elimina_lezione(self, corso, l):
        from tkinter import messagebox
        if messagebox.askyesno(core.APP_NOME, f"Eliminare definitivamente «{l['titolo']}» di {corso}?\n"
                                              "Trascrizione e materiali collegati non saranno più nella dispensa."):
            corsi.elimina_lezione(self.cfg, corso, l["id"])
            self.aggiorna_appunti()

    def apri_dispensa(self):
        corso = self.lezione_corrente["corso"] if self.lezione_corrente else self.cfg.get("ultimo_corso", "")
        if not corso:
            corsi_esistenti = core.elenco_corsi(self.cfg)
            corso = corsi_esistenti[0] if corsi_esistenti else ""
        if not corso:
            from tkinter import messagebox
            messagebox.showinfo(core.APP_NOME, "Non c'è ancora nessun corso: registra la prima lezione.")
            return
        if self.finestra_dispensa:
            self.finestra_dispensa.cmb.set(corso)
            self.finestra_dispensa.aggiorna()
            self.finestra_dispensa.win.lift()
            return
        self.finestra_dispensa = FinestraDispensa(self, corso)

    # ------------------------------------------------------------------ aggiornamenti
    def _mostra_agg(self, info):
        self.info_agg = info
        if info and self.stato == "pronto":
            note = info["note"].splitlines()
            riassunto = "\n".join(n.lstrip("-*• ").strip() for n in note[:3] if n.strip())
            self.lbl_agg.configure(text=f"È disponibile la versione {info['versione']}"
                                        + (f"\n{riassunto}" if riassunto else ""))
            self.banner_agg.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 8))
        else:
            self.banner_agg.grid_remove()

    def controlla_aggiornamenti(self, manuale=False):
        import aggiornamenti
        repo = self.cfg.get("repo_aggiornamenti", "")
        if manuale:
            self.btn_controlla.configure(state="disabled")
            self.lbl_agg_stato.configure(text="Controllo…")

        def lavoro():
            try:
                info = aggiornamenti.controlla(repo)
                self.cfg["ultimo_controllo_aggiornamenti"] = dt.date.today().isoformat()
                core.save_config(self.cfg)
                self.ui_q.put(("aggiornamento", info, manuale))
            except Exception as e:
                log(f"Controllo aggiornamenti: {e}")
                self.ui_q.put(("aggiornamento", None, manuale, f"Controllo non riuscito: {e}"))
        threading.Thread(target=lavoro, daemon=True).start()

    def _controllo_automatico(self):
        if self.cfg.get("repo_aggiornamenti") and \
                self.cfg.get("ultimo_controllo_aggiornamenti") != dt.date.today().isoformat():
            self.controlla_aggiornamenti()

    def aggiorna_programma(self):
        import aggiornamenti
        from tkinter import messagebox
        info = self.info_agg
        if not info:
            return
        if self.stato != "pronto":
            messagebox.showinfo(core.APP_NOME, "Aggiorna quando non c'è una lezione in corso.")
            return
        self._mostra_agg(None)
        self.stato, self.dettaglio = "elabora", "Aggiornamento in corso…"
        self._aggiorna_stato_ui()
        self.lbl_stato.configure(text="Aggiornamento")

        def lavoro():
            try:
                v = aggiornamenti.installa(info, lambda m: self.ui_q.put(("stato", "elabora", m)))
                self.ui_q.put(("aggiornato", v))
            except Exception as e:
                log(traceback.format_exc())
                self.ui_q.put(("aggiornamento_fallito", str(e)))
        threading.Thread(target=lavoro, daemon=True).start()

    def torna_indietro(self):
        import aggiornamenti
        from tkinter import messagebox
        if self.stato != "pronto":
            messagebox.showinfo(core.APP_NOME, "Aspetta che finisca la lezione in corso.")
            return
        if not messagebox.askyesno(core.APP_NOME, f"Tornare alla versione {aggiornamenti.versione_precedente()}? "
                                                  "Appunti e impostazioni non vengono toccati."):
            return
        try:
            aggiornamenti.ripristina_precedente()
        except Exception as e:
            messagebox.showerror(core.APP_NOME, str(e))
            return
        self._riavvia()

    def _riavvia(self):
        import aggiornamenti
        if self.isolamento:
            self.isolamento.ferma()
        if self.tray:
            self.tray.stop()
        aggiornamenti.riavvia(["--attendi"])
        self.root.destroy()

    def apri_cartella(self):
        c = core.cartella_appunti(self.cfg)
        c.mkdir(parents=True, exist_ok=True)
        self.sistema.apri(c)

    # ------------------------------------------------------------------ impostazioni
    def _pulisci_chiave(self):
        grezza = self.ent_chiave.get()
        pulita = core.estrai_chiave(grezza)
        if pulita != grezza:
            self.ent_chiave.delete(0, "end")
            self.ent_chiave.insert(0, pulita)
            self.lbl_verifica.configure(text="Ho tenuto solo la chiave dal testo incollato.", text_color=GRIGIO)

    def verifica_chiave(self):
        self._pulisci_chiave()
        chiave = self.ent_chiave.get().strip()
        self.btn_verifica.configure(state="disabled")
        self.lbl_verifica.configure(text="Verifico…", text_color=GRIGIO)
        threading.Thread(target=lambda: self.ui_q.put(("verifica",) + core.verifica_chiave(chiave)),
                         daemon=True).start()

    def _scegli_cartella(self):
        from tkinter import filedialog
        c = filedialog.askdirectory(initialdir=self.ent_cartella.get() or None, title="Cartella degli appunti")
        if c:
            self.ent_cartella.delete(0, "end")
            self.ent_cartella.insert(0, str(Path(c)))

    def salva_impostazioni(self):
        self._pulisci_chiave()
        cfg = self.cfg
        cfg["chiave_api_anthropic"] = self.ent_chiave.get().strip()
        cartella = self.ent_cartella.get().strip()
        cfg["cartella_appunti"] = "" if cartella == str(core.cartella_documenti() / "Appunti lezioni") else cartella
        inv = {v: k for k, v in QUALITA_ETICHETTE.items()}
        nuova_qualita = inv.get(self.seg_qualita.get(), "standard")
        cfg["minuti_silenzio_stop_automatico"] = STOP_OPZIONI.get(self.opt_stop.get(),
                                                                 cfg["minuti_silenzio_stop_automatico"])
        cfg["contenuti_solo_materiali"] = EXTRA_OPZIONI.get(self.opt_extra.get(), "segna")
        cfg["solo_browser"] = bool(self.var_solo_browser.get())
        cfg["apri_appunti_al_termine"] = bool(self.var_apri.get())
        cfg["stile_appunti"] = self.txt_stile.get("1.0", "end").strip() or core.DEFAULT_CONFIG["stile_appunti"]
        avvio = bool(self.var_avvio.get())
        cfg["avvio_con_windows"] = avvio
        messaggio = "Impostazioni salvate"
        if nuova_qualita != cfg["qualita_trascrizione"]:
            cfg["qualita_trascrizione"] = nuova_qualita
            if self.stato in ("registra", "pausa", "elabora"):
                self.ricarica_modello_dopo = True
                messaggio += " · la nuova qualità vale dalla prossima lezione"
            elif self.stato != "caricamento":
                self.trascrittore = None
                threading.Thread(target=self._carica_modello, daemon=True).start()
                messaggio += " · carico il nuovo modello…"
        core.save_config(cfg)
        try:
            if avvio != self.sistema.avvio_automatico_attivo():
                self.sistema.imposta_avvio_automatico(avvio)
        except Exception as e:
            messaggio += f" · avvio con Windows non impostato ({e})"
        self.aggiorna_appunti()
        self.lbl_salvato.configure(text="✔ " + messaggio)
        self.root.after(6000, lambda: self.lbl_salvato.configure(text=""))
        if cfg["chiave_api_anthropic"]:
            self.verifica_chiave()

    def run(self):
        self.root.mainloop()


def installa():
    """Crea icona e collegamenti (chiamato da installa.bat)."""
    import sistema
    ico = core.DATI / "icona.ico"
    crea_icona(ico)
    creati = sistema.crea_collegamenti(ico)
    for c in creati:
        print(f"Collegamento creato: {c}")
    core.load_config()
    return bool(creati)


def main():
    args = sys.argv[1:]
    if "--installa" in args:
        sys.exit(0 if installa() else 1)
    if "--autotest" in args:
        import autotest
        sys.exit(0 if autotest.esegui() else 1)

    import sistema
    app_ref = {}
    mostra = lambda: app_ref["app"].ui_q.put(("mostra",)) if "app" in app_ref else None
    istanza = sistema.IstanzaUnica(mostra)
    if not istanza.prima and "--attendi" in args:   # riavvio dopo un aggiornamento
        import time
        for _ in range(30):
            time.sleep(0.5)
            istanza = sistema.IstanzaUnica(mostra)
            if istanza.prima:
                break
    if not istanza.prima:
        sistema.IstanzaUnica.chiedi_di_mostrare()
        return
    try:
        app = App(nascosto="--nascosto" in args)
        app_ref["app"] = app
        app.run()
    except Exception:
        log("Errore fatale:\n" + traceback.format_exc())
        try:
            from tkinter import messagebox
            messagebox.showerror(core.APP_NOME, "Si è verificato un errore. Dettagli nel file:\n"
                                 + str(core.LOG_PATH))
        except Exception:
            pass
        raise
    finally:
        try:
            sistema.ripristina_sospesi()
        except Exception:
            pass


if __name__ == "__main__":
    main()
