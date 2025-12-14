@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sentinel MAX Launcher (DEBUG)
color 0A

REM Always run from repo root (folder this .bat lives in)
cd /d "%~dp0"
set "REPO=%cd%"

REM ---- Logs ----
if not exist "%REPO%\logs" mkdir "%REPO%\logs" >nul 2>&1

for /f "tokens=1-3 delims=/.- " %%a in ("%date%") do set "D=%%c-%%a-%%b"
for /f "tokens=1-4 delims=:., " %%a in ("%time%") do set "T=%%a%%b%%c%%d"
set "LOG=%REPO%\logs\gui_debug_%D%_%T%.log"

call :log ===== START %date% %time% =====
call :log Repo: %REPO%
call :log Computer: %COMPUTERNAME%

echo.
echo ================================
echo   Sentinel MAX Launcher (DEBUG)
echo ================================
echo Repo: %REPO%
echo Computer: %COMPUTERNAME%
echo Log: %LOG%
echo.

REM ---- Sandbox + storage (your SSD paths) ----
set "SENTINEL_SANDBOX_ROOT=F:\Sandbox"
set "SENTINEL_STORAGE_DIR=%SENTINEL_SANDBOX_ROOT%\sentinel-data\memory"
set "SENTINEL_PROJECT_STORAGE=%SENTINEL_SANDBOX_ROOT%\sentinel-data\projects"

for %%p in ("%SENTINEL_SANDBOX_ROOT%" "%SENTINEL_STORAGE_DIR%" "%SENTINEL_PROJECT_STORAGE%") do (
  if not exist "%%~p" mkdir "%%~p" >nul 2>&1
)

call :log SandboxRoot: %SENTINEL_SANDBOX_ROOT%
call :log StorageDir:  %SENTINEL_STORAGE_DIR%
call :log ProjectsDir: %SENTINEL_PROJECT_STORAGE%

REM ---- LLM backend (OpenAI default, Ollama optional) ----
set "SENTINEL_LLM_BACKEND=openai"
set "SENTINEL_LLM_BASE_URL=https://api.openai.com/v1"
set "SENTINEL_LLM_MODEL=gpt-4o"
set "SENTINEL_LLM_WORKER_MODEL="
set "SENTINEL_LLM_TIMEOUT_SECS=60"
set "OPENAI_API_KEY="

call :log LLM_BACKEND: %SENTINEL_LLM_BACKEND%
call :log LLM_BASE_URL: %SENTINEL_LLM_BASE_URL%
call :log LLM_MODEL: %SENTINEL_LLM_MODEL%

REM ---- Pick Python (DO NOT depend on py launcher) ----
set "PY_CREATE=C:\Program Files\Python312\python.exe"
if not exist "%PY_CREATE%" (
  for /f "delims=" %%P in ('where python 2^>nul') do (set "PY_CREATE=%%P" & goto :py_found)
  echo ERROR: Python not found.>>"%LOG%"
  echo ERROR: Python not found.
  pause
  exit /b 1
)
:py_found

call :log PythonSelected: %PY_CREATE%
"%PY_CREATE%" --version >> "%LOG%" 2>&1

REM ---- Per-computer venv ----
set "VENV_DIR=%REPO%\.venv-%COMPUTERNAME%"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
call :log VenvDir: %VENV_DIR%

if not exist "%VENV_PY%" (
  echo Creating venv: %VENV_DIR%
  call :log Creating venv...
  "%PY_CREATE%" -m venv "%VENV_DIR%" >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail

  echo Installing dependencies...
  call "%VENV_PY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
  call "%VENV_PY%" -m pip install -r "%REPO%\sentinel\requirements.txt" >> "%LOG%" 2>&1
  if errorlevel 1 goto :fail
)

REM ---- Make imports resolve from repo root ----
set "PYTHONPATH=%REPO%"

REM ---- Better visibility in logs ----
set "PYTHONUNBUFFERED=1"
set "PYTHONFAULTHANDLER=1"

REM ---- Live tail window so you can see where it stalls ----
echo Opening a live log tail window...
start "Sentinel Log Tail" powershell -NoProfile -Command "Get-Content -Path '%LOG%' -Wait -Tail 120"

REM ---- Pull latest (safe mode) ----
call :log git pull --ff-only
git pull --ff-only >> "%LOG%" 2>&1

echo.
echo Launching GUI...
echo TIP: If it looks stuck, press Ctrl+Break to dump Python stacks into the LOG.
call :log Launching GUI (Ctrl+Break to dump stacks)

REM -u + faulthandler so stack dumps and prints actually show up
"%VENV_PY%" -u -X faulthandler -m sentinel.main --mode gui >> "%LOG%" 2>&1

if errorlevel 1 goto :fail

echo.
echo GUI exited. Tail:
powershell -NoProfile -Command "Get-Content -Tail 160 '%LOG%'"
pause
exit /b 0

:fail
echo.
echo ERROR: Sentinel failed or crashed. Tail:
powershell -NoProfile -Command "Get-Content -Tail 220 '%LOG%'"
pause
exit /b 1

:log
>>"%LOG%" echo %*
exit /b 0
