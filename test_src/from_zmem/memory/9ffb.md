---
id: 9ffb
type: architecture
tags:
- cli
- builder
- generator
status: active
created_at: '2026-04-13T21:16:42Z'
updated_at: '2026-04-13T21:16:42Z'
metadata: {}
custom: {}
---

# Shared generation lives in lib/pvtro.dart, the CLI entrypoint is bin/pvtro.dart, builder integration is in lib/builder.dart, and code emission is handled by the scanner plus wrapper generator utilities.

## Context

The repository was refactored so direct CLI execution and builder execution reuse the same generation logic instead of diverging.

## Content

Current architecture:

- `bin/pvtro.dart`: thin CLI launcher
- `lib/pvtro.dart`: shared generation, file writing, and CLI orchestration
- `lib/builder.dart`: build_runner adapter and output declaration logic
- `lib/utils/package_scanner.dart`: package-config discovery and translation-layer detection
- `lib/utils/wrapper_generator.dart`: generated source emission

## Consequences / notes

Behavior changes should be implemented in the shared generation path first so CLI mode and builder mode stay aligned.
