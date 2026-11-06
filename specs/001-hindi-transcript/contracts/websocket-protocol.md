# Contract: WebSocket Protocol

Transport, framing, and audio rules are unchanged: `ws://127.0.0.1:8765`, JSON text
frames, binary Int16 mono PCM at 16 kHz. This document covers only the fields this feature
adds or tightens.

## `start` (client → server)

```json
{
  "type": "start",
  "sessionId": "0d9f...",
  "title": "Lecture 12",
  "url": "https://...",
  "sampleRate": 16000,
  "language": "hi"
}
```

| Field | Required | Rules |
|---|---|---|
| `language` | no | `en`, `hi`, or omitted. Invalid values are refused, never coerced. |
| everything else | unchanged | as today |

When `language` is omitted the server uses `ECHOSCRIBE_LANGUAGE`, preserving today's
behavior.

## `ready` (server → client)

```json
{
  "type": "ready",
  "model": "small",
  "language": "hi",
  "sessionId": "0d9f...",
  "resumed": false
}
```

`language` is the effective session language, after defaulting. The panel uses it to label
the session; the client does not re-derive it.

## `error` (server → client)

Existing shape, now with an optional `code`:

```json
{
  "type": "error",
  "code": "unsupported_language",
  "message": "Model small.en supports English only. Set ECHOSCRIBE_MODEL=small (multilingual) and restart the server."
}
```

**Client rules**:
- An `error` received before `ready` is fatal: the client stops, shows `ERR`, and displays
  `message` in the panel. No worklet is attached, so no PCM is produced.
- An `error` received after `ready` keeps today's behavior: log it, keep the session.

**Server rules**:
- Validation runs before the transcript file is created and before the session is stored.
- Refusal conditions: explicit non-English language with a model whose name ends in `.en`.
- Unknown language codes are refused with `code: "unsupported_language"` as well, so a typo
  cannot silently become English.

## `segment` (server → client)

Unchanged shape. `text` may be Devanagari, Latin, or both within one segment.

## Compatibility

A client that never sends `language` behaves exactly as before. A server that receives an
unknown field ignores it. No version negotiation is added.
