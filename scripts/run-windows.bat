@echo off
setlocal
cd /d "%~dp0\.."

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"

if not exist "profiles\profile.ja.json" (
  echo [FAIL] profiles\profile.ja.json not found.
  echo Run scripts\setup-windows.bat first.
  pause
  exit /b 1
)

set "TRANSLATE_URL="
for /f "usebackq delims=" %%U in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Get-Content 'profiles\profile.ja.json' -Raw | ConvertFrom-Json).translate_url } catch { '' }"`) do set "TRANSLATE_URL=%%U"

set "USE_LOCAL_TRANSLATION=1"
if /I "%CRISP_SKIP_LOCAL_TRANSLATION%"=="1" set "USE_LOCAL_TRANSLATION=0"
echo %TRANSLATE_URL% | findstr /I ".modal.run" >nul
if not errorlevel 1 set "USE_LOCAL_TRANSLATION=0"

if "%USE_LOCAL_TRANSLATION%"=="1" if not exist "tools\llama.cpp\llama-server.exe" (
  echo [FAIL] tools\llama.cpp\llama-server.exe not found.
  echo Run scripts\download-llama-cpp-windows.bat first.
  pause
  exit /b 1
)

if "%USE_LOCAL_TRANSLATION%"=="1" (
  echo Starting local translation server in a new window...
  start "crisp-caption translation" cmd /k scripts\start-translation-server-windows.bat

  echo Waiting for local translation server health endpoint...
  for /L %%i in (1,1,60) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8080/health; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { exit 0 } } catch { exit 1 }"
    if not errorlevel 1 goto translation_ready
    timeout /t 2 /nobreak >nul
  )

  echo [WARN] Translation server did not become healthy within 120 seconds.
  echo If the normal server failed, try scripts\start-translation-server-low-vram-windows.bat.
  goto translation_ready
)

echo Using remote translation endpoint from profiles\profile.ja.json.
if "%OPENAI_API_KEY%"=="" echo [WARN] OPENAI_API_KEY is not set; Modal translation requests will return 401.

:translation_ready
echo Starting crisp-caption bridge...
echo Opening http://127.0.0.1:8765/ after a short startup delay...
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8765/'"
if "%PY%"=="py -3" (
  py -3 bridge_server.py --config profiles\profile.ja.json
) else (
  "%PY%" bridge_server.py --config profiles\profile.ja.json
)
pause
