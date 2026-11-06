# Phase 0 Research: Hindi Transcript Support

## 1. Where the language is chosen

**Decision**: Per session, from a `<select>` in the side panel. The value is written to
`chrome.storage.session` on change and read by the service worker when the toolbar icon is
clicked.

**Rationale**: The user alternates Hindi and English lectures. A server-wide environment
variable would force a process restart and a second model download between lectures. The
spec also treats a mid-session change as "applies to the next session", which only makes
sense with a live control.

**Alternatives considered**:
- `ECHOSCRIBE_LANGUAGE` only (today's behavior). Rejected: restart per lecture, and the
  refusal reason would have to be discovered in a terminal.
- Reading the select directly at click time. Rejected: the toolbar click never reaches the
  panel, and MV3 gives no API to query another extension view.
- `chrome.storage.local`. Rejected: persists across browser restarts and invites drift
  between the visible select and the stored value.

## 2. Detecting model language capability

**Decision**: A model supports non-English languages unless its name ends in `.en`
(`tiny.en`, `base.en`, `small.en`, `medium.en`).

**Rationale**: faster-whisper does not expose a capability flag on `WhisperModel`, and the
`.en` suffix is the documented convention for the English-only variants. It is a single
predicate with no I/O.

**Alternatives considered**:
- Try a Hindi transcription and inspect output. Rejected: slow, unreliable, and it would
  transcribe audio just to decide whether audio may be transcribed.
- Maintain a hardcoded list of model names. Rejected: breaks on new model names, and the
  suffix rule already covers them.

## 3. Rendering Devanagari

**Decision**: Extend the panel font stack with `"Noto Sans Devanagari"` and `"Nirmala UI"`
ahead of the generic fallback, and mark segment text with `lang="hi"` when the session
language is Hindi.

**Rationale**: Devanagari needs a font with the script and correct shaping. On Linux,
fontconfig usually resolves it through the generic fallback, but an explicit list removes
the guesswork without shipping a font.

**Alternatives considered**:
- Bundle a Devanagari subset. Rejected: adds a binary asset and licensing surface for a
  script most desktop systems already cover.
- Convert Devanagari to Latin. Rejected by the spec: transliteration is out of scope.

## 4. Keeping Hinglish intact

**Decision**: Send no post-processing. Request `task="transcribe"` (the default) and let
the model emit Devanagari for Hindi words and Latin script for English words.

**Rationale**: The engine already switches script for loanwords; a transliteration or
script-normalization pass would destroy exactly the terms the spec wants preserved.

**Alternatives considered**:
- Force all output into Devanagari. Rejected: makes "API" unsearchable.
- Force all output into Latin. Rejected: that is transliteration, explicitly out of scope.

## 5. When the language is validated

**Decision**: The server validates the language against the loaded model when it receives
`start`, before creating the transcript file. The client waits for `ready` before attaching
the audio worklet.

**Rationale**: FR-006 requires refusal before audio is captured, and the transcript file
must not exist for a refused session. Both fall out of validating before `TranscriptWriter.create`
and before the worklet exists.

**Alternatives considered**:
- Fail at server startup when the pair is invalid. Rejected: the browser would only see a
  closed socket and show a generic reconnect state, not the reason.
- Validate in the extension. Rejected: the extension cannot know which model is loaded
  until the server says so.

## 6. Behavior when the server is unreachable at start

**Decision**: The initial handshake rejects with `ERR` ("server not reachable") instead of
starting capture and queuing audio. Mid-session disconnects keep the existing 30 s queue.

**Rationale**: Today a missing server produces a `REC` badge and a silently empty
transcript. The spec's visible-failure principle already requires the error; gating only the
first handshake keeps the reconnect design intact.

**Alternatives considered**:
- Keep capturing while retrying. Rejected: the user believes a session started when no
  server will ever accept it.
