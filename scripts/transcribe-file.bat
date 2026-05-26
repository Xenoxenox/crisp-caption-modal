@echo off
setlocal
cd /d "%~dp0\.."

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"

if "%~1"=="" (
  echo Usage: drag a media file onto this bat, or run:
  echo   scripts\transcribe-file.bat path\to\audio.wav
  pause
  exit /b 1
)

if "%PY%"=="py -3" (
  py -3 -m modal run modal_app\app.py::transcribe --audio-file "%~1" --output-dir output
) else (
  "%PY%" -m modal run modal_app\app.py::transcribe --audio-file "%~1" --output-dir output
)
pause
