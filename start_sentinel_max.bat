@echo off
title Sentinel MAX Launcher
color 0A

echo.
echo  ============================================
echo      SENTINEL MAX — FULL AUTO LAUNCHER
echo  ============================================
echo.

REM ---- Set external SSD sandbox paths ----
set SENTINEL_STORAGE_DIR=F:\Sandbox\sentinel-data\memory
set SENTINEL_PROJECT_STORAGE=F:\Sandbox\sentinel-data\projects

REM ---- Activate virtual environment ----
echo Activating virtual environment...
call .\.venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Could not activate .venv
    echo Make sure .venv exists in F:\SentinelMAX
    pause
    exit /b
)

REM ---- Pull latest version from GitHub ----
echo.
echo Pulling latest updates from GitHub...
git pull
if %errorlevel% neq 0 (
    echo.
    echo Git pull failed — you may have local changes.
    echo Run "git stash" manually if needed.
    pause
)

REM ---- Launch Sentinel MAX GUI ----
echo.
echo Launching GUI mode...
python -m sentinel.main --mode gui

echo.
echo Sentinel MAX exited.
pause
