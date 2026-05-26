from __future__ import annotations

import subprocess
import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path
import re

import httpx

from .runtime.crispasr_runner import final_segments, run_crispasr
from .runtime.llama_server import LlamaServerSidecar
from .runtime.profiles import SAMPLE_RATE, TRANSLATION_MODEL_ALIAS, normalize_target_lang
from .runtime.srt_writer import to_srt, to_vtt


def select_context_history(
    history: deque[tuple[str, str]],
    max_items: int,
) -> list[tuple[str, str]]:
    return list(history)[-max_items:]


def clean_translation_output(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"</?\s*source\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\s*translation\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("譯文：", "").replace("译文：", "").strip()
    return cleaned


def build_glossary_text(glossary: dict[str, str]) -> str:
    if not glossary:
        return ""
    lines = "\n".join(f"- {k} => {v}" for k, v in glossary.items())
    return f"术语表（必须固定使用以下译法）：\n{lines}"


def build_user_message(
    text: str,
    glossary: dict[str, str],
    target_lang: str = "繁體中文（台灣）",
    history: Sequence[tuple[str, str]] | None = None,
) -> str:
    context_blocks: list[str] = []

    if glossary:
        context_blocks.append(build_glossary_text(glossary))

    if history:
        history_lines = []
        for idx, (orig, trans) in enumerate(history, start=1):
            history_lines.append(f"{idx}. 原文：{orig}\n   译文：{trans}")
        context_blocks.append("上文参考（只用于理解语气、人物、代词和场景，不要重新翻译）：\n" + "\n".join(history_lines))

    if context_blocks:
        context = "\n\n".join(context_blocks)
        return (
            f"{context}\n\n"
            f"把【当前原文】翻译为{target_lang}。只输出译文，不要输出标签、原文、解释或额外内容。\n\n"
            f"【当前原文】\n{text}"
        )

    return (
        f"把【当前原文】翻译为{target_lang}。只输出译文，不要输出标签、原文、解释或额外内容。\n\n"
        f"【当前原文】\n{text}"
    )


def media_bytes_to_pcm(audio_bytes: bytes) -> bytes:
    input_path = Path("/tmp/crisp-caption-input.media")
    pcm_path = Path("/tmp/crisp-caption-input.s16le")
    input_path.write_bytes(audio_bytes)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            str(pcm_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return pcm_path.read_bytes()


def translate_segments(
    segments: list[dict[str, object]],
    *,
    target_lang: str,
    temperature: float = 0.7,
) -> list[dict[str, object]]:
    normalized_target = normalize_target_lang(target_lang)
    history: deque[tuple[str, str]] = deque(maxlen=32)
    translated: list[dict[str, object]] = []

    with httpx.Client(timeout=60.0) as client:
        for segment in segments:
            text = str(segment["text"])
            payload = {
                "model": TRANSLATION_MODEL_ALIAS,
                "messages": [
                    {
                        "role": "user",
                        "content": build_user_message(
                            text,
                            {},
                            target_lang=normalized_target,
                            history=select_context_history(history, 8),
                        ),
                    }
                ],
                "temperature": temperature,
                "top_k": 20,
                "top_p": 0.6,
                "repeat_penalty": 1.05,
                "max_tokens": 512,
                "stream": False,
            }
            response = client.post("http://127.0.0.1:8080/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            translation = clean_translation_output(data["choices"][0]["message"]["content"] or "")
            enriched = dict(segment)
            enriched["translation"] = translation
            translated.append(enriched)
            history.append((text, translation))
    return translated


def run_transcription(
    audio_bytes: bytes,
    *,
    target_lang: str = "zh-TW",
    profile: str = "ja",
) -> dict[str, object]:
    started = time.monotonic()
    pcm_bytes = media_bytes_to_pcm(audio_bytes)

    sidecar = LlamaServerSidecar()
    sidecar.start()
    try:
        import asyncio

        asyncio.run(sidecar.wait_ready(timeout=120))
        crisp_result = run_crispasr(pcm_bytes, profile=profile)
        events = crisp_result["events"]
        if not isinstance(events, list):
            raise RuntimeError("CrispASR runner returned invalid events")
        segments = final_segments(events)
        translated = translate_segments(segments, target_lang=target_lang)
    finally:
        sidecar.stop()

    elapsed = time.monotonic() - started
    stats = {
        "audio_seconds": round(len(pcm_bytes) / (SAMPLE_RATE * 2), 3),
        "segment_count": len(translated),
        "elapsed_sec": round(elapsed, 3),
        "crispasr": crisp_result.get("timings", {}),
    }
    return {
        "srt": to_srt(translated),
        "vtt": to_vtt(translated),
        "segments": translated,
        "stats": stats,
    }
