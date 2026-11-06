# Feature Specification: Hindi Transcript Support

**Feature Branch**: `001-hindi-transcript`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "add hindi transcript support"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hindi lecture transcribed in Devanagari (Priority: P1)

A learner plays a Hindi lecture and starts transcription the way they already do for
English. Each spoken sentence appears in the live panel and is appended to the Markdown
file in Devanagari with the same timestamps as an English session, while the lecture keeps
playing.

**Why this priority**: This is the feature. Without it none of the guardrails or
refinements matter.

**Independent Test**: Play 60 seconds of Hindi speech with a multilingual model selected
and Hindi chosen as the language. Confirm Devanagari sentences appear in the panel within
5 seconds, in spoken order, and that the file on disk matches the panel.

**Acceptance Scenarios**:

1. **Given** Hindi is selected and a multilingual model is configured, **When** the user
   starts a session on a Hindi lecture, **Then** segments appear in the panel and in the
   transcript file in Devanagari, timestamped and in spoken order.
2. **Given** a session is running, **When** a segment is transcribed, **Then** the
   transcript file is updated while the lecture is still playing, not only after stopping.
3. **Given** the user stops the session, **Then** the file is finalized with its header
   intact and no audio file exists anywhere on disk.

---

### User Story 2 - A language/model mismatch is refused, not faked (Priority: P2)

A learner who is set up for English-only transcription selects Hindi. Instead of
producing nonsense, the app refuses to start and says what is missing.

**Why this priority**: Hindi audio pushed through an English-only model produces
confident, wrong text. Silent bad output is worse than a refusal, and the project's
constitution makes visible failure mandatory.

**Independent Test**: Select Hindi with an English-only model and start. The badge shows
`ERR`, the panel names the limitation, no transcript file is created, and the lecture
audio is untouched.

**Acceptance Scenarios**:

1. **Given** an English-only model and Hindi selected, **When** the user starts,
   **Then** the badge shows `ERR` and the panel explains that the configured model only
   understands English, before any audio is captured.
2. **Given** that refusal is shown, **When** the user switches to a multilingual model and
   starts again, **Then** the session runs normally.
3. **Given** a multilingual model and English selected, **When** the user starts, **Then**
   the session behaves exactly as it does today.

---

### User Story 3 - Mixed Hindi-English lecture keeps both scripts (Priority: P3)

A lecture is mostly Hindi but the speaker says "gradient descent", "API", and "cache" in
English. Those terms stay in Latin script inside Hindi sentences instead of being
transliterated into Devanagari.

**Why this priority**: Real technical lectures in Hindi are bilingual. Transliteration
makes the terms unrecognizable in the file and unsearchable later.

**Independent Test**: Transcribe a bilingual sentence containing three English technical
terms. All three appear in Latin script, unaltered, inside the Devanagari sentence.

**Acceptance Scenarios**:

1. **Given** Hindi is selected, **When** the speaker says a Hindi sentence containing an
   English technical term, **Then** the term appears in Latin script within the Devanagari
   sentence.
2. **Given** the speaker delivers a full English sentence during a Hindi session,
   **Then** it is transcribed as English, not translated into Hindi.
3. **Given** the speaker uses an English acronym, **When** it is written to the file,
   **Then** the acronym keeps its original upper-case spelling.

---

### Edge Cases

- **Lecture language differs from the selection**: a Hindi selection on an English
  lecture produces readable text rather than an error or a translation.
- **Silence or non-speech audio in a Hindi session**: no empty or invented segments are
  written, matching today's English behavior.
- **Devanagari glyphs missing from the host fonts**: the panel and file still show
  legible characters, with no missing-glyph boxes.
- **Very long Hindi session (30+ minutes)**: one file, same naming pattern, same
  per-segment append behavior, no truncation.
- **Server restart mid-session**: reconnecting continues the same file in the same
  language instead of starting a new one.
- **Language changed while a session is running**: the running session keeps its
  language; the change applies to the next session.
- **Unsupported or misspelled language value**: startup fails visibly instead of falling
  back to English.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to choose Hindi as the transcription language for a
  session without editing source code.
- **FR-002**: The chosen language MUST apply to the whole session and MUST be visible in
  the panel while the session runs.
- **FR-003**: Hindi speech MUST be transcribed into Devanagari text. It MUST NOT be
  transliterated into Latin script and MUST NOT be translated into English.
- **FR-004**: Hindi transcripts MUST use the same file location, file naming pattern,
  header format, and `[HH:MM:SS]` timestamps as English transcripts.
- **FR-005**: Hindi sessions MUST append and flush the transcript after every segment,
  exactly as English sessions do.
- **FR-006**: The system MUST refuse to start a Hindi session when the configured model
  supports English only, before any audio is captured, and MUST show `ERR`.
- **FR-007**: The refusal MUST name the limitation in one line and state the corrective
  action, without a stack trace or a silent fallback.
- **FR-008**: English words and acronyms inside Hindi speech MUST remain in Latin script
  and unaltered.
- **FR-009**: The live panel MUST render Devanagari with correct character shaping and no
  missing-glyph boxes, without changing the layout of Latin text.
- **FR-010**: Selecting English MUST leave today's behavior unchanged, including the
  default configuration requiring no new choices.
- **FR-011**: An unsupported language value MUST fail visibly at startup instead of
  defaulting to English.
- **FR-012**: Hindi transcripts MUST remain UTF-8 Markdown written locally, with no new
  network calls and no audio persisted, per the project constitution.

### Key Entities

- **Language Selection**: a language the user can pick; has a name, a script, and the
  model capability it requires.
- **Transcription Session**: one running capture; has a language, a source tab, a start
  time, and one transcript file.
- **Transcript Segment**: one transcribed utterance; has a time range, text, and the
  script the text is written in.
- **Transcript File**: the Markdown artifact for a session; has a header, one timestamped
  line per segment, and is append-only while recording.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a 5-minute Hindi lecture, at least 95% of sampled Hindi words are
  written in Devanagari script, measured over a 100-word sample.
- **SC-002**: The first Hindi segment appears within 5 seconds of speech, matching the
  current English latency budget.
- **SC-003**: 100% of attempts to start Hindi with an English-only model are refused
  before capture, and none of them create a transcript file.
- **SC-004**: A 1-minute Hindi playback shows zero missing-glyph boxes in the live panel.
- **SC-005**: The existing English test checklist passes unchanged on the same build.
- **SC-006**: In a bilingual sentence containing three English technical terms, all three
  appear in the transcript with their original Latin spelling.
- **SC-007**: A user who has only transcribed English before can start a Hindi session
  after changing at most one setting, with no restart of the extension itself.

## Assumptions

- "Hindi" means Devanagari script. Romanized or transliterated Hindi is out of scope.
- No translation in either direction: Hindi speech produces Hindi text.
- One language per session; changing language mid-session takes effect on the next one.
- The current default model is English-only, so Hindi requires selecting a multilingual
  model of comparable size. Small accuracy and latency differences versus English are
  accepted.
- Language is chosen explicitly; automatic detection is not relied on for this feature.
- Lectures may mix Hindi with English technical vocabulary (Hinglish), and this is in
  scope.
- Transcripts stay local and personal, under the same privacy rules as today.
- Consumers read UTF-8 Markdown; legacy encodings are not supported.
