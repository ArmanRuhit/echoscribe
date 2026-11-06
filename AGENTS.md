# EchoScribe

Personal Chrome/Brave extension that live-transcribes the audio of a course video playing in a tab and appends the transcript to a local Markdown file.

Audio is captured only as temporary input. It is never saved.

Status: Steps 1-5 implemented. Hardening is in place; the 30-minute real-lecture test is pending.

## Next action

Run a 30-minute lecture test, then review and push the first commit.

## Skills

Installed globally: `ponytail`, `caveman`, `caveman-review`, `caveman-commit`.

| Skill | When | What it changes |
|---|---|---|
| `i-have-adhd` | every reply and code comment | Action first, numbered steps, no preamble, one-line comments that explain why. |
| `ponytail` | before writing or changing code | Smallest complete change. No library, abstraction, or build step unless it removes more code than it adds. |
| `caveman-review` | before every `git push` | One line per finding: `file:Lline: problem. fix.` Fix bugs and risks first. |
| `caveman-commit` | when writing a commit message | Conventional Commits, intent only. |

## Scope

MVP:

- Toolbar click starts and stops live transcription of the active tab.
- Capture tab audio only; keep the lecture audible.
- Stream 16 kHz mono PCM to a local Whisper server over WebSocket.
- Append transcript segments to a local `.md` file while the lecture plays.
- Show the live transcript in a side panel.
- Badge shows `REC` while active and `ERR` on failure.

Not in MVP:

- Saving audio. A debug flag may dump audio later, off by default.
- Cloud transcription, API keys, accounts, or network calls beyond `127.0.0.1`.
- Video capture.
- Speaker labels, translation, or summaries.
- DRM or protected content.
- TypeScript, frameworks, bundlers.

## Architecture

```text
extension/
  manifest.json      MV3, permissions, service worker, action, side panel
  background.js      click handling, tabCapture, offscreen lifecycle, badge
  offscreen.html     hidden document host
  offscreen.js       getUserMedia, playback, PCM streaming, cleanup
  pcm-worklet.js     Float32 -> Int16 PCM at 16 kHz
  sidepanel.html     live transcript UI
  sidepanel.js       renders segments, shows status
server/
  transcribe_server.py   WebSocket + faster-whisper + Markdown writer
  requirements.txt
transcripts/         generated Markdown files, gitignored
```

Why this shape:

- Chrome and Brave have no reliable built-in long-form speech-to-text. The Web Speech API is unreliable in Brave, stops on silence, and sends audio to Google.
- A local `faster-whisper` server is accurate, offline after the model download, and keeps lecture audio on the machine.
- An MV3 service worker has no DOM, so capture and audio processing run in an offscreen document.
- A side panel stays open while the lecture plays; a popup closes as soon as focus returns to the page.
- The server writes the transcript file and flushes each segment, so the file is live even if the browser closes.

Pipeline:

1. Toolbar click gets the active tab.
2. `chrome.tabCapture.getMediaStreamId({ targetTabId })` creates a stream ID.
3. The service worker creates the offscreen document if missing.
4. The offscreen document calls `getUserMedia` with `chromeMediaSource: "tab"`.
5. An `AudioContext` at 16 kHz routes the stream to the speakers and to an `AudioWorklet`.
6. The worklet downmixes all input channels to mono, converts Float32 samples to Int16 PCM, and posts ~100 ms frames.
7. The offscreen document sends binary frames to `ws://127.0.0.1:8765`.
8. The server buffers ~5-second windows, transcribes with `faster-whisper`, appends text to Markdown, and sends each segment back.
9. The side panel appends the segment. Stop closes the socket, tracks, context, and offscreen document; the server finalizes the file.

Latency: about 2 to 5 seconds behind the speaker on CPU. A GPU keeps up with real time, so the lag stops growing. This is near-live, not word-by-word captions.

Protocol:

```text
client -> server: {"type":"start","sessionId":"...","title":"...","url":"...","sampleRate":16000,"language":"hi"}
client -> server: binary Int16 mono PCM frames
client -> server: {"type":"stop"}

server -> client: {"type":"ready","model":"small","language":"hi","device":"cuda","compute":"float16","sessionId":"...","resumed":false}
server -> client: {"type":"segment","start":12.3,"end":16.8,"text":"..."}
server -> client: {"type":"error","code":"unsupported_language","message":"..."}
```

Language: chosen per session in the side panel (`en` or `hi`). The server validates it before opening a file and refuses a non-English language when the model name ends in `.en`, so a mismatch never produces a transcript.

Device: chosen at server start. `ECHOSCRIBE_DEVICE=cuda` loads the model, transcribes 1 s of silence, and only then binds the port. A missing CUDA library, absent GPU, bad precision, or out of memory exits with a named cause; it never falls back to CPU. Any transcription failure mid-session sends `{"code":"transcription_failed"}`, marks the session failed, and keeps the file written so far.

Transcript quality: a segment is dropped when `no_speech_prob > 0.6` and `avg_logprob < -0.5`, when `compression_ratio > 2.4`, or when a single word fills 60% of a line of 3+ words. Identical consecutive segments are dropped, timestamps never move backwards, and segments split by a pause under 0.6 s merge into one line. `ECHOSCRIBE_PROMPT` biases decoding toward domain words.

Transcript file: `~/EchoScribe/transcripts/YYYY-MM-DD_HH-MM_<slug>.md`. Header plus `[HH:MM:SS] text`, flushed after every segment.

Reconnect: the client reuses `sessionId`; the server keeps the session for 10 minutes and appends to the same file. Audio during a disconnect queues for up to 30 seconds; older frames drop first.

Key APIs:

