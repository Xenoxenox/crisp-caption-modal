from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass

import httpx

from .profiles import TRANSLATION_MODEL_ALIAS, TRANSLATION_MODEL_PATH


@dataclass
class LlamaServerSidecar:
    host: str = "127.0.0.1"
    port: int = 8080
    model_path: str = TRANSLATION_MODEL_PATH
    model_alias: str = TRANSLATION_MODEL_ALIAS
    proc: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return

        cmd = [
            "/opt/llama.cpp/llama-server",
            "-m",
            self.model_path,
            "-a",
            self.model_alias,
            "-ngl",
            os.environ.get("LLAMA_N_GPU_LAYERS", "0"),
            "-c",
            "8192",
            "-b",
            "2048",
            "-ub",
            "1024",
            "-fa",
            "on",
            "-np",
            "1",
            "--cache-prompt",
            "--cache-reuse",
            "64",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = "/opt/llama.cpp:" + env.get("LD_LIBRARY_PATH", "")
        self.proc = subprocess.Popen(
            cmd,
            cwd="/opt/llama.cpp",
            env=env,
        )

    async def wait_ready(self, timeout: float = 120.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        last_error = ""
        async with httpx.AsyncClient(timeout=2.0) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self.proc and self.proc.poll() is not None:
                    raise RuntimeError(f"llama-server exited early with code {self.proc.returncode}")
                try:
                    response = await client.get(f"{self.base_url}/health")
                    if 200 <= response.status_code < 300:
                        return
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                await asyncio.sleep(1.0)
        raise TimeoutError(f"llama-server was not ready after {timeout}s: {last_error}")

    def stop(self) -> None:
        if not self.proc or self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
