# Tasks: GPU-Accelerated Transcription

**Input**: Design documents from `/specs/002-gpu-acceleration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: none generated. This project has no test suite; verification is the manual scenarios in
`quickstart.md`, which is how every prior feature was validated.

**Organization**: Tasks are grouped by user story so each can be implemented and verified alone.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1-US4, matching `spec.md`
- Every task names the file it touches

## Path Conventions

Single project: `server/`, `extension/`, and `specs/002-gpu-acceleration/` at the repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install the CUDA runtime and record what CPU costs, so the speed claim has a baseline.

- [X] T001 Add `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` to `server/requirements.txt` with the marker `sys_platform == "linux" and platform_machine == "x86_64"`, then run `uv add -r server/requirements.txt` so `pyproject.toml` and `uv.lock` match
- [ ] T002 [P] Record CPU baseline in `specs/002-gpu-acceleration/quickstart.md` Scenario 7: start with defaults, transcribe one 60 s clip, note wall-clock seconds and model name

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Device resolution and CUDA library loading. Every story reads these values.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Implement `resolve_device_config()` in `server/transcribe_server.py`: validate `ECHOSCRIBE_DEVICE` is exactly `cpu` or `cuda` (default `cpu`), default `ECHOSCRIBE_COMPUTE` to `int8` on CPU and `float16` on CUDA, and record `requested = "ECHOSCRIBE_DEVICE" in os.environ`. Unknown device returns the message shape from `data-model.md` line 76
- [X] T004 Implement `preload_cuda_libraries()` in `server/transcribe_server.py`: glob `nvidia/{cublas,cudnn,cuda_nvrtc}/lib/*.so*` relative to the interpreter's site-packages, `ctypes.CDLL` each path in a retry loop until a pass adds nothing, return the count. No-op when device is `cpu`
- [X] T005 Wire device and compute into `load_model()` in `server/transcribe_server.py`: keep the lazy singleton, print `[model] loading <model> (<device>/<compute>)`, and never reload on a second session (FR-012)

**Checkpoint**: `ECHOSCRIBE_DEVICE=cuda uv run python -c "import server.transcribe_server"` loads without touching a socket.

---

## Phase 3: User Story 1 - A lecture transcribes at the speed of speech (Priority: P1) 🎯 MVP

**Goal**: GPU mode loads, proves it can encode, and keeps up with a 30-minute lecture.

**Independent Test**: Run one 30-minute lecture with GPU selected; the last line is written within 5 s of the lecture ending (SC-001), and the file format matches a CPU run (FR-010).

- [X] T006 [US1] Implement `verify_device()` in `server/transcribe_server.py`: transcribe a 1 s in-memory zero `float32` buffer at 16 kHz with `vad_filter=False`, raise `SystemExit` naming the model and device on failure, print `[verify] 1.0 s ok in <n> s` on success
- [X] T007 [US1] Call the startup sequence in `main()` in `server/transcribe_server.py` in the order parse → preload → load → verify → serve, so a failure exits before the port is bound
- [ ] T008 [US1] Run quickstart Scenario 2 in `specs/002-gpu-acceleration/quickstart.md` (GPU happy path) and record the observed numbers

**Checkpoint**: A GPU session transcribes a 5-minute clip with the transcript keeping pace.

---

## Phase 4: User Story 2 - A GPU request that cannot be honored is refused, not downgraded (Priority: P1)

**Goal**: Every failed GPU start names the cause and serves nothing; a mid-session failure surfaces as `ERR` and keeps the partial file.

**Independent Test**: `CUDA_VISIBLE_DEVICES="" ECHOSCRIBE_DEVICE=cuda uv run python server/transcribe_server.py` prints a message naming the cause, exits non-zero, creates no file.

- [X] T009 [US2] Map the five startup failures in `server/transcribe_server.py` to the message shapes in `data-model.md` lines 76-80: unknown device, no CUDA device, unsupported precision, missing library (name the `.so` and the wheel), out of memory (name model and device)
- [X] T010 [US2] Guarantee no fallback in `server/transcribe_server.py`: a failed verification exits non-zero and `serve()` is never reached; no `device` is retried with `cpu`
- [X] T011 [P] [US2] Make a post-`ready` `error` fatal in `extension/offscreen.js`: call `stop({type:"ERROR", message})` instead of `console.error`, so the panel shows the message and the badge shows `ERR` (reverses the Hindi-era log-only rule)
- [X] T012 [P] [US2] Handle a transcription exception in `Session._emit_window` in `server/transcribe_server.py`: set `Session.failed`, send `{"type":"error","code":"transcription_failed","message":...}`, flush and stop consuming audio; never delete the file
- [ ] T013 [US2] Run Scenarios 3, 4, and 6 of `specs/002-gpu-acceleration/quickstart.md` (missing library, no GPU, mid-session failure) and record each message

**Checkpoint**: Removing the CUDA libraries or hiding the GPU produces a named refusal, zero files, and `ERR` in the panel.

---

## Phase 5: User Story 3 - The user can tell which processor did the work (Priority: P2)

**Goal**: The device and model are visible during the session and in the file afterwards.

**Independent Test**: Start one session per device; the panel and the header both name the device.

- [X] T014 [US3] Add `device` and `compute` to the `ready` frame in `handle_client` in `server/transcribe_server.py`
- [X] T015 [US3] Append `, device <device>/<compute>` to the `Language:` header line in `TranscriptWriter.create` in `server/transcribe_server.py`, keeping the field order from `data-model.md` line 50
- [X] T016 [P] [US3] Relay `device` and `compute` from `ready` into the `STATUS` frame in `extension/offscreen.js`, including the reconnecting status
- [X] T017 [P] [US3] Render the suffix `· GPU float16` in `recordingLabel()` in `extension/sidepanel.js` when device is `cuda`, and clear it on `idle` and `error`
- [ ] T018 [US3] Run Scenario 2's evidence step in `specs/002-gpu-acceleration/quickstart.md`: panel shows the device, header line shows `device cuda/float16`

**Checkpoint**: `grep '^Language:' <transcript>` answers "was this GPU?" without asking the terminal.

---

## Phase 6: User Story 4 - CPU remains the default and still works (Priority: P3)

**Goal**: No configuration means CPU, exactly as before.

**Independent Test**: Start with no `ECHOSCRIBE_*` variables on a machine with a GPU; the run uses CPU and behaves as it does today.

- [X] T019 [US4] Confirm the default path in `server/transcribe_server.py` prints no GPU advice when `requested` is false and that `[model] loading ... (cpu/int8)` is unchanged
- [ ] T020 [US4] Run Scenarios 1 and 8 of `specs/002-gpu-acceleration/quickstart.md` (CPU default, language regression) and record the results

**Checkpoint**: A fresh clone with no `.env` transcribes a clip on CPU.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T021 [P] Update `AGENTS.md`: protocol block gains `device`/`compute` in `ready`, config section gains `.env` GPU notes, test checklist gains GPU refusal and device-visibility items
- [X] T022 [P] Update `README.md`: `ECHOSCRIBE_DEVICE=cuda` setup, the wheel download, and the CPU default
- [ ] T023 Run the full `specs/002-gpu-acceleration/quickstart.md`, including the 30-minute real lecture, and record SC-001/SC-002/SC-003 measurements
- [X] T024 Run `caveman-review` on `git diff`, apply findings, tick completed boxes in `specs/002-gpu-acceleration/tasks.md`, and commit as `feat: transcribe on cuda with named refusals`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on T001; blocks all stories
- **US1 (Phase 3)**: depends on Phase 2
- **US2 (Phase 4)**: depends on Phase 2; T011/T012 touch different files than T009/T010 and can run in parallel with US1
- **US3 (Phase 5)**: depends on Phase 2; T016/T017 are extension-only and parallel-safe
- **US4 (Phase 6)**: depends on Phase 2 only; it is a regression check, not new code
- **Polish (Phase 7)**: depends on the stories you intend to ship

### User Story Dependencies

- US1 and US2 are both P1 and share `verify_device()`; US2's refusals are the failure branch of US1's check
- US3 reads values US1 produces; its tasks are additive and cannot break US1
- US4 is independent by construction: it asserts the absence of the feature

### Parallel Opportunities

- T002 can run while dependencies install
- T011 and T012 touch `extension/offscreen.js` and `server/transcribe_server.py` respectively, so they parallelize
- T016 and T017 parallelize (different extension files)
- T021 and T022 parallelize (different docs)

---

## Parallel Example: User Story 2

```bash
Task: "Make a post-ready error fatal in extension/offscreen.js"
Task: "Handle a transcription exception in Session._emit_window in server/transcribe_server.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 → Phase 2 → Phase 3
2. Stop and run T008
3. Ship only if `[verify] 1.0 s ok` appears before `[ws] listening`

US2 is also P1, and T009-T010 are the constitution's Principle IV, not a nice-to-have. The first
real commit should include them even though the MVP checklist stops at US1.

### Incremental Delivery

1. Setup + Foundational → a server that can construct a CUDA model (but not prove it works)
2. US1 → proves encoding works; this is the first version worth running on a lecture
3. US2 → refuses visibly; safe to hand to a machine that lacks the libraries
4. US3 → answers "was it GPU?" from the file alone
5. US4 → confirms nothing regressed for the default user

### Notes

- T002, T008, T013, T018, T020, T023 need a browser and a real lecture; they cannot run headless
- Model cache is `HF_HOME=/desk/models/hf`; a model switch re-downloads
- The first uncached GPU call takes ~25 s building the CUDA JIT cache; do not mistake it for a hang

## Phase 8: Convergence

- [X] T025 Show the active device in the side-panel status for CPU sessions (`· CPU`), not only GPU, per FR-008 (partial)
- [ ] T026 Run a 30-minute GPU lecture and record timing and gap evidence for SC-001, SC-002, and SC-003 per SC-001 (partial)
- [X] T027 Give the transcript-quality heuristics (silence/loop filter, fragment merge, `ECHOSCRIBE_PROMPT`) a spec or an AGENTS.md section, or remove them per plan: scope (unrequested)
