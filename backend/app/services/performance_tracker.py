"""
[PERFORMANCE TRACKER] Post-Scan Auditing System
================================================
Captures the exact state of Top N recommendations at scan time,
then re-evaluates their end-of-day performance to audit scoring accuracy.

Phase 1: Data Gathering — no changes to core scoring logic.

Usage:
    # After scan completes (in swing_engine.run_scan):
    await performance_tracker.snapshot_scan_results(job_id, trade_plan)

    # At market close or on-demand:
    await performance_tracker.evaluate_eod_performance(scan_date)

    # View audit results:
    results = await performance_tracker.get_audit_report(scan_date)
"""

import logging
import asyncio
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.scan_snapshot import ScanSnapshot

logger = logging.getLogger("performance_tracker")

# How many top picks to track per scan
TOP_N = 10


class PerformanceTracker:
    """Invisible auditing layer that tracks recommendation accuracy."""

    async def snapshot_scan_results(self, job_id: str, trade_plan: List[Dict[str, Any]]) -> int:
        """
        Called immediately after a scan completes.
        Saves the top N recommendations with their full scoring breakdown.
        
        Returns: number of snapshots saved.
        """
        if not trade_plan:
            return 0

        today = date.today().isoformat()
        top_picks = trade_plan[:TOP_N]
        saved = 0

        try:
            async with AsyncSessionLocal() as session:
                for rank, pick in enumerate(top_picks, start=1):
                    snapshot = ScanSnapshot(
                        scan_date=today,
                        scan_job_id=job_id,
                        symbol=pick.get("symbol", ""),
                        name=pick.get("name", ""),
                        sector=pick.get("sector", ""),
                        rank=rank,
                        total_score=pick.get("score", 0),
                        signal=pick.get("signal", ""),
                        strategy=pick.get("strategy", ""),
                        setup_type=pick.get("setup_type", ""),
                        confidence=pick.get("confidence", ""),
                        ai_approved=pick.get("ai_approved"),
                        ai_confidence=pick.get("ai_confidence"),
                        entry_price=pick.get("price", 0),
                        stop_loss=pick.get("stop_loss"),
                        target=pick.get("target"),
                        vol_ratio=self._extract_vol_ratio(pick),
                        delivery_pct=pick.get("delivery_pct"),
                        reasons_json=pick.get("reasons", []),
                        is_tracked=False,
                    )
                    session.add(snapshot)
                    saved += 1

                await session.commit()
                print(f" [TRACKER] Saved {saved} scan snapshots for {today} (Job: {job_id[:8]}...)", flush=True)

        except Exception as e:
            logger.error(f"[TRACKER] Failed to save snapshots: {e}")
            import traceback
            traceback.print_exc()

        return saved

    async def evaluate_eod_performance(self, scan_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches current/closing prices for all tracked stocks from a given scan date,
        calculates performance metrics, and classifies each as WINNER/LOSER/TRAP.
        
        Call this at market close (~3:30 PM IST) or anytime after.
        """
        if scan_date is None:
            scan_date = date.today().isoformat()

        try:
            async with AsyncSessionLocal() as session:
                # Get all untracked snapshots for this date
                stmt = select(ScanSnapshot).where(
                    ScanSnapshot.scan_date == scan_date,
                    ScanSnapshot.is_tracked == False
                )
                result = await session.execute(stmt)
                snapshots = result.scalars().all()

                if not snapshots:
                    print(f" [TRACKER] No untracked snapshots for {scan_date}", flush=True)
                    return {"status": "NO_DATA", "date": scan_date}

                # Fetch live prices via Kite
                symbols = [s.symbol for s in snapshots]
                prices = await self._fetch_live_prices(symbols)

                if not prices:
                    print(f" [TRACKER] Could not fetch prices for {len(symbols)} symbols", flush=True)
                    return {"status": "PRICE_FETCH_FAILED", "date": scan_date}

                updated = 0
                for snap in snapshots:
                    price_data = prices.get(snap.symbol)
                    if not price_data:
                        continue

                    eod_price = price_data.get("price", 0)
                    if eod_price <= 0 or snap.entry_price <= 0:
                        continue

                    # Calculate performance
                    change_pct = ((eod_price - snap.entry_price) / snap.entry_price) * 100

                    snap.eod_price = eod_price
                    snap.eod_change_pct = round(change_pct, 2)
                    snap.is_tracked = True
                    snap.updated_at = datetime.utcnow()

                    # Classify performance
                    if change_pct >= 3.0:
                        snap.performance_tag = "WINNER"
                    elif change_pct >= 0:
                        snap.performance_tag = "NEUTRAL"
                    elif change_pct >= -2.0:
                        snap.performance_tag = "LOSER"
                    else:
                        snap.performance_tag = "TRAP"  # The ones we want to eliminate

                    updated += 1

                await session.commit()
                print(f" [TRACKER] Updated {updated}/{len(snapshots)} snapshots with EOD performance for {scan_date}", flush=True)

                # --- TRAP MEMORY: Auto-learn from any TRAP-classified stocks ---
                try:
                    from app.services.trap_memory import trap_memory
                    traps_learned = 0
                    for snap in snapshots:
                        if snap.performance_tag == "TRAP":
                            result_type = await trap_memory.learn_from_trap(snap)
                            if result_type:
                                traps_learned += 1
                    if traps_learned > 0:
                        print(f" [TRAP MEMORY] Learned {traps_learned} new trap pattern(s) from {scan_date}", flush=True)
                except Exception as e:
                    logger.debug(f"[TRAP MEMORY] Learning failed (non-critical): {e}")

                return {"status": "OK", "date": scan_date, "updated": updated}

        except Exception as e:
            logger.error(f"[TRACKER] EOD evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "ERROR", "error": str(e)}

    async def get_audit_report(self, scan_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns a full audit report for a given scan date.
        Includes per-stock performance, aggregate stats, and trap analysis.
        """
        if scan_date is None:
            scan_date = date.today().isoformat()

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ScanSnapshot).where(
                    ScanSnapshot.scan_date == scan_date
                ).order_by(ScanSnapshot.rank)
                result = await session.execute(stmt)
                snapshots = result.scalars().all()

                if not snapshots:
                    return {"status": "NO_DATA", "date": scan_date, "stocks": []}

                stocks = []
                winners = 0
                losers = 0
                traps = 0
                total_return = 0.0
                tracked_count = 0

                for snap in snapshots:
                    stock_data = {
                        "rank": snap.rank,
                        "symbol": snap.symbol,
                        "name": snap.name,
                        "sector": snap.sector,
                        "score": snap.total_score,
                        "signal": snap.signal,
                        "strategy": snap.strategy,
                        "setup_type": snap.setup_type,
                        "confidence": snap.confidence,
                        "ai_approved": snap.ai_approved,
                        "entry_price": snap.entry_price,
                        "stop_loss": snap.stop_loss,
                        "target": snap.target,
                        "vol_ratio": snap.vol_ratio,
                        "delivery_pct": snap.delivery_pct,
                        "eod_price": snap.eod_price,
                        "eod_change_pct": snap.eod_change_pct,
                        "performance_tag": snap.performance_tag,
                        "is_tracked": snap.is_tracked,
                        "reasons": snap.reasons_json or [],
                    }
                    stocks.append(stock_data)

                    if snap.is_tracked and snap.eod_change_pct is not None:
                        tracked_count += 1
                        total_return += snap.eod_change_pct
                        if snap.performance_tag == "WINNER":
                            winners += 1
                        elif snap.performance_tag == "LOSER":
                            losers += 1
                        elif snap.performance_tag == "TRAP":
                            traps += 1

                avg_return = round(total_return / max(tracked_count, 1), 2)

                return {
                    "status": "OK",
                    "date": scan_date,
                    "total_tracked": tracked_count,
                    "total_snapshots": len(snapshots),
                    "winners": winners,
                    "losers": losers,
                    "traps": traps,
                    "avg_return_pct": avg_return,
                    "accuracy_pct": round((winners / max(tracked_count, 1)) * 100, 1) if tracked_count > 0 else 0,
                    "stocks": stocks,
                }

        except Exception as e:
            logger.error(f"[TRACKER] Audit report failed: {e}")
            return {"status": "ERROR", "error": str(e)}

    async def get_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Returns summary stats for the last N days of scans."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ScanSnapshot.scan_date).distinct().order_by(
                    ScanSnapshot.scan_date.desc()
                ).limit(days)
                result = await session.execute(stmt)
                dates = [row[0] for row in result.all()]

            history = []
            for d in dates:
                report = await self.get_audit_report(d)
                if report.get("status") == "OK":
                    history.append({
                        "date": d,
                        "total_tracked": report["total_tracked"],
                        "winners": report["winners"],
                        "losers": report["losers"],
                        "traps": report["traps"],
                        "avg_return_pct": report["avg_return_pct"],
                        "accuracy_pct": report["accuracy_pct"],
                    })
            return history

        except Exception as e:
            logger.error(f"[TRACKER] History fetch failed: {e}")
            return []

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _extract_vol_ratio(self, pick: Dict[str, Any]) -> Optional[float]:
        """Extracts volume ratio from reasons array or direct field."""
        # Try direct field first
        for reason in pick.get("reasons", []):
            text = reason.get("text", "")
            if "Volume Quality" in text:
                # "Volume Quality (3.2x)" -> extract 3.2
                try:
                    import re
                    match = re.search(r'([\d.]+)x', text)
                    if match:
                        return float(match.group(1))
                except:
                    pass
        return None

    async def _fetch_live_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches current prices using Kite (primary) or market_data (fallback)."""
        try:
            from app.services.kite_data import kite_data
            if kite_data.is_ready:
                prices = await kite_data.get_ltp(symbols)
                if prices:
                    return prices
        except Exception as e:
            logger.debug(f"Kite LTP failed, falling back: {e}")

        # Fallback: use market_data service
        try:
            from app.services.market_data import market_service
            prices = await market_service.get_batch_prices(symbols)
            return prices or {}
        except Exception as e:
            logger.error(f"All price fetching failed: {e}")
            return {}


# Singleton
performance_tracker = PerformanceTracker()
