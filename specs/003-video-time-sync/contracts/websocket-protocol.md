# Contract: WebSocket Protocol (v3)

Extends v2 (language, device, named refusals). Everything below is additive; a v2 client that never
sends `clock` frames gets exactly the old session-clock behaviour.

## Client → server

```json
{"type":"start","sessionId":"...","title":"...","url":"...","sampleRate":16000,"language":"hi"}
{"type":"clock","video":754.2,"audio":96.5,"paused":false,"rate":1.0}
{"type":"stop"}
binary Int16 mono PCM frames                        # unchanged
```

`clock` frames may start at any time, may stop and resume, and may arrive out of order relative to
audio by one frame. The server keeps the newest 64, drops anything older than 60 s behind the newest,
and ignores a frame whose fields are not finite numbers or whose `rate` is outside 0.25–4.

`clock` frames are never queued for reconnect: they are only useful at the moment they describe, and
a replayed anchor would map old audio to a stale position. A reconnect is re-anchored by the next
frame, within 500 ms.

## Server → client

```json
{"type":"ready","model":"small","language":"hi","device":"cuda","compute":"float16","clock":"pending","sessionId":"...","resumed":false}
{"type":"segment","start":12.3,"end":16.8,"video":754.2,"clock":"video","text":"..."}
{"type":"segment","start":63.1,"end":67.0,"video":762.0,"clock":"video","replayFrom":754.2,"text":"..."}
{"type":"error","code":"transcription_failed","message":"..."}
```

| Field | Rule |
|---|---|
| `ready.clock` | always `"pending"`; the mode is not known until audio and anchors exist |
| `segment.clock` | `"video"` or `"session"`, constant for the session except one `session → video` switch |
| `segment.video` | present in video mode only |
| `segment.replayFrom` | present only when the segment falls inside an open replay event |

Resume: a resumed session keeps the clock mode and the anchors it had. If the server restarted, no
anchors survive, the session starts in session mode and may switch once the client re-anchors — the
switch line makes that visible in the file.

## Compatibility

- Old client, new server: no `clock` frames → session mode, `Clock: session` header, no markers.
- New client, old server: `clock` frames are unknown types; the server answers with its existing
  "unknown type" error frame, which the client treats as fatal. This is why extension and server
  ship together and why a version mismatch must be reported, not ignored.
