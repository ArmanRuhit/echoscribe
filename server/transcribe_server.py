"""EchoScribe local transcription server.

The extension sends 16kHz mono Int16 PCM over a local WebSocket.
Segments are transcribed with faster-whisper and appended to Markdown.
A dropped client can reconnect with the same session ID and continue the file.
Audio is never written to disk.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

HOST = "127.0.0.1"
PORT = int(os.getenv("ECHOSCRIBE_PORT", "8765"))
MODEL_NAME = os.getenv("ECHOSCRIBE_MODEL", "small.en")
LANGUAGE = os.getenv("ECHOSCRIBE_LANGUAGE", "en")
LANGUAGE = None if LANGUAGE.lower() == "auto" else LANGUAGE
DEVICE = os.getenv("ECHOSCRIBE_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("ECHOSCRIBE_COMPUTE", "int8")
BASE_DIR = Path(os.getenv("ECHOSCRIBE_DIR", Path.home() / "EchoScribe"))
OUT_DIR = BASE_DIR / "transcripts"
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
WINDOW_SECONDS = 5.0
OVERLAP_SECONDS = 1.0
WINDOW_BYTES = int(WINDOW_SECONDS * BYTES_PER_SECOND)
NEED_BYTES = int((WINDOW_SECONDS + OVERLAP_SECONDS) * BYTES_PER_SECOND)
SESSION_TTL_SECONDS = 10 * 60

MODEL: WhisperModel | None = None

def load_model()-> WhisperModel:
    global MODEL
    if MODEL is None:
        print(f"[model] loading {MODEL_NAME} ({DEVICE}/{COMPUTE_TYPE}) ...", flush=True)
        MODEL = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
        print("[model] ready", flush=True)
    return MODEL


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or "lecture"


def format_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class TranscriptWriter:
    path: Path
    started_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(cls, title: str, source: str) -> TranscriptWriter:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = " ".join(title.split()) or "Lecture"
        safe_source = " ".join(source.split()) or "unknown"
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = OUT_DIR / f"{stamp}_{slugify(safe_title)}.md"
        writer = cls(path)
        path.write_text(
            f"# {safe_title}\n\n"
            f"Source: {safe_source}\n"
            f"Started {writer.started_at.isoformat(timespec='seconds')}\n\n",
            encoding="utf-8",
        )
        return writer

    def append(self, text: str, offset: float) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{format_ts(offset)}] {text.strip()}\n")

def transcribe_pcm(pcm: np.ndarray)-> list[tuple[float, float, str]]:
    segments, _ = load_model().transcribe(
        pcm,
        language=LANGUAGE,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    return [(segment.start, segment.end, segment.text) for segment in segments]


@dataclass
class Session:
    writer: TranscriptWriter
    session_id: str
    buffer: bytearray = field(default_factory=bytearray)
    buffer_start: float = 0.0
    emitted_until: float = 0.0
    last_seen: float = field(default_factory=time.monotonic)

    def add(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def process(self, websocket) -> None:
        while len(self.buffer) >= NEED_BYTES:
            await self._emit_window(websocket, NEED_BYTES)
            del self.buffer[:WINDOW_BYTES]
            self.buffer_start += WINDOW_SECONDS

    async def flush(self, websocket=None) -> None:
        size = len(self.buffer)
        if size >= int(0.5 * BYTES_PER_SECOND):
            await self._emit_window(websocket, size)
        self.buffer_start += size / BYTES_PER_SECOND
        self.buffer.clear()

    async def _emit_window(self, websocket, size: int) -> None:
        chunk = bytes(self.buffer[:size])
        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        segments = await asyncio.to_thread(transcribe_pcm, pcm)

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

                    if existing is None:
                        session = Session(
                            TranscriptWriter.create(
                                data.get("title", "Lecture"),
                                data.get("url", ""),
                            ),
                            session_id=session_id,
                        )
                        SESSIONS[session_id] = session
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

    model = load_model()
    segments, info = model.transcribe(
        str(path),
        language=LANGUAGE,
        beam_size=1,
        vad_filter=True,
    )
    writer = TranscriptWriter.create(path.stem, str(path))
    print(f"[file] {writer.path}", flush=True)

    for segment in segments:
        text = segment.text.strip()
        if text:
            writer.append(text, segment.start)
            print(f"[{format_ts(segment.start)}] {text}", flush=True)

    print(f"[lang] {info.language} ({info.language_probability:.2f})", flush=True)
    print(f"[file] saved {writer.path}", flush=True)


async def main() -> None:
    load_model()
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