@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sentinel MAX Launcher (DEBUG)
color 0A

REM Always run from the folder this .bat lives in
cd /d "%~dp0"

echo.
echo ================================
echo   Sentinel MAX Launcher (DEBUG)
echo ================================
echo Repo: %cd%
echo Computer: %COMPUTERNAME%
echo.

REM ---- External SSD sandbox paths ----
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
echo.

REM ---- Check Python launcher ----
py --version >nul 2>&1
if %errorlevel% neq 0 (
  echo ERROR: Python launcher 'py' is not working on this PC.
  echo Try: py -0p
  pause
  exit /b 1
)

REM ---- Create venv if missing ----
if not exist "%VENV_PY%" (
  echo Venv not found. Creating: %VENV_DIR%
  py -3.12 -m venv "%VENV_DIR%"
  if %errorlevel% neq 0 (
    echo ERROR: Failed to create venv. Ensure Python 3.12 is installed.
    pause
    exit /b 1
  )

  echo Installing dependencies...
  "%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
  "%VENV_PY%" -m pip install -r ".\sentinel\requirements.txt"
  if %errorlevel% neq 0 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
  )
)

REM ---- Make sure imports resolve from repo root ----
set "PYTHONPATH=%cd%"

REM ---- Better crash output ----
set "PYTHONFAULTHANDLER=1"

REM ---- Log file ----
if not exist ".\logs" mkdir ".\logs" >nul 2>&1
for /f "tokens=1-3 delims=/.- " %%a in ("%date%") do set d=%%c-%%a-%%b
for /f "tokens=1-3 delims=:." %%a in ("%time%") do set t=%%a%%b%%c
set "LOG=logs\gui_debug_%d%_%t%.log"

echo Writing log to: %LOG%
echo ===== START %date% %time% ===== > "%LOG%"
echo Repo: %cd% >> "%LOG%"
echo Venv: %VENV_DIR% >> "%LOG%"
echo Python: >> "%LOG%"
"%VENV_PY%" --version >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo Ollama tags (api/tags): >> "%LOG%"
curl.exe http://localhost:11434/api/tags >> "%LOG%" 2>&1
echo. >> "%LOG%"

REM ---- Git pull (optional, but keep it visible) ----
echo Pulling latest updates from GitHub...
git pull >> "%LOG%" 2>&1
echo. >> "%LOG%"

REM ---- Launch GUI ----
echo Launching GUI...
"%VENV_PY%" -m sentinel.main --mode gui >> "%LOG%" 2>&1

echo.
echo GUI process exited. Tail of log:
echo --------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 120 '%LOG%'"
echo --------------------------------------------
echo.
pause
endlocal
