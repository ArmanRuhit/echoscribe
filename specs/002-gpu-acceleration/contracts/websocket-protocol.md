# Contract: WebSocket Protocol (GPU additions)

Inherits `../001-hindi-transcript/contracts/websocket-protocol.md`. Only the additions and one
behavior change are listed here; everything else is unchanged.

## `start` (client → server)

Unchanged. No device field: the device is a server setting, fixed for the run.

```json
{"type": "start", "sessionId": "...", "title": "...", "url": "...",
 "sampleRate": 16000, "language": "hi"}
```

## `ready` (server → client) — extended

```json
{"type": "ready", "model": "small", "language": "hi",
 "device": "cuda", "compute": "float16",
 "sessionId": "...", "resumed": false}
```

- `device`: `"cpu"` or `"cuda"` — the device actually in use, not the requested one.
- `compute`: `"int8"`, `"float16"`, `"float32"`, … — the precision actually in use.
- Both are additive. A client that ignores them keeps working.

## `error` (server → client) — extended

```json
{"type": "error", "code": "transcription_failed",
 "message": "CUDA out of memory while transcribing 12:30–12:35"}
```

Codes:

| `code` | When | Client response |
|---|---|---|
| `unsupported_language` | `start` named a language the model cannot do | Stop, `ERR`, no file was opened |
| `transcription_failed` | The model raised during a window | Stop, `ERR`, keep the partial file |
| `invalid_message` / others | Malformed frame, binary before `start` | Log; server is still serving |

**Behavior change**: an `error` frame is now fatal on the client whether it arrives before or
after `ready`. The server treats a model exception as unrecoverable for that session, so
reconnecting would only reproduce it.

## Startup refusal (server not running)

Not a protocol event. When the device or precision cannot be used, the server prints the cause and
exits before binding the port. The client sees a refused connection, reports `ERR` with "server
unreachable", and creates no file. The cause is read in the terminal running the server.

## Compatibility

- Old server + new client: `device`/`compute` absent → the panel omits them; nothing breaks.
- New server + old client: extra fields ignored; the post-`ready` error stays console-only, which
  is the old behavior and acceptable for a stale extension.
