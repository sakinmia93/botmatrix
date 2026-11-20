@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BOT MATRIX Launcher

echo ==============================================
echo   BOT MATRIX - One Command Start
echo ==============================================

where node >nul 2>&1 || (echo ERROR: Install Node.js from https://nodejs.org & pause & exit /b 1)

set "PY=python"
where python >nul 2>&1 || set "PY=py -3"

echo [1/3] npm install...
call npm install
if errorlevel 1 (echo npm install failed & pause & exit /b 1)

echo [2/3] Python deps...
%PY% -m pip install -r "backend\requirements.txt" >nul 2>&1

echo [3/3] Starting Backend + Frontend...
echo.
echo Backend: http://127.0.0.1:5001
echo Frontend: http://localhost:3000
echo.
echo NOTE: Only one backend process (via server.ts). Close other Python windows.
echo.

call npx --yes tsx server.ts
pause
