import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.notifier import notifier_service

logger = logging.getLogger("automated_scans")

class AutomatedScanService:
    async def trigger_scheduled_scan(self, job_type: str, phase_name: str):
        """
        Triggers a backend background job for the given engine type, waits for completion,
        and pushes the top 5 results to Telegram.
        """
        logger.info(f"[{phase_name}] Initiating scheduled automated scan ({job_type})...")
        
        # 1. Create the background job
        job_id = None
        try:
            async with AsyncSessionLocal() as session:
                new_job = Job(type=job_type, status="pending", trigger_source="auto", is_hidden=True)
                session.add(new_job)
                await session.commit()
                await session.refresh(new_job)
                job_id = new_job.id
        except Exception as e:
            logger.error(f"[{phase_name}] Failed to create job: {e}")
            await notifier_service.send_telegram_alert(f"⚠️ <b>{phase_name}</b>\nFailed to start automated scan. System Error.")
            return

        # Notify Start (Optional, but good for heartbeat)
        # await notifier_service.send_telegram_alert(f"⏳ <b>{phase_name}</b>\nScan initialized. Analyzing market...")

        # 2. Poll for completion (Timeout after 15 minutes)
        timeout_seconds = 15 * 60
        start_time = datetime.utcnow()
        completed = False
        final_job = None
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout_seconds:
            await asyncio.sleep(10) # Poll every 10 seconds
            try:
                async with AsyncSessionLocal() as session:
                    res = await session.execute(select(Job).where(Job.id == job_id))
                    job = res.scalars().first()
                    
                    if not job:
                        break
                        
                    if job.status in ["completed", "failed", "stopped"]:
                        completed = True
                        final_job = job
                        break
            except Exception as e:
                logger.error(f"[{phase_name}] Polling error: {e}")
        
        if not completed or not final_job:
            await notifier_service.send_telegram_alert(f"⚠️ <b>{phase_name}</b>\nScan timed out or disappeared.")
            return
            
        if final_job.status != "completed":
            await notifier_service.send_telegram_alert(f"⚠️ <b>{phase_name}</b>\nScan failed: {final_job.error_details}")
            return
            
        # 3. Parse Results and Send Telegram Push
        try:
            result_dict = final_job.result or {}
            stocks_data = result_dict.get("data", [])
            
            if not stocks_data:
                await notifier_service.send_telegram_alert(f"📡 <b>{phase_name}</b>\nScan complete. No high-conviction setups found matching current regime.")
                return
                
            # Sort by score descending and take top 5
            # Handle different score keys (e.g. 'score' for swing, 'score' for intraday)
            sorted_stocks = sorted(stocks_data, key=lambda x: float(x.get("score", 0)), reverse=True)
            top_stocks = sorted_stocks[:5]
            
            msg = f"🔥 <b>{phase_name} Complete</b>\n"
            msg += "--------------------------------------\n"
            
            for rank, stock in enumerate(top_stocks, 1):
                symbol = stock.get("symbol", "UNKNOWN")
                score = round(float(stock.get("score", 0)), 1)
                price = float(stock.get("price", stock.get("last_price", 0)))
                
                # Check for advisory warnings or setups
                setup = stock.get("setup_type", stock.get("strategy_name", ""))
                advisory = stock.get("strategic_summary", stock.get("advisory", ""))
                
                msg += f"<b>{rank}. {symbol}</b> (Score: {score})\n"
                msg += f"LTP: ₹{price:.2f} | Setup: {setup}\n"
                if advisory:
                    msg += f"<i>{advisory}</i>\n"
                msg += "\n"
                
            msg += "<i>Log in to dashboard for full scan details.</i>"
            
            await notifier_service.send_telegram_alert(msg)
            logger.info(f"[{phase_name}] Results pushed to Telegram successfully.")
            
        except Exception as e:
            logger.error(f"[{phase_name}] Failed to parse results: {e}")
            await notifier_service.send_telegram_alert(f"⚠️ <b>{phase_name}</b>\nScan completed but failed to parse results for Telegram.")

automated_scans_service = AutomatedScanService()
