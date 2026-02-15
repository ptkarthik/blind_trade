@echo off
setlocal
title Blind Trade - First Time Setup

echo ===================================================
echo      Blind Trade Engine - First Time Setup
echo ===================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and try again.
    pause
    exit /b
)

:: 2. Check for Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo Please install Node.js 18+ and try again.
    pause
    exit /b
)

:: 3. Setup Backend
echo.
echo [1/4] Setting up Backend...
cd backend
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing Python dependencies...
pip install -r requirements.txt
cd ..

:: 4. Setup Frontend
echo.
echo [2/4] Setting up Frontend...
cd frontend
echo Installing Node modules...
call npm install
cd ..

:: 5. Setup Infrastructure (Docker)
echo.
echo [3/4] Starting Database & Redis...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Docker is not running!
    echo Please start Docker Desktop and run this script again to start the database.
    echo You can continue if you just wanted to install dependencies.
) else (
    docker-compose up -d
)

echo.
echo ===================================================
echo           SETUP COMPLETE!
echo ===================================================
echo.
echo You can now run 'start_app.bat' to launch the engine.
echo.
pause
