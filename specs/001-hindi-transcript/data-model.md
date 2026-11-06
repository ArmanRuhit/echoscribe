# Data Model: Hindi Transcript Support

## Language Selection

A language the user can pick in the panel.

| Field | Type | Rules |
|---|---|---|
| `code` | string | `en` or `hi`; sent on the wire |
| `label` | string | `English`, `Hindi` |
| `script` | string | `Latin`, `Devanagari` |
| `requires_multilingual` | boolean | `false` for `en`, `true` for `hi` |

**Validation**: an unknown code is rejected by the server with an `error` frame rather than
silently treated as English. `auto` remains accepted server-side as "no language pinned"
for multilingual models only.

**Lifecycle**: selected in the panel → `chrome.storage.session` → read at toolbar click →
sent in the `start` frame → fixed for the life of that session.

## Transcription Session

One running capture, created by the server on `start`.

| Field | Type | Rules |
|---|---|---|
| `session_id` | string (UUID) | client-generated; reused on reconnect |
| `language` | string | from `start`, defaults to the server's `ECHOSCRIBE_LANGUAGE` |
| `model` | string | loaded model name; its `.en` suffix decides capability |
| `writer` | Transcript File | created only after validation passes |
| `buffer` | bytes | unchanged 5 s window, 1 s overlap |
| `emitted_until` | float | unchanged de-duplication boundary |
| `last_seen` | monotonic time | unchanged 10-minute expiry |

**State transitions**:

```text
start ──▶ validate ──ok──▶ open (file created, ready sent)
                  └─fail─▶ rejected (error sent, no file, no session entry)
open ──▶ stop ──▶ finalized
open ──▶ socket drop ──▶ paused (10 min TTL) ──▶ resumed (same language)
```

**Rules**:
- A resumed session keeps its original language; a new `language` value on reconnect is
  ignored.
- A rejected session leaves no entry in `SESSIONS` and no file on disk.

## Transcript Segment

One transcribed utterance, as today.

| Field | Type | Rules |
|---|---|---|
| `start` | float seconds | session-relative |
| `end` | float seconds | session-relative |
| `text` | string | trimmed; Devanagari for Hindi speech, Latin for English terms |

**Rules**: empty text is skipped; segments ending at or before `emitted_until + 0.05` are
dropped; text is appended as UTF-8 with no script normalization.

## Transcript File

Unchanged from the English path.

| Field | Type | Rules |
|---|---|---|
| `path` | `~/EchoScribe/transcripts/YYYY-MM-DD_HH-MM-SS_<slug>.md` | one per session |
| header | Markdown | title, source URL, ISO start time |
| body | lines | `[HH:MM:SS] <text>` in spoken order |

**Rules**: created after validation only; opened in append mode with `encoding="utf-8"`;
flushed after every segment.

## Relationships

```text
Language Selection 1 ──▶ 0..1 Transcription Session   (per start)
Transcription Session 1 ──▶ 1 Transcript File
Transcription Session 1 ──▶ 0..* Transcript Segment
Transcript File 1 ──▶ * Transcript Segment (as text lines)
```
