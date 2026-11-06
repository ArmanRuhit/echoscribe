# Quickstart: Validate Hindi Transcript Support

Manual validation. The repo has no test framework, and these scenarios need real audio.

## Prerequisites

- `uv` installed; `.venv` created and dependencies synced (`uv sync`)
- A multilingual model downloaded once: `small` is the default for Hindi
- A Hindi lecture you can play in a browser tab
- Extension reloaded from `chrome://extensions` after the manifest change

## Setup

Terminal 1, multilingual model for the Hindi scenarios:

```bash
ECHOSCRIBE_MODEL=small ECHOSCRIBE_LANGUAGE=en uv run python server/transcribe_server.py
```

Terminal 2, English-only model for the refusal scenario:

```bash
ECHOSCRIBE_MODEL=small.en uv run python server/transcribe_server.py
```

Load the extension at `chrome://extensions` (Developer mode → Load unpacked →
`extension/`). One server at a time on port 8765.

## Scenario 1 — Refusal (spec US2, FR-006, FR-007)

1. Run the `small.en` server.
2. Open the side panel, choose **Hindi**.
3. Play any lecture and click the toolbar icon.

**Expected**: badge shows `ERR`, panel shows one line naming the model as English-only and
telling you to select a multilingual model. No transcript file appears. No `REC` state is
entered, and the server console shows no `[file] new` line.

```bash
ls ~/EchoScribe/transcripts | tail -3   # no new file for this attempt
```

## Scenario 2 — Hindi happy path (spec US1, FR-003…FR-005, SC-001, SC-002)

1. Run the `small` server.
2. Choose **Hindi**, play a Hindi lecture, click the icon.
3. Watch the panel for 60 seconds, then stop.

**Expected**:
- `Recording · Hindi · small` in the status line.
- Devanagari segments appear within about 5 seconds of the corresponding speech.
- `~/EchoScribe/transcripts/<stamp>_<slug>.md` grows while the lecture still plays.
- Header, `[HH:MM:SS]` timestamps, and line order match an English session.
- Stopping finalizes the file; badge clears.

Check the file is valid UTF-8 with no replacement characters:

```bash
f=$(ls -t ~/EchoScribe/transcripts/*.md | head -1)
file "$f" && grep -c $'\uFFFD' "$f"    # expect "UTF-8 Unicode text"; 0 replacements
```

## Scenario 3 — Hinglish (spec US3, FR-008, SC-006)

1. Reuse the running Hindi session, or start a new one.
2. Find a lecture passage that mixes Hindi with English terms such as "API", "gradient
   descent", or "cache".

**Expected**: those terms stay in Latin script inside Devanagari sentences, with original
capitalisation. No transliteration and no translation into another language.

## Scenario 4 — English regression (spec FR-010, SC-005)

1. Choose **English** with the `small` server, then repeat with `small.en`.
2. Run the existing one-minute test from `AGENTS.md`.

**Expected**: identical behavior to before this feature — same latency, same file shape,
no new prompts, no language label issues.

## Scenario 5 — Reconnect mid-session

1. Start a Hindi session, let it run several minutes.
2. Kill the server mid-session, restart it with the same command, keep playing.

**Expected**: panel shows `Reconnecting…`, then resumes appending to the same file in
Hindi. Reconnect time is under 10 minutes so the session is not expired.

## Scenario 6 — Devanagari rendering (FR-009, SC-004)

1. With Hindi segments on screen, inspect the panel.

**Expected**: no empty boxes or broken conjuncts; Latin text keeps its current layout and
line height.

## Scenario 7 — Invalid language (FR-011)

1. Start the server with `ECHOSCRIBE_LANGUAGE=xx`.
2. Start any session from the panel.

**Expected**: the server refuses with `ERR` and a message naming `xx`, exactly as in
Scenario 1. No silent fallback to English, no transcript file. The server console may warn
at boot, but the refusal must be visible in the panel.

## Cleanup

Stop the server, clear the badge by stopping capture, and confirm no `.wav`, `.webm`, or
audio file was created anywhere in the repo or in `~/EchoScribe`.
