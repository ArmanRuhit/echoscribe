# Quickstart: GPU-Accelerated Transcription

Each scenario is runnable from the repository root. The server prints to the terminal that
launched it; the extension surfaces the same failures in the side panel and badge.

## Prerequisites

```bash
uv sync                       # installs the two nvidia wheels from the lockfile
uv run python -m py_compile server/transcribe_server.py
node --check extension/offscreen.js && node --check extension/sidepanel.js
```

Expected after `uv sync`: `ctranslate2` reports one CUDA device and the wheels resolve to
`nvidia-cublas-cu12 12.9.*` / `nvidia-cudnn-cu12 9.*`. Reload the extension after pulling the
change (`brave://extensions` → reload), since `offscreen.js` changed.

## Scenario 1 — CPU stays the default (SC-007)

```bash
uv run python server/transcribe_server.py
```

Expected: startup logs `small on cpu/int8`; no CUDA preload line; a session transcribes exactly as
before. Panel line: `Recording · English · small` (no GPU suffix).

## Scenario 2 — GPU happy path (SC-001, SC-005)

```bash
ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py
```

Expected, in order:
1. `[device] cuda/float16 (small)` before `listening`.
2. One `[verify] 1.0 s ok in <n> s` line — this is the dry run, not a lecture segment.
3. Panel: `Recording · English · small · GPU float16`.
4. Transcript header line:
   `Language: en (model small, device cuda/float16)`.
5. `nvidia-smi` shows `python` using ~1 GB and a nonzero `GPU-Util` during the lecture.

## Scenario 3 — Missing library is named (FR-006)

```bash
mv .venv/lib/python3.13/site-packages/nvidia /tmp/opencode/nvidia-bak
ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py
mv /tmp/opencode/nvidia-bak .venv/lib/python3.13/site-packages/nvidia
```

Expected: exit code 1 before any port is bound, message containing
`Library libcublas.so.12 is not found` and the `nvidia-cublas-cu12` hint. No transcript file
created. Start a session in the panel → `ERR` with "server unreachable".

## Scenario 4 — No GPU visible (FR-006)

```bash
CUDA_VISIBLE_DEVICES="" ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py
```

Expected: `ECHOSCRIBE_DEVICE=cuda found no CUDA device`, exit 1, no port. The message points at
`ECHOSCRIBE_DEVICE=cpu`.

## Scenario 5 — Bad configuration is refused, not guessed (FR-003, FR-004)

```bash
ECHOSCRIBE_DEVICE=metal uv run python server/transcribe_server.py       # unknown device
ECHOSCRIBE_DEVICE=cuda ECHOSCRIBE_COMPUTE=int4 uv run python server/transcribe_server.py
```

Expected: each exits 1 with the offending value in the message. Neither serves a session, neither
falls back to CPU.

## Scenario 6 — Mid-lecture failure keeps the file (FR-007)

With the server running (CPU is fine), in a second terminal run the scratch harness that stubs the
transcribe call to raise after two windows:

```bash
uv run python /tmp/opencode/test_handshake.py --fail-after 2
```

Expected:
1. Client receives `{"type": "error", "code": "transcription_failed", ...}`.
2. Panel shows the message and the badge turns `ERR`.
3. The transcript file exists and contains the segments emitted before the failure, with no
   truncation and no `[--:--:--]` placeholder.
4. No reconnect storm: exactly one `error` frame in the offscreen console.

## Scenario 7 — Speed, measured on a real lecture (SC-001, SC-002, SC-003)

Play a 10-minute recorded lecture twice, with the same model and language, first:

```bash
uv run python server/transcribe_server.py                 # CPU
```

then:

```bash
ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py
```

For each run note:
- `date +%T` when the lecture stops and the last line's `[HH:MM:SS]` — the gap is the backlog.
- Number of `[HH:MM:SS]` lines per 60 s of lecture audio from the file alone (no audio needed).

Expected: GPU gap ≤ 5 s and ≥ 5 lines per minute; GPU total wall time at least 2× shorter than
CPU; no multi-minute hole in the file. `medium` on GPU is an optional spot check (fits in 12 GB).

## Scenario 8 — Language still works on GPU (FR-011)

With `ECHOSCRIBE_DEVICE=cuda` and `ECHOSCRIBE_MODEL=small`, select Hindi in the panel and play
Hindi speech.

Expected: Devanagari lines, no replacement characters, header `Language: hi (model small,
device cuda/float16)`. Repeat with `ECHOSCRIBE_MODEL=small.en`: the session is refused with
`unsupported_language`, `ERR`, and no file — GPU does not loosen the language rule.
