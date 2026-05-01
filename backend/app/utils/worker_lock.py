
import os
import sys

class WorkerLock:
    def __init__(self, worker_type):
        self.worker_type = worker_type
        self.lock_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(self.lock_dir):
            os.makedirs(self.lock_dir)
        self.lock_file = os.path.join(self.lock_dir, f"worker_{worker_type}.pid")

    def acquire(self):
        """
        Attempts to acquire a lock by writing the current PID to a file.
        Returns True if successful, False if another process is already running.
        [V30 FIX] Hardened against PID reuse race condition on Windows.
        """
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    content = f.read().strip()
                    if not content:
                        # Empty lock file = stale, force acquire
                        pass
                    else:
                        old_pid = int(content)
                        
                        # [V30] Skip check if the old PID is our OWN PID (restart scenario)
                        if old_pid == os.getpid():
                            pass
                        elif self._is_pid_running(old_pid) and self._is_python_process(old_pid):
                            # Only block if the old PID is BOTH alive AND a Python process
                            # This prevents false positives from Windows PID reuse where
                            # the new backend API inherits the old worker's PID
                            return False
            except (ValueError, OSError):
                # File corrupted or something else, treat as no lock
                pass
            
            # If we reach here, the old lock is stale — remove it
            try:
                os.remove(self.lock_file)
            except OSError:
                pass

        # Acquire lock
        with open(self.lock_file, "w") as f:
            f.write(str(os.getpid()))
        return True

    def release(self):
        """Releases the lock by removing the PID file."""
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except OSError:
                pass

    def _is_pid_running(self, pid):
        """Checks if a PID is currently active on the system."""
        if pid <= 0: return False
        if sys.platform == "win32":
            # Windows implementation
            try:
                import ctypes
                PROCESS_QUERY_INFORMATION = 0x0400
                # OpenProcess returns 0 on failure
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                if handle == 0:
                    error = ctypes.windll.kernel32.GetLastError()
                    # ERROR_INVALID_PARAMETER (87) means the PID does not exist
                    if error == 87:
                        return False
                    # Other errors (like ERROR_ACCESS_DENIED) mean it might be running
                    return True
                
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            except:
                return True # Fallback to assume running if check fails
        else:
            # Unix implementation
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def _is_python_process(self, pid):
        """[V30] Verify the process at this PID is actually a Python process.
        Prevents false-positive lock blocking from PID reuse by other programs."""
        if pid <= 0: return False
        if sys.platform == "win32":
            try:
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                    capture_output=True, text=True, timeout=3
                )
                output = result.stdout.lower()
                return 'python' in output
            except Exception:
                # If we can't verify, assume it IS python (safe fallback)
                return True
        else:
            try:
                with open(f'/proc/{pid}/cmdline', 'r') as f:
                    cmdline = f.read().lower()
                    return 'python' in cmdline
            except Exception:
                return True
