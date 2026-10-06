// meeting-asr — offline speech-to-text (and optional speaker diarization) for one
// mono WAV, as JSON on stdout: the engines VoiceInk uses for file transcription.
// The meeting-notes pipeline (bin/meeting-notes) picks the engine from VoiceInk's
// selected model and does everything else (channels, filters, files).
//
//   meeting-asr transcribe [--engine tdt] --model-dir <dir> [--version v2|v3] <wav>
//   meeting-asr transcribe --engine unified --model-dir <dir> <wav>
//   meeting-asr transcribe --engine apple [--locale en] <wav>
//   meeting-asr check --engine tdt|unified|apple [same options]   (load only)
//   meeting-asr diarize --models-root <dir> [--num-speakers N | --max-speakers N] [--threshold T] <wav>
//   meeting-asr check-diarizer --models-root <dir>
//   meeting-asr format                   stdin text -> paragraphs (stdout JSON)
//
// Offline by construction, nothing is downloaded or deleted:
// - tdt (Parakeet TDT v2/v3): SDK offline guard on, AsrModels.loadLocal from one
//   exact folder.
// - unified (Parakeet Unified): UnifiedAsrManager.loadModels(from:), which reads
//   only that folder (int8 encoder, as VoiceInk uses it).
// - apple (Apple Speech, SpeechAnalyzer): on-device, and only when the locale's
//   speech assets are already installed; it never asks for an asset download.
// - diarizer: OfflineDiarizerModels.load, never prepareModels (which deletes and
//   re-downloads the cache when a load fails).
import Foundation
import FluidAudio
import NaturalLanguage
import Speech

let SDK_VERSION = "0.17.5"
let ADAPTER_VERSION = 2

struct Failure: Error, CustomStringConvertible { let description: String }

func option(_ args: [String], _ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}

func positional(_ args: [String]) -> String? {
    var skip = false
    for a in args.dropFirst(2) {
        if skip { skip = false; continue }
        if a.hasPrefix("--") { skip = true; continue }
        return a
    }
    return nil
}

func emit(_ obj: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

func asrVersion(_ args: [String]) throws -> AsrModelVersion {
    switch option(args, "--version") ?? "v2" {
    case "v2": return .v2
    case "v3": return .v3
    case let v: throw Failure(description: "unsupported --version \(v) (v2 or v3)")
    }
}

func loadAsr(_ args: [String]) async throws -> AsrManager {
    guard let dir = option(args, "--model-dir") else { throw Failure(description: "--model-dir is required") }
    let models = try AsrModels.loadLocal(from: URL(fileURLWithPath: dir, isDirectory: true), version: try asrVersion(args))
    let manager = AsrManager(config: .default)
    try await manager.loadModels(models)
    return manager
}

func transcribeUnified(_ args: [String], wav: String?) async throws -> [String: Any] {
    guard let dir = option(args, "--model-dir") else { throw Failure(description: "--model-dir is required") }
    let manager = UnifiedAsrManager(encoderPrecision: .int8)
    try await manager.loadModels(from: URL(fileURLWithPath: dir, isDirectory: true))
    guard let wav else { return [:] }
    let samples = try AudioConverter().resampleAudioFile(URL(fileURLWithPath: wav))
    let t = Date()
    let r = try await manager.transcribeWithTimings(samples)
    return ["text": r.text, "duration_s": Double(samples.count) / 16000.0, "processing_s": Date().timeIntervalSince(t),
            "words": words(r.tokenTimings)]
}

func transcribeApple(_ args: [String], wav: String?) async throws -> [String: Any] {
    guard #available(macOS 26.0, *) else { throw Failure(description: "Apple Speech needs macOS 26 or later") }
    let wanted = option(args, "--locale") ?? "en"
    guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Locale(identifier: wanted)) else {
        throw Failure(description: "Apple Speech does not support locale \(wanted)")
    }
    let id = locale.identifier(.bcp47)
    let installed = await SpeechTranscriber.installedLocales
    guard installed.contains(where: { $0.identifier(.bcp47) == id }) else {
        throw Failure(description: "Apple Speech assets for \(id) are not installed; not downloading them")
    }
    guard let wav else { return [:] }
    let transcriber = SpeechTranscriber(locale: locale, transcriptionOptions: [], reportingOptions: [],
                                        attributeOptions: [])
    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let file = try AVAudioFile(forReading: URL(fileURLWithPath: wav))
    let collect = Task { () -> String in
        var text = ""
        for try await result in transcriber.results { text += String(result.text.characters) }
        return text
    }
    let t = Date()
    if let last = try await analyzer.analyzeSequence(from: file) {
        try await analyzer.finalizeAndFinish(through: last)
    } else {
        await analyzer.cancelAndFinishNow()
    }
    let text = try await collect.value.trimmingCharacters(in: .whitespacesAndNewlines)
    return ["text": text, "duration_s": Double(file.length) / file.fileFormat.sampleRate,
            "processing_s": Date().timeIntervalSince(t), "words": [[String: Any]](), "locale": id]
}

func transcribeAny(_ args: [String], wav: String?) async throws -> [String: Any] {
    switch option(args, "--engine") ?? "tdt" {
    case "tdt":
        let manager = try await loadAsr(args)
        guard let wav else { return [:] }
        var state = TdtDecoderState.make()
        let r = try await manager.transcribe(URL(fileURLWithPath: wav), decoderState: &state)
        return ["text": r.text, "duration_s": r.duration, "processing_s": r.processingTime,
                "confidence": Double(r.confidence), "words": words(r.tokenTimings ?? [])]
    case "unified": return try await transcribeUnified(args, wav: wav)
    case "apple": return try await transcribeApple(args, wav: wav)
    case let e: throw Failure(description: "unknown --engine \(e) (tdt, unified, apple)")
    }
}

