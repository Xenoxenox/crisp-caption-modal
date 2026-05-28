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

## Phase 1.5 Token Rotation

The `crisp-caption-token` Modal secret was rotated before redeploying the service. The token value is intentionally not recorded here; retrieve it from Modal secret storage when configuring local `OPENAI_API_KEY`.

## Phase 1.5 Vulkan Switch

Status: passed.

The Modal image was switched from `llama-b9095-bin-ubuntu-x64.tar.gz` to `llama-b9095-bin-ubuntu-vulkan-x64.tar.gz`, verified with SHA256 `3ccb127c298abb2640911aac3e3d9221f197bbf6b7c1e0fedfb4a4dae1ab640b`, and redeployed.

Runtime Modal logs confirmed GPU offload:

```text
load_tensors: offloading output layer to GPU
load_tensors: offloading 31 repeating layers to GPU
load_tensors: offloaded 33/33 layers to GPU
```

Authenticated latency samples after the Vulkan deploy:

```text
sample_1=9.552s
sample_2=0.940s
sample_3=0.992s
sample_4=0.924s
sample_5=1.460s
```

The first request included container/model startup effects. The four warm follow-up requests averaged about 1.079s wall-clock from the local client, while Modal logs showed server-side request durations around 142-220ms after the first request.

## Phase 1.5 Cold Start Measurement

Status: passed, and production `scaledown_window` was restored to 1800 seconds afterward.

Temporary deployment used `scaledown_window=300`, then waited 360 seconds before measuring cold start:

```text
warm_call=1.256s
cold_start=12.056s
```

## Phase 1.5 E2E With NHK Live

Status: not executed.

Chrome DevTools MCP is available, but the local runtime prerequisites are missing in this checkout:

- `profiles/profile.ja.json` is not present.
- `tools/crispasr/crispasr.exe` is not present.

Stopped before launching the bridge so the test does not drift into a different setup path. Run `scripts/setup-windows.bat` or provide a prepared local profile/runtime, then repeat the browser E2E validation.
