import logging
import math
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class PortfolioEngine:
    """
    Portfolio Management Engine for Swing Trading.
    Manages capital allocation, risk per trade, and sector exposure.
    V1: Structural Foundation for Risk Control.
    """

    def __init__(self, capital: float = 100000.0):
        self.total_capital = capital
        self.risk_per_trade_pct = 1.0        # Risk 1% of total capital per trade
        self.max_concurrent_trades = 6       # Max 6 active swing positions
        self.max_capital_per_trade_pct = 20.0 # Max 20% of capital in a single stock
        self.max_sector_exposure_pct = 30.0   # Max 30% of capital in a single sector
        self.active_positions = []            # Track currently open trades {symbol, entry, quantity, sector, capital_used}

    def get_available_slots(self) -> int:
        """Returns the number of available trade slots."""
        current_count = len(self.active_positions)
        available = self.max_concurrent_trades - current_count
        return max(0, available)

    def calculate_risk_amount(self) -> float:
        """Calculates the absolute currency amount to risk per trade."""
        return self.total_capital * (self.risk_per_trade_pct / 100.0)

    def enforce_capital_limit(self, quantity: int, entry_price: float) -> int:
        """
        Ensures the total capital used for a trade does not exceed the per-trade limit.
        Returns the adjusted (possibly lower) quantity.
        """
        capital_used = quantity * entry_price
        max_capital = self.total_capital * (self.max_capital_per_trade_pct / 100.0)
        
        if capital_used > max_capital:
            logger.info(f"🛡️ Capital Limit Triggered: Capping allocation at {self.max_capital_per_trade_pct}% of portfolio.")
            return math.floor(max_capital / entry_price)
            
        return quantity

    def calculate_position_size(self, entry: float, stop_loss: float) -> Dict[str, Any]:
        """
        Calculates the quantity and capital allocation for a trade.
        Implements dual-cap logic: Risk-based sizing AND Capital-based sizing.
        """
        if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
            return {"quantity": 0, "capital_required": 0, "status": "Invalid Parameters"}

        # 1. Risk-Based Sizing (The "Hard" Risk)
        risk_per_trade = self.calculate_risk_amount()
        risk_per_share = abs(entry - stop_loss)
        qty_by_risk = math.floor(risk_per_trade / risk_per_share)

        # 2. Enforce Mandatory Capital Cap (Dual-Cap Logic)
        final_qty = self.enforce_capital_limit(qty_by_risk, entry)
        capital_required = final_qty * entry

        return {
            "quantity": final_qty,
            "capital_required": round(capital_required, 2),
            "risk_amount": round(final_qty * risk_per_share, 2),
            "exposure_pct": round((capital_required / self.total_capital) * 100, 2),
            "status": "Calculated" if final_qty > 0 else "Insufficient Capital/Risk"
        }

    def check_sector_exposure(self, trade: Dict[str, Any], active_positions: List[Dict[str, Any]]) -> bool:
        """
        Validates if adding this new trade breaches the sector exposure limit.
        """
        sector = trade.get("sector")
        if not sector: 
            return True # No sector info, allow but log
            
        proposed_capital = trade.get("capital_required", 0)
        
        # 1. Sum up capital currently deployed in the same sector
        current_sector_capital = sum(p.get("capital_required", 0) for p in active_positions if p.get("sector") == sector)
        
        # 2. Calculate Max Allowed
        max_sector_cap = self.total_capital * (self.max_sector_exposure_pct / 100.0)
        
        # 3. Decision
        if (current_sector_capital + proposed_capital) > max_sector_cap:
            logger.warning(f"🚫 Sector Risk: Allocation to {sector} already at limit. Skipping {trade.get('symbol')}.")
            return False
            
        return True

    def select_trades(self, scan_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters and ranks scan results to select the best trades for the portfolio.
        Automatically checks against internal active positions.
        """
        if not scan_results:
            return []

        # 1. Filter: Only HIGH/MEDIUM confidence + Gap Passed + Relative Strength OK
        filtered = [
            r for r in scan_results 
            if r.get("confidence") in ["HIGH", "MEDIUM"] 
            and r.get("gap_filter_passed", True) 
            and r.get("relative_strength") == "OUTPERFORM"
        ]

        # 2. Sort: By Score (Dynamic Priority Score) Descending
        # Note: 'score' in our engine is the strategy_priority_score (already weighted)
        sorted_results = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)

        # 3. Limit by Available Slots
        available_slots = self.get_available_slots()
        
        if available_slots <= 0:
            logger.info("⚠️ Portfolio is full. No new trades selected.")
            return []

        selected_trades = sorted_results[:available_slots]
        
        logger.info(f"✅ Selected {len(selected_trades)} best trades from {len(scan_results)} options.")
        return selected_trades

    def build_trade_plan(self, selected_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Converts selected signals into specialized, executable trade objects.
        Ensures the final plan respects all portfolio constraints.
        """
        if not selected_trades:
            return []

        final_plans = []
        # Create a copy to track 'simulated' capital/sector usage during the build
        temp_active_positions = list(self.active_positions)

        for trade in selected_trades:
            symbol = trade.get("symbol")
            entry = trade.get("entry", 0)
            sl = trade.get("stop_loss", 0)
            target = trade.get("target", 0)
            
            # 1. Final Risk Check & Position Sizing
            sizing = self.calculate_position_size(entry, sl)
            qty = sizing.get("quantity", 0)
            
            if qty <= 0:
                logger.warning(f"⏩ Skipping {symbol}: No valid quantity calculated.")
                continue

            # Add sizing info to trade for sector check
            trade["capital_required"] = sizing["capital_required"]

            # 2. Sector Exposure Check
            if not self.check_sector_exposure(trade, temp_active_positions):
                logger.warning(f"⏩ Skipping {symbol}: Sector limit reached.")
                continue

            # 3. Construct Final Trade Object without destroying rich UI card data
            plan = trade.copy()
            plan.update({
                "quantity": qty,
                "capital_required": sizing["capital_required"],
                "risk_amount": sizing["risk_amount"]
            })
            
            final_plans.append(plan)
            # Update temporary tracking to account for this new candidate
            temp_active_positions.append(plan)

        logger.info(f"📦 Trade Plan Built: {len(final_plans)} executable orders generated.")
        return final_plans

    def get_portfolio_summary(self, active_positions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Provides a high-level overview of portfolio risk and capital allocation.
        Uses internal active positions if none provided.
        """
        positions = active_positions if active_positions is not None else self.active_positions
        
        capital_deployed = sum(p.get("capital_required", 0) for p in positions)
        total_risk = sum(p.get("risk_amount", 0) for p in positions)
        
        return {
            "total_capital": self.total_capital,
            "capital_deployed": round(capital_deployed, 2),
            "available_capital": round(self.total_capital - capital_deployed, 2),
            "open_positions": len(positions),
            "available_slots": self.get_available_slots(),
            "risk_exposure": round(total_risk, 2),
            "utilization_pct": round((capital_deployed / self.total_capital) * 100, 2) if self.total_capital > 0 else 0
        }

    def update_active_positions(self, new_trade: Dict[str, Any]):
        """
        Appends a newly entered trade to the active portfolio tracking.
        """
        symbol = new_trade.get("symbol")
        if not any(p["symbol"] == symbol for p in self.active_positions):
            # Ensure we store minimal data for risk tracking
            pos = {
                "symbol": symbol,
                "capital_required": new_trade.get("capital_required", new_trade.get("entry", 0) * new_trade.get("quantity", 0)),
                "risk_amount": new_trade.get("risk_amount", abs(new_trade.get("entry", 0) - new_trade.get("stop_loss", 0)) * new_trade.get("quantity", 0)),
                "sector": new_trade.get("sector")
            }
            self.active_positions.append(pos)
            logger.info(f"📈 Portfolio Updated: Added position in {symbol}.")
        else:
            logger.warning(f"⚠️ Position in {symbol} already exists in portfolio.")

    def add_realized_pnl(self, realized_amount: float):
        """
        Dynamically updates the base capital from closed trades (compounding NAV).
        """
        old_capital = self.total_capital
        self.total_capital += realized_amount
        logger.info(f"🔄 Portfolio Engine NAV Update: PnL {round(realized_amount, 2)} applied. New Total Capital: {round(self.total_capital, 2)} (was {round(old_capital, 2)}).")

    def sync_active_positions(self, active_trades: List[Dict[str, Any]]):
        """
        Syncs internal tracking with the TradeManager's active list (usually on startup).
        """
        self.active_positions = []
        for trade in active_trades:
            self.update_active_positions(trade)
        logger.info(f"♻️ Portfolio Engine: Synced {len(self.active_positions)} positions from TradeManager.")

    def close_position(self, symbol: str):
        """
        Removes a position from tracking (called when trade hits SL/TP).
        """
        self.active_positions = [p for p in self.active_positions if p["symbol"] != symbol]
        logger.info(f"📉 Portfolio Updated: Closed position in {symbol}.")

portfolio_engine = PortfolioEngine()
