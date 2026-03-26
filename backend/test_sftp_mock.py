import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.worker_logger import WorkerLogger
from app.core.config import settings

async def test_worker_logger_sftp_mock():
    print("--- Testing WorkerLogger SFTP Mock ---")
    
    # 1. Setup Mock Settings
    settings.SFTP_HOST = "mock.sftp.com"
    settings.SFTP_USER = "testuser"
    settings.SFTP_PASSWORD = "testpassword"
    settings.SFTP_REMOTE_PATH = "/mock_logs"
    
    # 2. Initialize Logger
    logger = WorkerLogger(job_id="test_job_123", worker_id="W-999", worker_type="intraday")
    logger.info("Starting mock scan...")
    logger.info("Analyzing symbol: RELIANCE.NS")
    logger.error("Something went wrong with analysis.")
    logger.info("Scan finished.")
    
    # 3. Patch Paramiko to avoid real network calls
    with patch('paramiko.Transport') as mock_transport, \
         patch('paramiko.SFTPClient.from_transport') as mock_sftp_client:
        
        # Setup mock behavior
        instance_transport = mock_transport.return_value
        instance_sftp = mock_sftp_client.return_value
        
        # Call upload
        await logger.upload_to_sftp()
        
        # 4. Verify calls
        mock_transport.assert_called_once_with(("mock.sftp.com", 22))
        instance_transport.connect.assert_called_once_with(username="testuser", password="testpassword")
        mock_sftp_client.assert_called_once_with(instance_transport)
        
        # Check if mkdir was called for the remote path
        instance_sftp.mkdir.assert_called_once_with("/mock_logs")
        
        # Check if file was opened for writing
        instance_sftp.file.assert_called()
        
        print("✅ WorkerLogger SFTP Upload Mock Verified.")

if __name__ == "__main__":
    asyncio.run(test_worker_logger_sftp_mock())
