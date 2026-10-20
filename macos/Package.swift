// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "Fetchmunk", platforms: [.macOS(.v13)],
    products: [.executable(name: "Fetchmunk", targets: ["Fetchmunk"])],
    targets: [.executableTarget(name: "Fetchmunk"), .testTarget(name: "FetchmunkTests", dependencies: ["Fetchmunk"])])
