# Research: Video-Time Transcript Sync

## D1 — Page access via `activeTab` + `scripting`, injected at the toolbar click

**Decision**: add `"scripting"` to the manifest and call
`chrome.scripting.executeScript({ target: { tabId }, files: ["video-clock.js"] })` from the
existing `action.onClicked` handler, using the same tab ID that `tabCapture` is given.

**Rationale**: `activeTab` is granted by the click itself and covers `scripting` on that tab, so the
manifest gains no host permission and the extension still cannot read any site it was not invited
into. Injection happens once per capture start and costs one call.

**Alternatives considered**: `tabs` + host permissions (broad, violates Principle I); a declared
content script matching all sites (runs everywhere, worse); `chrome.debugger` (shows a banner,
overkill); having the user paste a timestamp (not a feature).

## D2 — Sampling every 500 ms from an injected file

**Decision**: `video-clock.js` runs an interval at 500 ms, picks the element that is actually
playing (`!paused && !ended && readyState > 0`), falls back to the first `video`/`audio`, and posts
`{ position, paused, rate }`. Identical consecutive readings are dropped before sending.

**Rationale**: 500 ms is four samples inside the 2 s tolerance, so a dropped sample cannot break the
budget. Deduping keeps a paused video from generating 2 messages a second for a minute.

**Alternatives considered**: `requestAnimationFrame` (60 messages/s, pointless, and it stops when
the tab is hidden); `timeupdate` events (4 Hz, irregular, fine in theory but needs the same
listener plumbing); polling from the service worker (wakes it constantly, cannot read DOM).

## D3 — Anchors ride the audio clock, not the wall clock

**Decision**: when a reading arrives, the offscreen document stamps it with the audio position it
has already streamed — `samplesSent / 16000` — and sends `{type:"clock", video, audio, paused, rate}`
to the server. The server records anchors in that same coordinate space as segment offsets.

**Rationale**: segments are emitted with audio offsets computed from received samples. Wall-clock
timestamps on the page and the server differ by an unknown amount (different processes, clock drift,
message latency), so matching them would add error. The audio stream is already the shared timeline;
using it makes the mapping exact by construction and makes reconnect behaviour free.

**Alternatives considered**: `Date.now()` on both sides (unbounded skew, fails the 2 s budget);
stamping on the client before sending PCM (the segment boundaries are only known after Whisper
decodes); `performance.now()` relayed through (still two clocks).

## D4 — Extrapolate from the last anchor; clamp at 30 s

**Decision**: `video_at(audio_t)` takes the newest anchor with `anchor.audio <= audio_t` and returns
`anchor.video + (paused ? 0 : (audio_t - anchor.audio) * rate)`. If the anchor is older than 30 s of
audio, the extrapolation stops at the 30 s mark. If a later anchor exists, the result is clamped to
it so a seek cannot be smoothed away.

**Rationale**: background tabs throttle `setInterval` to about once a minute, and a hidden tab is a
normal way to watch a lecture. Extrapolating by `playbackRate` is exact while the player keeps
playing, and `paused` covers the stop case. The 30 s clamp keeps a stalled player from inventing
positions far past the end.

**Alternatives considered**: reject stale anchors and fall back to session time (breaks the session
mid-lecture for no reason); interpolate only between two fresh anchors (fails whenever sampling is
throttled).

## D5 — Replay is a 3 s backwards step between anchors

**Decision**: when a new anchor lands more than 3 s behind the previous maximum video position, open
a replay event `{ from, to, audio }`. Lines whose audio offset is at or after the event and whose
mapped video position is still below `from` get the marker; the event closes once the playhead
passes `from`, so a second rewind opens a second event.

**Rationale**: comparing anchors rather than individual lines survives the sampling interval and
never fires on the normal playback jitter of ±0.2 s. Tying the end of the event to `from` matches
what a reader sees: while the speaker repeats the passage, the playhead sits below the origin.

**Alternatives considered**: per-line position delta (a long pause can fake a jump); a fixed time
window after the seek (marks lines that are not replays); marking every backwards move (jitter
noise).

## D6 — Clock mode is decided by the first line, and can switch with an appended note

**Decision**: if at least one anchor exists when the first segment is emitted, the header says
`Clock: video`. Otherwise it says `Clock: session`, and if anchors arrive later the next emitted
line is preceded by `Clock: video from HH:MM:SS`. The panel shows the current mode from the first
`segment` frame.

**Rationale**: the header cannot be rewritten because the file is append-only (Principle III), so a
late switch has to be stated where it happens. The panel is the live signal; the header is the
record.

**Alternatives considered**: freeze the mode at start (a player that loads in 3 s would leave the
whole lecture session-relative); rewrite the header line (violates append-only, races with readers);
two files (splits one lecture).

## D7 — Replay lines bypass dedupe, and the monotonic guard stays on audio offsets

**Decision**: the existing consecutive-duplicate suppression skips rows that carry a replay marker.
The existing "timestamps never move backwards" guard keeps operating on audio offsets
(`emitted_until`), not on the displayed video time.

**Rationale**: FR-006 requires the same words to appear twice when they were said twice. Displayed
time legitimately moves backwards during a replay; clamping it would either drop the replay or
print a position the playhead never reached.

**Alternatives considered**: exempting whole sessions that contain a replay (loses protection for
the rest of the lecture); a separate duplicate key per replay (more state, same result).

## D8 — A failed injection is a fallback, not an error

**Decision**: if `executeScript` throws, log the API name and message, continue in session mode, and
let the panel show `session`. If the page navigates during capture, the reporter dies; anchors go
stale and the session continues on the last known position.

**Rationale**: the spec makes the feature an enhancement, not a prerequisite. Failing a lecture
because a site blocks injection would violate Principle III for a cosmetic gain.

**Alternatives considered**: stop capture with `ERR` (loses the transcript); retry injection from
`tabs.onUpdated` (needs `tabs` events plus activeTab regranted, which navigation removes).
