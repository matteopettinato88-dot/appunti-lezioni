#!/bin/bash
# Installazione (o reinstallazione) di Appunti Lezioni su macOS.
#
# Nel Terminale:
#   curl -fsSL https://raw.githubusercontent.com/matteopettinato88-dot/appunti-lezioni/main/installa.sh | bash
#
# Solo la prova automatica:      ... | bash -s prova
# Da una copia locale del codice: bash installa.sh   (dalla cartella del codice, con SORGENTE=.)
# Da un altro ramo:              ... | RAMO=nome-ramo bash
#
# Cosa fa: Strumenti da riga di comando di Apple (se mancano), Python 3.14 da python.org (se manca),
# programma in ~/Library/Application Support/AppuntiLezioni/programma, librerie, cattura audio,
# app "Appunti Lezioni" in ~/Applications, prova automatica.

set -u
REPO="matteopettinato88-dot/appunti-lezioni"
RAMO="${RAMO:-main}"
DATI="$HOME/Library/Application Support/AppuntiLezioni"
PROG="$DATI/programma"
APP="$HOME/Applications/Appunti Lezioni.app"
LOG="$DATI/installazione.log"

mkdir -p "$DATI"
echo "==== Installazione $(date) ====" >> "$LOG"

passo() { printf '\n  \033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
errore() {
    printf '\n  \033[31mERRORE:\033[0m %s\n  Dettagli in: %s\n\n' "$1" "$LOG"
    echo "ERRORE: $1" >> "$LOG"
    exit 1
}
attendi_invio() { read -r -p "  $1" _ < /dev/tty || true; }

# ---------------------------------------------------------------- prova automatica
prova() {
    local risultato="$PROG/autotest_risultato.txt"
    rm -f "$risultato"
    info "Il Mac dirà alcune frasi con una voce di prova: tieni il volume acceso."
    info "Se compaiono richieste di permesso (audio, cartella Documenti), rispondi «Consenti»."
    open -n -W "$APP" --args --autotest
    if [ -f "$risultato" ]; then
        echo
        sed 's/^/    /' "$risultato"
        cat "$risultato" >> "$LOG"
    else
        info "La prova non ha prodotto un risultato: guarda $DATI/appunti_lezioni.log"
    fi
}

prova_con_permesso() {
    prova
    if grep -q "Permesso di registrare l'audio: manca" "$PROG/autotest_risultato.txt" 2>/dev/null; then
        passo "Serve un permesso"
        info "Si apre Impostazioni di Sistema → Privacy e sicurezza → Registrazione schermo e audio di sistema."
        info "Attiva «Appunti Lezioni» (se macOS chiede di chiudere l'app, scegli «Più tardi»)."
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        attendi_invio "Quando l'hai attivato, premi Invio per ripetere la prova… "
        prova
    fi
}

if [ "${1:-}" = "prova" ]; then
    [ -d "$APP" ] || errore "Appunti Lezioni non è installato."
    passo "Prova automatica"
    prova_con_permesso
    exit 0
fi

echo
echo "  Installazione di Appunti Lezioni"
echo "  ================================"

[ "$(uname -s)" = "Darwin" ] || errore "Questo programma funziona solo su macOS."
MACOS="$(sw_vers -productVersion)"
[ "${MACOS%%.*}" -ge 13 ] 2>/dev/null || errore "Serve macOS 13 Ventura o successivo (questo Mac ha $MACOS)."
echo "macOS $MACOS, $(uname -m)" >> "$LOG"

# ---------------------------------------------------------------- 1. Strumenti di Apple
passo "[1/6] Strumenti da riga di comando di Apple"
if ! xcode-select -p >/dev/null 2>&1; then
    info "Si apre una finestra di macOS: scegli «Installa» e accetta la licenza."
    info "Il download richiede qualche minuto; questa installazione aspetta e poi prosegue da sola."
    xcode-select --install >> "$LOG" 2>&1 || true
    attese=0
    until xcode-select -p >/dev/null 2>&1; do
        sleep 10
        attese=$((attese + 1))
        [ $attese -lt 360 ] || errore "Gli Strumenti da riga di comando non risultano installati."
    done
fi
xcrun swiftc --version >> "$LOG" 2>&1 || errore "Il compilatore Swift non funziona. Prova: xcode-select --install"
info "Pronti."

# ---------------------------------------------------------------- 2. Python
passo "[2/6] Python"
trova_python() {
    for v in 3.14 3.13; do
        p="/Library/Frameworks/Python.framework/Versions/$v/bin/python$v"
        if [ -x "$p" ] && "$p" -c "import tkinter, ssl" >/dev/null 2>&1; then
            echo "$p"
            return 0
        fi
    done
    return 1
}
if ! PY="$(trova_python)"; then
    info "Scarico Python 3.14 da python.org…"
    URL=""
    for V in $(curl -fsSL https://www.python.org/ftp/python/ | grep -oE 'href="3\.14\.[0-9]+/"' \
               | grep -oE '3\.14\.[0-9]+' | sort -u -t. -k3,3nr); do
        if curl -fsIL "https://www.python.org/ftp/python/$V/python-$V-macos11.pkg" >/dev/null 2>&1; then
            URL="https://www.python.org/ftp/python/$V/python-$V-macos11.pkg"
            break
        fi
    done
    [ -n "$URL" ] || errore "Non trovo l'installer di Python. Installa Python 3.14 da python.org e rilancia."
    echo "Python: $URL" >> "$LOG"
    curl -fL --progress-bar "$URL" -o "/tmp/python-appunti.pkg" || errore "Download di Python non riuscito."
    info "Per installare Python serve la password del Mac (mentre la scrivi non si vede nulla)."
    sudo installer -pkg "/tmp/python-appunti.pkg" -target / >> "$LOG" 2>&1 || errore "Installazione di Python non riuscita."
    rm -f "/tmp/python-appunti.pkg"
    PY="$(trova_python)" || errore "Python installato ma non funzionante."
fi
echo "Python: $PY" >> "$LOG"
info "$("$PY" --version)"

# ---------------------------------------------------------------- 3. Programma
passo "[3/6] Scarico il programma"
TMP="$(mktemp -d)"
if [ -n "${SORGENTE:-}" ]; then
    SRC="$(cd "$SORGENTE" && pwd)"
else
    curl -fsSL "https://github.com/$REPO/archive/refs/heads/$RAMO.zip" -o "$TMP/programma.zip" \
        || errore "Download del programma non riuscito (ramo $RAMO)."
    unzip -q "$TMP/programma.zip" -d "$TMP" || errore "Archivio del programma non valido."
    SRC="$(dirname "$(find "$TMP" -maxdepth 2 -name app.py | head -1)")"
fi
[ -f "$SRC/app.py" ] || errore "Il programma scaricato è incompleto."
mkdir -p "$PROG"
pkill -f "AppuntiLezioni/programma/app.py" >/dev/null 2>&1 && sleep 2   # chiude il programma se è aperto
find "$SRC" -maxdepth 1 -type f \( -name '*.py' -o -name '*.swift' -o -name '*.sh' -o -name '*.txt' \
     -o -name '*.md' -o -name '*.json' \) -exec cp {} "$PROG/" \;
rm -rf "$TMP"
info "Versione $(grep -oE 'APP_VERSIONE = "[^"]+"' "$PROG/core.py" | cut -d'"' -f2) in $PROG"

# ---------------------------------------------------------------- 4. Librerie
passo "[4/6] Librerie (qualche minuto)"
if [ ! -x "$PROG/.venv/bin/python" ]; then
    "$PY" -m venv "$PROG/.venv" >> "$LOG" 2>&1 || errore "Non riesco a creare l'ambiente Python."
fi
"$PROG/.venv/bin/python" -m pip install --upgrade pip >> "$LOG" 2>&1
"$PROG/.venv/bin/python" -m pip install -r "$PROG/requirements.txt" >> "$LOG" 2>&1 \
    || errore "Installazione delle librerie non riuscita."
info "Fatto."

# ---------------------------------------------------------------- 5. App
passo "[5/6] Cattura audio e app «Appunti Lezioni»"
"$PROG/.venv/bin/python" "$PROG/app.py" --installa >> "$LOG" 2>&1 || errore "Preparazione dell'app non riuscita."
info "L'app è in Applicazioni (la trovi anche con Spotlight: ⌘ Spazio, «Appunti»)."

# ---------------------------------------------------------------- 6. Prova
passo "[6/6] Prova automatica (la prima volta scarica anche il modello di trascrizione)"
prova_con_permesso

passo "Finito! Apro Appunti Lezioni…"
info "Al primo avvio inserisci la chiave API di Claude nella scheda Impostazioni."
open "$APP"
echo
