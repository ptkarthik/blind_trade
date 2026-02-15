# Blind Trade Engine

A powerful trading engine with a FastAPI backend and React frontend.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

1.  **Python 3.10+**: [Download Python](https://www.python.org/downloads/)
2.  **Node.js 18+**: [Download Node.js](https://nodejs.org/en/download/)
3.  **Docker Desktop**: [Download Docker](https://www.docker.com/products/docker-desktop/) (Required for database)

---

## 🚀 Quick Start

### 1. First Time Setup
Open the project folder and double-click:
**`setup.bat`**

This script will:
- Create a Python virtual environment (`venv`).
- Install all backend dependencies.
- Install all frontend dependencies.
- Start the Database and Redis using Docker.

### 2. Start the App
Double-click:
**`start_app.bat`**

This will verify your database is running and launch both the Backend and Frontend servers.

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000/docs

---

## 🛑 Troubleshooting

- **"Docker is not running"**: Open Docker Desktop and wait for the engine to start completely before running the scripts.
- **"Python not found"**: Ensure Python is added to your system PATH during installation.
- **API Key Errors**: Open `backend/.env` and ensure your `MARKET_DATA_API_KEY` is correct.
