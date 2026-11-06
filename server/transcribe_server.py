"""EchoScribe local transcription server.

The extension sends 16kHz mono Int16 PCM over a local WebSocket.
Segments are transcribed with faster-whisper and appended to Markdown.
A dropped client can reconnect with the same session ID and continue the file.
Audio is never written to disk.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import re
import sysconfig
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from ctranslate2 import get_cuda_device_count
from faster_whisper import WhisperModel
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


def load_env_file(path: Path) -> None:
    """Fill os.environ from KEY=VALUE lines; real shell variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file(Path(__file__).resolve().parent.parent / ".env")

HOST = "127.0.0.1"
PORT = int(os.getenv("ECHOSCRIBE_PORT", "8765"))
MODEL_NAME = os.getenv("ECHOSCRIBE_MODEL", "small.en")
LANGUAGE = os.getenv("ECHOSCRIBE_LANGUAGE", "en")
LANGUAGE = None if LANGUAGE.lower() == "auto" else LANGUAGE
SUPPORTED_LANGUAGES = {"en", "hi"}
SUPPORTED_DEVICES = ("cpu", "cuda")
DEFAULT_COMPUTE = {"cpu": "int8", "cuda": "float16"}


def resolve_device_config() -> tuple[str, str, str | None]:
    """Validate the requested device; a bad request is reported, never downgraded."""
    device = os.getenv("ECHOSCRIBE_DEVICE", "cpu").strip().lower()
    compute = os.getenv("ECHOSCRIBE_COMPUTE", "").strip().lower()
    if device not in SUPPORTED_DEVICES:
        return "cpu", "int8", f"ECHOSCRIBE_DEVICE={device} is not supported. Use cpu or cuda."
    return device, compute or DEFAULT_COMPUTE[device], None


DEVICE, COMPUTE_TYPE, DEVICE_ERROR = resolve_device_config()
DEVICE_REQUESTED = "ECHOSCRIBE_DEVICE" in os.environ
BASE_DIR = Path(os.getenv("ECHOSCRIBE_DIR", Path.home() / "EchoScribe")).expanduser()
OUT_DIR = BASE_DIR / "transcripts"
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
WINDOW_SECONDS = 5.0
OVERLAP_SECONDS = 1.0
WINDOW_BYTES = int(WINDOW_SECONDS * BYTES_PER_SECOND)
NEED_BYTES = int((WINDOW_SECONDS + OVERLAP_SECONDS) * BYTES_PER_SECOND)
SESSION_TTL_SECONDS = 10 * 60

MODEL: WhisperModel | None = None


def describe_failure(error: Exception) -> str:
    """Turn a CTranslate2 exception into one line that names the cause."""
    text = str(error).strip()
    lowered = text.lower()
    library = re.search(r"lib\w+\.so[\w.]*", text)
    if library and "not found" in lowered:
        return (
            f"ECHOSCRIBE_DEVICE={DEVICE} cannot run {MODEL_NAME}: {library.group(0)} is missing. "
            "Install nvidia-cublas-cu12 and nvidia-cudnn-cu12 (uv sync)."
        )
    if "out of memory" in lowered:
        return f"ECHOSCRIBE_DEVICE={DEVICE} cannot run {MODEL_NAME}: {text}"
    if "compute type" in lowered or "compute_type" in lowered:
        return (
            f"ECHOSCRIBE_DEVICE={DEVICE} with ECHOSCRIBE_COMPUTE={COMPUTE_TYPE} "
            f"cannot run {MODEL_NAME}: {text}"
        )
    return f"ECHOSCRIBE_DEVICE={DEVICE} cannot run {MODEL_NAME}: {text}"


def preload_cuda_libraries() -> int:
    """Load cuBLAS/cuDNN from site-packages; CTranslate2 dlopens them by soname."""
    if DEVICE != "cuda":
        return 0

    root = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    pending = [
        str(path)
        for package in ("cublas", "cudnn", "cuda_nvrtc")
        for path in sorted((root / package / "lib").glob("*.so*"))
    ]

    loaded = 0
    while pending:
        progressed = False
        for path in list(pending):
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                continue
            pending.remove(path)
            loaded += 1
            progressed = True
        if not progressed:
            break

    print(f"[device] preloaded {loaded} CUDA libraries", flush=True)
    return loaded


def load_model() -> WhisperModel:
    global MODEL
    if MODEL is not None:
        return MODEL

    if DEVICE_ERROR:
        raise SystemExit(f"[device] {DEVICE_ERROR}")
    if DEVICE == "cuda" and get_cuda_device_count() == 0:
        raise SystemExit(
            "[device] ECHOSCRIBE_DEVICE=cuda found no CUDA device. "
            "Set ECHOSCRIBE_DEVICE=cpu."
        )

    print(f"[model] loading {MODEL_NAME} ({DEVICE}/{COMPUTE_TYPE}) ...", flush=True)
    try:
        MODEL = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception as error:  # noqa: BLE001 - every refusal is user-facing
        raise SystemExit(f"[device] {describe_failure(error)}") from error
    print("[model] ready", flush=True)
    return MODEL


