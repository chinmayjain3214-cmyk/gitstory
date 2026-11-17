@echo off
rem Start gitstory (already installed by setup.bat) without reinstalling or testing.
cd /d "%~dp0"
title gitstory
rem Stop any gitstory that is still running, so the browser shows this one.
taskkill /F /IM gitstory.exe >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m gitstory*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo ^> .venv\Scripts\python.exe -m gitstory --serve --open
echo.
".venv\Scripts\python.exe" -m gitstory --serve --open
pause
