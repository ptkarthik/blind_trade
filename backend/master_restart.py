
import os
import subprocess
import time
import sqlite3

def run_db_cleanup():
    print("🧹 Cleaning up database...")
    db_path = "blind_trade.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        cursor.execute("VACUUM;")
        conn.commit()
        conn.close()
        print("✅ Database checkpointed and vacuumed.")
    except Exception as e:
        print(f"❌ DB cleanup failed: {e}")

def kill_python():
    print("🛑 Killing all python processes...")
    mypid = os.getpid()
    subprocess.run(["powershell", "-Command", f"Get-Process python | Where-Object {{$_.Id -ne {mypid}}} | Stop-Process -Force"], capture_output=True)
    time.sleep(2)

def start_services():
    print("🚀 Starting API and Workers...")
    
    # Robust venv path (relative to this script)
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    
    if not os.path.exists(venv_python):
        # Fallback to system python if venv not found (though venv is preferred)
        print(f"⚠️ Venv Python not found at {venv_python}, falling back to system 'python'")
        venv_python = "python"

    # Start API
    api_env = os.environ.copy()
    api_env["PYTHONPATH"] = backend_dir
    api_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8012"],
        env=api_env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=backend_dir
    )
    print(f"📡 API started (PID {api_proc.pid})")
    time.sleep(3)

    # Start Workers
    lt_env = os.environ.copy()
    lt_env["WORKER_TYPE"] = "longterm"
    lt_env["PYTHONPATH"] = backend_dir
    lt_proc = subprocess.Popen(
        [venv_python, "app/worker/worker_main.py"],
        env=lt_env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=backend_dir
    )
    print(f"📡 Longterm Worker started (PID {lt_proc.pid})")

    int_env = os.environ.copy()
    int_env["WORKER_TYPE"] = "intraday"
    int_env["PYTHONPATH"] = backend_dir
    int_proc = subprocess.Popen(
        [venv_python, "app/worker/worker_main.py"],
        env=int_env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=backend_dir
    )
    print(f"📡 Intraday Worker started (PID {int_proc.pid})")

    swg_env = os.environ.copy()
    swg_env["WORKER_TYPE"] = "swing"
    swg_env["PYTHONPATH"] = backend_dir
    swg_proc = subprocess.Popen(
        [venv_python, "app/worker/worker_main.py"],
        env=swg_env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=backend_dir
    )
    print(f"📡 Swing Worker started (PID {swg_proc.pid})")
    
    # Start Automated Cron Scheduler
    sched_env = os.environ.copy()
    sched_env["PYTHONPATH"] = backend_dir
    sched_proc = subprocess.Popen(
        [venv_python, "scheduler.py"],
        env=sched_env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=backend_dir
    )
    print(f"⏱️ Cron Scheduler started (PID {sched_proc.pid})")

if __name__ == "__main__":
    kill_python()
    run_db_cleanup()
    start_services()
    print("\n✨ System recovery complete. Check the console windows or the app logs.")
