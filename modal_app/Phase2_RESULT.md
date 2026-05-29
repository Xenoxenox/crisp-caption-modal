# Phase 2 Result

Status: realtime ASR WebSocket path passed a Modal smoke test with the deployed `realtime_service`.

## Endpoint

Realtime WebSocket URL:

```text
wss://litardphobia--crisp-caption-runtime-realtime-service.modal.run/v1/realtime
```

Health URL:

```text
https://litardphobia--crisp-caption-runtime-realtime-service.modal.run/healthz
```

Use the value stored in Modal secret `crisp-caption-token` as the browser token. The token value is intentionally not recorded here.

## Validation Log

- `python -m py_compile bridge_server.py bridge_runtime.py bridge_config.py translation.py modal_app\app.py modal_app\realtime_service.py modal_app\runtime\realtime_session.py modal_app\scripts\smoke_realtime.py`: passed
- `cd frontend && corepack pnpm build`: passed
- `cd frontend && corepack pnpm lint`: passed
- Browser static UI smoke at `http://127.0.0.1:4173/`: passed for endpoint switching UI
- `modal deploy modal_app/app.py`: passed
- `modal_app/scripts/smoke_realtime.py --check-auth`: passed

Smoke input:

```text
demo\overlay.mp4
```

Smoke output:

```text
output\Phase2_smoke_events.jsonl
```

Smoke summary:

```text
audio_seconds=57.317
partial=2
final=1
translation=1
translation_error=0
first_final_elapsed_sec=5.209
first_translation_after_final_sec=0.439
```

Authentication behavior:

```text
wrong token -> WebSocket close code 1008
```

## Event Sample

```json
{"type":"transcript","seq":1,"kind":"partial","final":false,"text":"言うのよ","utterance_id":1,"t0":0.86,"t1":1.5}
{"type":"transcript","seq":3,"kind":"final","final":true,"text":"っていうのを。","utterance_id":1,"t0":0.86,"t1":1.59}
{"type":"translation","seq":3,"text":"那個是什麼？"}
```

## Frontend Notes

- Settings now persist `crisp.endpoint` and `crisp.token` in `localStorage`.
- `Local bridge` keeps the existing WebRTC path.
- `Modal cloud` uses `AudioWorklet` PCM encoding and streams binary frames to the Modal WebSocket endpoint.
- Static preview through `python -m http.server` cannot serve local bridge APIs, so `/profiles` and `/ws` are expected to 404 while testing the standalone built frontend. Switching to `Modal cloud` stops the local WebSocket reconnect loop.

## Known Gaps

- Manual microphone capture against the live Modal endpoint was not completed in this pass.
- `/healthz` was not separately recorded because the WebSocket smoke test already exercised container startup, llama sidecar readiness, CrispASR startup, transcript delivery, and translation delivery.
- The Phase 2 scope remains Japanese-only. Chinese and English profiles are deferred.
