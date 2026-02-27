@echo off
setlocal
title Blind Trade Engine Launcher

echo ===================================================
echo        Starting Blind Trade Engine (Job Queue)
echo ===================================================

echo [0/4] Cleaning up old processes...
:: Use fast native taskkill. Some "Not Found" errors are normal and hidden.

:: 1. Murder by Window Title (Fastest)
taskkill /F /FI "WINDOWTITLE eq Blind Trade*" /IM cmd.exe >nul 2>&1

:: 2. Murder by Port (Reliable)
:: Port 8010 (API)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8010" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
:: Port 8000 (Docs)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8000" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
:: Port 5173 (Frontend)
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5173" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo Done.

:: 3. Start Backend API
echo.
echo [1/4] Starting Backend Server (API)...
start "Blind Trade Backend API" cmd /k "cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8010"

:: 4. Start Backend Worker
echo.
echo [2/4] Starting Background Worker (Scanner)...
start "Blind Trade Worker" cmd /k "cd backend && venv\Scripts\activate && python -m app.worker.worker_main"

:: Wait for a moment
echo.
echo [3/4] Waiting 3s for services to initialize...
timeout /t 3 /nobreak >nul

:: 5. Start Frontend
echo.
echo [4/4] Starting Frontend Client...
start "Blind Trade Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ===================================================
echo               ALL SYSTEMS GO 🚀
echo ===================================================
echo.
echo 1. Backend API : http://localhost:8010/docs
echo 2. Worker      : Running in background window
echo 3. Frontend    : http://localhost:5173
echo.
echo Keep the other windows open. You can close this launcher.
pause
