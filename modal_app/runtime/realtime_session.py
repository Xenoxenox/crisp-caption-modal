from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Sequence
import json
import logging
import re
import subprocess
import threading
from pathlib import Path

import httpx

from .llama_server import LlamaServerSidecar
from .profiles import (
    CRISPASR_BIN,
    TRANSLATION_MODEL_ALIAS,
    crisp_args_for_profile,
    normalize_target_lang,
    stream_step_bytes,
)

logger = logging.getLogger(__name__)


def _build_glossary_text(glossary: dict[str, str]) -> str:
    if not glossary:
        return ""
    lines = "\n".join(f"- {key} => {value}" for key, value in glossary.items())
    return f"术语表（必须固定使用以下译法）：\n{lines}"


def _clean_translation_output(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"</?\s*source\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\s*translation\s*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.replace("譯文：", "").replace("译文：", "").strip()


def _build_user_message(
    text: str,
    glossary: dict[str, str],
    target_lang: str = "繁體中文（台灣）",
    history: Sequence[tuple[str, str]] | None = None,
) -> str:
    context_blocks: list[str] = []
    if glossary:
        context_blocks.append(_build_glossary_text(glossary))
    if history:
        history_lines = [
            f"{idx}. 原文：{orig}\n   译文：{trans}"
            for idx, (orig, trans) in enumerate(history, start=1)
        ]
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


class RealtimeSession:
    def __init__(
        self,
        llama_sidecar: LlamaServerSidecar,
        *,
        profile: str = "ja",
        target_lang: str = "zh-TW",
        translate_window: int = 8,
        glossary: dict[str, str] | None = None,
    ) -> None:
        self.llama_sidecar = llama_sidecar
        self.profile = profile
        self.target_lang = normalize_target_lang(target_lang)
        self.translate_window = max(1, translate_window)
        self.glossary = glossary or {}
        self.outbound_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.transcript_queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self.context_history: deque[tuple[str, str]] = deque(maxlen=max(32, self.translate_window * 4))

        self.crispasr_proc: subprocess.Popen[bytes] | None = None
        self.stdout_thread: threading.Thread | None = None
        self.translator_tasks: list[asyncio.Task[None]] = []
        self.watch_task: asyncio.Task[None] | None = None
        self.transcript_seq = 0

        self._loop: asyncio.AbstractEventLoop | None = None
        self._stdin_lock = threading.Lock()
        self._stderr_fh = None
        self._stopping = False
        self._chunk_size = 0

    async def start(self) -> None:
        if self.crispasr_proc and self.crispasr_proc.poll() is None:
            return
        self._loop = asyncio.get_running_loop()
        self._stopping = False

        crisp_args = crisp_args_for_profile(self.profile)
        self._chunk_size = stream_step_bytes(crisp_args)
        cmd = [CRISPASR_BIN, "--stream", "--monitor", "--no-prints", *crisp_args]
        self._stderr_fh = Path("/tmp/crispasr-realtime-stderr.log").open("ab")
        logger.info("Starting realtime CrispASR: %s", " ".join(cmd))
        self.crispasr_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_fh,
            cwd=str(Path(CRISPASR_BIN).parent),
            bufsize=0,
        )
        if self.crispasr_proc.stdin is None or self.crispasr_proc.stdout is None:
            raise RuntimeError("CrispASR did not expose stdin/stdout pipes")

        self.stdout_thread = threading.Thread(
            target=self._stdout_reader_thread,
            name="crispasr-realtime-stdout",
            daemon=True,
        )
        self.stdout_thread.start()
        self.translator_tasks = [
            asyncio.create_task(self._translator_worker(worker_id=index), name=f"realtime-translator-{index}")
            for index in range(4)
        ]
        self.watch_task = asyncio.create_task(self._watch_crispasr(), name="realtime-crispasr-watch")

        await self._send_health(crisp_status="starting", translator_status="checking")
        await self.feed_pcm(b"\x00" * self._chunk_size)
        await self._send_health(crisp_status="running", translator_status="online")

    async def feed_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_write, pcm)

    async def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True

        tasks: list[asyncio.Task[None]] = [*self.translator_tasks]
        if self.watch_task is not None:
            tasks.append(self.watch_task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.translator_tasks = []
        self.watch_task = None

        proc = self.crispasr_proc
        self.crispasr_proc = None
        if proc:
            await asyncio.get_running_loop().run_in_executor(None, self._stop_process, proc)
        if self.stdout_thread:
            self.stdout_thread.join(timeout=2)
            self.stdout_thread = None
        if self._stderr_fh:
            self._stderr_fh.close()
            self._stderr_fh = None
        await self._send_health(crisp_status="stopped", translator_status="disabled")

    def _sync_write(self, pcm: bytes) -> None:
        proc = self.crispasr_proc
        if self._stopping or proc is None or proc.poll() is not None or proc.stdin is None:
            raise RuntimeError("CrispASR is not running")
        with self._stdin_lock:
            proc.stdin.write(pcm)
            proc.stdin.flush()

    @staticmethod
    def _stop_process(proc: subprocess.Popen[bytes]) -> None:
        if proc.stdin:
            try:
                proc.stdin.close()
            except OSError:
                pass
        if proc.poll() is None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

    def _stdout_reader_thread(self) -> None:
        proc = self.crispasr_proc
        loop = self._loop
        if proc is None or proc.stdout is None or loop is None:
            return
        for line in iter(proc.stdout.readline, b""):
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                event = {"type": "plain", "text": text}
            if isinstance(event, dict):
                loop.call_soon_threadsafe(self._handle_crisp_event, event)

    def _handle_crisp_event(self, event: dict[str, object]) -> None:
        kind = event.get("type")
        if kind in {"partial", "final"}:
            self.transcript_seq += 1
            seq = self.transcript_seq
            text = str(event.get("text") or "")
            payload: dict[str, object] = {
                "type": "transcript",
                "seq": seq,
                "kind": kind,
                "final": kind == "final",
                "text": text,
            }
            utterance_id = event.get("utterance_id")
            if isinstance(utterance_id, int):
                payload["utterance_id"] = utterance_id
            for key in ("t0", "t1"):
                value = event.get(key)
                if isinstance(value, (int, float)):
                    payload[key] = value
            self.outbound_queue.put_nowait(payload)
            if kind == "final" and text.strip():
                self.transcript_queue.put_nowait((seq, text))
                self._queue_health()
            return

        if kind == "silence":
            payload = {"type": "silence"}
            value = event.get("t")
            if isinstance(value, (int, float)):
                payload["t"] = value
            self.outbound_queue.put_nowait(payload)
            return

        text = str(event.get("text") or "").strip()
        if text:
            self.transcript_seq += 1
            seq = self.transcript_seq
            self.outbound_queue.put_nowait(
                {"type": "transcript", "seq": seq, "kind": "plain", "final": True, "text": text}
            )
            self.transcript_queue.put_nowait((seq, text))
            self._queue_health()

    async def _translator_worker(self, *, worker_id: int) -> None:
        headers = {"Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                seq, text = await self.transcript_queue.get()
                try:
                    stripped = text.strip()
                    if not stripped:
                        continue
                    history = list(self.context_history)[-self.translate_window :]
                    payload = {
                        "model": TRANSLATION_MODEL_ALIAS,
                        "messages": [
                            {
                                "role": "user",
                                "content": _build_user_message(
                                    stripped,
                                    self.glossary,
                                    target_lang=self.target_lang,
                                    history=history,
                                ),
                            }
                        ],
                        "temperature": 0.7,
                        "top_k": 20,
                        "top_p": 0.6,
                        "repeat_penalty": 1.05,
                        "max_tokens": 4096,
                        "stream": False,
                    }
                    try:
                        response = await client.post(
                            f"{self.llama_sidecar.base_url}/v1/chat/completions",
                            json=payload,
                            headers=headers,
                        )
                        response.raise_for_status()
                        data = response.json()
                        result = _clean_translation_output(data["choices"][0]["message"]["content"] or "")
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        message = f"translate worker {worker_id} request failed: {exc}"
                        logger.warning("%s", message)
                        self.outbound_queue.put_nowait({"type": "translation_error", "seq": seq, "message": message})
                        await self._send_health(translator_status="error", last_error=message)
                        continue

                    self.context_history.append((stripped, result))
                    self.outbound_queue.put_nowait({"type": "translation", "seq": seq, "text": result})
                    await self._send_health(translator_status="online", last_error="")
                finally:
                    self.transcript_queue.task_done()

    async def _watch_crispasr(self) -> None:
        proc = self.crispasr_proc
        if proc is None:
            return
        return_code = await asyncio.get_running_loop().run_in_executor(None, proc.wait)
        if self._stopping or proc is not self.crispasr_proc:
            return
        if return_code == 0:
            await self._send_health(crisp_status="stopped")
        else:
            message = f"CrispASR exited with code {return_code}"
            logger.warning("%s", message)
            await self._send_health(crisp_status="error", last_error=message)

    def _queue_health(self) -> None:
        self.outbound_queue.put_nowait(
            {
                "type": "health",
                "translator_status": "online",
                "translation_queue_size": self.transcript_queue.qsize(),
                "last_error": "",
                "active_profile": self.profile,
                "crisp_status": "running",
            }
        )

    async def _send_health(
        self,
        *,
        crisp_status: str | None = None,
        translator_status: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self.outbound_queue.put_nowait(
            {
                "type": "health",
                "translator_status": translator_status or "online",
                "translation_queue_size": self.transcript_queue.qsize(),
                "last_error": last_error or "",
                "active_profile": self.profile,
                "crisp_status": crisp_status or "running",
            }
        )
