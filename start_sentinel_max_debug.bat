@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sentinel MAX Launcher (DEBUG)
color 0A

cd /d "%~dp0"

set "SENTINEL_STORAGE_DIR=F:\Sandbox\sentinel-data\memory"
set "SENTINEL_PROJECT_STORAGE=F:\Sandbox\sentinel-data\projects"

if not exist "%SENTINEL_STORAGE_DIR%" mkdir "%SENTINEL_STORAGE_DIR%" >nul 2>&1
if not exist "%SENTINEL_PROJECT_STORAGE%" mkdir "%SENTINEL_PROJECT_STORAGE%" >nul 2>&1

if not exist ".\.venv\Scripts\activate.bat" (
  echo ERROR: .venv missing at "%cd%\.venv"
  pause
  exit /b 1
)

call ".\.venv\Scripts\activate.bat"

REM make sure imports resolve from repo root
set "PYTHONPATH=%cd%"

REM better crash output
set "PYTHONFAULTHANDLER=1"

REM log file
if not exist ".\logs" mkdir ".\logs" >nul 2>&1
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set d=%%c-%%a-%%b
for /f "tokens=1-3 delims=:." %%a in ("%time%") do set t=%%a%%b%%c
set "LOG=logs\gui_debug_%d%_%t%.log"

echo Writing log to: %LOG%
echo ===== START %date% %time% ===== > "%LOG%"
echo Repo: %cd% >> "%LOG%"
echo Python: >> "%LOG%"
python --version >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo Launching GUI...
python -m sentinel.main --mode gui >> "%LOG%" 2>&1

echo.
echo GUI process exited. Tail of log:
echo --------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 80 '%LOG%'" 
echo --------------------------------------------
echo.
pause
endlocal
