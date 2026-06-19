import os
import time
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

import asyncio
from app.services.alert_monitor import alert_monitor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8012/api/v1/jobs/scan"

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

def trigger_market_summary():
    """Trigger the half-hourly market summary notification."""
    logger.info("🕒 Scheduled Event: Triggering Market Summary...")
    try:
        asyncio.run(alert_monitor.run_periodic_summary())
    except Exception as e:
        logger.error(f"❌ Error triggering Market Summary: {e}")

def trigger_position_radar():
    """Trigger the Position Manager to evaluate active trades."""
    logger.info("🕒 Scheduled Event: Triggering Position Radar...")
    try:
        response = requests.post("http://localhost:8012/api/v1/positions/evaluate_now", timeout=60)
        if response.status_code in [200, 201]:
            logger.info("✅ Position Radar evaluation complete.")
        else:
            logger.error(f"❌ Failed to trigger Position Radar: {response.text}")
    except Exception as e:
        logger.error(f"❌ Connection Error triggering Position Radar: {e}")

if __name__ == "__main__":
    logger.info("🚀 Blind Trade Automated Scheduler Starting...")
    logger.info("Market Hours (IST): Mon-Fri")
    logger.info("- 09:20 AM: Early Bird 'Gap & Go' Intraday Scan")
    logger.info("- 09:45 AM: Morning ORB Intraday Scan")
    logger.info("- 10:30 AM: Bullish Pullback Intraday Scan")
    logger.info("- 01:15 PM: Midday Trend Intraday Scan")
    logger.info("- 03:15 PM: Pre-close Swing Scan")

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # 1. Early Bird Scan (9:20 AM)
    scheduler.add_job(
        trigger_intraday_scan, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=20),
        id='early_bird_scan',
        name='Early Bird Intraday Scan'
    )

    # 2. Morning ORB Scan (9:45 AM)
    scheduler.add_job(
        trigger_intraday_scan, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=45),
        id='orb_scan',
        name='Morning ORB Intraday Scan'
    )

    # 3. Pullback Setup Scan (10:30 AM)
    scheduler.add_job(
        trigger_intraday_scan, 
        CronTrigger(day_of_week='mon-fri', hour=10, minute=30),
        id='pullback_scan',
        name='Bullish Pullback Intraday Scan'
    )

    # 4. Midday Trend Continuation Scan (1:15 PM)
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

    # 4. Half-Hourly Market Summary (9:15 AM to 3:30 PM)
    # Cron: Every 30 minutes between 9 and 15 hours. We can refine to exact market hours if needed.
    scheduler.add_job(
        trigger_market_summary,
        CronTrigger(day_of_week='mon-fri', hour='9-15', minute='0,30'),
        id='market_summary',
        name='Half-Hourly Market Summary'
    )
    
    # 5. Position Radar Guardian (Every 30 mins)
    scheduler.add_job(
        trigger_position_radar,
        CronTrigger(day_of_week='mon-fri', hour='9-15', minute='15,45'),
        id='position_radar',
        name='Half-Hourly Position Guardian Radar'
    )

    try:
         scheduler.start()
    except (KeyboardInterrupt, SystemExit):
         logger.info("🛑 Scheduler Stopped.")
