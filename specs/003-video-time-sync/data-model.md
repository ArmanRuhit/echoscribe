# Data Model: Video-Time Transcript Sync

## Clock Reading

Produced in the captured tab, consumed by the offscreen document.

| Field | Type | Rule |
|---|---|---|
| `position` | number | seconds; finite, `>= 0`; clamped to `[0, duration]` when duration is finite |
| `paused` | boolean | `video.paused` |
| `rate` | number | `video.playbackRate`; accepted range 0.25–4, otherwise treated as 1 |
| `element` | `"video"` \| `"audio"` | only for logging; not sent |

A reading is discarded when the element has `readyState === 0`, when `position` is not finite, or
when it is identical to the previous reading.

## Anchor

Server-side record of one reading placed on the audio timeline.

| Field | Type | Rule |
|---|---|---|
| `audio` | number | seconds of audio received when the reading arrived; non-decreasing |
| `video` | number | the reading's position |
| `paused` | boolean | copied from the reading |
| `rate` | number | copied from the reading |

Stored in a bounded list per session (last 64 anchors). Anchors older than the newest by more than
60 s of audio are dropped. A session with no anchors is not in video mode.

## Clock Mode

| Value | Meaning | Header |
|---|---|---|
| `pending` | no line written yet | not written |
| `session` | audio offsets are displayed | `Clock: session` |
| `video` | anchors are used | `Clock: video` |

Transitions: `pending → session` or `pending → video` at the first emitted line; `session → video`
at most once, announced by a `Clock: video from HH:MM:SS` line before the next segment. `video` is
terminal: stale anchors stop the clock at the last known position rather than switching back and
mixing two time bases in one file.

## Replay Event

| Field | Type | Rule |
|---|---|---|
| `from` | number | highest video position seen before the jump |
| `to` | number | position the playhead landed on; `from - to >= 3` |
| `audio` | number | audio position at which the jump was observed |
| `closed` | boolean | set once a mapped position reaches `from` again |

At most one event is open at a time. A second rewind while the first is open closes the first at the
new `from` and opens another, so a repeated passage carries the marker twice.

## Segment

Existing `{start, end, text}`, plus:

| Field | Type | Rule |
|---|---|---|
| `video` | number | mapped video position of `start`; absent in session mode |
| `replayFrom` | number | present only while a replay event is open for this offset |

Duplicate suppression is skipped when `replayFrom` is present. The speech/loop filters still run:
a hallucinated loop inside a replay is still junk.

## Transcript Line

```text
[HH:MM:SS] text                                # normal
[HH:MM:SS] (replay from HH:MM:SS) text         # replay
```

The `[HH:MM:SS]` prefix keeps its existing shape, so current readers still parse the line; the
marker sits after it. Timestamps are the video clock in video mode and the session clock otherwise.

## Header

```text
# <title>

Source: <url>
Started <ISO 8601>
Clock: video
```

`Clock:` is appended by the first emitted line, then never edited. A late switch adds
`Clock: video from HH:MM:SS` as a new line at the switch point, so the file stays append-only.
