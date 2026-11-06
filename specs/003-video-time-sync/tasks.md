# Tasks: Video-Time Transcript Sync

**Input**: Design documents from `/specs/003-video-time-sync/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: none requested. No test framework exists in this repo; verification is the quickstart
scenarios plus a throwaway Python harness for the clock mapper, the same pattern used for 001 and 002.

**Organization**: Tasks are grouped by user story. US1 is the MVP; US2 and US3 are additive.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different file, no dependency on an incomplete task
- **[Story]**: US1, US2, US3
- Exact paths in every task

## Phase 1: Setup

- [X] T001 Add `"scripting"` to the `permissions` array in `extension/manifest.json`, keeping `activeTab` (no `host_permissions`)

---

## Phase 2: Foundational (blocking)

**Purpose**: the reporter, its transport, and the audio→video mapper that every story needs.

- [X] T002 [P] Create `extension/video-clock.js` that picks the playing element (`!paused && !ended && readyState > 0`, else the first `video`, else the first `audio`), samples `currentTime`/`paused`/`playbackRate` every 500 ms, discards a reading when `readyState === 0` or the position is not finite or identical to the previous one, clamps `position` to `[0, duration]` when duration is finite, treats `rate` outside 0.25–4 as 1, and posts `{ target: "offscreen", type: "VIDEO_CLOCK", position, paused, rate }`
- [X] T003 Inject the reporter once at capture start in `extension/background.js`, inside the existing `chrome.action.onClicked` handler after `getMediaStreamId`: `await chrome.scripting.executeScript({ target: { tabId }, files: ["video-clock.js"] })` wrapped in try/catch that logs `executeScript: <message>` and continues; it must never block the session or set `ERR`
- [X] T004 [P] Relay readings in `extension/offscreen.js`: handle `VIDEO_CLOCK`, stamp `audio: samplesSent / 16000` at the moment the message is handled, and send `{ type: "clock", video: position, audio, paused, rate }` only when the socket is OPEN; clock frames must never enter the reconnect queue
- [X] T005 [P] Accept clock frames in `server/transcribe_server.py`: add `Anchor(audio, video, paused, rate)` and `Session.anchors: list[Anchor]`; on `{"type":"clock"}` ignore non-finite fields or `rate` outside 0.25–4, append otherwise, keep the newest 64, drop anchors more than 60 s of audio behind the newest
- [X] T006 Implement `video_at(audio)` in `server/transcribe_server.py`: newest anchor with `anchor.audio <= audio`, else the oldest; extrapolate `video + (audio - anchor.audio) * (0 if paused else rate)`; clamp to 30 s of staleness; never return more than the next anchor's `video`
- [X] T007 [P] Write `/tmp/opencode/clock_harness.py` feeding anchor sequences to `video_at` and asserting: pause holds position, `rate=1.5` extrapolates, a stale anchor freezes, a later anchor wins after a seek, and a reading older than 60 s is dropped

**Checkpoint**: a session can stream anchors and map any audio offset to a video position.

---

## Phase 3: User Story 1 — Timestamps follow the video clock (P1) 🎯 MVP

**Goal**: every transcript line carries the player's position, including across pauses and speed changes.

**Independent Test**: start capture at 12:30 of an HTML5 video; the first line reads `[00:12:30]`, and after a 30 s pause followed by 1.5× playback the line times still match the player within 2 s.

- [X] T008 [US1] Track clock mode in `server/transcribe_server.py`: `pending` until the first emitted segment, then `video` when anchors exist and `session` otherwise; `TranscriptWriter.create` writes no `Clock:` line and the first `append` adds `Clock: video` or `Clock: session` once (append-only, never edited)
- [X] T009 [US1] Stamp segments in `Session._emit_window` in `server/transcribe_server.py`: when the mode is video, compute `video = video_at(global_start)` and pass it to `writer.append`; keep the monotonic `emitted_until` guard on audio offsets only so displayed video time may go backwards
- [X] T010 [US1] Extend the `segment` frame in `server/transcribe_server.py` with `video` (video mode only) and `clock` (`"video"` or `"session"`)
- [X] T011 [US1] Add `"clock": "pending"` to the `ready` frame in `server/transcribe_server.py`
- [X] T012 [P] [US1] Relay the clock in `extension/offscreen.js`: store `ready.clock` (and the `clock` field on `segment`/`STATUS`) in module state, and include `clock` in every `STATUS recording` / `STATUS reconnecting`
- [X] T013 [P] [US1] Render the clock in `extension/sidepanel.js`: append ` · video` or ` · session` to the status label, show nothing while `pending`, and clear it on `idle` and `error` alongside language/model/device
- [ ] T014 [US1] Run quickstart Scenarios 1 and 2 (first line position; accuracy across pause and 1.5×) and paste the observed line times into this task

**Checkpoint**: US1 is shippable on its own — timestamps match the player even with no replay support.

---

## Phase 4: User Story 2 — A replay is visibly a replay (P2)

**Goal**: lines written after a backwards seek name the position they returned to.

**Independent Test**: rewind 20 s mid-lecture; every following line until the playhead passes the origin reads `[HH:MM:SS] (replay from HH:MM:SS)`, and the original pass keeps its own lines.

- [X] T015 [US2] Detect replays in `server/transcribe_server.py` while ingesting anchors: a new anchor more than 3 s behind the highest video position seen opens a `Replay(from, to, audio, closed=False)`; a second rewind while one is open closes the first at the new `from` and opens another; close the open event once a mapped position reaches `from` again
- [X] T016 [US2] Print the marker in `Session._emit_window` and `TranscriptWriter.append` in `server/transcribe_server.py`: `[HH:MM:SS] (replay from HH:MM:SS) text`, send `replayFrom` in the segment frame, skip consecutive-duplicate suppression for these segments, and keep the speech/loop filters running
- [ ] T017 [US2] Run quickstart Scenarios 3, 4 and 5 (rewind marked with correct origin; forward seek leaves a gap only; the same passage twice is marked both times)

---

## Phase 5: User Story 3 — A tab with no readable player still transcribes (P3)

**Goal**: no player, no reporter, no problem — the transcript falls back and says so.

**Independent Test**: capture an audio-only tab (or block `executeScript`); lines use session time, the header says `Clock: session`, and nothing is lost.

- [X] T018 [US3] Finish the fallback in `server/transcribe_server.py`: a session that never receives anchors writes `Clock: session` and session timestamps, keeps all existing filters, and never errors
- [X] T019 [US3] Handle the late switch in `server/transcribe_server.py`: `session → video` at most once, announced by a `Clock: video from HH:MM:SS` line before the next segment; `video` is terminal, so stale anchors freeze time instead of switching back
- [ ] T020 [US3] Run quickstart Scenarios 6 and 7 (audio-only fallback; player disappears mid-session)

---

## Phase 6: Polish

- [X] T021 Update `AGENTS.md`: protocol block gains the `clock` frame and the `video`/`clock`/`replayFrom` fields, a Clock paragraph (anchors ride the audio clock, 3 s replay threshold, one-way mode switch), and the `scripting` permission in the ladder
- [X] T022 [P] Update `README.md`: what the timestamp means now, the replay marker, the session-clock fallback, and the `scripting` permission note
- [ ] T023 Run the full `quickstart.md` and a 30-minute lecture, recording accuracy against SC-001 (95% within 2 s), SC-002 (first line), and SC-003 (every rewind ≥10 s marked)
- [ ] T024 Run the caveman review on `git diff`, apply nits, then commit `feat: sync transcript timestamps to video time`

---

## Dependencies & Execution Order

- T001 → T003 (the injected filename must exist and be permitted)
- T002 → T003 → T004
- T004 → T005 → T006 → T008
- T007 depends on T006
- T008 → T009 → T010 → T014
- T011 → T012 → T013
- T015 → T016 → T017 (needs T009's video mapping)
- T018, T019 need T008; US3 can run before US2
- T024 last

## Parallel Opportunities

```text
T002 video-clock.js   |  T004 offscreen.js  |  T005 server anchors
T012 offscreen STATUS |  T013 sidepanel label
T021 AGENTS.md        |  T022 README.md
```

## Implementation Strategy

**MVP**: Phases 1–3 (T001–T014). That alone fixes the stated problem — timestamps that track the
lecture — and is worth committing before replay work starts.

**Incremental**: US2 (T015–T017) then US3 (T018–T020). Each leaves the file readable by the current
Markdown shape.

## Notes

- Only `server/transcribe_server.py` is touched by T005, T006, T008–T011, T015, T016, T018, T019: run them in order.
- The client and server must ship together: a new client against an old server gets `Unknown message type: clock`, which is intentionally fatal.
- Manual tasks that need a browser and a real lecture: T014, T017, T020, T023.
