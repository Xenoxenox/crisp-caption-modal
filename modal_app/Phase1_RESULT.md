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

Status: partial pass. Browser tab capture and Japanese ASR passed after forcing local CrispASR to CPU; Modal translation failed with HTTP 404.

Chrome DevTools MCP was used for the browser portion. Local prerequisites were present for this run:

- `profiles/profile.ja.json` was configured with the Modal `translate_url`.
- `profiles/profile.ja.json` included `--gpu-backend cpu` in `crisp_args` to avoid the AMD Radeon 780M Vulkan crash path.
- `OPENAI_API_KEY` was loaded from local `.env` value `CRISP_API_TOKEN` before launching the bridge.
- `.venv\Scripts\python.exe bridge_server.py --config profiles\profile.ja.json` reached `Serving http://127.0.0.1:8765/`.
- The bridge UI loaded at `http://127.0.0.1:8765/` and showed `CrispASR` running.

The requested NHK live URL `https://www.youtube.com/watch?v=coYw-eVU0Ks` was opened in a second tab, but YouTube reported:

```text
出了点小问题。请刷新或稍后重试。
```

The source was changed to the replacement recording `https://www.youtube.com/watch?v=0YsnCY6Bs9M`. That page initially played, then failed before tab-audio capture could complete. DevTools inspection showed the visible player error:

```text
出了点问题。请刷新或稍后重试。
```

The current YouTube player object reported:

```text
videoData.errorCode = "ump.spsrejectfailure"
videoData.isPlayable = true
playerState = -1
video.readyState = 0
video.error = null
```

Network logs showed multiple `googlevideo.com/videoplayback` requests ending with `net::ERR_ABORTED` around the playback failure, and YouTube QoE telemetry included an error state. No bridge-side WebSocket or translation failure was identified before playback stopped.

The source was then changed to `https://www.acfun.cn/v/ac31211508`. This avoided the YouTube player failure. AcFun loaded and showed playback at about `06:24 / 24:42`.

Chrome DevTools MCP could open the bridge and AcFun tabs, but the native Chrome tab picker still required manual action. After clicking `Tab audio`, the user manually selected and shared the AcFun tab. The bridge UI and logs confirmed browser capture succeeded:

```text
Capture connected: tab audio
track received kind=audio
pc connectionState=connected
```

With `--gpu-backend cpu`, the previous local crash did not reproduce. During the 30-second observation window, the bridge stayed connected and `CrispASR` stayed `running`. The UI showed `60` partials and `8` finals.

Observed Japanese ASR samples from the UI:

- `ケーキのイチゴは最初に食べますか?あ、ロボコちゃん、強々でしょ。ロボコちゃんに10回買ったもんね、うい`
- `ケーキのいちごは最初に食べますか?最後に食べましょうか?`
- `私もね、98位、はぁ?`
- `何だお前。`
- `1回お水飲んでいいですか?`

Translation did not pass. The UI and bridge logs repeatedly reported:

```text
translate HTTP 404: modal-http: invalid function call
llama-server health check failed: HTTP 404: modal-http: invalid function call
```

Final 30-second observation state:

- Capture: `connected`
- CrispASR: `running`
- Translator: `error / queue 0`
- Japanese partial subtitles: passed.
- Japanese final subtitles: passed.
- Chinese translations: failed with Modal HTTP 404.
- Partial-to-translation latency samples: not measured because no translation completed.
- Original + translation samples: ASR originals were collected; translations were 404 error messages, not Chinese output.
- `translation_error` / translation failure messages: present.
- Screenshot: saved to `modal_app/e2e_screenshot.png`.

Phase 1.5 browser capture plus local Japanese ASR is validated with the AcFun fallback source and CPU ASR backend. Full E2E remains blocked on the Modal translation endpoint returning HTTP 404 for both health checks and translation requests.
