# Repository Guidelines

## Project Structure & Module Organization

`crisp-caption` is a Windows-first live captioning bridge. Python entry points and runtime modules live at the repository root: `bridge_server.py`, `bridge_runtime.py`, `bridge_config.py`, `translation.py`, and overlay helpers such as `subtitle_overlay_qt.py`. The browser control panel is in `frontend/` with Vue components under `frontend/src/components/`, API clients under `frontend/src/api/`, and Pinia state in `frontend/src/stores/`. Windows setup and runtime helpers live in `scripts/`. Public examples and local configuration templates live in `profiles/`, `glossary.example.json`, and `translate_prompt.example.txt`. Documentation belongs in `docs/`; demo media and screenshots are in `demo/`. Runtime downloads under `tools/` and model payloads under `models/` are intentionally not committed, except `models/manifest.json`.

## Build, Test, and Development Commands

- `scripts\setup-windows.bat`: create `.venv`, install Python and frontend dependencies, create a local profile, and build `frontend\dist`.
- `scripts\check-deps.bat`: verify Python packages, model/runtime files, profile JSON, ports, and translation server reachability.
- `scripts\run-windows.bat`: start the local translation server and bridge, then open `http://127.0.0.1:8765/`.
- `cd frontend && corepack pnpm dev`: run the Vite dev server; keep the Python bridge on `127.0.0.1:8765`.
- `cd frontend && corepack pnpm build`: type-check with `vue-tsc` and build production assets.
- `cd frontend && corepack pnpm lint`: run ESLint over the frontend.

For Python syntax checks, use `.venv\Scripts\python.exe -m py_compile bridge_server.py bridge_runtime.py bridge_config.py translation.py`.

## Coding Style & Naming Conventions

Python uses type hints, small modules, and `from __future__ import annotations`; keep CLI parsing, runtime orchestration, and translation concerns separated. Use `snake_case` for Python functions and variables. Frontend code uses Vue 3 `<script setup lang="ts">`, strict TypeScript, path alias `@/*`, and component names in `PascalCase`. Run Prettier with `cd frontend && corepack pnpm format` before larger frontend changes.

## Testing Guidelines

There is no dedicated automated test suite in this repository. Validate Python edits with `py_compile`, frontend edits with `pnpm build` and `pnpm lint`, and end-to-end runtime behavior with `scripts\check-deps.bat` plus the relevant local flow in the browser. For UI changes, verify transcript capture, profile selection, overlay launch, and export behavior when affected.

## Modal / Linux CUDA Spike Notes

Keep Modal experiments isolated under ignored `modal_spike/`; do not mix spike code, logs, samples, or temporary reports into production runtime changes unless explicitly requested. For CrispASR Linux CUDA probes, use an NVIDIA CUDA runtime image with a new enough libc/libstdc++, such as `nvidia/cuda:12.6.0-runtime-ubuntu24.04`. `modal.Image.debian_slim(...)` is not sufficient for the v0.6.10 CUDA asset because it lacks `libcudart.so.12` / `libcublas.so.12` and has older `GLIBC` / `GLIBCXX` symbols. The verified v0.6.10 Linux CUDA asset SHA256 is `76223ab25faaf03be98afd9c934932e29bb527f32642123395435d47e3089228`.

The current Modal spike result was GO on L4: `crispasr --version` passed, stdout emitted aligned `partial` / `final` / `silence` JSON events, 10 final events were produced from the demo FLAC, first final elapsed time was about 11.0s, and GPU memory sampled at about 1.7 GB. Treat transcript quality tuning as a later phase; the Linux/CUDA feasibility decision was about binary compatibility, event shape, latency, and memory only.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries, for example `Use GitHub-hosted demo video previews`. Keep commits focused and avoid including local profiles, models, binaries, logs, or generated `frontend/dist`. Pull requests should describe the user-visible change, list validation commands run, mention any profile/model assumptions, and include screenshots or short clips for UI, overlay, or demo changes.

## Security & Configuration Tips

Do not commit `profiles/profile.ja.json`, API keys, downloaded runtimes, or model files. Use the example profile and prompt files for shareable defaults. Third-party runtime and model licensing details belong in `docs/third-party.md`.
