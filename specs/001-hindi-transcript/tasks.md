# Tasks: Hindi Transcript Support

**Input**: Design documents from `/specs/001-hindi-transcript/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: None generated. The repo has no test framework and the spec did not request TDD;
validation is manual through `quickstart.md`.

**Organization**: Tasks are grouped by user story so each one is independently
implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3
- Every task names the exact file it touches

## Path Conventions

Single project, existing layout: `extension/` (MV3, plain JS) and `server/`
(`transcribe_server.py`). No new files are created by this feature.

---

## Phase 1: Setup

**Purpose**: One permission and a recorded baseline before any code changes.

- [X] T001 [P] Add `"storage"` to `permissions` in `extension/manifest.json`, keeping
      `activeTab`, `tabCapture`, `offscreen`, `sidePanel` and no host permissions.
- [ ] T002 Run one English session on the current build per `quickstart.md` Scenario 4 and
      confirm it still passes; this is the regression baseline for `SC-005`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Carry a language value from the panel to the server without changing what
the transcriber does yet. No story works until this is done.

**⚠️ CRITICAL**: Complete before Phase 3.

- [X] T003 [P] In `extension/background.js`, handle `{target:"background", type:"LANGUAGE",
      language}` by writing `chrome.storage.session.set({ language })`, and read
      `chrome.storage.session.get("language")` in `chrome.action.onClicked`, defaulting to
      `"en"`, then include it in the `START` message. Unknown values are ignored.
- [X] T004 [P] In `extension/sidepanel.html`, add `<select id="language">` with options
      `en` → `English` and `hi` → `Hindi`. No inline handlers; the extension CSP blocks them.
- [X] T005 [P] In `extension/sidepanel.js`, restore the stored value into `#language` on
      load and send `{target:"background", type:"LANGUAGE", language}` on change.
- [X] T006 [P] In `extension/offscreen.js`, accept `language` in `start({...})`, keep it in
      a module-level `sessionLanguage`, and include `"language": sessionLanguage` in the
      `start` frame sent by `connectSocket()`. Reconnects reuse the stored value.
- [X] T007 In `server/transcribe_server.py`, add `language: str` to the `Session` dataclass
      and set it from `data.get("language")` in `handle_client`, falling back to the existing
      module default. A resumed session keeps its original language and ignores the incoming
      value. `Session` gains no other fields.
- [X] T008 In `server/transcribe_server.py`, include the effective `"language"` in the
      `ready` frame sent by `handle_client`, after defaulting, for new and resumed sessions.

**Checkpoint**: a language value reaches the server and comes back in `ready`; transcription
behavior is unchanged.

---

## Phase 3: User Story 1 - Hindi lecture transcribed in Devanagari (Priority: P1) 🎯 MVP

**Goal**: A Hindi lecture produces Devanagari segments in the panel and in the file with the
same timestamps, naming, and flush behavior as English.

**Independent Test**: With a multilingual model and Hindi selected, play 60 seconds of Hindi
speech; Devanagari appears in the panel within 5 seconds, matches the file, and the file has
`[HH:MM:SS]` timestamps.

- [X] T009 [US1] In `server/transcribe_server.py`, change `transcribe_pcm(pcm)` to
      `transcribe_pcm(pcm, language)` and pass `self.language` from `Session._emit_window`,
      removing the module-global `LANGUAGE` read inside it.
- [X] T010 [P] [US1] In `extension/sidepanel.html`, extend the body font stack with
      `"Noto Sans Devanagari"` and `"Nirmala UI"` ahead of `sans-serif` so Devanagari shapes
      without a bundled font.
- [X] T011 [US1] In `extension/sidepanel.js`, keep the session's `language` and `model` from
      `STATUS`, set `lang="hi"` on segment text spans when the language is Hindi, and render
      `Recording · Hindi · small` (label from `en`→`English`, `hi`→`Hindi`). Fall back to
      today's text when the fields are absent.
- [X] T012 [US1] In `extension/offscreen.js`, send the `recording` `STATUS` only after
      `ready`, carrying `language` and `model`, and keep sending them on `reconnecting`.
- [ ] T013 [US1] Run `quickstart.md` Scenario 2: 60 seconds of Hindi with a multilingual
      model. Confirm Devanagari in panel and file, identical text, no U+FFFD, no audio file.

**Checkpoint**: Hindi works end to end. This is a demoable increment.

---

## Phase 4: User Story 2 - A language/model mismatch is refused, not faked (Priority: P2)

**Goal**: Hindi plus an English-only model stops before capture with `ERR` and one
actionable line; nothing is written.

**Independent Test**: Select Hindi with an English-only model and start. Badge shows `ERR`,
the panel names the model, no transcript file appears, and the lecture keeps playing.

- [X] T014 [US2] In `server/transcribe_server.py`, add
      `resolve_language(requested: str | None, model_name: str)` that accepts `en`, `hi`, and
      `auto` (as unpinned), refuses unknown codes, and refuses any non-English value when
      `model_name` ends in `.en`. The message is one line:
      `Model small.en supports English only. Set ECHOSCRIBE_MODEL=small (multilingual) and restart the server.`
