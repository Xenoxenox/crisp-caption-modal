from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import aiohttp

try:
    from smoke_realtime import endpoint_with_token
except ImportError:  # pragma: no cover
    from .smoke_realtime import endpoint_with_token


SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
IDLE_TIMEOUT_SEC = 60.0
LRC_RE = re.compile(r"\[(?P<mm>\d{1,2}):(?P<ss>\d{2}(?:\.\d+)?)\](?P<text>.*)")


@dataclass
class ReceivedEvent:
    event: dict[str, Any]
    received_at: float


@dataclass
class FinalEvent:
    seq: int
    t0: float | None
    t1: float | None
    text: str
    received_at: float


@dataclass
class LrcEntry:
    index: int
    time_sec: float
    text: str
    watermark: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Modal realtime ASR over a bounded long session.")
    parser.add_argument("--endpoint", required=True, help="Realtime WS endpoint without token.")
    parser.add_argument("--audio", required=True, help="Input audio file.")
    parser.add_argument("--lrc", required=True, help="Human Chinese LRC reference.")
    parser.add_argument("--start-sec", type=float, required=True, help="Start offset in seconds.")
    parser.add_argument("--end-sec", type=float, required=True, help="End offset in seconds.")
    parser.add_argument("--chunk-ms", type=int, default=750, help="PCM chunk cadence in milliseconds.")
    parser.add_argument("--tail-silence-sec", type=float, default=3.0, help="Silence appended after the range.")
    parser.add_argument("--events-out", default="output/Phase2_eval_events.jsonl", help="Raw event JSONL path.")
    parser.add_argument("--alignment-out", default="output/Phase2_eval_alignment.tsv", help="Alignment TSV path.")
    parser.add_argument("--report-out", default="modal_app/Phase2_EVAL_RESULT.md", help="Markdown report path.")
    parser.add_argument("--token", default="", help="Token override; otherwise CRISP_API_TOKEN or .env is used.")
    return parser.parse_args()


def load_token(cli_token: str) -> str:
    if cli_token:
        return cli_token
    if os.environ.get("CRISP_API_TOKEN"):
        return os.environ["CRISP_API_TOKEN"]

    env_path = Path.cwd() / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "CRISP_API_TOKEN":
                return value.strip().strip('"').strip("'")
    raise SystemExit("Missing CRISP_API_TOKEN. Pass --token, set env var, or provide .env.")


def load_pcm(audio: str, start_sec: float, end_sec: float) -> bytes:
    duration = end_sec - start_sec
    if duration <= 0:
        raise SystemExit("--end-sec must be greater than --start-sec.")
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        audio,
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "pipe:1",
    ]
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout


def parse_lrc(path: Path, start_sec: float, end_sec: float) -> list[LrcEntry]:
    entries: list[LrcEntry] = []
    normal_index = 1
    parsed_line_index = 0
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        match = LRC_RE.search(raw_line)
        if not match:
            continue
        parsed_line_index += 1
        minute = int(match.group("mm"))
        second = float(match.group("ss"))
        timestamp = minute * 60 + second
        text = match.group("text").strip()
        if parsed_line_index == 1:
            entries.append(LrcEntry(index=0, time_sec=timestamp, text=text, watermark=True))
            continue
        if not (start_sec <= timestamp < end_sec):
            continue
        for part in [part.strip() for part in text.split("&") if part.strip()]:
            entries.append(LrcEntry(index=normal_index, time_sec=timestamp, text=part))
            normal_index += 1
    return entries


async def send_pcm(
    ws: aiohttp.ClientWebSocketResponse,
    pcm: bytes,
    chunk_size: int,
    chunk_seconds: float,
    first_send_at: list[float | None],
) -> None:
    for offset in range(0, len(pcm), chunk_size):
        if first_send_at[0] is None:
            first_send_at[0] = time.monotonic()
        await ws.send_bytes(pcm[offset : offset + chunk_size])
        await asyncio.sleep(chunk_seconds)


