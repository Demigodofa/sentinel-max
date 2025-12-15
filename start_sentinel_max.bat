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
set "SENTINEL_SANDBOX_ROOT=F:\"
set "SENTINEL_STORAGE_DIR=%SENTINEL_SANDBOX_ROOT%\sentinel-data\memory"
set "SENTINEL_PROJECT_STORAGE=%SENTINEL_SANDBOX_ROOT%\sentinel-data\projects"

if not exist "%SENTINEL_SANDBOX_ROOT%" mkdir "%SENTINEL_SANDBOX_ROOT%" >nul 2>&1
if not exist "%SENTINEL_STORAGE_DIR%" mkdir "%SENTINEL_STORAGE_DIR%" >nul 2>&1
if not exist "%SENTINEL_PROJECT_STORAGE%" mkdir "%SENTINEL_PROJECT_STORAGE%" >nul 2>&1

>>"%LOG%" echo SandboxRoot: %SENTINEL_SANDBOX_ROOT%
>>"%LOG%" echo StorageDir:  %SENTINEL_STORAGE_DIR%
>>"%LOG%" echo ProjectsDir: %SENTINEL_PROJECT_STORAGE%

REM ---- LLM (OpenAI default, Ollama optional) ----
set "SENTINEL_LLM_BACKEND=openai"
set "SENTINEL_LLM_BASE_URL=https://api.openai.com/v1"
set "SENTINEL_LLM_MODEL=gpt-4o"
set "SENTINEL_LLM_WORKER_MODEL="
set "SENTINEL_LLM_TIMEOUT_SECS=60"
set "OPENAI_API_KEY="

>>"%LOG%" echo LLM_BACKEND: %SENTINEL_LLM_BACKEND%
>>"%LOG%" echo LLM_BASE_URL: %SENTINEL_LLM_BASE_URL%
>>"%LOG%" echo LLM_MODEL: %SENTINEL_LLM_MODEL%

REM ---- Listener toggle ----
if not defined START_BROWSER_RELAY set "START_BROWSER_RELAY=1"
set "START_BROWSER_RELAY_NORMALIZED=%START_BROWSER_RELAY%"
if /I "%START_BROWSER_RELAY%"=="true" set "START_BROWSER_RELAY_NORMALIZED=1"
if /I "%START_BROWSER_RELAY%"=="yes" set "START_BROWSER_RELAY_NORMALIZED=1"
if /I "%START_BROWSER_RELAY%"=="on" set "START_BROWSER_RELAY_NORMALIZED=1"
echo ChatGPT relay flag: %START_BROWSER_RELAY%  ^(normalized: %START_BROWSER_RELAY_NORMALIZED%^) 
>>"%LOG%" echo ChatGPT relay flag: %START_BROWSER_RELAY% ^(normalized: %START_BROWSER_RELAY_NORMALIZED%^)

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

REM ---- Chromedriver check (Selenium Manager fallback allowed) ----
set "CHROMEDRIVER_FOUND=0"
set "CHROMEDRIVER_MSG=chromedriver not found on PATH; Selenium Manager will try to fetch a driver dynamically"
set "CHROMEDRIVER_PATH="

if /I "%START_BROWSER_RELAY_NORMALIZED%"=="1" (
  where chromedriver >nul 2>&1 && (
    set "CHROMEDRIVER_FOUND=1"
    for /f "usebackq delims=" %%C in (`where chromedriver`) do if not defined CHROMEDRIVER_PATH set "CHROMEDRIVER_PATH=%%C"
  )

  if "%CHROMEDRIVER_FOUND%"=="0" (
    for %%P in ("%VENV_DIR%\Scripts\chromedriver.exe" "%REPO%\scripts\chromedriver.exe" "%REPO%\chromedriver.exe") do (
      if exist %%P (
        set "CHROMEDRIVER_FOUND=1"
        if not defined CHROMEDRIVER_PATH set "CHROMEDRIVER_PATH=%%~fP"
      )
    )
  )

  if defined CHROMEDRIVER_PATH (
    for %%D in ("%CHROMEDRIVER_PATH%") do set "CHROMEDRIVER_MSG=chromedriver: %%~fD" & set "CHROMEDRIVER_DIR=%%~dpD"
    if defined CHROMEDRIVER_DIR set "PATH=%CHROMEDRIVER_DIR%;%PATH%"
  )

  >>"%LOG%" echo %CHROMEDRIVER_MSG%
)

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

REM ---- ChatGPT browser relay listener ----
if /I "%START_BROWSER_RELAY_NORMALIZED%"=="1" (
  if "%CHROMEDRIVER_FOUND%"=="0" (
    echo WARNING: chromedriver not found on PATH; relying on Selenium Manager to fetch a compatible driver. Ensure Chrome is installed and internet access is available.
    >>"%LOG%" echo WARNING: chromedriver missing; using Selenium Manager fallback for relay startup.
  ) else (
    echo %CHROMEDRIVER_MSG%
    >>"%LOG%" echo %CHROMEDRIVER_MSG%
  )

  echo Starting ChatGPT browser relay listener (Selenium Chrome window should appear)...
  >>"%LOG%" echo Starting ChatGPT browser relay listener...
  >>"%LOG%" echo %CHROMEDRIVER_MSG%
  if "%CHROMEDRIVER_FOUND%"=="0" >>"%LOG%" echo Using Selenium Manager fallback to resolve driver.
  start "Sentinel Browser Relay" cmd /k "echo ChatGPT relay log: %LOG% & echo %CHROMEDRIVER_MSG% & \"%VENV_PY%\" -u -X faulthandler scripts\\browser_chatgpt_relay.py >> \"%LOG%\" 2>&1"
  if errorlevel 1 (
    echo WARNING: Failed to launch ChatGPT browser relay. See log for details.
    >>"%LOG%" echo WARNING: Failed to launch ChatGPT browser relay.
  ) else (
    echo ChatGPT browser relay requested; a Chrome window should open. If it does not, open %LOG% and search for "selenium" or "chromedriver" errors.
    >>"%LOG%" echo ChatGPT browser relay process launched.
  )
) else (
  echo ChatGPT browser relay disabled by START_BROWSER_RELAY=%START_BROWSER_RELAY%.
  echo Set START_BROWSER_RELAY=1 (true/yes/on accepted) to launch the Selenium Chrome relay window.
  >>"%LOG%" echo ChatGPT browser relay disabled by flag.
)

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
