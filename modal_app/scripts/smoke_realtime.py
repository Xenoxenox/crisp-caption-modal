from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp


SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the Modal realtime ASR WebSocket endpoint.")
    parser.add_argument("--endpoint", required=True, help="Realtime WS endpoint, ending in /v1/realtime.")
    parser.add_argument("--token", default=os.environ.get("CRISP_API_TOKEN", ""), help="Token, or CRISP_API_TOKEN.")
    parser.add_argument("--pcm-file", help="Raw 16kHz s16le mono PCM input.")
    parser.add_argument("--audio-file", help="Audio/video input to convert through ffmpeg.")
    parser.add_argument("--output", default="output/Phase2_smoke_events.jsonl", help="JSONL event output path.")
    parser.add_argument("--chunk-ms", type=int, default=750, help="Send cadence in milliseconds.")
    parser.add_argument("--tail-silence-sec", type=float, default=2.0, help="Silence to append after input.")
    parser.add_argument("--timeout-sec", type=float, default=90.0, help="Overall receive timeout.")
    parser.add_argument("--check-auth", action="store_true", help="Verify a wrong token is rejected with close code 1008.")
    return parser.parse_args()


def endpoint_with_token(endpoint: str, token: str) -> str:
    parts = urlsplit(endpoint)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def load_pcm(args: argparse.Namespace) -> bytes:
    if bool(args.pcm_file) == bool(args.audio_file):
        raise SystemExit("Provide exactly one of --pcm-file or --audio-file.")
    if args.pcm_file:
        return Path(args.pcm_file).read_bytes()

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        args.audio_file,
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE)
    return proc.stdout


async def check_auth_rejection(endpoint: str, token: str) -> None:
    wrong_url = endpoint_with_token(endpoint, f"{token}-invalid")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(wrong_url, heartbeat=10) as ws:
            message = await ws.receive(timeout=10)
            close_code = ws.close_code or getattr(message, "data", None)
            if close_code != 1008:
                raise RuntimeError(f"Expected auth close code 1008, got {close_code!r}")


async def send_pcm(ws: aiohttp.ClientWebSocketResponse, pcm: bytes, chunk_size: int, chunk_seconds: float) -> None:
    for offset in range(0, len(pcm), chunk_size):
        await ws.send_bytes(pcm[offset : offset + chunk_size])
        await asyncio.sleep(chunk_seconds)


async def run_smoke(args: argparse.Namespace) -> dict[str, object]:
    if not args.token:
        raise SystemExit("Missing token. Pass --token or set CRISP_API_TOKEN.")
    if args.check_auth:
        await check_auth_rejection(args.endpoint, args.token)

    pcm = load_pcm(args)
    tail = b"\x00" * int(max(0.0, args.tail_silence_sec) * SAMPLE_RATE * BYTES_PER_SAMPLE)
    pcm = pcm + tail
    chunk_size = max(1, args.chunk_ms) * SAMPLE_RATE // 1000 * BYTES_PER_SAMPLE
    chunk_seconds = max(1, args.chunk_ms) / 1000
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    url = endpoint_with_token(args.endpoint, args.token)
    counts = {"partial": 0, "final": 0, "translation": 0, "translation_error": 0}
    first_final_at: float | None = None
    first_translation_at: float | None = None
    started = time.monotonic()

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, heartbeat=20, max_msg_size=4 * 1024 * 1024) as ws:
            sender = asyncio.create_task(send_pcm(ws, pcm, chunk_size, chunk_seconds))
            try:
                with output_path.open("w", encoding="utf-8") as fh:
                    deadline = started + args.timeout_sec
                    while time.monotonic() < deadline:
                        try:
                            message = await ws.receive(timeout=max(0.1, deadline - time.monotonic()))
                        except TimeoutError:
                            break

                        if message.type == aiohttp.WSMsgType.TEXT:
                            event = json.loads(message.data)
                            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                            kind = str(event.get("type") or "")
                            if kind == "transcript":
                                row_kind = str(event.get("kind") or "")
                                if row_kind in counts:
                                    counts[row_kind] += 1
                                if row_kind == "final" and first_final_at is None:
                                    first_final_at = time.monotonic()
                            elif kind in counts:
                                counts[kind] += 1
                                if kind == "translation" and first_translation_at is None:
                                    first_translation_at = time.monotonic()
                            if counts["partial"] and counts["final"] and counts["translation"]:
                                break
                        elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                            raise RuntimeError(f"WebSocket closed early: code={ws.close_code}, message={message}")
            finally:
                if not sender.done():
                    sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)

    summary: dict[str, object] = {
        "output": str(output_path),
        "audio_seconds": round(len(pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE), 3),
        "counts": counts,
    }
    if first_final_at is not None:
        summary["first_final_elapsed_sec"] = round(first_final_at - started, 3)
    if first_final_at is not None and first_translation_at is not None:
        summary["first_translation_after_final_sec"] = round(first_translation_at - first_final_at, 3)
    if not (counts["partial"] and counts["final"] and counts["translation"]):
        raise RuntimeError(f"Smoke criteria not met: {summary}")
    return summary


def main() -> None:
    summary = asyncio.run(run_smoke(parse_args()))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
