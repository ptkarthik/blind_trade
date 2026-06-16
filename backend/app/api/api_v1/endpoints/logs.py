from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.deps import get_current_user
import subprocess
import os

router = APIRouter()

@router.get("/")
def get_logs(
    service: str = Query("worker", description="The PM2 service name (e.g. fastapi, worker)"),
    lines: int = Query(100, description="Number of lines to fetch"),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch live production logs from PM2 for a specific service.
    Requires admin privileges.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Not authorized to view system logs")

    # Only allow safe service names to prevent injection
    allowed_services = {"worker", "fastapi", "all"}
    if service not in allowed_services:
        raise HTTPException(status_code=400, detail="Invalid service name")

    try:
        # Check if pm2 is in path
        result = subprocess.run(
            ["pm2", "logs", service, "--lines", str(lines), "--nostream"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        if not output.strip():
            output = f"No logs found for service '{service}' or PM2 is not running."

        return {"status": "success", "service": service, "logs": output}

    except FileNotFoundError:
        # PM2 not installed (likely local Windows dev environment)
        return {
            "status": "warning",
            "service": service,
            "logs": "PM2 command not found. This is expected if you are running locally without PM2.\nTo view logs locally, check your IDE terminal or Uvicorn output."
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout while fetching logs from PM2")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")
