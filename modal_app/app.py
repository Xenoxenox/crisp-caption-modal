from __future__ import annotations

from pathlib import Path

import modal


APP_NAME = "crisp-caption-runtime"
CRISPASR_VERSION = "v0.6.10"
CRISPASR_ASSET = "crispasr-linux-x86_64-cuda.tar.gz"
CRISPASR_URL = (
    "https://github.com/CrispStrobe/CrispASR/releases/download/"
    f"{CRISPASR_VERSION}/{CRISPASR_ASSET}"
)
CRISPASR_SHA256 = "76223ab25faaf03be98afd9c934932e29bb527f32642123395435d47e3089228"

LLAMA_CPP_TAG = "b9095"
LLAMA_CPP_ASSET = "llama-b9095-bin-ubuntu-vulkan-x64.tar.gz"
LLAMA_CPP_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/{LLAMA_CPP_ASSET}"
LLAMA_CPP_SHA256 = "3ccb127c298abb2640911aac3e3d9221f197bbf6b7c1e0fedfb4a4dae1ab640b"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

app = modal.App(APP_NAME)
models_volume = modal.Volume.from_name("crisp-caption-models", create_if_missing=True)
secret = modal.Secret.from_name("crisp-caption-token")

image = (
    modal.Image.from_registry("nvidia/cuda:12.6.0-runtime-ubuntu24.04", add_python="3.11")
    .apt_install("ca-certificates", "curl", "ffmpeg", "libgomp1", "tar", "libvulkan1")
    .run_commands(
        "mkdir -p /opt/crispasr /tmp/crispasr-download",
        f"curl -L --fail --retry 3 {CRISPASR_URL} -o /tmp/crispasr-download/{CRISPASR_ASSET}",
        (
            f"echo '{CRISPASR_SHA256}  /tmp/crispasr-download/{CRISPASR_ASSET}' "
            "| sha256sum -c -"
        ),
        (
            f"tar -xzf /tmp/crispasr-download/{CRISPASR_ASSET} "
            "-C /opt/crispasr --strip-components=1"
        ),
        "test -f /opt/crispasr/crispasr",
        "chmod +x /opt/crispasr/crispasr",
        "rm -rf /tmp/crispasr-download",
        "mkdir -p /opt/llama.cpp /tmp/llama-download/extracted",
        f"curl -L --fail --retry 3 {LLAMA_CPP_URL} -o /tmp/llama-download/{LLAMA_CPP_ASSET}",
        (
            f"echo '{LLAMA_CPP_SHA256}  /tmp/llama-download/{LLAMA_CPP_ASSET}' "
            "| sha256sum -c -"
        ),
        f"tar -xzf /tmp/llama-download/{LLAMA_CPP_ASSET} -C /tmp/llama-download/extracted",
        (
            "server_dir=$(dirname \"$(find /tmp/llama-download/extracted -type f -name llama-server -print -quit)\") "
            "&& cp -a \"$server_dir\"/. /opt/llama.cpp/"
        ),
        "test -f /opt/llama.cpp/llama-server",
        "chmod +x /opt/llama.cpp/llama-server",
        "LD_LIBRARY_PATH=/opt/llama.cpp /opt/llama.cpp/llama-server --version",
        "test -f /usr/share/vulkan/icd.d/nvidia_icd.json || echo 'WARN: NVIDIA ICD missing'",
        "rm -rf /tmp/llama-download",
    )
    .pip_install("fastapi==0.115.*", "uvicorn[standard]", "httpx==0.27.*")
    .env({"PYTHONPATH": "/opt/crisp-caption:/opt/crisp-caption/modal_app"})
    .add_local_dir(HERE, remote_path="/opt/crisp-caption/modal_app")
    .add_local_file(ROOT / "models" / "manifest.json", remote_path="/opt/crisp-caption/models/manifest.json")
)


@app.function(image=image, volumes={"/models": models_volume}, timeout=1200)
def preload_models() -> None:
    from modal_app.runtime.model_store import ensure_models

    ensure_models(include_asr=True, include_translation=True)
    models_volume.commit()


@app.function(
    image=image,
    gpu="L4",
    volumes={"/models": models_volume},
    secrets=[secret],
    scaledown_window=1800,
    timeout=3600,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def translation_service():
    from modal_app.translation_service import create_app

    return create_app()


@app.function(
    image=image,
    gpu="L4",
    volumes={"/models": models_volume},
    secrets=[secret],
    timeout=7200,
)
def transcribe_file(
    audio_bytes: bytes,
    *,
    target_lang: str = "zh-TW",
    profile: str = "ja",
) -> dict[str, object]:
    from modal_app.transcribe import run_transcription

    return run_transcription(audio_bytes, target_lang=target_lang, profile=profile)


@app.local_entrypoint()
def transcribe(audio_file: str, output_dir: str = "output", profile: str = "ja", target_lang: str = "zh-TW") -> None:
    audio_path = Path(audio_file)
    if not audio_path.exists():
        raise SystemExit(f"Input file not found: {audio_path}")
    audio_bytes = audio_path.read_bytes()
    if len(audio_bytes) > 500 * 1024 * 1024:
        raise SystemExit("File > 500MB; use a Volume upload flow in a later phase.")

    result = transcribe_file.remote(audio_bytes, profile=profile, target_lang=target_lang)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem
    srt_path = out / f"{stem}.srt"
    vtt_path = out / f"{stem}.vtt"
    srt_path.write_text(str(result["srt"]), encoding="utf-8")
    vtt_path.write_text(str(result["vtt"]), encoding="utf-8")
    print(f"Wrote {srt_path} and {vtt_path}")
    print(f"Stats: {result['stats']}")
