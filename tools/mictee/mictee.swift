// mictee — capture the default microphone via AVAudioEngine and stream raw
// PCM to stdout: 32-bit float little-endian, 48000 Hz, mono, regardless of the
// device's native format (AVAudioConverter resamples as needed).
// Diagnostics go to stderr. SIGINT/SIGTERM stop cleanly; output is raw PCM, so
// the file is valid at any truncation point. Companion to audiotee in the
// record-meeting rig: mic leg only — system audio is audiotee's job.
import AVFoundation

let TARGET_RATE = 48000.0

func log(_ msg: String) {
    FileHandle.standardError.write(("mictee: " + msg + "\n").data(using: .utf8)!)
}

let engine = AVAudioEngine()
var bytesOut: UInt64 = 0

func startCapture() {
    let input = engine.inputNode
    let inFmt = input.inputFormat(forBus: 0)
    guard inFmt.sampleRate > 0, inFmt.channelCount > 0 else {
        log("no usable input device (format \(inFmt.sampleRate) Hz / \(inFmt.channelCount) ch)")
        exit(1)
    }
    guard let outFmt = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                     sampleRate: TARGET_RATE, channels: 1,
                                     interleaved: true),
          let conv = AVAudioConverter(from: inFmt, to: outFmt) else {
        log("cannot build converter \(inFmt.sampleRate)Hz/\(inFmt.channelCount)ch -> 48kHz mono f32")
        exit(1)
    }
    log("capturing: \(inFmt.sampleRate) Hz \(inFmt.channelCount) ch -> 48000 Hz mono f32")

    input.installTap(onBus: 0, bufferSize: 4800, format: inFmt) { buffer, _ in
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * TARGET_RATE / inFmt.sampleRate) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: outFmt, frameCapacity: capacity) else { return }
        var err: NSError?
        var fed = false
        let status = conv.convert(to: out, error: &err) { _, inputStatus in
            if fed { inputStatus.pointee = .noDataNow; return nil }
            fed = true
            inputStatus.pointee = .haveData
            return buffer
        }
        if status == .error {
            log("convert error: \(err?.localizedDescription ?? "unknown")")
            return
        }
        let ab = out.audioBufferList.pointee.mBuffers
        if let data = ab.mData, ab.mDataByteSize > 0 {
            FileHandle.standardOutput.write(Data(bytes: data, count: Int(ab.mDataByteSize)))
            bytesOut += UInt64(ab.mDataByteSize)
        }
    }

    do {
        try engine.start()
    } catch {
        log("engine start failed: \(error.localizedDescription)")
        exit(1)
    }
}

// Default input device changed (e.g. AirPods connected/disconnected): the
// engine stops and the input format may differ — reinstall the tap and resume.
NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange,
                                       object: engine, queue: .main) { _ in
    log("input configuration changed — restarting capture")
    engine.inputNode.removeTap(onBus: 0)
    engine.stop()
    startCapture()
}

func installStop(_ sig: Int32) -> DispatchSourceSignal {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        log(String(format: "stopped; captured %.2f s", Double(bytesOut) / (TARGET_RATE * 4.0)))
        exit(0)
    }
    src.resume()
    return src
}
let sigint = installStop(SIGINT)
let sigterm = installStop(SIGTERM)

startCapture()
RunLoop.main.run()
