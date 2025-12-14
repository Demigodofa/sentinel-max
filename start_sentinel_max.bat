@echo off
setlocal EnableExtensions
title Sentinel MAX Launcher
color 0A

cd /d "%~dp0"
set "REPO=%cd%"
chcp 65001 >nul

REM ---- Log file ----
if not exist "%REPO%\logs" mkdir "%REPO%\logs" >nul 2>&1
set "LOG=%REPO%\logs\launcher_last.log"

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'"`) do set "TS=%%T"
> "%LOG%" echo ===== START %TS% =====
>>"%LOG%" echo Repo: %REPO%
>>"%LOG%" echo Computer: %COMPUTERNAME%
>>"%LOG%" echo.

echo.
echo  ============================================
echo      SENTINEL MAX - FULL AUTO LAUNCHER
echo  ============================================
echo.
echo Writing log to: %LOG%
echo.

REM ---- Paths ----
set "SENTINEL_SANDBOX_ROOT=F:\Sandbox"
set "SENTINEL_STORAGE_DIR=%SENTINEL_SANDBOX_ROOT%\sentinel-data\memory"
set "SENTINEL_PROJECT_STORAGE=%SENTINEL_SANDBOX_ROOT%\sentinel-data\projects"

if not exist "%SENTINEL_SANDBOX_ROOT%" mkdir "%SENTINEL_SANDBOX_ROOT%" >nul 2>&1
if not exist "%SENTINEL_STORAGE_DIR%" mkdir "%SENTINEL_STORAGE_DIR%" >nul 2>&1
if not exist "%SENTINEL_PROJECT_STORAGE%" mkdir "%SENTINEL_PROJECT_STORAGE%" >nul 2>&1

>>"%LOG%" echo SandboxRoot: %SENTINEL_SANDBOX_ROOT%
>>"%LOG%" echo StorageDir:  %SENTINEL_STORAGE_DIR%
>>"%LOG%" echo ProjectsDir: %SENTINEL_PROJECT_STORAGE%

REM ---- LLM (Ollama) ----
set "SENTINEL_LLM_BACKEND=ollama"
set "SENTINEL_LLM_BASE_URL=http://127.0.0.1:11434/v1"
set "SENTINEL_LLM_MODEL=qwen2.5:1.5b"
set "SENTINEL_LLM_API_KEY=ollama"

>>"%LOG%" echo LLM_BASE_URL: %SENTINEL_LLM_BASE_URL%
>>"%LOG%" echo LLM_MODEL: %SENTINEL_LLM_MODEL%

REM ---- Python behavior ----
set "PYTHONUNBUFFERED=1"
set "PYTHONFAULTHANDLER=1"
set "PYTHONPATH=%REPO%"

REM ---- Venv ----
set "VENV_DIR=.venv-%COMPUTERNAME%"
set "VENV_PY=%REPO%\%VENV_DIR%\Scripts\python.exe"

echo Using venv: %VENV_DIR%
>>"%LOG%" echo Using venv: %VENV_DIR%

REM ---- Pick Python (avoid py launcher) ----
set "PY_CREATE=C:\Program Files\Python312\python.exe"
if not exist "%PY_CREATE%" (
  echo ERROR: Missing Python 3.12 at: %PY_CREATE%
  >>"%LOG%" echo ERROR: Missing Python 3.12 at: %PY_CREATE%
  goto :done
)

>>"%LOG%" echo PythonSelected: %PY_CREATE%
"%PY_CREATE%" --version >> "%LOG%" 2>&1

REM ---- Create venv if missing ----
if not exist "%VENV_PY%" (
  echo Creating venv...
  >>"%LOG%" echo Creating venv...
  "%PY_CREATE%" -m venv "%VENV_DIR%" >> "%LOG%" 2>&1
  if errorlevel 1 goto :done

  echo Installing deps...
  >>"%LOG%" echo Installing deps...
  "%VENV_PY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
  "%VENV_PY%" -m pip install -r ".\sentinel\requirements.txt" >> "%LOG%" 2>&1
  if errorlevel 1 goto :done
)

REM ---- Ollama check (fast) ----
>>"%LOG%" echo.
>>"%LOG%" echo Ollama /api/tags (3s timeout):
curl.exe -sS --max-time 3 http://127.0.0.1:11434/api/tags >> "%LOG%" 2>&1

REM ---- Git sync + proof ----
echo Pulling latest updates from GitHub...
>>"%LOG%" echo.
>>"%LOG%" echo ---- Git sync ----
git fetch origin >> "%LOG%" 2>&1
git pull --ff-only >> "%LOG%" 2>&1
git fetch origin >> "%LOG%" 2>&1

>>"%LOG%" echo Git HEAD:
git rev-parse HEAD >> "%LOG%" 2>&1
>>"%LOG%" echo Git origin/main:
git rev-parse origin/main >> "%LOG%" 2>&1
>>"%LOG%" echo Git status:
git status -sb >> "%LOG%" 2>&1
>>"%LOG%" echo.

REM ---- Live tail window so you SEE logs while running ----
start "Sentinel Log Tail" powershell -NoProfile -Command "Get-Content -Path '%LOG%' -Wait -Tail 120"

REM ---- Launch ----
set "MODE=gui"
if not "%~1"=="" set "MODE=%~1"

echo Launching mode: %MODE%...
>>"%LOG%" echo Launching mode: %MODE%...

"%VENV_PY%" -u -X faulthandler -m sentinel.main --mode %MODE% >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo Sentinel exited with code %RC%.
>>"%LOG%" echo Sentinel exited with code %RC%.

:done
echo.
echo Tail of log:
powershell -NoProfile -Command "Get-Content -Tail 160 '%LOG%'"
echo.
echo Press any key to close...
pause >nul
endlocal
exit /b %RC%
