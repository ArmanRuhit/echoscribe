# Implementation Plan: Hindi Transcript Support

**Branch**: `001-hindi-transcript` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-hindi-transcript/spec.md`

## Summary

Let a learner transcribe a Hindi lecture into Devanagari with the same live panel, file
naming, timestamps, and flush-per-segment behavior as an English session. The language is
chosen per session in the side panel, carried in the existing `start` frame, and validated
against the loaded model before any audio is processed. An English-only model plus a Hindi
request is refused with `ERR` and one actionable line instead of producing confident
garbage. English sessions keep today's defaults and behavior.

## Technical Context

**Language/Version**: JavaScript (ES2022, no build step) in Chrome MV3; Python 3.13

**Primary Dependencies**: faster-whisper 1.2.1, websockets 17.3, numpy; multilingual
Whisper model (`small` default for Hindi); Chrome `tabCapture`, `offscreen`, `sidePanel`,
`storage.session`

**Storage**: local Markdown under `~/EchoScribe/transcripts/`; selected language in
`chrome.storage.session` (memory only, cleared when the browser exits)

**Testing**: manual quickstart scenarios plus `server/transcribe_server.py --file <wav>`
for a repeatable Hindi sample; the repo has no test framework

**Target Platform**: Chrome/Brave desktop (MV3)

**Project Type**: browser extension plus a local Python service

**Performance Goals**: first Hindi segment within 5 s of speech; unchanged 5 s window /
1 s overlap cadence; multilingual `small` is the same size class as `small.en`

**Constraints**: offline after model download, `127.0.0.1` only, no audio persisted, one
session at a time, 16 kHz mono Int16 PCM

**Scale/Scope**: single user, one tab, 30+ minute lectures

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Local-Only Processing | No new network calls; model runs locally; server stays on `127.0.0.1` | PASS |
| II. Audio Is Ephemeral | No audio written; handshake gate means no PCM is produced until a session is accepted | PASS |
| III. No Lost Transcript | Same writer, append + flush per segment, same reconnect/resume path | PASS |
| IV. Visible Failure | Server `error` frames become fatal before recording; `ERR` badge and panel message | PASS |
| V. Smallest Complete Change | One permission (`storage`), one protocol field, one select element; no framework, no build step | PASS |

No violations, so Complexity Tracking stays empty.

**Permission note**: `storage` is added only because the language choice must survive a
service-worker eviction between the panel selection and the toolbar click.
`chrome.storage.session` is memory-only, which keeps principle II intact.

## Project Structure

### Documentation (this feature)

```text
specs/001-hindi-transcript/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
extension/
├── manifest.json        # + "storage" permission
├── background.js        # read selected language, pass it in START, allow fatal start errors
├── offscreen.js         # wait for ready before attaching the worklet, send language, surface errors
├── sidepanel.html       # language select, Devanagari font fallback
└── sidepanel.js         # persist selection, render language in status, per-segment lang

server/
└── transcribe_server.py # per-session language, model/language validation, language in ready

specs/001-hindi-transcript/
```

**Structure Decision**: keep the existing two-part layout (extension + Python server). No
new packages or modules: the feature is a field in the existing message contract plus a
validation function, both in files that already own that responsibility.

## Phase 0: Research

See [research.md](./research.md). Decisions resolved:

1. Language is chosen per session in the panel, not per server process.
2. Model capability is detected from the model name suffix (`.en`).
3. Devanagari renders through an explicit system font fallback; no bundled font file.
4. No transliteration and no translation pass: the engine emits Devanagari directly.
5. The initial handshake completes before the worklet is attached.

## Phase 1: Design

- [data-model.md](./data-model.md) — language selection, session, segment, transcript file
- [contracts/websocket-protocol.md](./contracts/websocket-protocol.md) — `start`, `ready`,
  `error` frame changes and the refusal message
- [contracts/extension-messages.md](./contracts/extension-messages.md) — panel to
  background to offscreen messages, including status fields
- [quickstart.md](./quickstart.md) — runnable validation scenarios

## Constitution Check (post-design)

Re-evaluated after Phase 1. Still PASS on all five principles:

- I: the only new frame fields travel over the existing loopback socket.
- II: refusal happens before the worklet exists, so no PCM frame is ever produced for a
  rejected session; no audio path writes to disk.
- III: `TranscriptWriter` and the reconnect/resume logic are untouched apart from carrying
  a language value.
- IV: this feature removes a silent-failure path (`error` frames were previously only
  logged to the console).
- V: net addition is roughly one select element, one permission, one validated field.

## Complexity Tracking

No constitution violations. Nothing to justify.
