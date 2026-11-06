# Implementation Plan: Video-Time Transcript Sync

**Branch**: `003-video-time-sync` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-video-time-sync/spec.md`

## Summary

Stamp each transcript line with the captured tab's own video position instead of the session clock,
and mark the lines written after a backwards seek as a replay that names its origin.

Approach: inject a small reporter into the captured tab once, at the toolbar click that already
starts capture. It samples `currentTime`, `paused`, and `playbackRate` and posts them to the
offscreen document, which pairs each reading with the audio position it has streamed so far and
forwards it to the server as a clock anchor. The server maps segment audio offsets onto video
positions by walking those anchors, so pauses and speed changes need no special case — they are
already in the anchor data. A backwards jump of 3 s or more opens a replay event that is appended to
the timestamp of following lines until the playhead passes the origin again.

## Technical Context

**Language/Version**: JavaScript ES2022 (MV3 extension), Python 3.13 (server)

**Primary Dependencies**: none new. `chrome.scripting` (MV3 API, ships with the browser),
`faster-whisper` 1.2.1, `websockets` 17.3

**Storage**: transcript Markdown only; no new storage, no audio

**Testing**: manual quickstart scenarios against a real player; a Python harness that feeds anchor
sequences to the clock mapper and asserts replay edges

**Target Platform**: Chrome / Brave desktop, MV3

**Project Type**: browser extension + local WebSocket server

**Performance Goals**: anchor every 500 ms (≈100 B/s); no measurable CPU on the page; no added
transcription latency; ≤1 s of CPU per minute of lecture

**Constraints**: displayed time within 2 s of the player; file stays append-only; `127.0.0.1` only;
no host permissions; existing 2–5 s transcription lag unchanged

**Scale/Scope**: one tab, one session, one video element at a time

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Verdict |
|---|---|---|
| I. Local-Only Processing | No network, no host permissions, narrowest permission | PASS — `scripting` is granted only by the toolbar click and scoped to that tab (activeTab); nothing leaves the machine |
| II. Audio Is Ephemeral | No new audio path | PASS — position is a number, never audio |
| III. No Lost Transcript | Append-only, flush per segment, fallback never fails | PASS — the clock only changes what is printed inside `[ ]`; a missing player falls back to session time and still writes |
| IV. Visible Failure | Panel states which clock is in use; injection failure is not silent | PASS — panel shows `video` or `session`; injection errors are logged and the session continues in session mode |
| V. Smallest Complete Change | No dependency, no build step | PASS — one new 30-line file and ~120 lines across five existing files; no library |

Re-check after design: PASS. The design adds no permission beyond `scripting`, no storage, and no
server dependency. Displays times that can move backwards — deliberate, and limited to replay lines.

## Project Structure

### Documentation (this feature)

```text
specs/003-video-time-sync/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── websocket-protocol.md
│   └── extension-messages.md
└── tasks.md            # /speckit.tasks
```

### Source Code (repository root)

```text
extension/
├── manifest.json        # + "scripting"
├── background.js        # inject the reporter on the existing toolbar click
├── video-clock.js       # NEW: samples the player, posts readings
├── offscreen.js         # anchors readings to the audio clock, sends "clock" frames
└── sidepanel.js         # shows "video" or "session" in the status line

server/
└── transcribe_server.py # anchor table, audio→video mapping, replay marker, header note

specs/003-video-time-sync/  # this feature's artifacts
```

**Structure Decision**: the existing split is unchanged. The reporter is a separate injected file
rather than an inline `func` in `background.js` so it can be read and reasoned about as a unit, and
so it survives the service worker being suspended.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New `scripting` permission | Reading `currentTime` requires touching the page | No alternative exists; the alternative is the session clock, which is the feature being replaced |
| Persistent injected reporter | Samples must continue while the service worker sleeps | Re-injecting per sample wakes the worker every 500 ms; `chrome.tabs` cannot read DOM |
| Anchor mapping in the server | Segments arrive as audio offsets; only the server knows when a window was cut | Client-side stamping needs the segment's audio offset, which is a server-side number; clock skew between page and server is unbounded |
| A clock mode that can switch mid-session | Capture can start before the player reports a position | Refusing to switch makes the first minutes permanently session-relative, contradicting spec edge case "capture starts before the video has loaded" |
