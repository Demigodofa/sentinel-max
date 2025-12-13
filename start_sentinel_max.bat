@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sentinel MAX Launcher
color 0A

cd /d "%~dp0"

REM ---- Log everything ----
if not exist ".\logs" mkdir ".\logs" >nul 2>&1
set "LOG=%cd%\logs\launcher_last.log"
echo ===== START %date% %time% ===== > "%LOG%"
echo Repo: %cd% >> "%LOG%"

echo.
echo  ============================================
echo      SENTINEL MAX — FULL AUTO LAUNCHER
echo  ============================================
echo.
echo Writing log to: %LOG%
echo.

REM ---- Set external SSD sandbox paths ----
set "SENTINEL_STORAGE_DIR=F:\Sandbox\sentinel-data\memory"
set "SENTINEL_PROJECT_STORAGE=F:\Sandbox\sentinel-data\projects"

if not exist "%SENTINEL_STORAGE_DIR%" mkdir "%SENTINEL_STORAGE_DIR%" >nul 2>&1
if not exist "%SENTINEL_PROJECT_STORAGE%" mkdir "%SENTINEL_PROJECT_STORAGE%" >nul 2>&1

REM ---- LLM backend (Ollama) ----
set "SENTINEL_LLM_BACKEND=ollama"
set "SENTINEL_LLM_BASE_URL=http://localhost:11434/v1"
set "SENTINEL_LLM_MODEL=qwen2.5:1.5b"
set "SENTINEL_LLM_API_KEY=ollama"

REM ---- Per-computer venv on the SSD ----
set "VENV_DIR=.venv-%COMPUTERNAME%"
set "VENV_PY=%cd%\%VENV_DIR%\Scripts\python.exe"

echo Using venv: %VENV_DIR%
echo Using venv: %VENV_DIR% >> "%LOG%"

REM ---- Choose a Python to CREATE the venv (avoid broken 'py' defaults) ----
set "PY_CREATE=C:\Program Files\Python312\python.exe"
if exist "%PY_CREATE%" goto :py_ok

REM fallback: try launcher explicitly
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
  set "PY_CREATE=py -3.12"
  goto :py_ok
)

echo ERROR: Could not find Python 3.12.
echo ERROR: Could not find Python 3.12. >> "%LOG%"
echo Install Python 3.12 OR fix py.ini, then retry.
pause
exit /b 1

:py_ok
echo Python create cmd: %PY_CREATE% >> "%LOG%"

REM ---- Create venv if missing ----
if not exist "%VENV_PY%" (
  echo Creating venv...
  echo Creating venv... >> "%LOG%"
  %PY_CREATE% -m venv "%VENV_DIR%" >> "%LOG%" 2>&1
  if %errorlevel% neq 0 (
    echo ERROR: Failed to create venv. See log: %LOG%
    pause
    exit /b 1
  )

  echo Installing dependencies...
  "%VENV_PY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
  "%VENV_PY%" -m pip install -r ".\sentinel\requirements.txt" >> "%LOG%" 2>&1
  if %errorlevel% neq 0 (
    echo ERROR: pip install failed. See log: %LOG%
    pause
    exit /b 1
  )
)

REM ---- Pull latest version from GitHub ----
echo Pulling latest updates from GitHub...
git pull >> "%LOG%" 2>&1

REM ---- Launch Sentinel MAX GUI ----
echo Launching GUI mode...
echo Launching GUI mode... >> "%LOG%"
"%VENV_PY%" -m sentinel.main --mode gui >> "%LOG%" 2>&1

echo.
echo Sentinel MAX exited.
echo Tail of log:
powershell -NoProfile -Command "Get-Content -Tail 80 '%LOG%'"
pause
endlocal
