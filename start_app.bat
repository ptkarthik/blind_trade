@echo off
setlocal
title Blind Trade Engine Launcher

echo ===================================================
echo        Starting Blind Trade Engine (Job Queue)
echo ===================================================

echo [0/4] Cleaning up old processes...
taskkill /IM python.exe /F >nul 2>&1
taskkill /IM node.exe /F >nul 2>&1
echo Done.

:: 1. Start Backend API
echo.
echo [1/4] Starting Backend Server (API)...
start "Blind Trade Backend API" cmd /k "cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8010"

:: 2. Start Backend Worker
echo.
echo [2/4] Starting Background Worker (Scanner)...
start "Blind Trade Worker" cmd /k "cd backend && venv\Scripts\activate && python -m app.worker.worker_main"

:: Wait for a moment
echo.
echo [3/4] Waiting 5s for services to initialize...
timeout /t 5 /nobreak >nul

:: 3. Start Frontend
echo.
echo [4/4] Starting Frontend Client...
start "Blind Trade Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ===================================================
echo               ALL SYSTEMS GO 🚀
echo ===================================================
echo.
echo 1. Backend API : http://localhost:8000/docs
echo 2. Worker      : Running in background window
echo 3. Frontend    : http://localhost:5173
echo.
echo Keep the other windows open. You can close this launcher.
pause
