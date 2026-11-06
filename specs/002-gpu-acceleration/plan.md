# Implementation Plan: GPU-Accelerated Transcription

**Branch**: `002-gpu-acceleration` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-gpu-acceleration/spec.md`

## Summary

Add an opt-in CUDA path to the local Whisper server. `ECHOSCRIBE_DEVICE=cuda` selects
`float16` on a CTranslate2 `cuda` device; CPU stays the default with `int8`. The two missing
runtime libraries (`libcublas.so.12`, cuDNN 9) are supplied as pinned `nvidia-*-cu12` wheels and
preloaded with `ctypes`, because the system toolchain here is CUDA 13 and CTranslate2 4.8.5 is
built against CUDA 12 sonames. Startup verifies the device by transcribing one second of silence —
model construction alone succeeds without cuBLAS, so a dry run is the only honest gate. The
resolved device and precision are reported in `ready`, in the side panel, and in the transcript
header. A transcription failure mid-session is fatal and visible: error frame, `ERR` badge, partial
file intact. Nothing else about capture, language, or file format changes.

Measured on the reference machine (`small`, one 5 s window, noise input):

| Device | Precision | Model load | First window | Steady window |
|---|---|---|---|---|
| CPU (Ryzen 7 9700X) | int8 | 2.4 s | 2.9 s | 2.45 s |
| RTX 5070 | float16 | 1.9 s | 0.9 s | 0.08 s |

The first GPU window costs ~1 s of cuDNN algorithm selection. That cost is paid during startup
verification instead of during the lecture.

## Technical Context

**Language/Version**: Python 3.13 (server); JavaScript ES2022 (extension, renderer path unchanged)

**Primary Dependencies**: `faster-whisper==1.2.1`, `ctranslate2==4.8.5`, `websockets==17.3`,
`numpy>=2.0`, `av>=16.1,<17`; new: `nvidia-cublas-cu12==12.9.3.13` and
`nvidia-cudnn-cu12==9.28.0.42` (Linux x86_64 only, marker-gated)

**Storage**: `~/EchoScribe/transcripts/*.md` (unchanged); no new files, no audio written

**Testing**: manual quickstart plus the existing scratch harness pattern
(`/tmp/opencode/test_handshake.py`) for protocol and failure injection; `py_compile` and
`node --check` for syntax

**Target Platform**: Linux x86_64 with an NVIDIA GPU (RTX 5070, driver 615.78.08, CUDA 13.4
toolkit present); Chrome/Brave MV3 extension unchanged on the client side

**Project Type**: single project — local WebSocket service plus a browser extension

**Performance Goals**: finish a 30-minute lecture with the last line written within 5 s of the
end (SC-001); ≥2× faster end-to-end than CPU on the same lecture and model (SC-003); keep the
existing 2–5 s behind-speech budget

**Constraints**: GPU is opt-in and CPU is the default (FR-002); never fall back silently (FR-006);
no new permissions, no cloud, no audio on disk; one model load per server run (FR-012)

**Scale/Scope**: one session at a time, one GPU, `small`-class models (up to `medium` on 12 GB in
float16); three server functions and two extension render paths change

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| I. Local-Only Processing (NON-NEGOTIABLE) | PASS | Wheels are fetched at install time only; runtime stays on `127.0.0.1`. No manifest change, no new permission, no network call. |
| II. Audio Is Ephemeral (NON-NEGOTIABLE) | PASS | Verification transcribes an in-memory 1 s zero buffer. No capture path touched; still no audio file. |
| III. No Lost Transcript (NON-NEGOTIABLE) | PASS | Writer and flush path unchanged. Mid-session failure closes the session without truncating; resume still appends to the same file. |
| IV. Visible Failure, No Silent Degradation | PASS | Startup refusal exits with the named cause and serves nothing; mid-session failure sends `error` + `ERR`; no CPU fallback anywhere. |
| V. Smallest Complete Change | PASS (justified) | One env var, one preload function, one verification call, one error branch. The two new deps are platform runtime libraries, not code abstractions — see Complexity Tracking. |

Post-design re-check: unchanged, no new violations. Gate: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-gpu-acceleration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # /speckit.tasks output
```

### Source Code (repository root)

```text
server/
├── transcribe_server.py     # device/compute config, CUDA preload, startup verify, error frame
└── requirements.txt         # mirrors pyproject pins; gains the two nvidia wheels

extension/
├── background.js            # unchanged
├── offscreen.js             # relay device/compute from ready; treat post-ready error as fatal
├── sidepanel.js             # render device in the status line
├── sidepanel.html           # unchanged (no GPU control: device is a server setting)
└── manifest.json            # unchanged (no new permission)

pyproject.toml               # declare the two nvidia wheels with platform markers
uv.lock
```

**Structure Decision**: the existing single-project layout is kept. GPU support is a server
concern; the extension only gains a word in the status line and one stricter error branch.
No new module, no new process, no build step.

## Complexity Tracking

> Principle V asks that added complexity remove more than it costs.

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (≈2.1 GB on disk) | CTranslate2 4.8.5 dlopens `libcublas.so.12` and cuDNN 9; this machine only has CUDA 13 (`libcublas.so.13`) and no cuDNN | System CUDA 13 libs cannot satisfy a `.so.12` soname; symlinking across major versions is an ABI gamble. Docker or conda add a whole runtime layer for one dependency. Accepted cost: CPU-only Linux installs download the same 2.1 GB; splitting GPU wheels behind an opt-in install path is follow-up work, tracked in the spec assumptions. |
| ~10-line `ctypes` preload loop | `uv run` cannot inject `LD_LIBRARY_PATH` before the interpreter starts, and a wrapper script would change the documented run command | A shell wrapper (`LD_LIBRARY_PATH=... uv run ...`) is the alternative; rejected because it replaces one documented command with one more file and one more thing to forget. |
| Startup dry-run (~1 s GPU, ~3 s CPU) | Model construction succeeds without cuBLAS, so it cannot detect a broken GPU path; the first real encode failed with the library error | Loading only the model was the original plan; it passes on a machine that cannot transcribe a single frame. |
