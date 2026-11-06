# Research: GPU-Accelerated Transcription

All findings verified on the reference machine: RTX 5070 (12 GB), driver 615.78.08, CUDA toolkit
13.4, `ctranslate2 4.8.5`, `faster-whisper 1.2.1`, model cache at `HF_HOME=/desk/models/hf`.

## D1. How CTranslate2 gets its CUDA runtime

**Decision**: Ship the CUDA 12 runtime as pip wheels (`nvidia-cublas-cu12==12.9.3.13`,
`nvidia-cudnn-cu12==9.28.0.42`) and load them into the process with `ctypes` before the model is
built.

**Evidence**:
- `ctranslate2.get_cuda_device_count()` → `1` and `get_supported_compute_types("cuda")` →
  `{float16, bfloat16, float32, int8, int8_float16, ...}`, so the driver and device are fine.
- `WhisperModel("small", device="cuda", compute_type="float16")` constructs in 2.8 s, then the
  first `encode()` raises `RuntimeError: Library libcublas.so.12 is not found or cannot be loaded`.
- `ldconfig -p` exposes only `/opt/cuda/lib64/libcublas.so.13`; there is no cuDNN anywhere.
  4.8.5 wheels are built against CUDA 12 sonames and cuDNN 9, so CUDA 13 cannot satisfy them.
- After `uv pip install --target` of the two wheels, `LD_LIBRARY_PATH` pointing at their `lib`
  directories makes the same call succeed. A pure-Python preload of all 17 `*.so*` files in
  `site-packages/nvidia/*/lib` (retry until no progress, ignore individual failures) works with no
  environment changes at all — verified twice in a row.

**Alternatives considered**:
- System CUDA 13 or a symlinked `libcublas.so.12` → `libcublas.so.13`: rejected, major-version ABI
  mismatch, and cuDNN is still absent.
- Conda / a dedicated container: rejected, adds a second package manager or an image build for a
  feature that must stay a `uv run` away.
- `nvidia-cudnn-cu12` alone and system cuBLAS: rejected, no CUDA 12 cuBLAS exists here.

## D2. Device and precision configuration

**Decision**: `ECHOSCRIBE_DEVICE` accepts `cpu` (default) or `cuda`; anything else is refused.
`ECHOSCRIBE_COMPUTE` is optional and defaults to `int8` on CPU and `float16` on CUDA. The resolved
pair is logged once at startup.

**Rationale**: one setting decides the feature (SC-006), and the precision default only needs to
be correct for the device it belongs to. `float16` is in the supported set for this GPU;
`bfloat16` is available but not better for Whisper and needs newer CTranslate2 kernels.

**Alternatives considered**: `auto` device selection — rejected, it hides the decision the user
asked to make; per-session selection — rejected, switching reloads the model and breaks FR-012.

## D3. Verification must transcribe, not just load

**Decision**: on every start, after `load_model()`, transcribe one second of zeroed audio with
`vad_filter=False` and discard the result. Any exception prints the device, precision, exception
message, and a pointer to the missing library, then `sys.exit(1)`.

**Rationale**: the model constructed successfully on this machine while `libcublas.so.12` was
missing; only an actual encode failed. A load-only check would report a healthy server that dies
on the first lecture window. The dry run also absorbs the ~0.9 s cuDNN algorithm-selection cost,
so the first real segment is not late.

**Alternatives considered**: `ctranslate2.get_cuda_device_count()` alone — rejected, it reflects
the driver, not the libraries; a lazy first-segment failure — rejected, that is exactly the silent
late failure FR-006 forbids.

## D4. Runtime dependencies are regular deps, not an extra

**Decision**: declare both wheels in `pyproject.toml` with a
`sys_platform == "linux" and platform_machine == "x86_64"` marker. No `--extra gpu`.

**Rationale**: `uv run python server/transcribe_server.py` stays the only command. An extra would
make GPU work depend on remembering `--extra gpu` at every launch, and a forgotten extra fails at
startup with "library missing" — a legitimate error that looks like a bug. Download and disk are the only
costs on a CPU-only Linux machine (≈2.1 GB); the preload never runs there. Splitting GPU wheels into an
opt-in install path is follow-up work, not part of this feature.

**Alternatives considered**: optional dependency group — rejected for the reason above; vendoring
the `.so` files into `models/` — rejected, unversioned binaries outside the lockfile.

## D5. A post-`ready` error is fatal

**Decision**: the client stops the session with `ERR` and the server's message on **any** error
frame, before or after `ready`. The server only emits an error frame for fatal conditions, so the
distinction has no use.

**Rationale**: FR-007 requires a mid-lecture transcription failure to be visible and to keep the
partial file. Leaving post-`ready` errors as console-only (the Hindi-era behavior) would make an
out-of-memory GPU session look like the lecture going quiet. The file is already flushed by the
server, so stopping the client loses nothing.

**Alternatives considered**: keep the split and add a `fatal` flag — rejected, one more field to
keep consistent for no behavior difference.

## D6. Reporting the device

**Decision**: `ready` gains `device` and `compute`; `STATUS` carries them to the panel; the
transcript header line becomes `Language: hi (model small, device cuda/float16)`.

**Rationale**: the panel answers "was this GPU?" during the lecture (FR-008) and the header
answers it afterwards (FR-009) from the same two values. Keeping the device out of the panel
controls avoids implying a switch that cannot take effect mid-session.

**Alternatives considered**: a header-only record — rejected, too late to explain a slow session;
a second status line — rejected, the existing line has room.

## D7. Benchmark honesty

The measured 2.45 s (CPU) vs 0.08 s (GPU) per 5 s window used noise input, which exercises the
encoder but produces almost no decoder tokens. It proves the ≥2× gap structurally but understates
GPU decoder cost. SC-003 is therefore validated in the quickstart with a real recorded lecture,
not with this number.

Memory: `small` in float16 occupies roughly 1 GB of the 12 GB available; `medium` fits; `large-v3`
would not, and is out of scope.
