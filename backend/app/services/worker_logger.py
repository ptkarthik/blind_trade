import os
import time
from datetime import datetime
import paramiko
from app.core.config import settings
import io
import logging
from logging.handlers import RotatingFileHandler

# --- SYSTEM-WIDE WORKER LOGGER (Rotation Implementation) ---
# Create logs directory if missing
_log_dir = os.path.join(os.getcwd(), "logs")
if not os.path.exists(_log_dir):
    os.makedirs(_log_dir)

_log_file = os.path.join(_log_dir, "worker_system.log")

# Setup Rotating Logger (Global instance for the process)
system_logger = logging.getLogger("worker_system")
system_logger.setLevel(logging.INFO)

if not system_logger.handlers:
    # [V14.1 HARDENED] Increase limit to 512MB to prevent rotation crashes on Windows during large scans.
    # Added delay=True to mitigate file handle contention.
    handler = RotatingFileHandler(_log_file, maxBytes=512*1024*1024, backupCount=10, encoding='utf-8', delay=True)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%H:%M:%S')
    handler.setFormatter(formatter)
    system_logger.addHandler(handler)

class WorkerLogger:
    def __init__(self, job_id, worker_id, worker_type):
        self.job_id = job_id
        self.worker_id = worker_id
        self.worker_type = worker_type
        self.logs = []
        self.start_time = datetime.now()
        
        # Initial Log Entry
        self.info(f"Worker Logger Initialized for Job {job_id}")
        self.info(f"Worker ID: {worker_id}, Type: {worker_type}")

    def info(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [INFO] {msg}"
        self.logs.append(log_line)
        
        # 1. System Rotation Log
        system_logger.info(f"[{self.worker_type.upper()}] [ID-{self.worker_id}] {msg}")

        # 2. Stdout for real-time visibility
        try:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}] {msg}", flush=True)
        except UnicodeEncodeError:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}] {msg.encode('ascii', 'ignore').decode('ascii')}", flush=True)

    def warning(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [WARNING] {msg}"
        self.logs.append(log_line)

        # 1. System Rotation Log
        system_logger.warning(f"[{self.worker_type.upper()}] [ID-{self.worker_id}] {msg}")

        # 2. Stdout
        try:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}] ️ {msg}", flush=True)
        except UnicodeEncodeError:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}] WARN: {msg.encode('ascii', 'ignore').decode('ascii')}", flush=True)

    def error(self, msg):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [ERROR] {msg}"
        self.logs.append(log_line)

        # 1. System Rotation Log
        system_logger.error(f"[{self.worker_type.upper()}] [ID-{self.worker_id}] {msg}")

        # 2. Stdout
        try:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}]  {msg}", flush=True)
        except UnicodeEncodeError:
            print(f"[{timestamp}] [{self.worker_type.upper()}] [ID-{self.worker_id}] ERR: {msg.encode('ascii', 'ignore').decode('ascii')}", flush=True)

    def get_full_log(self):
        header = f"=== Worker Log: Job {self.job_id} ===\n"
        header += f"Start Time: {self.start_time}\n"
        header += f"Worker: {self.worker_type} (ID: {self.worker_id})\n"
        header += "="*40 + "\n"
        return header + "\n".join(self.logs) + "\n"

    def save_local_log(self):
        """
        Saves the log to a local .txt file for redundancy and secondary analysis.
        """
        try:
            log_dir = os.path.join(os.getcwd(), "logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            filename = f"job_{self.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            local_path = os.path.join(log_dir, filename)
            
            log_content = self.get_full_log()
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(log_content)
            
            self.info(f" Local log saved: {local_path}")
            return local_path
        except Exception as e:
            self.error(f"Failed to save local log: {str(e)}")
            return None

    async def upload_to_sftp(self):
        """
        Uploads the collected logs to the configured SFTP server.
        Also triggers local log save as a secondary backup.
        """
        # Always try to save local backup first
        self.save_local_log()

        if not settings.SFTP_HOST or not settings.SFTP_USER:
            self.info("SFTP not configured. Skipping upload (Local backup only).")
            return

        filename = f"job_{self.job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        remote_path = os.path.join(settings.SFTP_REMOTE_PATH, filename).replace("\\", "/")
        
        log_content = self.get_full_log()
        
        try:
            self.info(f"Connecting to SFTP {settings.SFTP_HOST}...")
            
            # Use Paramiko for SFTP
            transport = paramiko.Transport((settings.SFTP_HOST, settings.SFTP_PORT))
            transport.connect(username=settings.SFTP_USER, password=settings.SFTP_PASSWORD)
            
            sftp = paramiko.SFTPClient.from_transport(transport)
            
            # Ensure remote directory exists (simple check)
            try:
                sftp.mkdir(settings.SFTP_REMOTE_PATH)
            except IOError:
                pass # Already exists or no permission
            
            # Upload from memory buffer
            with sftp.file(remote_path, 'w') as f:
                f.write(log_content)
            
            sftp.close()
            transport.close()
            
            self.info(f" Log uploaded to SFTP: {remote_path}")
            
        except Exception as e:
            self.error(f"Failed to upload log to SFTP: {str(e)}")

# Singleton-like factory or just create fresh per job
def get_worker_logger(job_id, worker_id, worker_type):
    return WorkerLogger(job_id, worker_id, worker_type)
