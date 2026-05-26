from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from .profiles import CRISPASR_BIN, SAMPLE_RATE, crisp_args_for_profile, stream_step_bytes


def run_crispasr(
    pcm_bytes: bytes,
    *,
    profile: str = "ja",
    stderr_path: Path | None = None,
) -> dict[str, object]:
    crisp_args = crisp_args_for_profile(profile)
    cmd = [CRISPASR_BIN, "--stream", "--monitor", "--no-prints", *crisp_args]
    chunk_size = stream_step_bytes(crisp_args)
    chunk_seconds = chunk_size / (SAMPLE_RATE * 2)
    events: list[dict[str, object]] = []
    raw_lines: list[str] = []
    first_final_at: list[float | None] = [None]
    events_lock = threading.Lock()
    started = time.monotonic()

    stderr_target = stderr_path or Path("/tmp/crispasr-stderr.log")
    with stderr_target.open("wb") as stderr_fh:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_fh,
            cwd=str(Path(CRISPASR_BIN).parent),
            bufsize=0,
        )

        assert proc.stdin is not None
        assert proc.stdout is not None

        def stdout_reader() -> None:
            for line in iter(proc.stdout.readline, b""):
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                with events_lock:
                    raw_lines.append(text)
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    with events_lock:
                        events.append(event)
                        if event.get("type") == "final" and first_final_at[0] is None:
                            first_final_at[0] = time.monotonic()

        reader = threading.Thread(target=stdout_reader, name="crispasr-stdout-reader", daemon=True)
        reader.start()

        proc.stdin.write(b"\x00" * chunk_size)
        proc.stdin.flush()
        time.sleep(chunk_seconds)

        try:
            for offset in range(0, len(pcm_bytes), chunk_size):
                proc.stdin.write(pcm_bytes[offset : offset + chunk_size])
                proc.stdin.flush()
                time.sleep(chunk_seconds)
        finally:
            proc.stdin.close()

        try:
            return_code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            return_code = proc.wait(timeout=10)
        reader.join(timeout=2)

    finished = time.monotonic()
    timings: dict[str, object] = {
        "chunk_size_bytes": chunk_size,
        "chunk_seconds": round(chunk_seconds, 3),
        "audio_seconds": round(len(pcm_bytes) / (SAMPLE_RATE * 2), 3),
        "process_return_code": return_code,
        "process_elapsed_sec": round(finished - started, 3),
    }
    if first_final_at[0] is not None:
        timings["first_final_elapsed_sec"] = round(first_final_at[0] - started, 3)

    return {"events": events, "raw_lines": raw_lines, "timings": timings}


def final_segments(events: list[dict[str, object]]) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    fallback_t0 = 0.0
    for index, event in enumerate(events, start=1):
        if event.get("type") != "final":
            continue
        text = str(event.get("text") or "").strip()
        if not text:
            continue

        t0_raw = event.get("t0")
        t1_raw = event.get("t1")
        t0 = float(t0_raw) if isinstance(t0_raw, (int, float)) else fallback_t0
        t1 = float(t1_raw) if isinstance(t1_raw, (int, float)) else max(t0 + 1.0, fallback_t0 + 1.0)
        if t1 <= t0:
            t1 = t0 + 1.0
        fallback_t0 = t1

        utterance_id = event.get("utterance_id")
        segments.append(
            {
                "utterance_id": utterance_id if isinstance(utterance_id, int) else index,
                "t0": t0,
                "t1": t1,
                "text": text,
            }
        )
    return segments
