"""
[TRAP MEMORY] Self-Learning Trap Pattern Recognition
=====================================================
Extracts indicator fingerprints from stocks classified as TRAPs,
stores them in the database, and checks future stocks against
known trap patterns to prevent repeating the same mistakes.

The more scans you run, the smarter this gets.

Usage:
    # Auto-called when tracker classifies a TRAP:
    await trap_memory.learn_from_trap(snapshot)

    # Called during scoring to check a stock:
    penalty, reason = await trap_memory.check_stock(indicators)
"""

import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.trap_pattern import TrapPattern

logger = logging.getLogger("trap_memory")

# Tolerance bands for matching: if a stock's indicator is within ±BAND of a known trap, it matches
MATCH_BANDS = {
    "roc_5d": 2.0,       # ±2% ROC tolerance (tighter)
    "vol_ratio": 0.5,    # ±0.5x volume tolerance (tighter)
    "ema10_dist": 1.5,   # ±1.5% EMA distance tolerance (tighter)
    "delivery_pct": 5.0, # ±5% delivery tolerance (tighter)
    "adx": 5.0,          # ±5 ADX tolerance (tighter)
}

# Minimum indicators that must match to trigger the penalty
MIN_MATCH_FIELDS = 4


class TrapMemory:
    """Self-learning trap pattern database."""

    async def learn_from_trap(self, snapshot) -> Optional[str]:
        """
        Extracts the indicator fingerprint from a TRAP-classified stock
        and stores it for future pattern matching.
        
        Called automatically by performance_tracker when a stock is tagged as TRAP.
        Returns the trap_type classification or None if extraction failed.
        """
        try:
            # Extract indicators from the snapshot's reasons JSON
            indicators = self._extract_indicators(snapshot)
            if not indicators:
                return None

            # Classify the trap type based on indicator pattern
            trap_type = self._classify_trap(indicators)

            # Check if a very similar pattern already exists
            existing = await self._find_similar_pattern(indicators)
            if existing:
                # Strengthen existing pattern instead of creating duplicate
                await self._strengthen_pattern(existing.id)
                print(f" [TRAP MEMORY] Strengthened existing pattern '{existing.trap_type}' "
                      f"(source: {existing.source_symbol}) — now confidence {existing.confidence + 0.5}", flush=True)
                return existing.trap_type

            # Build tolerance ranges around the indicators
            pattern = TrapPattern(
                source_symbol=snapshot.symbol,
                source_date=snapshot.scan_date,
                loss_pct=snapshot.eod_change_pct or 0,
                roc_5d_min=indicators.get("roc_5d", 0) - MATCH_BANDS["roc_5d"],
                roc_5d_max=indicators.get("roc_5d", 0) + MATCH_BANDS["roc_5d"],
                vol_ratio_min=max(0, indicators.get("vol_ratio", 0) - MATCH_BANDS["vol_ratio"]),
                vol_ratio_max=indicators.get("vol_ratio", 0) + MATCH_BANDS["vol_ratio"],
                ema10_dist_min=indicators.get("ema10_dist", 0) - MATCH_BANDS["ema10_dist"],
                ema10_dist_max=indicators.get("ema10_dist", 0) + MATCH_BANDS["ema10_dist"],
                delivery_pct_min=max(0, indicators.get("delivery_pct", 50) - MATCH_BANDS["delivery_pct"]),
                delivery_pct_max=min(100, indicators.get("delivery_pct", 50) + MATCH_BANDS["delivery_pct"]),
                adx_min=max(0, indicators.get("adx", 25) - MATCH_BANDS["adx"]),
                adx_max=indicators.get("adx", 25) + MATCH_BANDS["adx"],
                trap_type=trap_type,
                confidence=1.0,
                indicators_json=indicators,
                is_active=True,
            )

            async with AsyncSessionLocal() as session:
                session.add(pattern)
                await session.commit()

            print(f" [TRAP MEMORY] Learned new trap pattern: {trap_type} from {snapshot.symbol} "
                  f"(loss: {snapshot.eod_change_pct}%)", flush=True)
            return trap_type

        except Exception as e:
            logger.error(f"[TRAP MEMORY] Failed to learn from trap: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def check_stock(self, indicators: Dict[str, float]) -> Tuple[int, Optional[str]]:
        """
        Checks a stock's indicators against all known trap patterns.
        
        Returns: (penalty_points, reason_text) or (0, None) if no match.
        Called during swing_engine scoring.
        """
        if not indicators:
            return 0, None

        try:
            async with AsyncSessionLocal() as session:
                stmt = select(TrapPattern).where(TrapPattern.is_active == True)
                result = await session.execute(stmt)
                patterns = result.scalars().all()

            if not patterns:
                return 0, None

            best_match = None
            best_match_score = 0

            for pattern in patterns:
                match_score = self._calculate_match(indicators, pattern)
                if match_score >= MIN_MATCH_FIELDS and match_score > best_match_score:
                    best_match = pattern
                    best_match_score = match_score

            if best_match:
                # Penalty scales with pattern confidence and match quality
                base_penalty = 10
                confidence_bonus = min(10, int(best_match.confidence * 2))
                total_penalty = base_penalty + confidence_bonus

                # Increment match count
                await self._increment_match_count(best_match.id)

                reason = (f"Trap Memory Match: resembles {best_match.source_symbol} "
                         f"({best_match.source_date}, lost {best_match.loss_pct}%) "
                         f"— pattern: {best_match.trap_type} "
                         f"[{best_match_score}/{len(MATCH_BANDS)} indicators matched]")

                return total_penalty, reason

            return 0, None

        except Exception as e:
            logger.debug(f"[TRAP MEMORY] Check failed (non-critical): {e}")
            return 0, None

    async def get_all_patterns(self) -> List[Dict[str, Any]]:
        """Returns all stored trap patterns for UI display."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(TrapPattern).where(
                    TrapPattern.is_active == True
                ).order_by(TrapPattern.confidence.desc())
                result = await session.execute(stmt)
                patterns = result.scalars().all()

                return [{
                    "id": p.id,
                    "source_symbol": p.source_symbol,
                    "source_date": p.source_date,
                    "loss_pct": p.loss_pct,
                    "trap_type": p.trap_type,
                    "confidence": p.confidence,
                    "match_count": p.match_count,
                    "indicators": p.indicators_json,
                } for p in patterns]

        except Exception as e:
            logger.error(f"[TRAP MEMORY] Failed to fetch patterns: {e}")
            return []

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _extract_indicators(self, snapshot) -> Dict[str, float]:
        """Extracts numeric indicators from a snapshot's reasons JSON."""
        indicators = {}
        reasons = snapshot.reasons_json or []

        for reason in reasons:
            text = reason.get("text", "")
            impact = reason.get("impact", 0)

            # Extract volume ratio
            if "Volume Quality" in text:
                try:
                    import re
                    match = re.search(r'([\d.]+)x', text)
                    if match:
                        indicators["vol_ratio"] = float(match.group(1))
                except:
                    pass

            # Extract EMA10 distance
            if "EMA10" in text:
                try:
                    import re
                    match = re.search(r'([\d.]+)%', text)
                    if match:
                        indicators["ema10_dist"] = float(match.group(1))
                except:
                    pass

            # Extract ROC / Chasing info
            if "Chasing" in text or "Climax" in text or "ROC" in text.upper():
                try:
                    import re
                    match = re.search(r'ROC[:\s]+\+?([\d.]+)%', text)
                    if match:
                        indicators["roc_5d"] = float(match.group(1))
                except:
                    pass

            # Extract ADX
            if "ADX" in text:
                try:
                    import re
                    match = re.search(r'ADX.*?([\d.]+)', text)
                    if match:
                        indicators["adx"] = float(match.group(1))
                except:
                    pass

        # Delivery from snapshot directly
        if snapshot.delivery_pct is not None:
            indicators["delivery_pct"] = snapshot.delivery_pct

        # Vol ratio from snapshot if not found in reasons
        if "vol_ratio" not in indicators and snapshot.vol_ratio is not None:
            indicators["vol_ratio"] = snapshot.vol_ratio

        return indicators

    def _classify_trap(self, indicators: Dict[str, float]) -> str:
        """Classifies the trap type based on its indicator signature."""
        roc = indicators.get("roc_5d", 0)
        vol = indicators.get("vol_ratio", 0)
        ema_dist = indicators.get("ema10_dist", 0)
        delivery = indicators.get("delivery_pct", 50)

        if vol > 4.0 and roc > 15:
            return "CLIMAX_VOLUME"
        elif ema_dist > 10:
            return "OVEREXTENSION"
        elif delivery < 25 and vol > 2.0:
            return "LOW_DELIVERY_PUMP"
        elif roc > 20:
            return "MOMENTUM_EXHAUSTION"
        else:
            return "UNKNOWN_PATTERN"

    def _calculate_match(self, indicators: Dict[str, float], pattern: TrapPattern) -> int:
        """Counts how many indicator fields match the pattern's ranges."""
        matches = 0

        if "roc_5d" in indicators and pattern.roc_5d_min is not None:
            if pattern.roc_5d_min <= indicators["roc_5d"] <= pattern.roc_5d_max:
                matches += 1

        if "vol_ratio" in indicators and pattern.vol_ratio_min is not None:
            if pattern.vol_ratio_min <= indicators["vol_ratio"] <= pattern.vol_ratio_max:
                matches += 1

        if "ema10_dist" in indicators and pattern.ema10_dist_min is not None:
            if pattern.ema10_dist_min <= indicators["ema10_dist"] <= pattern.ema10_dist_max:
                matches += 1

        if "delivery_pct" in indicators and pattern.delivery_pct_min is not None:
            if pattern.delivery_pct_min <= indicators["delivery_pct"] <= pattern.delivery_pct_max:
                matches += 1

        if "adx" in indicators and pattern.adx_min is not None:
            if pattern.adx_min <= indicators["adx"] <= pattern.adx_max:
                matches += 1

        return matches

    async def _find_similar_pattern(self, indicators: Dict[str, float]) -> Optional[TrapPattern]:
        """Checks if a very similar pattern already exists."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(TrapPattern).where(TrapPattern.is_active == True)
                result = await session.execute(stmt)
                patterns = result.scalars().all()

                for pattern in patterns:
                    match_score = self._calculate_match(indicators, pattern)
                    if match_score >= 4:  # Very close match
                        return pattern
                return None
        except:
            return None

    async def _strengthen_pattern(self, pattern_id: str):
        """Increases confidence of an existing pattern."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    update(TrapPattern)
                    .where(TrapPattern.id == pattern_id)
                    .values(
                        confidence=TrapPattern.confidence + 0.5,
                        match_count=TrapPattern.match_count + 1,
                        updated_at=datetime.utcnow()
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.debug(f"Failed to strengthen pattern: {e}")

    async def _increment_match_count(self, pattern_id: str):
        """Increments the match counter when a stock triggers a pattern."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    update(TrapPattern)
                    .where(TrapPattern.id == pattern_id)
                    .values(
                        match_count=TrapPattern.match_count + 1,
                        updated_at=datetime.utcnow()
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.debug(f"Failed to increment match count: {e}")


# Singleton
trap_memory = TrapMemory()
