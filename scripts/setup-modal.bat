@echo off
setlocal
cd /d "%~dp0\.."

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"

echo Installing Modal CLI into the local Python environment...
if "%PY%"=="py -3" (
  py -3 -m pip install modal
) else (
  "%PY%" -m pip install modal
)
if errorlevel 1 (
  echo [FAIL] Modal install failed.
  pause
  exit /b 1
)

echo.
echo Opening Modal login flow if needed...
if "%PY%"=="py -3" (
  py -3 -m modal token new
) else (
  "%PY%" -m modal token new
)
if errorlevel 1 (
  echo [FAIL] Modal token setup failed.
  pause
  exit /b 1
)

if "%CRISP_API_TOKEN%"=="" (
  for /f "delims=" %%T in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "[guid]::NewGuid().ToString('N')"') do set "CRISP_API_TOKEN=%%T"
)

echo.
echo Creating Modal secret crisp-caption-token...
if "%PY%"=="py -3" (
  py -3 -m modal secret create crisp-caption-token CRISP_API_TOKEN=%CRISP_API_TOKEN%
) else (
  "%PY%" -m modal secret create crisp-caption-token CRISP_API_TOKEN=%CRISP_API_TOKEN%
)
if errorlevel 1 (
  echo [WARN] Secret creation failed. If crisp-caption-token already exists, deployment can continue.
  echo        To rotate it later, update or recreate the Modal secret with CRISP_API_TOKEN.
)

echo.
echo Deploying Modal translation endpoint...
if "%PY%"=="py -3" (
  py -3 -m modal deploy modal_app\app.py
) else (
  "%PY%" -m modal deploy modal_app\app.py
)
if errorlevel 1 (
  echo [FAIL] Modal deploy failed.
  pause
  exit /b 1
)

echo.
echo Preloading models into the crisp-caption-models Volume...
if "%PY%"=="py -3" (
  py -3 -m modal run modal_app\app.py::preload_models
) else (
  "%PY%" -m modal run modal_app\app.py::preload_models
)
if errorlevel 1 (
  echo [FAIL] Model preload failed.
  pause
  exit /b 1
)

echo.
echo [OK] Modal setup finished.
echo Endpoint template:
echo   https://^<workspace^>--crisp-caption-runtime-translation-service.modal.run/v1/chat/completions
echo.
echo Use this token locally as OPENAI_API_KEY:
echo   %CRISP_API_TOKEN%
echo.
echo Set profiles\profile.ja.json translate_url to the endpoint above, replacing ^<workspace^>.
pause
