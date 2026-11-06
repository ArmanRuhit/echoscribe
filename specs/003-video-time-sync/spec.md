# Feature Specification: Video-Time Transcript Sync

**Feature Branch**: `003-video-time-sync`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "keep the time in sync with videos time
that way it will be easier to track
also if replay some seconds it will help me understand this is replayed part"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Timestamps follow the video clock (Priority: P1)

A learner starts capture ten minutes into a lecture. Every line in the transcript is stamped with the position in the video where it was said, so `12:30` in the file means `12:30` in the player. Later, they read the transcript, see a line that matters, and jump straight to that point in the video without doing arithmetic.

**Why this priority**: This is the whole request. A transcript whose clock disagrees with the video forces the reader to add the capture start offset mentally, which is exactly the friction being removed. Without this, the rest of the feature has nothing to attach to.

**Independent Test**: Start capture at a known player position, speak or play a clip, then compare the first timestamped line with the player clock. Both should name the same position within tolerance.

**Acceptance Scenarios**:

1. **Given** a lecture paused at 12:30, **When** capture starts and playback resumes, **Then** the first transcript line is stamped near 12:30, not near 00:00.
2. **Given** capture running during continuous playback, **When** the learner checks a line against the player at any later point, **Then** the line's timestamp matches the player position within the stated tolerance.
3. **Given** the learner pauses the video for a minute and resumes, **When** transcription continues, **Then** timestamps resume from the paused position instead of drifting a minute ahead.
4. **Given** playback at 1.5× speed, **When** a line is written, **Then** its timestamp still matches the player's displayed position.

---

### User Story 2 - A replay is visibly a replay (Priority: P2)

The learner rewinds fifteen seconds to hear a sentence again. The transcript shows those lines with a marker saying they are a replay and where the playhead came from, instead of appending what looks like new material at a later time.

**Why this priority**: Re-reading a lecture is confusing when the same words appear twice with no explanation. Marking the jump keeps the transcript honest about what happened in the room.

**Independent Test**: Rewind during a session and confirm the next lines carry a replay marker naming the position jumped from.

**Acceptance Scenarios**:

1. **Given** capture running at 12:30, **When** the learner rewinds to 12:15, **Then** lines written after the rewind carry a visible replay marker and the position 12:30 as the origin.
2. **Given** the same passage is replayed twice, **When** both replays are transcribed, **Then** both are marked; neither is silently dropped as a duplicate.
3. **Given** the learner seeks forward instead of back, **When** transcription resumes, **Then** the transcript shows a gap in timestamps with no replay marker, because nothing was repeated.
4. **Given** a small backwards jitter of a second or two, **When** transcription continues, **Then** it is not marked as a replay.

---

### User Story 3 - A tab with no readable player still transcribes (Priority: P3)

Some pages have no video element, or the player refuses to report its position. Capture still works, the file is still written, and the header says the clock is the session clock rather than pretend otherwise.

**Why this priority**: Degrading to today's behaviour is acceptable; failing the session or writing misleading timestamps is not. This story protects the other two from turning into a hard dependency.

**Independent Test**: Start capture on an audio-only page and confirm the file is written with a header stating session-relative timing.

**Acceptance Scenarios**:

1. **Given** a tab with no video element, **When** capture runs, **Then** the transcript is written and the header states that timestamps are session-relative.
2. **Given** a readable player that stops reporting mid-session, **When** transcription continues, **Then** the last known position is used, the session does not fail, and no line is lost.
3. **Given** a session with no readable player, **When** the learner reads the file, **Then** they can tell the timestamps are not video positions.

---

### Edge Cases

- Video reaches its end while capture continues: timestamps hold at the final position; no line claims a position past the end.
- The page replaces its player mid-session (single-page navigation): sync re-establishes or falls back, without an error badge.
- Several video elements on one page: the one actually playing is the clock; a paused decorative video is ignored.
- The learner scrubs backwards across a long stretch, then forwards again: each direction change is reflected once, not once per sample.
- Live streams: player position is used when available; DVR behaviour is not guaranteed.
- Capture starts before the video has loaded: the first lines fall back to session time until the player reports a position.
- The learner switches tabs while capture is running: only the captured tab is read, never the newly focused one.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Transcript lines MUST be stamped with the captured video's own playback position, in `HH:MM:SS`, for any page where that position can be read.
- **FR-002**: The first line of a session MUST reflect the position at which capture started, not zero.
- **FR-003**: Timestamps MUST stay within 2 seconds of the player's displayed position for the whole session, including after pauses and at non-default playback speeds.
- **FR-004**: When the playhead moves backwards by 3 seconds or more, lines written afterwards MUST carry a visible replay marker that names the position the playhead jumped from.
- **FR-005**: A forward jump MUST appear as a timestamp gap only; it MUST NOT be marked as a replay.
- **FR-006**: Replayed lines MUST NOT be suppressed by duplicate filtering, and MUST NOT overwrite the earlier occurrence of the same words.
- **FR-007**: When no live video position is available, the session MUST fall back to session-relative timestamps and state that in the transcript header, without failing or losing lines.
- **FR-008**: The transcript file MUST remain append-only and keep the existing line shape, so existing readers and destinations continue to work.
- **FR-009**: The feature MUST read the clock only from the tab being captured; it MUST NOT read other tabs and MUST NOT make network requests.
- **FR-010**: The side panel MUST show whether the current session is following the video clock or the session clock.
- **FR-011**: Language selection, device selection, and audio handling MUST behave exactly as before.

### Key Entities

- **Video Clock Reading**: the player position at a moment in capture time. Attributes: position, capture instant, whether it is fresh.
- **Sync Anchor**: the mapping between capture time and video position that lets a line written later be stamped correctly.
- **Replay Event**: a backwards jump of the playhead. Attributes: origin position, landing position, capture instant.
- **Transcript Line**: the existing timestamped text plus an optional replay marker. The line's shape stays readable by existing tooling.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a 30-minute session started mid-lecture, at least 95% of lines read within 2 seconds of the player position where those words are spoken.
- **SC-002**: Starting capture at a known player position, the first line is stamped within 2 seconds of that position.
- **SC-003**: 100% of test rewinds of 10 seconds or more appear as marked replays with the correct origin.
- **SC-004**: Zero sessions fail and zero lines are lost when the player position cannot be read; every such session still produces a transcript file.
- **SC-005**: A reader who seeks to a timestamped line lands on those words in the video on the first attempt in at least 9 of 10 tries.
- **SC-006**: The file remains parseable by the existing line format; a diff of a replay-free session shows no format change beyond the header.

## Assumptions

- The learner watches a standard HTML5 video or audio player in the captured tab. DRM-protected content stays out of scope.
- A backwards jump under 3 seconds is treated as jitter, not a replay; 3 seconds is the threshold.
- Position is sampled frequently enough that a 2-second tolerance holds; the exact sampling belongs to planning.
- The feature reads the captured tab only, keeping the existing local-only, no-network stance.
- Session-relative timing remains the fallback and the format of that fallback does not change.
- Marker wording and glyph are decided during planning; the requirement is only that a replay is unmistakable and names its origin.
- Existing behaviour for language, device, transcript location, and audio handling is unchanged.
