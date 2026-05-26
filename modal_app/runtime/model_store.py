from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import urlopen


ROOT = Path("/opt/crisp-caption")
MANIFEST_PATH = ROOT / "models" / "manifest.json"
MODELS_ROOT = Path("/models")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_if_needed(name: str, url: str, path: Path, expected_sha256: str) -> None:
    if path.exists() and sha256_file(path) == expected_sha256:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.unlink(missing_ok=True)

    print(f"Downloading {name} to {path}", flush=True)
    with urlopen(url, timeout=180) as response, tmp.open("wb") as out:
        shutil.copyfileobj(response, out)

    actual = sha256_file(tmp)
    if actual != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{name} sha256 mismatch: expected {expected_sha256}, got {actual}")
    tmp.replace(path)


def load_manifest() -> list[dict[str, str]]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError(f"Invalid model manifest: {MANIFEST_PATH}")
    return [artifact for artifact in artifacts if isinstance(artifact, dict)]


def remote_model_path(manifest_path: str) -> Path:
    path = manifest_path.replace("\\", "/")
    if path.startswith("models/"):
        path = path.removeprefix("models/")
    return MODELS_ROOT / path


def ensure_models(*, include_asr: bool = True, include_translation: bool = True) -> None:
    for artifact in load_manifest():
        path = str(artifact.get("path") or "")
        if not path:
            continue
        is_translation = "/translation/" in path.replace("\\", "/")
        if is_translation and not include_translation:
            continue
        if not is_translation and not include_asr:
            continue

        download_if_needed(
            str(artifact["name"]),
            str(artifact["url"]),
            remote_model_path(path),
            str(artifact["sha256"]),
        )
