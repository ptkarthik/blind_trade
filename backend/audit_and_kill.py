
import subprocess
import os
import signal

def audit_and_kill():
    print("--- SYSTEM PROCESS AUDIT ---")
    try:
        # Get all python processes with PIDs and CommandLines
        output = subprocess.check_output('wmic process where "name=\'python.exe\'" get commandline,processid', shell=True).decode()
        lines = output.strip().split('\n')[1:] # Skip header
        
        my_pid = os.getpid()
        killed_count = 0
        
        for line in lines:
            if not line.strip(): continue
            parts = line.rsplit(None, 1)
            if len(parts) < 2: continue
            cmd, pid_str = parts[0].strip(), parts[1].strip()
            try:
                pid = int(pid_str)
            except ValueError: continue
            
            if pid == my_pid: 
                print(f"KEEPING (SELF): PID {pid} | {cmd}")
                continue
            
            # Identify worker processes
            if "worker_main" in cmd or "uvicorn" in cmd or "app.main" in cmd:
                print(f"TERMINATING: PID {pid} | {cmd}")
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed_count += 1
                except:
                    print(f"FAILED to kill PID {pid}")
            else:
                print(f"SKIPPING: PID {pid} | {cmd}")
        
        print(f"--- AUDIT COMPLETE. KILLED {killed_count} PROCESSES ---")
    except Exception as e:
        print(f"Audit Error: {e}")

if __name__ == "__main__":
    audit_and_kill()
