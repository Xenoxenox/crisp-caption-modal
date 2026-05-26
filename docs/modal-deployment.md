# Modal Deployment

Phase 1 moves translation and offline file transcription to Modal while keeping local CrispASR live ASR unchanged.

## Architecture

`modal_app/app.py` defines one Modal app, `crisp-caption-runtime`, with two GPU functions sharing the `crisp-caption-models` Volume:

- `translation_service`: OpenAI-compatible `/v1/chat/completions` endpoint behind `CRISP_API_TOKEN`.
- `transcribe_file`: one-shot offline media transcription that returns SRT and VTT text.

`/health` is intentionally unauthenticated so the existing local health monitor can keep using it.

## Setup

Run:

```bat
scripts\setup-modal.bat
```

The script installs Modal, starts the Modal token flow, creates the `crisp-caption-token` secret when possible, deploys the app, and preloads models into the Volume.

Then copy `profiles\profile.ja.example.json` to `profiles\profile.ja.json` if needed and set:

```json
"translate_url": "https://<workspace>--crisp-caption-runtime-translation-service.modal.run/v1/chat/completions"
```

Before starting the bridge:

```bat
set OPENAI_API_KEY=<CRISP_API_TOKEN>
scripts\run-windows.bat
```

When `profiles\profile.ja.json` points at a `.modal.run` URL, `scripts\run-windows.bat` skips the local llama.cpp server.

## Offline Transcription

After Modal setup:

```bat
scripts\transcribe-file.bat demo\sample-jp.mp4
```

Outputs are written to `output\<stem>.srt` and `output\<stem>.vtt`. Files larger than 500 MB are rejected in Phase 1; a Volume upload flow belongs in a later phase.

## Validation

Health:

```bat
curl https://<workspace>--crisp-caption-runtime-translation-service.modal.run/health
```

Auth failure:

```bat
curl -X POST https://<workspace>--crisp-caption-runtime-translation-service.modal.run/v1/chat/completions
```

Translation:

```bat
curl -X POST https://<workspace>--crisp-caption-runtime-translation-service.modal.run/v1/chat/completions ^
  -H "Authorization: Bearer %OPENAI_API_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"Hy-MT2-1.8B\",\"messages\":[{\"role\":\"user\",\"content\":\"把【当前原文】翻译为繁體中文（台灣）。只输出译文。\n\n【当前原文】\nこんにちは\"}],\"temperature\":0.7,\"max_tokens\":64,\"stream\":false}"
```

Offline:

```bat
scripts\transcribe-file.bat modal_spike\samples\sample.flac
```

## Notes

The llama.cpp `b9095` release does not publish a Linux CUDA binary asset. The Modal image uses the official `llama-b9095-bin-ubuntu-x64.tar.gz` asset on the CUDA 12.6 runtime base image. This keeps the image aligned with the verified CrispASR base, but translation currently runs through the Linux x64 llama.cpp binary rather than a Linux CUDA llama.cpp binary.

Local llama.cpp scripts remain as the fallback path.