- `chrome.action.onClicked`
- `chrome.tabCapture.getMediaStreamId`
- `chrome.offscreen.createDocument`
- `AudioContext`, `AudioWorklet`
- `WebSocket`
- `chrome.sidePanel`
- `faster-whisper`

Permissions:

- Step 1: `activeTab` only.
- Step 3: add `tabCapture` and `offscreen`.
- Step 4: add `sidePanel`.
- Hindi: add `storage`; only `chrome.storage.session` is used, so the choice never touches disk.
- Add `content_security_policy.extension_pages` with `connect-src ws://127.0.0.1:8765`.
- No `downloads` or broad host permissions.

## Build order

One step per turn. Do not start the next step until the test passes.

1. Skeleton: `manifest.json` + service worker. Load unpacked.
   Test: icon appears; click logs the active tab title.
2. Local server: Python WebSocket + `faster-whisper`, no extension yet.
   Test: feed a WAV file; server prints text and writes `transcript.md`.
3. Capture stream: `tabCapture` + offscreen + 16 kHz PCM + WebSocket.
   Test: play 30 seconds of speech; text appears in the server console and file; lecture stays audible.
4. Live UI: side panel + badge + clean stop.
   Test: segments appear in the side panel within 5 seconds; file is finalized on stop.
5. Hardening: reconnect, tab close, error states, 30-minute lecture.
   Test: one 30-minute session with no lost file and no stuck badge.

## Test checklist

- [ ] One-minute lecture produces a transcript file with timestamps.
- [ ] File updates while the lecture is still playing.
- [ ] Lecture audio stays audible during capture.
- [ ] Stop finalizes the file and clears the badge.
- [ ] No audio file is created.
- [ ] Start and stop work twice without reloading the extension.
- [ ] Server disconnect shows `ERR`; no silent failure.
- [ ] Hindi with `ECHOSCRIBE_MODEL=small` writes Devanagari, no replacement characters.
- [ ] Hindi selected with `small.en` shows `ERR` and creates no file.
- [ ] `ECHOSCRIBE_DEVICE=cuda` prints `[verify] 1.0 s ok` and the header records `device cuda/float16`.
- [ ] A missing CUDA library exits with the library name and serves nothing.

## Commands

Server setup:

```bash
cd /home/arman/Jobs/projects/echoscribe
uv venv
uv pip install -r server/requirements.txt
uv run python server/transcribe_server.py
```

`uv run` uses the project `.venv`; no activation needed. Dependencies also live in `pyproject.toml` (which `uv.lock` pins), so `uv run` does not prune them; after editing `server/requirements.txt`, run `uv add -r server/requirements.txt`.

Dependency note: pin `av>=16.1,<17`. PyAV 19 removed `metadata_errors`, but `faster-whisper` 1.2.1 still passes it. `av` 16.1.0 is the newest release with standard Python 3.14 wheels.

The first run downloads the model. Default is `small.en`; use `base.en` for speed.

Load unpacked:

```text
chrome://extensions  or  brave://extensions
Developer mode -> Load unpacked -> select echoscribe/extension
```

Inspect:

- Extensions page -> EchoScribe -> service worker: Inspect
- Extensions page -> Inspect views -> `offscreen.html`
- Side panel -> right-click -> Inspect

No build step. Reload the extension after changing `manifest.json` or the service worker.

Config:

- Copy `.env.example` to `.env`; the server loads it at startup and shell variables win
- `ECHOSCRIBE_MODEL` default `small.en`; use `base.en` for speed or `small`/`medium` for multilingual
- `ECHOSCRIBE_LANGUAGE` default `en`; the panel selection overrides it; `auto` for Bangla or mixed lectures
- `ECHOSCRIBE_DEVICE` default `cpu`; `cuda` needs the CUDA 12 wheels that `server/requirements.txt` installs on linux/x86_64 (≈2.1 GB on disk)
- `ECHOSCRIBE_COMPUTE` default `int8` on CPU and `float16` on GPU; leave unset so it follows the device
- `ECHOSCRIBE_DIR` default `~/EchoScribe`
- `ECHOSCRIBE_PORT` default `8765`
- `ECHOSCRIBE_PROMPT` default empty; domain words to bias decoding (`BODMAS, JSON, system prompt`)

## Conventions

- Existing files: provide a unified diff with 3 lines of context, not a full rewrite. New files: full body.
- Review nits: apply directly and list changed files. Bugs and risks still need a diff or explicit apply.
- Plain JavaScript, ES modules, 2-space indent, semicolons.
- `async/await`; no callback style when a promise exists.
- One transcription session at a time. Close the socket, tracks, and context in `finally`.
- Comments: one line, explain why. No section banners. Follow `i-have-adhd`.
- Errors: log the API name and message; show `ERR`; never swallow.
- Server binds `127.0.0.1` only.
- Audio stays in memory and is discarded. Never write it to disk by default.
- Append and flush the transcript after every segment.
- No secrets, remote code, analytics, or cloud calls.

## Safety

Personal study only. Transcribe content you can already play. Respect platform terms and copyright. Do not redistribute transcripts. No DRM circumvention; if capture is blocked, stop. Transcripts may contain sensitive material; keep them local.

## Git

- Conventional Commits, for example `feat: stream tab audio to local whisper`.
- Before push: run `caveman-review` on `git diff`. Apply nits directly; fix bugs and risks.
- Never commit `.venv/`, models, `transcripts/`, `.wav`, or `.webm` files.
- `.gitignore` should include `.venv/`, `transcripts/`, `models/`, `*.wav`, `*.webm`.

## Open questions

- Default model: `small.en` for accuracy or `base.en` for speed?
- Segmenting: fixed 5-second windows or VAD utterance boundaries?
- Add a download button for the `.md` as a backup, or rely on the server file?
