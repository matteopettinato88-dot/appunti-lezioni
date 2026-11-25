// Appunti Lezioni – piccola app che avvia il programma Python.
//
// È l'eseguibile di "Appunti Lezioni.app" (in ~/Applications). Serve perché macOS associ i permessi
// (registrazione dell'audio, cartella Documenti) ad "Appunti Lezioni" e non al Terminale o a Python.
// Avvia .venv/bin/python app.py dalla cartella del programma (chiave AppuntiProgramma di Info.plist),
// passa gli argomenti ricevuti (es. --nascosto, --autotest) e si chiude quando il programma si chiude.
// Se si riapre l'app mentre è già attiva, chiede al programma di mostrare la finestra.
//
// Viene compilata da sistema.crea_app() con: swiftc -O avvio_app.swift -o "Appunti Lezioni"

import AppKit
import Foundation

let PORTA_ISTANZA: UInt16 = 47651

func mostraFinestra() {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { return }
    defer { close(fd) }
    var ind = sockaddr_in()
    ind.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    ind.sin_family = sa_family_t(AF_INET)
    ind.sin_port = PORTA_ISTANZA.bigEndian
    ind.sin_addr.s_addr = inet_addr("127.0.0.1")
    let ok = withUnsafePointer(to: &ind) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    if ok == 0 {
        _ = "MOSTRA".withCString { send(fd, $0, 6, 0) }
    }
}

final class Delegato: NSObject, NSApplicationDelegate {
    var processo: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let info = Bundle.main.infoDictionary ?? [:]
        let cartella = (info["AppuntiProgramma"] as? String) ?? ""
        let python = cartella + "/.venv/bin/python"
        guard !cartella.isEmpty, FileManager.default.isExecutableFile(atPath: python) else {
            errore("Non trovo il programma in:\n\(cartella)\n\nRilancia l'installazione.")
            return
        }
        let argomenti = CommandLine.arguments.dropFirst().filter { !$0.hasPrefix("-psn_") }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = [cartella + "/app.py"] + argomenti
        p.currentDirectoryURL = URL(fileURLWithPath: cartella)
        var ambiente = ProcessInfo.processInfo.environment
        ambiente["APPUNTI_APP"] = Bundle.main.bundlePath
        ambiente["PYTHONUNBUFFERED"] = "1"
        p.environment = ambiente
        p.terminationHandler = { _ in
            DispatchQueue.main.async { NSApp.terminate(nil) }
        }
        do {
            try p.run()
            processo = p
        } catch {
            errore("Non riesco ad avviare il programma:\n\(error.localizedDescription)")
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        mostraFinestra()
        return false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if let p = processo, p.isRunning {
            p.terminate()
        }
        return .terminateNow
    }

    func errore(_ testo: String) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Appunti Lezioni"
        a.informativeText = testo
        a.alertStyle = .warning
        a.runModal()
        NSApp.terminate(nil)
    }
}

let applicazione = NSApplication.shared
let delegato = Delegato()
applicazione.delegate = delegato
applicazione.run()
