# Data Model: GPU-Accelerated Transcription

No persisted schema changes. The structures below are server runtime state plus one file header
line.

## Device Setting

Resolved once per server run from the environment, before the model is built.

| Field | Source | Values | Rules |
|---|---|---|---|
| `device` | `ECHOSCRIBE_DEVICE` | `cpu` (default), `cuda` | Case-sensitive; anything else → startup refusal naming the value |
| `compute` | `ECHOSCRIBE_COMPUTE` | `int8` on CPU, `float16` on CUDA | Explicit value wins; unsupported value → CTranslate2 raises → startup refusal naming the value and device |
| `requested` | derived | `true` when the variable was set | Only used to phrase the error; a default CPU start never prints GPU advice |

Validation order: parse `device` → parse `compute` (or apply the device default) → preload CUDA
libraries when `device == "cuda"` → `load_model()` → dry-run transcribe → serve. A failure at any
step before `serve` exits non-zero with a message and creates no file.

## Session

Existing structure, extended.

| Field | Type | Notes |
|---|---|---|
| `writer` | `TranscriptWriter` | Unchanged; still flushed after every segment |
| `session_id` | `str` | Reused on reconnect |
| `buffer`, `buffer_start`, `emitted_until`, `last_seen` | unchanged | Window bookkeeping |
| `language` | `str \| None` | From the Hindi feature; resume keeps the original |
| `failed` | `bool` (new) | Set when a transcribe call raises; `process()` stops consuming audio |

State transitions:

```text
start → validate(language, device ready?) → open (writer created)
open → segment* → stop → done
open → transcribe raises → failed → error frame → closed (file kept, flushed)
open → disconnect → paused (10 min) → resume (same writer, same language, same device)
```

## Transcript Header

Existing lines, one extended:

```text
# <title>

Source: <url or file>
Started <ISO-8601>
Language: <code|auto> (model <model>, device <device>/<compute>)
```

The device and precision appear on the existing `Language:` line rather than a new one, so every
transcript produced before this feature still parses: readers that split on `(` keep working, and
the field is appended, never reordered.

## Error Frame

| Field | Type | Notes |
|---|---|---|
| `type` | `"error"` | Unchanged |
| `code` | `str` | `unsupported_language` (existing), `transcription_failed` (new), server-internal codes |
| `message` | `str` | One line, user-readable, names the cause |

A `transcription_failed` frame is fatal to the session: the server has already flushed every
completed segment, so the client's correct response is to stop and show `ERR`, not to reconnect.

## Startup Refusal

Not a frame — the server never binds, so the extension sees a closed socket and reports `ERR`
with the existing "server unreachable" path. The human-readable cause lives in the server's
stderr/stdout, which the user has open in the terminal that launched it.

| Condition | Message shape |
|---|---|
| Unknown device | `ECHOSCRIBE_DEVICE=metal is not supported. Use cpu or cuda.` |
| No CUDA device | `ECHOSCRIBE_DEVICE=cuda found no CUDA device. Set ECHOSCRIBE_DEVICE=cpu.` |
| Bad precision | `ECHOSCRIBE_DEVICE=cuda with ECHOSCRIBE_COMPUTE=int4 cannot run small: <ct2 error>` |
| Missing library | `ECHOSCRIBE_DEVICE=cuda cannot run small: Library libcublas.so.12 is not found ... Install nvidia-cublas-cu12 and nvidia-cudnn-cu12 (uv sync).` |
| Out of memory | `ECHOSCRIBE_DEVICE=cuda cannot run medium: CUDA out of memory ...` |
