@echo off
rem gitstory setup: installs into .venv, runs the tests, starts the web page.
cd /d "%~dp0"
rem Close any gitstory server left running from an earlier run, so the
rem browser never shows an old version.
taskkill /F /IM gitstory.exe >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m gitstory*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment...
  python -m venv .venv || goto :fail
)
echo.
echo === Installing gitstory and pytest into .venv ===
".venv\Scripts\python.exe" -m pip install -e ".[dev]" || goto :fail
echo.
echo === Running the tests ===
".venv\Scripts\python.exe" -m pytest -q || goto :fail
echo.
echo === Starting gitstory. Your browser will open. Press Ctrl+C here to stop. ===
rem Run through python.exe: some Windows security policies block the
rem gitstory.exe launcher that pip creates.
".venv\Scripts\python.exe" -m gitstory --serve --open
pause
exit /b 0
:fail
echo.
echo Something went wrong. Copy the text above and paste it to Claude.
pause
exit /b 1
