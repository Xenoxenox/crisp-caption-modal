from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse

from .runtime.llama_server import LlamaServerSidecar


def create_app() -> FastAPI:
    api = FastAPI()
    sidecar = LlamaServerSidecar()

    @api.on_event("startup")
    async def _on_startup() -> None:
        sidecar.start()
        await sidecar.wait_ready(timeout=120)

    @api.on_event("shutdown")
    async def _on_shutdown() -> None:
        sidecar.stop()

    @api.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        expected = os.environ.get("CRISP_API_TOKEN")
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not expected or token != expected:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @api.get("/health")
    async def health() -> Response:
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                response = await client.get(f"{sidecar.base_url}/health")
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"status": "error", "error": str(exc)}, status_code=503)
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
        )

    @api.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        body = await request.body()
        headers = {"Content-Type": request.headers.get("content-type", "application/json")}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{sidecar.base_url}/v1/chat/completions",
                content=body,
                headers=headers,
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
        )

    return api
