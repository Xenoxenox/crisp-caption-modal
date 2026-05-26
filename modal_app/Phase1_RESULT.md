# Phase 1 Result

Status: Phase 1a and Phase 1b smoke checks passed with the official Linux x64 llama.cpp asset.

## Endpoint

Deployment URL:

```text
https://litardphobia--crisp-caption-runtime-translation-service.modal.run/v1/chat/completions
```

Use the value stored in Modal secret `crisp-caption-token` as local `OPENAI_API_KEY`.

## Validation Log

- `modal deploy modal_app/app.py`: passed
- `modal run modal_app/app.py::preload_models`: passed
- `/health` 200: passed, returned `{"status":"ok"}` in 1.013s on a warm container
- unauthenticated translation request returns 401: passed
- authenticated translation request: passed, returned OpenAI-compatible `choices[0].message.content`
- offline SRT/VTT generation: passed with `modal_spike/samples/sample.flac`
- offline output: `output/sample.srt` and `output/sample.vtt`
- offline stats: 59.082s audio, 10 segments, 69.68s total, first final at 11.817s
- cold-start after full 30-minute scaledown: not yet measured

## Implementation Note

The official llama.cpp `b9095` release page and release API do not provide a Linux CUDA binary asset. The current Modal image downloads and verifies `llama-b9095-bin-ubuntu-x64.tar.gz` with SHA256 `167e12288da2dc4dcece7327010844edcfb18ee3a76eb45b2e232a04723865e6`.

The Linux x64 llama.cpp binary loaded the CPU backend, not CUDA:

```text
load_backend: loaded CPU backend from /opt/llama.cpp/libggml-cpu-haswell.so
load_tensors: offloaded 0/33 layers to GPU
```