- [X] T015 [US2] In `server/transcribe_server.py`, call `resolve_language` inside
      `handle_client` before `TranscriptWriter.create` and before the session is stored. On
      refusal send `{"type":"error","code":"unsupported_language","message":...}`, leave
      `session` as `None`, and create no file and no `SESSIONS` entry.
- [X] T016 [US2] In `extension/offscreen.js`, attach the `AudioWorklet` only after `ready`:
      keep `getUserMedia`, the `AudioContext`, and `source → destination` (audible), but
      create the worklet node and `port.onmessage` after the frame arrives, so a refused
      session produces no PCM.
- [X] T017 [US2] In `extension/offscreen.js`, treat an `error` before `ready` as fatal:
      `stop({ type: "ERROR", message })` so the badge shows `ERR` and the panel shows the
      server's message. After `ready`, keep today's log-only behavior. Also stop with `ERR`
      when the first connection attempt fails before any `ready`; keep the 30-second queue and
      backoff for drops after `ready`.
- [ ] T018 [US2] Run `quickstart.md` Scenarios 1 and 7: Hindi with `small.en` is refused with
      `ERR` and no new file under `~/EchoScribe/transcripts/`; `ECHOSCRIBE_LANGUAGE=xx` is
      refused at session start.

**Checkpoint**: US1 and US2 both work; a misconfiguration cannot silently produce English
text for Hindi audio.

---

## Phase 5: User Story 3 - Mixed Hindi-English lecture keeps both scripts (Priority: P3)

**Goal**: English terms inside Hindi sentences stay in Latin script and are never
translated.

**Independent Test**: Transcribe a bilingual sentence with three English technical terms;
all three appear in Latin, unaltered.

- [X] T019 [P] [US3] In `server/transcribe_server.py`, pass `task="transcribe"` explicitly in
      both `transcribe_pcm` and `transcribe_file`, with a one-line comment that translation
      must never run.
- [ ] T020 [US3] Run `quickstart.md` Scenario 3. Confirm the three English terms and an
      acronym keep their Latin spelling inside Devanagari sentences, and that no sentence was
      translated.

**Checkpoint**: Hinglish lectures remain searchable in the file.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T021 [P] Update `AGENTS.md`: add `language` to the protocol block, `storage` to the
      permission ladder, and state that `ECHOSCRIBE_LANGUAGE` is now a default, not the
      source of truth.
- [X] T022 [P] Update `README.md` with the Hindi step: pick Hindi in the panel and run a
      multilingual model.
- [ ] T023 Run all seven `quickstart.md` scenarios in one sitting, including reconnect
      mid-session with Hindi.
- [ ] T024 Run `caveman-review` over the diff of `extension/background.js`,
      `extension/offscreen.js`, `extension/sidepanel.js`, `extension/sidepanel.html`,
      `extension/manifest.json`, and `server/transcribe_server.py`. Fix bugs and risks first,
      then commit with `feat: transcribe hindi lectures to devanagari`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup; blocks every story.
- **US1 (Phase 3)**: after Phase 2.
- **US2 (Phase 4)**: after Phase 2; touches server validation and offscreen lifecycle,
  independent of T009-T013 except for T012's `ready` handling.
- **US3 (Phase 5)**: after US1 — Hinglish can only be observed once Hindi sessions run.
- **Polish (Phase 6)**: after the stories you intend to ship.

### Within Each Story

- Server validation (T014, T015) before client gating (T016, T017) only for testing speed;
  either order is safe.
- Styling (T010) and status rendering (T011) are independent files.
- T012 depends on T008 (`ready.language`).
- Verification tasks run after the code tasks in their phase.

### Parallel Opportunities

- T003, T004, T006 touch three different files: run together.
- T010 is independent of every other US1 task.
- T019 is independent of T014-T018.
- T021 and T022 are different files.

---

## Parallel Example: User Story 1

```bash
# Different files, no shared state:
Task: "Add Devanagari font fallback in extension/sidepanel.html"
Task: "Thread session language through transcribe_pcm in server/transcribe_server.py"
```

---

## Implementation Strategy

### MVP First

1. Phase 1 → Phase 2 → Phase 3 (US1).
2. Stop and run T013. Devanagari in the panel and the file is the demo.
3. Ship US1 plus T014-T015 before calling it usable: Hindi on the default model is the one
   failure that looks like success, and the constitution forbids it.

### Incremental Delivery

1. Foundation → language reaches the server.
2. US1 → Hindi transcript.
3. US2 → refusal guardrail.
4. US3 → Hinglish verification.
5. Polish → docs, full quickstart, commit.

---

## Notes

- Each phase ends at a testable checkpoint; stop there rather than starting the next.
- `specs/001-hindi-transcript/` artifacts are already committed inputs; only source files
  change here.
- Commit after each phase, not after every task, to keep the one-step-per-turn discipline.
