@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
setlocal

title Blind Trade Engine Launcher

echo ===================================================
echo        Starting Blind Trade Engine (Job Queue)
echo ===================================================
echo.

:: ---- STEP 0: CLEANUP (PowerShell - fast, no DNS hang) ----
echo [%TIME%] [0/4] Cleaning up old processes...
powershell -Command "Stop-Process -Name python,uvicorn,msedgedriver,node -Force -ErrorAction SilentlyContinue"
echo [%TIME%]   [OK] All old processes terminated.
echo.

:: ---- STEP 0.5: LOCK FILES ----
echo [%TIME%] [0.5/4] Cleaning stale lock files...
del /F /Q "backend\logs\worker_*.pid" >nul 2>&1
echo [%TIME%]   [OK] Lock files cleaned.
echo.

:: ---- STEP 0.7: PYCACHE CLEANUP ----
echo [%TIME%] [0.7/4] Clearing __pycache__...
for /d /r "backend" %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d" >nul 2>&1
)
echo [%TIME%]   [OK] __pycache__ cleared.
echo.

:: ---- STEP 0.8: DATABASE GHOSTS ----
echo [%TIME%] [0.8/4] Cleaning Database Ghost Jobs...
cd backend
call venv\Scripts\activate
python ..\reset_db.py
cd ..
echo [%TIME%]   [OK] Database cleaned.
echo.

:: ---- STEP 1: BACKEND API ----
echo [%TIME%] [1/4] Starting Backend Server (API) on port 8012...
start "Blind Trade Backend API" cmd /k "chcp 65001 >nul & set PYTHONIOENCODING=utf-8 & cd backend && venv\Scripts\activate && uvicorn app.main:app --reload --port 8012"
echo [%TIME%]   [OK] Backend API launched.
echo.

:: ---- STEP 2: WORKER ----
echo [%TIME%] [2/4] Starting Background Worker (Scanner)...
start "Blind Trade Worker" cmd /k "chcp 65001 >nul & set PYTHONIOENCODING=utf-8 & cd backend && venv\Scripts\activate && python -m app.worker.worker_main"
echo [%TIME%]   [OK] Worker launched.
echo.

:: ---- STEP 3: WAIT ----
echo [%TIME%] [3/4] Waiting 3s for services to boot...
timeout /t 3 /nobreak >nul
echo [%TIME%]   [OK] Wait complete.
echo.

:: ---- STEP 4: FRONTEND ----
echo [%TIME%] [4/4] Starting Frontend Client...
start "Blind Trade Frontend" cmd /k "cd frontend && npm run dev"
echo [%TIME%]   [OK] Frontend launched.
echo.

echo ===================================================
echo    [%TIME%]  ALL SYSTEMS GO!
echo ===================================================
echo.
echo   Backend API : http://localhost:8012/docs
echo   Worker      : Running in background window
echo   Frontend    : http://localhost:5173
echo.
echo Keep the other windows open. You can close this launcher.
pause