def verify_device(model: WhisperModel) -> None:
    """A loaded model can still fail on the first encode; prove one works."""
    buffer = np.zeros(SAMPLE_RATE, dtype=np.float32)
    started = time.perf_counter()
    try:
        segments, _ = model.transcribe(
            buffer,
            language="en",
            task="transcribe",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        list(segments)
    except Exception as error:  # noqa: BLE001 - every refusal is user-facing
        raise SystemExit(f"[device] {describe_failure(error)}") from error
    elapsed = time.perf_counter() - started
    print(f"[verify] 1.0 s ok in {elapsed:.2f} s", flush=True)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or "lecture"


def format_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def resolve_language(
    requested: str | None, model_name: str
) -> tuple[str | None, str | None]:
    """Return (language, error). A None language means the model detects it."""
    code = (requested or "").strip().lower()
    language = None if code in ("", "auto") else code

    if language is not None and language not in SUPPORTED_LANGUAGES:
        return None, f"Unsupported language {code!r}. Use en, hi, or auto."
    if language not in (None, "en") and model_name.endswith(".en"):
        return None, (
            f"Model {model_name} supports English only. "
            "Set ECHOSCRIBE_MODEL=small (multilingual) and restart the server."
        )
    return language, None


@dataclass
class TranscriptWriter:
    path: Path
    started_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(cls, title: str, source: str, language: str | None = None) -> TranscriptWriter:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = " ".join(title.split()) or "Lecture"
        safe_source = " ".join(source.split()) or "unknown"
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = OUT_DIR / f"{stamp}_{slugify(safe_title)}.md"
        # Two starts inside one second would otherwise truncate the first transcript.
        suffix = 2
        while path.exists():
            path = OUT_DIR / f"{stamp}_{slugify(safe_title)}-{suffix}.md"
            suffix += 1
        writer = cls(path)
        path.write_text(
            f"# {safe_title}\n\n"
            f"Source: {safe_source}\n"
            f"Started {writer.started_at.isoformat(timespec='seconds')}\n"
            f"Language: {language or 'auto'} (model {MODEL_NAME}, device {DEVICE}/{COMPUTE_TYPE})\n\n",
            encoding="utf-8",
        )
        return writer

    def append(self, text: str, offset: float) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{format_ts(offset)}] {text.strip()}\n")

def transcribe_pcm(pcm: np.ndarray, language: str | None) -> list[tuple[float, float, str]]:
    segments, _ = load_model().transcribe(
        pcm,
        language=language,
        task="transcribe",  # Hindi must stay Hindi, never translated
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    return [(segment.start, segment.end, segment.text) for segment in segments]


@dataclass
class Session:
    writer: TranscriptWriter
    session_id: str
    language: str | None = None
    buffer: bytearray = field(default_factory=bytearray)
    buffer_start: float = 0.0
    emitted_until: float = 0.0
    last_seen: float = field(default_factory=time.monotonic)
    failed: bool = False

    def add(self, data: bytes) -> None:
        if self.failed:
            return
        self.buffer.extend(data)

    async def process(self, websocket) -> None:
        while len(self.buffer) >= NEED_BYTES and not self.failed:
            await self._emit_window(websocket, NEED_BYTES)
            del self.buffer[:WINDOW_BYTES]
            self.buffer_start += WINDOW_SECONDS

    async def flush(self, websocket=None) -> None:
        size = len(self.buffer)
        if size >= int(0.5 * BYTES_PER_SECOND) and not self.failed:
            await self._emit_window(websocket, size)
        self.buffer_start += size / BYTES_PER_SECOND
        self.buffer.clear()

    async def _emit_window(self, websocket, size: int) -> None:
        if self.failed:
            return

        chunk = bytes(self.buffer[:size])
        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            segments = await asyncio.to_thread(transcribe_pcm, pcm, self.language)
        except Exception as error:  # noqa: BLE001 - one dead window must not kill the file
            self.failed = True
            self.buffer.clear()
            message = f"Transcription failed: {error}"
            print(f"[error] {message}", flush=True)
            if websocket is not None:
                try:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "transcription_failed",
                                "message": message,
                            }
                        )
                    )
                except ConnectionClosed:
                    pass
            return

        for start, end, text in segments:
            text = text.strip()
            if not text:
                continue
            global_start = self.buffer_start + start
            global_end = self.buffer_start + end

            if global_end <= self.emitted_until + 0.05:
                continue

            self.writer.append(text, global_start)
            self.emitted_until = max(self.emitted_until, global_end)
            print(f"[{format_ts(global_start)}] {text}", flush=True)

            if websocket is None:
                continue

            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "segment",
                            "start": round(global_start, 2),
                            "end": round(global_end, 2),
                            "text": text,
                        }
                    )
                )
            except ConnectionClosed:
                pass

