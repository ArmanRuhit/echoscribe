# Quickstart: Video-Time Transcript Sync

## Prerequisites

1. Restart the server — a stale process answers `clock` frames with "Unknown message type", which
   the new client treats as fatal on purpose. The message names the cause; the fix is a restart.
2. Reload the extension in `chrome://extensions` (or `brave://extensions`). `manifest.json` gained
   `scripting`, and permissions only apply after a reload.
3. Open a lecture in a standard HTML5 player (YouTube, Coursera, a local `<video>` page). DRM is out
   of scope.

```bash
ECHOSCRIBE_MODEL=large-v3 ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py
```

The panel's status line ends in `· video` or `· session`; the header of the new file repeats it.

## Scenario 1 — First line reflects where capture started (SC-002)

1. Pause the lecture at a known position, ideally past 10:00.
2. Start capture, then resume playback.
3. Read the first line of the new file.

```bash
tail -n +1 ~/EchoScribe/transcripts/<file>.md | head -12
```

**Expected**: `Clock: video`, and the first timestamped line is within 2 s of the paused position,
not `00:00:0x`.

## Scenario 2 — Accuracy survives pause and speed (SC-001)

1. Play for two minutes at 1×, pause for 60 s, resume, switch to 1.5× for two minutes.
2. At the end, compare the newest line with the player.

```bash
tail -1 ~/EchoScribe/transcripts/<file>.md; date +%H:%M:%S
```

**Expected**: the line's position matches the player within 2 s. During the pause the position holds
instead of advancing. At 1.5× the position advances 1.5 s per second of audio.

## Scenario 3 — A rewind is marked (SC-003)

1. Note the player position (for example `12:30`), rewind 15 s, and listen through the passage.
2. Find the lines written after the rewind.

```bash
grep -n "replay from" ~/EchoScribe/transcripts/<file>.md
```

**Expected**: `[12:15] (replay from 12:30) …` on the lines covering the repeated passage, and the
marker stops once the playhead passes `12:30`.

## Scenario 4 — A forward seek is a gap, not a replay

1. Seek forward 5 minutes without listening to what was skipped.

**Expected**: timestamps jump forward, no `(replay from …)` appears, and no line claims the skipped
material. A gap in the timestamps is the correct result.

## Scenario 5 — The same passage twice is written twice (FR-006)

1. Replay the same 20 s twice.

**Expected**: two marked lines for the same words. The duplicate filter never drops a replay line.

## Scenario 6 — No player falls back cleanly (SC-004)

1. Start capture on an audio-only page or a page whose player is inside an iframe the extension
   cannot read.
2. Speak for a minute.

**Expected**: the file is created, `Clock: session` is in the header, the panel says `· session`,
and every line is present. No `ERR`.

## Scenario 7 — The player disappears mid-session

1. Start on a player page, then navigate the player away (or let a single-page player remount).

**Expected**: timestamps hold at the last known position, the session keeps writing, no `ERR` badge.
If the new player reports again, the clock resumes from there.

## Scenario 8 — Everything else is unchanged

```bash
node --check extension/*.js
uv run python -m py_compile server/transcribe_server.py
```

**Expected**: language selection still refuses `hi` on `small.en`, the device line still reads
`GPU float16`, and the transcript still lives in `~/EchoScribe/transcripts/`.

## Failure signs

| Symptom | Likely cause |
|---|---|
| `Unknown message type: clock` then `ERR` | server not restarted |
| `· session` on a page that has a video | injection failed or the player is cross-origin in an iframe; check the service worker console |
| timestamps drift ahead of the player | anchors are stale because the tab was hidden for minutes; bring the tab forward and confirm they resync |
| replay marker never appears | the jump was under 3 s by design, or the anchor after the seek was dropped |
