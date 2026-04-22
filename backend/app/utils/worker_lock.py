
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
        """
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    old_pid = int(f.read().strip())
                
                # Check if the process is actually running
                if self._is_pid_running(old_pid):
                    return False
            except (ValueError, OSError):
                # File corrupted or something else, treat as no lock
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
