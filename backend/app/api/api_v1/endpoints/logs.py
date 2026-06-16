from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.deps import get_current_user
import os

router = APIRouter()

@router.get("")
def get_logs(
    service: str = Query("worker", description="The service name (e.g. fastapi, worker)"),
    lines: int = Query(100, description="Number of lines to fetch"),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch live production logs directly from the backend's internal rotating log files.
    This works universally across Local (Windows) and Production (Linux) without PM2.
    Requires admin privileges.
    """
    if getattr(current_user, 'is_admin', False) == False:
        raise HTTPException(status_code=403, detail="Not authorized to view system logs")

    allowed_services = {"worker": "worker_system.log", "fastapi": "fastapi_system.log"}
    if service not in allowed_services:
        raise HTTPException(status_code=400, detail="Invalid service name")

    log_file_path = os.path.join(os.getcwd(), "logs", allowed_services[service])

    try:
        if not os.path.exists(log_file_path):
            return {
                "status": "warning", 
                "service": service, 
                "logs": f"Log file not found at {log_file_path}.\nThe service may not have written any logs yet."
            }

        # Efficiently read the last N lines from the file
        with open(log_file_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            buffer = bytearray()
            pointer_location = f.tell()
            lines_found = 0
            
            while pointer_location >= 0 and lines_found <= lines:
                f.seek(pointer_location)
                pointer_location -= 1
                char = f.read(1)
                if char == b'\n':
                    lines_found += 1
                buffer.extend(char)
            
            output = buffer[::-1].decode('utf-8', errors='replace').strip()
            
            if not output:
                output = "Log file is empty."

            return {"status": "success", "service": service, "logs": output}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs from file: {str(e)}")
