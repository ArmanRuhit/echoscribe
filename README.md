# EchoScribe

Live transcript for course videos that do not provide captions.

EchoScribe captures the audio of the current browser tab, streams 16 kHz mono PCM to a local Whisper server, and appends timestamped text to a Markdown file. Audio is never stored; only the transcript is saved.

## How it works

```text
lecture tab audio
  -> chrome.tabCapture
  -> offscreen document
  -> 16 kHz mono PCM
  -> WebSocket ws://127.0.0.1:8765
  -> faster-whisper
  -> ~/EchoScribe/transcripts/*.md
```

- The manifest V3 service worker starts and stops capture.
- An offscreen document owns the media stream and keeps the lecture audible.
- An AudioWorklet downmixes to mono and sends 100 ms PCM frames.
- A local Python server transcribes 5-second windows and writes Markdown.
- The side panel shows the live transcript.
- Timestamps follow the video, not the session: `video-clock.js` samples the player every 500 ms, and a rewind of 3 s or more adds `(replay from HH:MM:SS)`. With no readable player the clock falls back to the session and the header says so.

## Requirements

- Chrome or Brave 116 or newer.
- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/).
- About 500 MB free for the default `small.en` model on first run.

## Setup

1. Install the Python dependencies:

```bash
uv venv
uv pip install -r server/requirements.txt
```

2. Start the local server:

```bash
uv run server/transcribe_server.py
```

3. Load the extension:

```text
chrome://extensions  or  brave://extensions
Developer mode -> Load unpacked -> select the extension/ directory
```

4. Open a lecture, click the EchoScribe icon, and keep the side panel visible.
5. Click the icon again to stop. The transcript is in `~/EchoScribe/transcripts/`.

## Configuration

Copy `.env.example` to `.env` and edit; the server reads it at startup and shell variables win.

| Variable | Default | Notes |
|---|---|---|
| `ECHOSCRIBE_MODEL` | `small.en` | `base.en` is faster; `small`/`medium` support other languages |
| `ECHOSCRIBE_LANGUAGE` | `en` | Default only; the side panel picks the language per session |
| `ECHOSCRIBE_DEVICE` | `cpu` | `cuda` for an NVIDIA GPU; pulls ~2.1 GB of CUDA 12 wheels on linux/x86_64 |
| `ECHOSCRIBE_COMPUTE` | follows device | `int8` on CPU, `float16` on GPU |
| `ECHOSCRIBE_DIR` | `~/EchoScribe` | Transcript root |
| `ECHOSCRIBE_PORT` | `8765` | Local WebSocket port |
| `ECHOSCRIBE_PROMPT` | empty | Domain words Whisper mishears, e.g. `BODMAS, JSON` |

Example for Bangla:

```bash
ECHOSCRIBE_MODEL=small ECHOSCRIBE_LANGUAGE=auto uv run server/transcribe_server.py
```

For Hindi, choose Hindi in the side panel and start the server with a multilingual model:

```bash
ECHOSCRIBE_MODEL=small uv run server/transcribe_server.py
```

The default `small.en` is English-only. Selecting Hindi with it fails with `ERR` and writes no file.

## GPU

`cuda` trades about 2.1 GB of disk for speed. The CUDA 12 wheels ship in `server/requirements.txt`, so nothing is downloaded at run time.

```bash
ECHOSCRIBE_DEVICE=cuda ECHOSCRIBE_MODEL=small uv run server/transcribe_server.py
```

Before it binds the port the server prints `[device] preloaded <n> CUDA libraries` and `[verify] 1.0 s ok in <n> s`. The first run after a driver update compiles kernels and can take ~25 s; later starts take about a second.

If the GPU, a library, or memory is missing, the server exits and names the cause. It never falls back to CPU silently.

## Limits

- Audio is sent only to `127.0.0.1`; nothing goes to a cloud service.
- DRM-protected content and browser-internal pages cannot be captured.
- Closing the lecture tab stops the session.
- A dropped WebSocket reconnects and resumes the same transcript for up to 10 minutes.
- A full server restart starts a new transcript file.
- If the server is offline, the first start fails with `ERR` and captures nothing. A disconnect mid-session queues audio for about 30 seconds; older frames drop first.

Use this for personal study. Respect course terms and copyright. Do not redistribute recordings or transcripts.