SESSIONS: dict[str, Session] = {}


async def cleanup_sessions() -> None:
    while True:
        await asyncio.sleep(60)
        cutoff = time.monotonic() - SESSION_TTL_SECONDS
        for session_id, session in list(SESSIONS.items()):
            if session.last_seen >= cutoff:
                continue
            try:
                await session.flush()
            except Exception as error:  # noqa: BLE001 - keep cleanup alive
                print(f"[file] expiry flush failed: {error}", flush=True)
            SESSIONS.pop(session_id, None)
            print(f"[file] expired {session.writer.path}", flush=True)


async def handle_client(websocket) -> None:
    session: Session | None = None
    print(f"[ws] client {websocket.remote_address}", flush=True)

    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "invalid json"})
                    )
                    continue

                kind = data.get("type")
                if kind == "start":
                    session_id = str(data.get("sessionId") or uuid.uuid4())
                    existing = SESSIONS.get(session_id)

                    if session is not None:
                        await session.flush(websocket)
                        SESSIONS.pop(session.session_id, None)
                        session = None

                    if existing is None:
                        language, error = resolve_language(
                            data.get("language") or LANGUAGE, MODEL_NAME
                        )
                        if error is not None:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "code": "unsupported_language",
                                        "message": error,
                                    }
                                )
                            )
                            continue

                        session = Session(
                            TranscriptWriter.create(
                                data.get("title", "Lecture"),
                                data.get("url", ""),
                                language,
                            ),
                            session_id=session_id,
                            language=language,
                        )
                        SESSIONS[session_id] = session
                        # The only place the actual language is visible; wrong output starts here.
                        print(
                            f"[lang] {language or 'auto'} (model {MODEL_NAME})",
                            flush=True,
                        )
                        print(f"[file] new {session.writer.path}", flush=True)
                    else:
                        session = existing
                        session.last_seen = time.monotonic()
                        SESSIONS[session_id] = session
                        print(f"[file] resumed {session.writer.path}", flush=True)

                    await websocket.send(
                        json.dumps(
                            {
                                "type": "ready",
                                "model": MODEL_NAME,
                                "language": session.language,
                                "device": DEVICE,
                                "compute": COMPUTE_TYPE,
                                "sessionId": session_id,
                                "resumed": existing is not None,
                            }
                        )
                    )
                elif kind == "stop":
                    if session is not None:
                        await session.flush(websocket)
                        SESSIONS.pop(session.session_id, None)
                        print(f"[file] saved {session.writer.path}", flush=True)
                        session = None
                    await websocket.send(json.dumps({"type": "done"}))
                else:
                    await websocket.send(
                        json.dumps({"type": "error", "message": f"unknown type {kind}"})
                    )
            else:
                if session is None:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "send start first"})
                    )
                    continue
                session.add(message)
                session.last_seen = time.monotonic()
                await session.process(websocket)
    except ConnectionClosed:
        pass
    finally:
        if session is not None:
            try:
                await session.flush()
            except Exception as error:  # noqa: BLE001 - keep cleanup alive
                print(f"[ws] flush failed: {error}", flush=True)
            session.last_seen = time.monotonic()
            print(f"[ws] paused {session.writer.path}", flush=True)


def transcribe_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    preload_cuda_libraries()
    model = load_model()
    segments, info = model.transcribe(
        str(path),
        language=LANGUAGE,
        task="transcribe",  # Hindi must stay Hindi, never translated
        beam_size=1,
        vad_filter=True,
    )
    writer = TranscriptWriter.create(path.stem, str(path), LANGUAGE)
    print(f"[file] {writer.path}", flush=True)

    for segment in segments:
        text = segment.text.strip()
        if text:
            writer.append(text, segment.start)
            print(f"[{format_ts(segment.start)}] {text}", flush=True)

    print(f"[lang] {info.language} ({info.language_probability:.2f})", flush=True)
    print(f"[file] saved {writer.path}", flush=True)


async def main() -> None:
    preload_cuda_libraries()
    model = load_model()
    if DEVICE_REQUESTED:
        print(f"[device] {DEVICE}/{COMPUTE_TYPE} ({MODEL_NAME})", flush=True)
    verify_device(model)
    print(f"[ws] listening on ws://{HOST}:{PORT}", flush=True)
    async with serve(handle_client, HOST, PORT):
        cleanup_task = asyncio.create_task(cleanup_sessions())
        try:
            await asyncio.Future()
        finally:
            cleanup_task.cancel()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EchoScribe local Whisper server")
    parser.add_argument("--file", type=Path, help="transcribe one audio/video file and exit")
    args=parser.parse_args()

    if args.file:
        transcribe_file(args.file)

    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n[ws] stopped", flush=True)