async def collect_events(args: argparse.Namespace, token: str, pcm: bytes) -> tuple[list[ReceivedEvent], dict[str, Any]]:
    events_path = Path(args.events_out)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_size = max(1, args.chunk_ms) * SAMPLE_RATE // 1000 * BYTES_PER_SAMPLE
    chunk_seconds = max(1, args.chunk_ms) / 1000
    duration = args.end_sec - args.start_sec
    max_elapsed = duration + 90.0
    first_send_at: list[float | None] = [None]
    final_seq: set[int] = set()
    translated_seq: set[int] = set()
    received: list[ReceivedEvent] = []
    close_code: int | None = None
    close_reason = ""
    started = time.monotonic()
    last_event_at = started

    url = endpoint_with_token(args.endpoint, token)
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, heartbeat=20, max_msg_size=16 * 1024 * 1024) as ws:
            sender = asyncio.create_task(send_pcm(ws, pcm, chunk_size, chunk_seconds, first_send_at))
            try:
                with events_path.open("w", encoding="utf-8") as fh:
                    while True:
                        now = time.monotonic()
                        sender_done = sender.done()
                        translations_caught_up = final_seq and translated_seq.issuperset(final_seq)
                        if sender_done and translations_caught_up:
                            break
                        if now - last_event_at >= IDLE_TIMEOUT_SEC:
                            break
                        if now - started >= max_elapsed:
                            break

                        receive_timeout = min(1.0, IDLE_TIMEOUT_SEC - (now - last_event_at), max_elapsed - (now - started))
                        try:
                            message = await ws.receive(timeout=max(0.1, receive_timeout))
                        except TimeoutError:
                            continue

                        if message.type == aiohttp.WSMsgType.TEXT:
                            event = json.loads(message.data)
                            received_at = time.monotonic()
                            last_event_at = received_at
                            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                            received.append(ReceivedEvent(event=event, received_at=received_at))
                            if event.get("type") == "transcript" and event.get("kind") == "final":
                                seq = event.get("seq")
                                if isinstance(seq, int):
                                    final_seq.add(seq)
                            elif event.get("type") == "translation":
                                seq = event.get("seq")
                                if isinstance(seq, int):
                                    translated_seq.add(seq)
                        elif message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                            close_code = ws.close_code
                            close_reason = str(getattr(message, "extra", "") or "")
                            break
            finally:
                if not sender.done():
                    sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
                await ws.close()
                close_code = close_code if close_code is not None else ws.close_code
                if close_code is None:
                    close_code = 1000

    metadata = {
        "events_out": str(events_path),
        "first_send_at": first_send_at[0],
        "started_at": started,
        "finished_at": time.monotonic(),
        "close_code": close_code,
        "close_reason": close_reason,
    }
    return received, metadata


def event_counts(events: list[ReceivedEvent]) -> dict[str, int]:
    counts = {"partial": 0, "final": 0, "translation": 0, "translation_error": 0, "silence": 0, "health": 0}
    for item in events:
        event = item.event
        if event.get("type") == "transcript":
            kind = str(event.get("kind") or "")
            if kind in {"partial", "final"}:
                counts[kind] += 1
        else:
            kind = str(event.get("type") or "")
            if kind in counts:
                counts[kind] += 1
    return counts


def final_events(events: list[ReceivedEvent]) -> list[FinalEvent]:
    finals: list[FinalEvent] = []
    for item in events:
        event = item.event
        if event.get("type") != "transcript" or event.get("kind") != "final":
            continue
        seq = event.get("seq")
        if not isinstance(seq, int):
            continue
        t0 = event.get("t0")
        t1 = event.get("t1")
        finals.append(
            FinalEvent(
                seq=seq,
                t0=float(t0) if isinstance(t0, (int, float)) else None,
                t1=float(t1) if isinstance(t1, (int, float)) else None,
                text=str(event.get("text") or ""),
                received_at=item.received_at,
            )
        )
    return finals


def translations_by_seq(events: list[ReceivedEvent]) -> dict[int, tuple[str, float]]:
    result: dict[int, tuple[str, float]] = {}
    for item in events:
        event = item.event
        if event.get("type") != "translation":
            continue
        seq = event.get("seq")
        if isinstance(seq, int):
            result[seq] = (str(event.get("text") or ""), item.received_at)
    return result


def translation_errors(events: list[ReceivedEvent]) -> list[tuple[int | str, str]]:
    errors: list[tuple[int | str, str]] = []
    for item in events:
        event = item.event
        if event.get("type") == "translation_error":
            errors.append((event.get("seq", ""), str(event.get("message") or "")[:240]))
    return errors


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * pct) - 1))
    return ordered[index]


def latency_stats(finals: list[FinalEvent], translations: dict[int, tuple[str, float]]) -> tuple[dict[str, float | None], list[tuple[int, float]]]:
    latencies: list[tuple[int, float]] = []
    for final in finals:
        translation = translations.get(final.seq)
        if translation:
            latencies.append((final.seq, translation[1] - final.received_at))
    values = [value for _, value in latencies]
    return (
        {
            "min": min(values) if values else None,
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "max": max(values) if values else None,
        },
        sorted(latencies, key=lambda item: item[1], reverse=True),
    )


