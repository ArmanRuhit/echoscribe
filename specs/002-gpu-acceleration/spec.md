# Feature Specification: GPU-Accelerated Transcription

**Feature Branch**: `002-gpu-acceleration`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "I want a gpu option — as in gpu this is significantly slow"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A lecture transcribes at the speed of speech (Priority: P1)

A student starts a 30-minute lecture with GPU acceleration enabled. The first line appears within seconds, the gap between the speaker and the transcript stays small for the whole lecture, and the file covers the entire talk. On CPU today the backlog grows faster than it drains, so the second half of a lecture is unusable.

**Why this priority**: Speed is the whole request. Without it, the feature adds configuration and changes nothing.

**Independent Test**: Run one 30-minute lecture through the server with the GPU setting on, then compare the last transcript timestamp against the lecture's end time. Delivers a complete, near-live transcript on its own.

**Acceptance Scenarios**:

1. **Given** a GPU-capable machine and GPU acceleration selected, **When** a 30-minute lecture is transcribed, **Then** the final segment is written within 5 seconds of the lecture's end.
2. **Given** the same lecture and setting, **When** the transcript is inspected, **Then** it contains a timestamped line for every 30-second stretch of speech, with no multi-minute gaps.
3. **Given** GPU acceleration is selected, **When** the session runs, **Then** the transcript file format, timestamps, and per-segment flushing are identical to a CPU session.

---

### User Story 2 - A GPU request that cannot be honored is refused, not downgraded (Priority: P1)

A student enables GPU acceleration on a machine that cannot run it — no compatible GPU, a driver too old, a missing runtime library. The server says exactly what is missing and stops. It does not quietly run on CPU, because a silent fallback would look like the feature simply failed to help.

**Why this priority**: A silent CPU fallback is indistinguishable from "GPU is slow too" and sends the user hunting in the wrong place. The project already treats silent degradation as a defect.

**Independent Test**: Select GPU on a machine with no usable GPU; confirm the server names the missing capability, serves no session, and writes no transcript.

**Acceptance Scenarios**:

1. **Given** GPU is selected and no compatible GPU is visible, **When** the server starts, **Then** it reports that no GPU was found and exits without serving.
2. **Given** GPU is selected and the configured precision is unsupported by the hardware, **When** the server starts, **Then** it reports the unsupported precision and exits.
3. **Given** GPU is selected and the required GPU library is missing, **When** the server starts, **Then** it names the missing library and exits.
4. **Given** any of the above failures, **When** the extension attempts to start a session, **Then** the panel shows an error and no transcript file is created.

---

### User Story 3 - The user can tell which processor did the work (Priority: P2)

A student wants to know whether a slow session was GPU or CPU. The side panel and the transcript header both name the device and model used, so the answer is visible during and after the lecture.

**Why this priority**: Without it, "it felt slow" is unfalsifiable and every future report costs another round of guessing.

**Independent Test**: Start a session on each device; both the panel and the file header name the device.

**Acceptance Scenarios**:

1. **Given** a session starts on GPU, **When** the panel shows the recording state, **Then** it names the device and model.
2. **Given** a session finishes, **When** the transcript header is read, **Then** it records the device and model used.

---

### User Story 4 - CPU remains the default and still works (Priority: P3)

A student on a laptop without a dedicated GPU installs the project and runs it without configuring anything. It behaves exactly as it does today.

**Why this priority**: The feature must not turn a working default into a required setup step.

**Independent Test**: Start the server with no device configuration on a machine with no GPU; transcribe a short clip successfully.

**Acceptance Scenarios**:

1. **Given** no device setting is provided, **When** the server starts, **Then** it runs on CPU.
2. **Given** CPU mode, **When** a session runs, **Then** transcript content and file behavior are unchanged from today.

---

### Edge Cases

