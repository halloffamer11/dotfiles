// mictee — capture the default microphone via AVAudioEngine and stream raw
// PCM to stdout: 32-bit float little-endian, 48000 Hz, mono, regardless of the
// device's native format (AVAudioConverter resamples as needed).
// Diagnostics go to stderr. SIGINT/SIGTERM stop cleanly; output is raw PCM, so
// the file is valid at any truncation point. Companion to audiotee in the
// record-meeting rig: mic leg only — system audio is audiotee's job.
//
// Timing lines on stderr (the stdout contract is unchanged), all on the
// CLOCK_UPTIME_RAW nanosecond clock (= mach_absolute_time, AVAudioTime's host
// time) so record-meeting can align this leg with the system leg:
//   mictee: first-sample host_ns=<ns>
//   mictee: gap at_sample=<output samples written before it> samples=<lost> host_ns=<ns>
//   mictee: last-sample host_ns=<end of last buffer> samples=<total output samples>
// A gap is any jump of more than GAP_NS between where a tap buffer should start
// and where it does: dropped buffers, or the restart after a device change.
import AVFoundation
import Darwin

let TARGET_RATE = 48000.0
let GAP_NS: Int64 = 5_000_000

var timebase = mach_timebase_info_data_t()
mach_timebase_info(&timebase)
func hostNs(_ t: UInt64) -> Int64 { Int64(t) * Int64(timebase.numer) / Int64(timebase.denom) }

func log(_ msg: String) {
    FileHandle.standardError.write(("mictee: " + msg + "\n").data(using: .utf8)!)
}

let engine = AVAudioEngine()
var bytesOut: UInt64 = 0
var firstNs: Int64? = nil
var nextNs: Int64 = 0  // where the next tap buffer should start, if no samples are lost

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

    input.installTap(onBus: 0, bufferSize: 4800, format: inFmt) { buffer, when in
        let startNs = when.isHostTimeValid ? hostNs(when.hostTime) : Int64(clock_gettime_nsec_np(CLOCK_UPTIME_RAW))
        if firstNs == nil {
            firstNs = startNs
            log("first-sample host_ns=\(startNs)")
        } else if startNs - nextNs > GAP_NS {
            let lost = Int64((Double(startNs - nextNs) / 1e9 * TARGET_RATE).rounded())
            log("gap at_sample=\(bytesOut / 4) samples=\(lost) host_ns=\(startNs)")
        }
        nextNs = startNs + Int64(Double(buffer.frameLength) / inFmt.sampleRate * 1e9)
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
        if firstNs != nil { log("last-sample host_ns=\(nextNs) samples=\(bytesOut / 4)") }
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
