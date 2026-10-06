// swift-tools-version: 6.0
// meeting-asr: the thin offline adapter over FluidAudio for the meeting-notes
// pipeline. FluidAudio is pinned to one release; `make meeting-notes` builds it
// outside the repo (debug: a release build of FluidAudio takes over 20 minutes,
// and Core ML does the heavy work either way).
import PackageDescription

let package = Package(
    name: "meeting-notes",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/FluidInference/FluidAudio.git", exact: "0.17.5")
    ],
    targets: [
        .executableTarget(
            name: "meeting-asr",
            dependencies: [.product(name: "FluidAudio", package: "FluidAudio")]
        )
    ]
)
