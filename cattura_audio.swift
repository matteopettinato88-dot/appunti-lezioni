// Appunti Lezioni – cattura dell'audio del Mac con ScreenCaptureKit.
//
// Scrive su stdout l'audio come campioni float32 mono a 48 kHz (little-endian), senza intestazioni.
// Su stderr scrive righe di stato: "PRONTO", "APP: ...", "PERMESSO_NEGATO", "ERRORE: ...".
//
//   cattura-audio --verifica        esce con 0 se il permesso di registrazione c'è, 2 se manca
//   cattura-audio --chiedi          mostra la richiesta di permesso di macOS (solo la prima volta)
//   cattura-audio                   registra tutto l'audio del Mac
//   cattura-audio --app a,b,c       registra solo le app il cui bundle id inizia con a, b o c
//                                   (browser e videoconferenze); le app aperte dopo vengono aggiunte
//
// Viene compilato sul Mac da sistema.compila_helper() con: swiftc -O cattura_audio.swift -o cattura-audio

import AppKit
import CoreGraphics
import CoreMedia
import Foundation
import ScreenCaptureKit

setvbuf(stderr, nil, _IONBF, 0)
signal(SIGPIPE, SIG_IGN)

func stato(_ testo: String) {
    FileHandle.standardError.write((testo + "\n").data(using: .utf8)!)
}

let argomenti = CommandLine.arguments
if argomenti.contains("--verifica") {
    exit(CGPreflightScreenCaptureAccess() ? 0 : 2)
}
if argomenti.contains("--chiedi") {
    exit(CGRequestScreenCaptureAccess() ? 0 : 2)
}

let soloApp = argomenti.contains("--app")
var prefissi: [String] = []
if let i = argomenti.firstIndex(of: "--app"), i + 1 < argomenti.count {
    prefissi = argomenti[i + 1].split(separator: ",").map { String($0).lowercased() }
}

// Scrive tutti i byte su stdout; se il programma principale si è chiuso, esce.
func scriviTutto(_ p: UnsafeRawPointer, _ n: Int) {
    var fatto = 0
    while fatto < n {
        let r = write(1, p + fatto, n - fatto)
        if r < 0 {
            if errno == EINTR { continue }
            exit(0)
        }
        fatto += r
    }
}

final class Cattura: NSObject, SCStreamOutput, SCStreamDelegate {
    var stream: SCStream?
    var incluse: [String] = []
    var formatoScritto = false
    let codaAudio = DispatchQueue(label: "appunti.audio")
    let codaVideo = DispatchQueue(label: "appunti.video")

    func filtro() async throws -> (SCContentFilter, [String]) {
        let contenuto = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let schermo = contenuto.displays.first else {
            throw NSError(domain: "cattura", code: 3, userInfo: [NSLocalizedDescriptionKey: "Nessuno schermo trovato"])
        }
        if !soloApp {
            return (SCContentFilter(display: schermo, excludingApplications: [], exceptingWindows: []), [])
        }
        let app = contenuto.applications.filter { a in
            let id = a.bundleIdentifier.lowercased()
            return prefissi.contains { id.hasPrefix($0) }
        }
        let nomi = Array(Set(app.map { $0.applicationName.isEmpty ? $0.bundleIdentifier : $0.applicationName })).sorted()
        return (SCContentFilter(display: schermo, including: app, exceptingWindows: []), nomi)
    }

    func avvia() async throws {
        let (f, nomi) = try await filtro()
        let conf = SCStreamConfiguration()
        conf.capturesAudio = true
        conf.sampleRate = 48000
        conf.channelCount = 1
        conf.excludesCurrentProcessAudio = true
        // Il video non serve: immagine minuscola, un fotogramma al secondo.
        conf.width = 2
        conf.height = 2
        conf.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        conf.showsCursor = false
        let s = SCStream(filter: f, configuration: conf, delegate: self)
        try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: codaAudio)
        try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: codaVideo)
        try await s.startCapture()
        stream = s
        incluse = nomi
        if soloApp {
            stato("APP: " + nomi.joined(separator: ", "))
        }
    }

    // Aggiunge al filtro i browser aperti dopo l'inizio della registrazione (e toglie quelli chiusi).
    func aggiorna() async {
        guard soloApp, let s = stream else { return }
        do {
            let (f, nomi) = try await filtro()
            if nomi != incluse {
                try await s.updateContentFilter(f)
                incluse = nomi
                stato("APP: " + nomi.joined(separator: ", "))
            }
        } catch {
            stato("AVVISO: filtro non aggiornato (\(error.localizedDescription))")
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sb.isValid else { return }
        if !formatoScritto, let fd = CMSampleBufferGetFormatDescription(sb),
           let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd)?.pointee {
            formatoScritto = true
            stato("FORMATO: \(Int(asbd.mSampleRate)) Hz, \(asbd.mChannelsPerFrame) canali, \(asbd.mBitsPerChannel) bit, flag \(asbd.mFormatFlags)")
        }
        do {
            try sb.withAudioBufferList { lista, _ in
                // Audio float32 non interlacciato: il primo buffer è il canale (mono) da usare.
                guard let primo = lista.first, let dati = primo.mData, primo.mDataByteSize > 0 else { return }
                scriviTutto(UnsafeRawPointer(dati), Int(primo.mDataByteSize))
            }
        } catch {
            // buffer non leggibile: lo salto
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        stato("ERRORE: la registrazione si è interrotta (\(error.localizedDescription))")
        exit(4)
    }
}

// Connessione al window server (serve a ScreenCaptureKit) senza icona nel Dock.
let applicazione = NSApplication.shared
applicazione.setActivationPolicy(.prohibited)

signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

let cattura = Cattura()
Task {
    do {
        try await cattura.avvia()
        stato("PRONTO")
    } catch {
        if !CGPreflightScreenCaptureAccess() {
            stato("PERMESSO_NEGATO")
            exit(2)
        }
        stato("ERRORE: \(error.localizedDescription)")
        exit(1)
    }
    while true {
        try? await Task.sleep(nanoseconds: 3_000_000_000)
        await cattura.aggiorna()
    }
}

RunLoop.main.run()