/// Paragraphs for readability, in the spirit of VoiceInk's formatter: aim for about
/// 50 words and at most 4 sentences per paragraph; sentences under 4 words do not
/// count toward the sentence cap.
func paragraphs(_ text: String) -> String {
    let lang = NLLanguageRecognizer.dominantLanguage(for: text) ?? .english
    let sentenceTok = NLTokenizer(unit: .sentence)
    sentenceTok.setLanguage(lang)
    sentenceTok.string = text
    var sentences: [String] = []
    sentenceTok.enumerateTokens(in: text.startIndex..<text.endIndex) { range, _ in
        let s = text[range].trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.isEmpty { sentences.append(s) }
        return true
    }
    func wordCount(_ s: String) -> Int {
        let tok = NLTokenizer(unit: .word)
        tok.string = s
        return tok.tokens(for: s.startIndex..<s.endIndex).count
    }
    var out: [String] = [], cur: [String] = [], words = 0, significant = 0
    for s in sentences {
        let n = wordCount(s)
        cur.append(s)
        words += n
        if n >= 4 { significant += 1 }
        if words >= 50 || significant >= 4 {
            out.append(cur.joined(separator: " "))
            cur = []; words = 0; significant = 0
        }
    }
    if !cur.isEmpty { out.append(cur.joined(separator: " ")) }
    return out.joined(separator: "\n\n")
}

func loadDiarizer(_ args: [String]) async throws -> OfflineDiarizerManager {
    guard let root = option(args, "--models-root") else { throw Failure(description: "--models-root is required") }
    var config = OfflineDiarizerConfig.default
    if let n = option(args, "--num-speakers").flatMap(Int.init) { config.clustering.numSpeakers = n }
    if let n = option(args, "--max-speakers").flatMap(Int.init) { config.clustering.maxSpeakers = n }
    // Clustering cut distance in [0, 2]; larger merges more (fewer speakers). SDK default 0.6.
    if let t = option(args, "--threshold").flatMap(Double.init) { config.clustering.threshold = t }
    let manager = OfflineDiarizerManager(config: config)
    manager.initialize(models: try await OfflineDiarizerModels.load(from: URL(fileURLWithPath: root, isDirectory: true)))
    return manager
}

/// Tokens → words: a token with leading whitespace starts a new word (SentencePiece).
/// A punctuation-only token keeps its text but not its time: TDT often emits the
/// final "." after the following silence, which would stretch the word by seconds.
func words(_ tokens: [TokenTiming]) -> [[String: Any]] {
    var out: [[String: Any]] = []
    var word = "", start = 0.0, end = 0.0, conf: [Float] = []
    func flush() {
        if !word.isEmpty {
            out.append(["w": word, "s": start, "e": end, "c": Double(conf.reduce(0, +) / Float(max(conf.count, 1)))])
        }
    }
    for t in tokens {
        if t.token.first?.isWhitespace == true || word.isEmpty {
            flush()
            word = t.token.trimmingCharacters(in: .whitespacesAndNewlines)
            start = t.startTime
            conf = []
            end = t.endTime
        } else {
            word += t.token
            if t.token.contains(where: { $0.isLetter || $0.isNumber }) { end = t.endTime }
        }
        conf.append(t.confidence)
    }
    flush()
    return out
}

@main
struct MeetingAsr {
    static func main() async {
        ModelHub.offlineMode = true
        let args = CommandLine.arguments
        do {
            switch args.count > 1 ? args[1] : "" {
            case "transcribe":
                guard let wav = positional(args) else { throw Failure(description: "a WAV path is required") }
                var out = try await transcribeAny(args, wav: wav)
                out["sdk"] = SDK_VERSION
                out["adapter"] = ADAPTER_VERSION
                out["engine"] = option(args, "--engine") ?? "tdt"
                try emit(out)
            case "check":
                _ = try await transcribeAny(args, wav: nil)
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION, "engine": option(args, "--engine") ?? "tdt",
                          "loads": true])
            case "check-diarizer":
                _ = try await loadDiarizer(args)
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION, "diarizer": "ok"])
            case "format":
                let text = String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
                try emit(["text": paragraphs(text)])
            case "diarize":
                guard let wav = positional(args) else { throw Failure(description: "a WAV path is required") }
                let manager = try await loadDiarizer(args)
                let t = Date()
                let r = try await manager.process(URL(fileURLWithPath: wav))
                let segments: [[String: Any]] = r.segments.map {
                    ["speaker": $0.speakerId, "start": Double($0.startTimeSeconds), "end": Double($0.endTimeSeconds),
                     "embedding": $0.embedding.map { Double($0) }]
                }
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION, "processing_s": Date().timeIntervalSince(t),
                          "segments": segments])
            case "version":
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION])
            default:
                throw Failure(description: "usage: meeting-asr transcribe|check|diarize|check-diarizer|format|version (see the source header)")
            }
        } catch {
            FileHandle.standardError.write("meeting-asr: \(error)\n".data(using: .utf8)!)
            exit(1)
        }
    }
}
