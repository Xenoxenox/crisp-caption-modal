# crisp-caption Modal App

This directory contains the Phase 1 Modal runtime:

- `app.py`: shared image, Volume, Secret, deployment targets, and local entrypoint.
- `translation_service.py`: FastAPI wrapper around a local llama.cpp sidecar.
- `transcribe.py`: offline media-to-SRT/VTT flow.
- `runtime/`: shared model download, CrispASR runner, llama sidecar, and subtitle writers.

Targets:

```bat
modal deploy modal_app\app.py
modal run modal_app\app.py::preload_models
modal run modal_app\app.py::transcribe --audio-file modal_spike\samples\sample.flac --output-dir output
```

The Modal secret must be named `crisp-caption-token` and contain `CRISP_API_TOKEN`.
