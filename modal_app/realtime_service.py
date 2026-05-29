from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .runtime.llama_server import LlamaServerSidecar
from .runtime.realtime_session import RealtimeSession


def create_app() -> FastAPI:
    api = FastAPI()
    sidecar = LlamaServerSidecar()
    state = {"translator_ready": False}

    @api.on_event("startup")
    async def _on_startup() -> None:
        sidecar.start()
        await sidecar.wait_ready(timeout=120)
        state["translator_ready"] = True

    @api.on_event("shutdown")
    async def _on_shutdown() -> None:
        state["translator_ready"] = False
        sidecar.stop()

    @api.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"translator_ready": state["translator_ready"], "version": "phase2"})

    @api.websocket("/v1/realtime")
    async def realtime(websocket: WebSocket) -> None:
        await websocket.accept()
        expected = os.environ.get("CRISP_API_TOKEN")
        token = websocket.query_params.get("token", "")
        if not expected or token != expected:
            await websocket.close(code=1008, reason="unauthorized")
            return

        session = RealtimeSession(sidecar, profile="ja")
        await session.start()
        sender = _create_sender_task(websocket, session)
        try:
            while True:
                chunk = await websocket.receive_bytes()
                await session.feed_pcm(chunk)
        except WebSocketDisconnect:
            pass
        finally:
            await session.stop()
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    return api


def _create_sender_task(websocket: WebSocket, session: RealtimeSession) -> asyncio.Task[None]:
    async def _sender() -> None:
        while True:
            payload = await session.outbound_queue.get()
            try:
                await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            finally:
                session.outbound_queue.task_done()

    return asyncio.create_task(_sender(), name="realtime-ws-sender")
