import os
import time
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8010/api/v1/jobs/scan"

def trigger_intraday_scan():
    """Trigger the Intraday Scan for Morning ORB and Midday Trend."""
    logger.info("🕒 Scheduled Event: Triggering Intraday Scan...")
    try:
        response = requests.post(API_URL, json={"type": "intraday"}, timeout=10)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Intraday Scan started successfully: {response.json()}")
        else:
            logger.error(f"❌ Failed to start Intraday Scan: {response.text}")
    except Exception as e:
        logger.error(f"❌ Connection Error triggering Intraday Scan: {e}")

def trigger_swing_scan():
    """Trigger the Swing Scan right before market close."""
    logger.info("🕒 Scheduled Event: Triggering Swing Scan...")
    try:
        response = requests.post(API_URL, json={"type": "swing_scan"}, timeout=10)
        if response.status_code in [200, 201]:
            logger.info(f"✅ Swing Scan started successfully: {response.json()}")
        else:
            logger.error(f"❌ Failed to start Swing Scan: {response.text}")
    except Exception as e:
        logger.error(f"❌ Connection Error triggering Swing Scan: {e}")

if __name__ == "__main__":
    logger.info("🚀 Blind Trade Automated Scheduler Starting...")
    logger.info("Market Hours (IST): Mon-Fri")
    logger.info("- 09:45 AM: Morning ORB Intraday Scan")
    logger.info("- 01:15 PM: Midday Trend Intraday Scan")
    logger.info("- 03:15 PM: Pre-close Swing Scan")

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # 1. Morning ORB Scan (9:45 AM)
    scheduler.add_job(
        trigger_intraday_scan, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=45),
        id='orb_scan',
        name='Morning ORB Intraday Scan'
    )

    # 2. Midday Trend Continuation Scan (1:15 PM)
    scheduler.add_job(
        trigger_intraday_scan, 
        CronTrigger(day_of_week='mon-fri', hour=13, minute=15),
        id='midday_scan',
        name='Midday Trend Intraday Scan'
    )

    # 3. Pre-close Swing Setup Scan (3:15 PM)
    scheduler.add_job(
        trigger_swing_scan, 
        CronTrigger(day_of_week='mon-fri', hour=15, minute=15),
        id='swing_scan',
        name='Pre-close Swing Scan'
    )

    try:
         scheduler.start()
    except (KeyboardInterrupt, SystemExit):
         logger.info("🛑 Scheduler Stopped.")
