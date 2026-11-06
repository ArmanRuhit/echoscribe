# EchoScribe Constitution

## Core Principles

### I. Local-Only Processing (NON-NEGOTIABLE)

Every step of the pipeline runs on the user's machine. Speech recognition MUST use a local
`faster-whisper` server; the server MUST bind `127.0.0.1` only. The extension MUST NOT call any
remote service, load remote code, ship API keys, or include analytics or telemetry. Its
`connect-src` CSP MUST allow `ws://127.0.0.1:8765` and nothing else. The manifest MUST request the
narrowest permission set a step needs, added one step at a time (`activeTab`, then `tabCapture` +
`offscreen`, then `sidePanel`); `downloads`, `storage`, and broad host permissions are prohibited
unless a step demonstrably needs them.

Rationale: lecture audio is sensitive and the tool must keep working offline after the model
download. A local boundary is the only version of this product whose privacy claim is true.

### II. Audio Is Ephemeral (NON-NEGOTIABLE)

Captured audio exists in memory only and MUST be discarded when the session ends. No audio file,
partial recording, or sample excerpt may be written to disk by default. A debug audio dump is
permitted only behind a flag that is off by default, documented as such, and never enabled in a
committed configuration. No `.wav`, `.webm`, or model artifacts may be committed.

Rationale: the user consented to a transcript, not a recording. Persisting audio silently converts
a study tool into a recorder and breaks the privacy claim in Principle I.

### III. No Lost Transcript (NON-NEGOTIABLE)

The transcript file MUST be appended and flushed after every segment, so it is readable while the
lecture is still playing. Any stop path — user stop, tab close, socket drop, server restart, error —
MUST finalize rather than truncate the file. Reconnect MUST reuse the `sessionId` and append to the
same file rather than starting a new one. The server MUST retain a session for at least 10 minutes,
and the client MUST queue audio for up to 30 seconds during a disconnect, dropping the oldest
frames first.

Rationale: a 30-minute lecture cannot be replayed on demand, so losing the tail of a transcript is
the worst failure this project can have — worse than a visible error.

### IV. Visible Failure, No Silent Degradation

Every failure MUST log the failing API name and message and surface a state the user can see
(`ERR` badge, status text). Errors MUST NOT be swallowed by an empty `catch` or a resolved promise.
A dead socket, a blocked capture, and a missing model MUST all be distinguishable. Cleanup of the
WebSocket, media tracks, `AudioContext`, and offscreen document MUST run in `finally`. Exactly one
transcription session may be active at a time.

Rationale: a silent failure is discovered an hour after the lecture ends, when it is unrecoverable.
Visible failure keeps the cost of a bug to one glance at the badge.

### V. Smallest Complete Change

Plain JavaScript ES modules, 2-space indent, semicolons, `async/await` over callbacks. No
TypeScript, framework, bundler, or build step. No library, abstraction, or dependency may be added
unless it removes more code than it introduces — `faster-whisper`, `websockets`, `numpy`, and `av`
are the whole server dependency set. Comments are one line and explain why. Prefer deleting code to
configuring it.

Rationale: this is a single-user extension maintained occasionally. Every abstraction is a cost paid
on each future visit to the code, and a build step is a cost paid before the tool can even run.

## Technical Constraints

- Chrome/Brave MV3; capture via `chrome.tabCapture.getMediaStreamId` + offscreen document +
  `AudioWorklet`; stream 16 kHz mono Int16 PCM over WebSocket. Lecture audio MUST stay audible
  during capture.
- Python 3.13+; pin `av>=16.1,<17` (PyAV 19 removed `metadata_errors`, still passed by
  `faster-whisper` 1.2.1). Dependencies are declared in `pyproject.toml`/`uv.lock` and installed
  with `uv run`.
- Default model `small.en`; `ECHOSCRIBE_DEVICE=cpu`, `ECHOSCRIBE_COMPUTE=int8` unless a GPU is
  present. Target latency is 2–5 seconds behind the speaker; word-by-word captions are out of scope.
- Transcripts are written to `~/EchoScribe/transcripts/` as
  `YYYY-MM-DD_HH-MM_<slug>.md`, header plus `[HH:MM:SS] text`.
- Out of scope and not to be proposed: video capture, cloud transcription, speaker labels,
  translation, summaries, DRM or protected content, accounts, and any network call beyond the
  loopback server.

## Development Workflow

- Work proceeds one build step per turn (skeleton → server → capture → live UI → hardening). The
  current step's test MUST pass before the next step starts; a failing test blocks new scope, not
  the reverse.
- Every change is verified against the test checklist: transcript file with timestamps, file updates
  while playing, lecture stays audible, stop finalizes and clears the badge, no audio file created,
  start/stop works twice without reload, disconnect shows `ERR`.
- Debugging uses the extension's own surfaces: service worker inspector, `offscreen.html` inspector,
  and side panel inspector. A failure that cannot be observed there is a missing log, not a mystery.
- Conventional Commits, intent only. `caveman-review` runs on `git diff` before every push; bugs and
  risks are fixed, not deferred. `.venv/`, models, `transcripts/`, `*.wav`, and `*.webm` never enter
  the repository.
- Personal study use only: transcribe content the user can already play, respect platform terms, do
  not redistribute transcripts, and stop if capture is blocked.

## Governance

This constitution governs specification, planning, and task decisions. `AGENTS.md` remains the
operational guide for commands, file layout, and code conventions; where the two conflict, this
document wins and `AGENTS.md` MUST be updated in the same change rather than diverging.

Amendments require an explicit request, a written rationale, and a version bump under semantic
versioning: MAJOR for removing or redefining a principle, MINOR for adding a principle or materially
expanding guidance, PATCH for clarifications and wording. Every amendment MUST update the
`Last Amended` date and record the change in the Sync Impact Report until the change is committed.
Ratification of v1.0.0 adopts the principles above as the baseline; the three NON-NEGOTIABLE
principles may not be waived by a feature plan.

Compliance is reviewed at `/speckit.plan` (each principle checked against the proposed design) and
at `/speckit.analyze` (violations reported, not waved through). Any added complexity MUST be
justified in the plan against Principle V; unjustified complexity is a defect. A plan that requires
cloud transcription, persisted audio, or a build step is rejected rather than amended.

**Version**: 1.0.0 | **Ratified**: 2026-11-06 | **Last Amended**: 2026-11-06
