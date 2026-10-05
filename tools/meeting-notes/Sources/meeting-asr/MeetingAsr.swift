// meeting-asr — offline speech-to-text and speaker diarization for one mono WAV,
// as JSON on stdout. The thin adapter over FluidAudio that the meeting-notes
// pipeline calls; everything else (channels, merging, files) is in bin/meeting-notes.
//
//   meeting-asr transcribe --model-dir <dir> [--version v2|v3] <wav>
//   meeting-asr diarize --models-root <dir> [--num-speakers N | --max-speakers N] [--threshold T] <wav>
//   meeting-asr check --model-dir <dir> [--version v2|v3] --models-root <dir>
//
// Offline by construction: the SDK's offline guard is on before any loader, the
// ASR model loads from one exact directory (AsrModels.loadLocal), and the
// diarizer loads through OfflineDiarizerModels.load, never prepareModels (which
// deletes and re-downloads the cache when a load fails). A missing or damaged
// model is an error; nothing is downloaded or deleted.
import Foundation
import FluidAudio

let SDK_VERSION = "0.17.5"
let ADAPTER_VERSION = 1

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
                let manager = try await loadAsr(args)
                var state = TdtDecoderState.make()
                let r = try await manager.transcribe(URL(fileURLWithPath: wav), decoderState: &state)
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION, "model_version": option(args, "--version") ?? "v2",
                          "text": r.text, "duration_s": r.duration, "processing_s": r.processingTime,
                          "confidence": Double(r.confidence), "words": words(r.tokenTimings ?? [])])
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
            case "check":
                _ = try await loadAsr(args)
                _ = try await loadDiarizer(args)
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION, "asr": "ok", "diarizer": "ok"])
            case "version":
                try emit(["sdk": SDK_VERSION, "adapter": ADAPTER_VERSION])
            default:
                throw Failure(description: "usage: meeting-asr transcribe|diarize|check|version (see the source header)")
            }
        } catch {
            FileHandle.standardError.write("meeting-asr: \(error)\n".data(using: .utf8)!)
            exit(1)
        }
    }
}
