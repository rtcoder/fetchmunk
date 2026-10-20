# fetchmunk
A friendly desktop app powered by gallery-dl. Paste a link, click download, and keep your media — no terminal or manual setup.

## Status

Fetchmunk is in the design phase. The application is not implemented yet.

## Selected architecture

- **macOS first:** Swift and SwiftUI, with AppKit where needed.
- **Windows and Linux later:** C# and Avalonia, sharing one UI implementation.
- **Shared local backend:** Python, using gallery-dl as the download engine.

The application will bundle Python, gallery-dl, and required dependencies.
Users will not need a terminal or a separately installed Python environment.
Detailed MVP scope, packaging, and update mechanisms are still to be decided.

## Design proposals

- [MVP and architecture (Polish)](docs/design/mvp.md)
- [GUI–backend protocol v1 (Polish)](docs/design/protocol-v1.md)

These documents are proposals for review, not implemented functionality.

## Implementation plan

- [First working macOS build (Polish)](docs/superpowers/plans/2026-10-20-macos-first-build.md)

The plan covers public downloads and a self-contained local build.
Authentication and public release distribution follow in separate stages.
