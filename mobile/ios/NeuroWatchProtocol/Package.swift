// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NeuroWatchProtocol",
    products: [.library(name: "NeuroWatchProtocol", targets: ["NeuroWatchProtocol"])],
    targets: [
        .target(name: "NeuroWatchProtocol", path: "Sources/NeuroWatchProtocol"),
        .testTarget(
            name: "NeuroWatchProtocolTests",
            dependencies: ["NeuroWatchProtocol"],
            path: "Tests/NeuroWatchProtocolTests"
        ),
    ]
)