def align(
    lrc_entries: list[LrcEntry],
    finals: list[FinalEvent],
    translations: dict[int, tuple[str, float]],
    start_sec: float,
) -> tuple[list[dict[str, str]], dict[str, int], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    matched_final_seq: set[int] = set()
    sample_rows: list[dict[str, str]] = []

    for entry in lrc_entries:
        if entry.watermark:
            rows.append(
                {
                    "lrc_index": "0",
                    "lrc_time_sec": f"{entry.time_sec:.3f}",
                    "modal_seq": "",
                    "modal_t0": "",
                    "modal_t1": "",
                    "lrc_zh": entry.text,
                    "modal_ja": "",
                    "modal_zh": "",
                    "match_quality": "watermark",
                }
            )
            continue

        candidates = [
            final
            for final in finals
            if final.seq not in matched_final_seq
            and final.t0 is not None
            and abs((final.t0 + start_sec) - entry.time_sec) <= 2.5
        ]
        candidates.sort(key=lambda final: abs(((final.t0 or 0.0) + start_sec) - entry.time_sec))
        if not candidates:
            rows.append(
                {
                    "lrc_index": str(entry.index),
                    "lrc_time_sec": f"{entry.time_sec:.3f}",
                    "modal_seq": "",
                    "modal_t0": "",
                    "modal_t1": "",
                    "lrc_zh": entry.text,
                    "modal_ja": "",
                    "modal_zh": "",
                    "match_quality": "miss",
                }
            )
            continue

        final = candidates[0]
        matched_final_seq.add(final.seq)
        delta = abs(((final.t0 or 0.0) + start_sec) - entry.time_sec)
        quality = "exact" if delta <= 1.0 else "near"
        modal_zh = translations.get(final.seq, ("", 0.0))[0]
        row = {
            "lrc_index": str(entry.index),
            "lrc_time_sec": f"{entry.time_sec:.3f}",
            "modal_seq": str(final.seq),
            "modal_t0": "" if final.t0 is None else f"{final.t0:.3f}",
            "modal_t1": "" if final.t1 is None else f"{final.t1:.3f}",
            "lrc_zh": entry.text,
            "modal_ja": final.text,
            "modal_zh": modal_zh,
            "match_quality": quality,
        }
        rows.append(row)
        if len(sample_rows) < 5:
            sample_rows.append(row)

    for final in finals:
        if final.seq in matched_final_seq:
            continue
        modal_zh = translations.get(final.seq, ("", 0.0))[0]
        rows.append(
            {
                "lrc_index": "NULL",
                "lrc_time_sec": "",
                "modal_seq": str(final.seq),
                "modal_t0": "" if final.t0 is None else f"{final.t0:.3f}",
                "modal_t1": "" if final.t1 is None else f"{final.t1:.3f}",
                "lrc_zh": "",
                "modal_ja": final.text,
                "modal_zh": modal_zh,
                "match_quality": "extra",
            }
        )

    summary = {
        "lrc_total": sum(1 for entry in lrc_entries if not entry.watermark),
        "matched_exact": sum(1 for row in rows if row["match_quality"] == "exact"),
        "matched_near": sum(1 for row in rows if row["match_quality"] == "near"),
        "miss": sum(1 for row in rows if row["match_quality"] == "miss"),
        "extra": sum(1 for row in rows if row["match_quality"] == "extra"),
    }
    return rows, summary, sample_rows


def write_alignment(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "lrc_index",
        "lrc_time_sec",
        "modal_seq",
        "modal_t0",
        "modal_t1",
        "lrc_zh",
        "modal_ja",
        "modal_zh",
        "match_quality",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE, text=True).stdout.strip()


def fmt_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def write_report(
    args: argparse.Namespace,
    events: list[ReceivedEvent],
    metadata: dict[str, Any],
    counts: dict[str, int],
    lrc_summary: dict[str, int],
    samples: list[dict[str, str]],
    errors: list[tuple[int | str, str]],
    latency: dict[str, float | None],
    slow_latencies: list[tuple[int, float]],
) -> None:
    first_send_at = metadata["first_send_at"]
    first_final = next((item.received_at for item in events if item.event.get("type") == "transcript" and item.event.get("kind") == "final"), None)
    first_final_elapsed = (first_final - first_send_at) if first_send_at is not None and first_final is not None else None
    known_issues: list[str] = []
    if errors:
        known_issues.append("translation_error events were observed.")
    if latency["p95"] is not None and latency["p95"] > 10:
        known_issues.append("translation latency p95 exceeded 10 seconds.")
    if counts["final"] < max(1, lrc_summary["lrc_total"] // 2):
        known_issues.append("final count was below 50% of LRC entry count.")
    if metadata["close_code"] not in {1000, 1005, None}:
        known_issues.append(f"unexpected WebSocket close code: {metadata['close_code']}")
    if not known_issues:
        known_issues.append("None.")

    lines = [
        "# Phase 2 Realtime Evaluation Result",
        "",
        "## Test Range",
        "",
        f"- start_sec: {args.start_sec:.3f}",
        f"- end_sec: {args.end_sec:.3f}",
        f"- audio_seconds: {args.end_sec - args.start_sec:.3f}",
        f"- chunk_ms: {args.chunk_ms}",
        f"- tail_silence_sec: {args.tail_silence_sec:.3f}",
        "",
        "## Link",
        "",
        f"- endpoint: `{args.endpoint}`",
        f"- git_head: `{git_head()}`",
        "- token_source: `CRISP_API_TOKEN` / project `.env` / CLI override; value not recorded",
        "",
        "## Event Counts",
        "",
        f"- partial: {counts['partial']}",
        f"- final: {counts['final']}",
        f"- translation: {counts['translation']}",
        f"- translation_error: {counts['translation_error']}",
        f"- silence: {counts['silence']}",
        f"- health: {counts['health']}",
        "",
        "## Latency",
        "",
        f"- first_final_elapsed_sec: {fmt_number(first_final_elapsed)}",
        f"- translation_latency_sec.min: {fmt_number(latency['min'])}",
        f"- translation_latency_sec.p50: {fmt_number(latency['p50'])}",
        f"- translation_latency_sec.p95: {fmt_number(latency['p95'])}",
        f"- translation_latency_sec.max: {fmt_number(latency['max'])}",
        "",
        "## WebSocket Close",
        "",
        f"- close_code: {metadata['close_code']}",
        f"- close_reason: {metadata['close_reason'] or ''}",
        "",
        "## Translation Errors",
        "",
    ]
    if errors:
        for seq, message in errors:
            lines.append(f"- seq={seq}: {message}")
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## LRC Alignment Summary",
            "",
            f"- lrc_total: {lrc_summary['lrc_total']}",
            f"- matched_exact: {lrc_summary['matched_exact']}",
            f"- matched_near: {lrc_summary['matched_near']}",
            f"- miss: {lrc_summary['miss']}",
            f"- extra: {lrc_summary['extra']}",
            "",
            "## Samples",
            "",
        ]
    )
    if samples:
        for row in samples:
            lines.append(f"- LRC: {row['lrc_zh']} / Modal: {row['modal_zh']} / quality={row['match_quality']}")
    else:
        lines.append("- No exact or near matches available.")

    lines.extend(["", "## Slowest Translation Latencies", ""])
    if slow_latencies:
        for seq, value in slow_latencies[:5]:
            lines.append(f"- seq={seq}: {value:.3f}s")
    else:
        lines.append("- None.")

    lines.extend(["", "## Known Issues", ""])
    for issue in known_issues:
        lines.append(f"- {issue}")

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> dict[str, Any]:
    token = load_token(args.token)
    pcm = load_pcm(args.audio, args.start_sec, args.end_sec)
    tail = b"\x00" * int(max(0.0, args.tail_silence_sec) * SAMPLE_RATE * BYTES_PER_SAMPLE)
    events, metadata = await collect_events(args, token, pcm + tail)
    counts = event_counts(events)
    finals = final_events(events)
    translations = translations_by_seq(events)
    errors = translation_errors(events)
    latency, slow_latencies = latency_stats(finals, translations)
    lrc_entries = parse_lrc(Path(args.lrc), args.start_sec, args.end_sec)
    alignment_rows, lrc_summary, samples = align(lrc_entries, finals, translations, args.start_sec)
    write_alignment(Path(args.alignment_out), alignment_rows)
    write_report(args, events, metadata, counts, lrc_summary, samples, errors, latency, slow_latencies)
    return {
        "events_out": args.events_out,
        "alignment_out": args.alignment_out,
        "report_out": args.report_out,
        "counts": counts,
        "latency": latency,
        "close_code": metadata["close_code"],
        "lrc_summary": lrc_summary,
    }


def main() -> None:
    summary = asyncio.run(run(parse_args()))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