- GPU is visible but already occupied by another workload: startup must fail with a message about the GPU, not hang or fall back.
- GPU memory is insufficient for the configured model: startup must fail with a message naming the model and the device.
- A GPU failure occurs mid-lecture (driver reset, out of memory): the panel must show an error and the badge `ERR`; the partial transcript must remain on disk.
- The GPU disappears between sessions: the next session must fail visibly rather than silently continue on CPU.
- The same session reconnects after a dropped connection: it keeps the same device and model.
- CPU-only machine with GPU selected: refused at startup, per User Story 2.
- Switching device while a lecture is playing: not supported; the change applies to the next server start.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The server MUST support transcribing on a GPU when one is available and capable of running the configured model.
- **FR-002**: The server MUST continue to support transcribing on CPU, and CPU MUST remain the default when no device is chosen.
- **FR-003**: The device MUST be selectable through configuration, with no source edit and no rebuild.
- **FR-004**: The precision used on the GPU MUST be selectable through configuration, with a default that works on current hardware.
- **FR-005**: The server MUST verify at startup, before serving any session, that the chosen device and precision can actually load the model.
- **FR-006**: If verification fails, the server MUST exit with a message naming the missing capability (no device, unsupported precision, missing library, insufficient memory) and MUST NOT fall back to the other device.
- **FR-007**: A transcription failure during a session MUST produce an error to the client and set `ERR`; the partial transcript MUST remain readable on disk.
- **FR-008**: The active device and model MUST be reported when a session starts and displayed in the side panel.
- **FR-009**: The transcript header MUST record the device and model used.
- **FR-010**: GPU mode MUST preserve the existing contract: same file format and timestamps, flushed after every segment, no audio written to disk, silence never transcribed as text.
- **FR-011**: GPU mode MUST preserve language handling: a language selected in the panel is honored, and an English-only model still refuses a non-English language.
- **FR-012**: The model MUST be loaded once per server run; starting a second session MUST NOT pay a load cost again.

### Key Entities *(include if feature involves data)*

- **Device Setting**: the processor class chosen for a server run. Known values: automatic CPU default, GPU. Attributes: device, precision, whether it was explicitly requested.
- **Session**: an active transcription. Gains the device and precision actually in use, so the panel and file can report them.
- **Transcript Header**: the block at the top of each file. Gains device and model alongside the existing title, source, start time, and language.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 30-minute lecture finishes with its last transcript line written within 5 seconds of the lecture ending.
- **SC-002**: No stretch of speech longer than 30 seconds is missing from a GPU transcript of a 30-minute lecture.
- **SC-003**: On the same lecture and model, the GPU run finishes at least twice as fast end-to-end as the CPU run.
- **SC-004**: 100% of failed GPU startups produce a message naming the cause, and 0% serve a session or create a file.
- **SC-005**: 100% of sessions record their device and model in both the panel and the transcript header.
- **SC-006**: Enabling GPU requires one configuration change and a restart, with zero code edits.
- **SC-007**: A CPU-only machine with no configuration completes a session exactly as it does today.

## Assumptions

- The reference machine has an NVIDIA GPU with a working driver; verification here found an RTX 5070 with 12 GB and CUDA 13.4 present.
- The device is chosen when the server starts, not per session, because changing it means reloading the model. A toggle inside the extension is out of scope; the panel only reports the active device.
- "GPU" means a single NVIDIA GPU. AMD, Intel, Apple Silicon, multi-GPU, and cloud transcription are out of scope.
- Precision defaults to half precision on GPU and low-precision integer arithmetic on CPU, matching what the hardware supports; the exact values are a planning concern.
- The existing latency budget (2–5 seconds behind speech) still applies; GPU mode should sit at the low end of it rather than redefine it.
- Language selection, transcript format, and the no-audio-on-disk rule are unchanged by this feature.
- The CUDA runtime arrives as ordinary dependencies, so a CPU-only Linux x86_64 install also pays the download (≈2.1 GB) and disk cost. Accepted for now; a separate install path for GPU wheels is a follow-up, not part of this feature.
