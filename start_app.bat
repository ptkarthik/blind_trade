@echo off
setlocal
title Blind Trade Engine Launcher

echo ===================================================
echo        Starting Blind Trade Engine (Job Queue)
echo ===================================================

echo [0/4] Cleaning up old processes...
:: Murder by name (python and uvicorn)
echo   - Terminating background scanners...
taskkill /F /IM python.exe /T >nul 2>&1
echo   - Terminating web servers...
taskkill /F /IM uvicorn.exe /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Blind Trade*" /IM cmd.exe >nul 2>&1
echo   - Success.

:: New: Clean Database Ghosts
echo.
echo [0.5/4] Cleaning Database Ghosts...
python reset_db.py

:: 3. Start Backend API
echo.
echo [1/4] Starting Backend Server (API)...
start "Blind Trade Backend API" cmd /k "cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8012"

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
echo 1. Backend API : http://localhost:8012/docs
echo 2. Worker      : Running in background window
echo 3. Frontend    : http://localhost:5173
echo.
echo Keep the other windows open. You can close this launcher.
pause
