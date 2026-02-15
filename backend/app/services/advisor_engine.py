
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import numpy as np

class AdvisorEngine:
    """
    Investment Advisor Engine (Refactored for Strict Separation & Dynamic Horizons)
    Transforms raw metrics into professional, strategy-specific advisor outputs.
    """

    def generate_advice(self, sym: str, current_price: float, fund_data: Dict, ta_data: Dict, risk_data: Dict, sector_data: Dict, portfolio_context: Dict = None, mode: str = "longterm") -> Dict:
        """
        Main entry point. STRICTLY dispatches to the appropriate engine.
        NO shared logic bleeding between timeframes.
        """
        if not current_price or current_price <= 0: return {}

        # Flatten metrics
        metrics = fund_data.get("raw_metrics", fund_data)

        if mode == "intraday":
            return self._generate_intraday_advice(sym, current_price, ta_data, risk_data, sector_data)
        else:
            return self._generate_longterm_advice(sym, current_price, metrics, ta_data, risk_data, sector_data, portfolio_context)

    # =========================================================================
    # 🟢 LONG TERM STRATEGY ENGINE (Wealth Creation)
    # Focus: ROI, CAGR, Compounding, Weeks-to-Years
    # =========================================================================
    def _generate_longterm_advice(self, sym: str, price: float, metrics: Dict, ta: Dict, risk: Dict, sector: Dict, portfolio_context: Dict) -> Dict:
        
        # 1. Determine The Driver & Strategy (Dynamic Horizon Engine)
        # -----------------------------------------------------------
        driver, strategy, horizon_months = self._determine_longterm_driver(metrics, ta, risk, sector)
        
        # 2. Calculate ROI-Based Targets
        # -----------------------------------------------------------
        targets = self._calculate_longterm_targets(price, metrics, ta, driver, horizon_months)
        
        # 3. Smart Structural Stop Loss
        # -----------------------------------------------------------
        stop_loss = self._determine_longterm_stop(price, ta, risk)
        
        # 4. Scenario Analysis (Risk-Adjusted Expectancy)
        # -----------------------------------------------------------
        scenarios = self._generate_scenarios(price, targets["3_year_target"], metrics, risk)

        # 5. Smart Entry (Institutional Zones)
        # -----------------------------------------------------------
        entry_analysis = self._determine_smart_entry(price, ta, mode="longterm", driver=driver)

        # 6. Trend & Review Cycle
        # -----------------------------------------------------------
        trend_status = self._analyze_trend_slope(ta)
        review_cycle = "Weekly" if driver == "MOMENTUM" else "Quarterly"

        # 7. Construct The Verdict
        # -----------------------------------------------------------
        score = int(metrics.get("fundamental_score", 50))
        # Boost score for High Momentum if Driver is Momentum
        if driver == "MOMENTUM":
            score = max(score, int(ta.get("trend_score", 50)))

        return {
            "holding_period": {
                "years": round(horizon_months / 12, 1),
                "period_display": self._format_horizon(horizon_months),
                "label": f"{driver} Play",
                "play_type": strategy,
                "driver": driver
            },
            "entry_analysis": entry_analysis,
            "targets": targets,
            "stop_loss": stop_loss,
            "scenarios": scenarios,
            "trend_status": trend_status,
            "review_cycle": review_cycle,
            "confidence": f"{score}%",
            "fair_value": metrics.get("intrinsic_value", price),
            "strategy_tag": "[LONG TERM STEATEGY]"
        }

    def _determine_longterm_driver(self, metrics, ta, risk, sector):
        """
        Identifies the primary stock driver to tailor the horizon.
        """
        trend_score = ta.get("trend_score", 50)
        mom_score = ta.get("mom_score", 50)
        val_gap = metrics.get("valuation_gap", 0)
        beta = risk.get("beta", 1.0)
        
        # A. MOMENTUM DRIVER (The "Zomato" Case)
        # High Trend, High Beta, Breaking Out
        if trend_score > 75 and mom_score > 65 and beta > 0.9:
            return "MOMENTUM", "Aggressive Swing / Breakout", 4 # 4-6 Months
            
        # B. VALUE DRIVER (The "HDFC Bank" Case)
        # High Intrinsic Value, Price Beaten Down
        if val_gap > 25:
            return "VALUE", "Mean Reversion / Recovery", 18 # 1.5 Years
            
        # C. GROWTH DRIVER (The "Titan" Case)
        # Expensive but Compounding
        if metrics.get("rev_cagr", 0) > 0.15:
            return "GROWTH", "Structural Compounder", 48 # 4 Years
            
        # D. INCOME / DEFENSIVE
        if metrics.get("dividend_yield", 0) > 0.03:
             return "INCOME", "Dividend Yield Harvest", 36 # 3 Years
             
        # Default
        return "QUALITY", "Core Portfolio Hold", 36

    def _calculate_longterm_targets(self, price, metrics, ta, driver, horizon_months):
        """
        Calculates targets based on the DRIVER, not just generic formulas.
        """
        atr = ta.get("atr", price * 0.03)
        weekly_vol = atr * 2.2 # Approx weekly range
        years = max(0.5, horizon_months / 12)
        
        # 1. Technical Target (Aggressive)
        # Project volatility expansion
        if driver == "MOMENTUM":
            # Momentum moves often extend 15-25% in a swing
            tech_upside = (weekly_vol * 12) # 12 weeks of volatility
            tech_target = price + tech_upside
        else:
            # Standard trend extension
            tech_target = price * (1.12 ** years)

        # 2. Fundamental Target (Conservative)
        intrinsic = metrics.get("intrinsic_value", price)
        cagr = metrics.get("rev_cagr", 0.12) or 0.12
        fund_target = intrinsic * ((1 + cagr) ** years)
        if driver == "VALUE":
            fund_target = intrinsic # Expect convergence
            
        # 3. Blended Target based on Driver
        if driver == "MOMENTUM":
            target = (tech_target * 0.70) + (fund_target * 0.30)
            logic = "Volatility Expansion (Aggressive)"
        elif driver == "VALUE":
            target = (fund_target * 0.80) + (tech_target * 0.20)
            logic = "Fair Value Convergence"
        else:
            target = (fund_target * 0.50) + (tech_target * 0.50)
            logic = f"{int(cagr*100)}% Compounding Growth"
            
        # Safety Check: Target shouldn't be lower than price for a Buy recommendation
        if target < price * 1.05: target = price * 1.15
        
        # ROI Calculation
        abs_return = ((target - price) / price) * 100
        annualized_roi = ((target / price) ** (1/years) - 1) * 100
        
        return {
            "3_year_target": round(target, 2), # Keeping key name for UI compatibility
            "projected_cagr": round(annualized_roi, 1), # This is now ROI
            "absolute_return": round(abs_return, 1),
            "blend_logic": logic
        }

    def _determine_longterm_stop(self, price, ta, risk):
        """
        Structural stops for investments.
        """
        ema_200 = ta.get("ema_200_val", 0)
        atr = ta.get("atr", price * 0.03)
        
        # 1. Structural Floor
        if ema_200 > 0 and price > ema_200:
            stop = ema_200
            typ = "200 EMA (Structural)"
        else:
            # 2. Volatility Stop (2x Weekly ATR)
            stop = price - (atr * 3)
            typ = "Volatility Stop (3x ATR)"
            
        return {
            "stop_price": round(stop, 2),
            "type": typ,
            "risk_pct": round(((price - stop)/price)*100, 1)
        }

    # =========================================================================
    # 🟠 INTRADAY STRATEGY ENGINE (Income Generation)
    # Focus: Daily Pivots, VWAP, Liquidity, Hours
    # =========================================================================
    def _generate_intraday_advice(self, sym, price, ta, risk, sector):
        
        # 1. Identify Setup
        # -----------------
        vwap = ta.get("vwap_val", 0)
        pivot_r1 = ta.get("resistance", price * 1.02)
        pivot_s1 = ta.get("support", price * 0.98)
        
        setup = "Neutral"
        if vwap > 0 and price > vwap:
            setup = "Bullish Trend Day"
        elif vwap > 0 and price < vwap:
            setup = "Bearish Fade"
            
        # 2. Precision Targets (Scalping)
        # -----------------
        atr_daily = ta.get("atr", price * 0.02)
        scalp_target = price + (atr_daily * 0.5) # Quick 0.5 ATR move
        run_target = pivot_r1 # Stretch goal
        
        # 3. Tight Stop
        # -----------------
        stop = price - (atr_daily * 0.25) # Tight stop
        
        # 4. Entry
        # -----------------
        entry_analysis = self._determine_smart_entry(price, ta, mode="intraday", driver="SCALP")
        
        return {
            "holding_period": {
                "years": 0.003, # ~1 Day
                "period_display": "Intraday (Exit by 3:15 PM)",
                "label": "Day Trade",
                "play_type": "Scalp / Momentum",
                "driver": "Liquidity"
            },
            "entry_analysis": entry_analysis,
            "targets": {
                "3_year_target": round(run_target, 2), # UI maps this key
                "scalp_target": round(scalp_target, 2),
                "projected_cagr": 0, # N/A for intraday
                "absolute_return": round(((run_target-price)/price)*100, 1),
                "blend_logic": "Intraday Pivot / ATR Expansion"
            },
            "stop_loss": {
                "stop_price": round(stop, 2),
                "type": "Tight Volatility Stop",
                "risk_pct": round(((price - stop)/price)*100, 2)
            },
            "scenarios": [],
            "trend_status": {"slope": setup, "action": "Trade Levels"},
            "review_cycle": "Daily",
            "confidence": "High" if ta.get("mom_score", 0) > 60 else "Medium",
            "fair_value": vwap,
            "strategy_tag": "[INTRADAY STRATEGY]"
        }

    # =========================================================================
    # 🟡 SHARED UTILITIES (Smart Entry & Scenarios)
    # =========================================================================

    def _determine_smart_entry(self, price, ta, mode="longterm", driver="QUALITY"):
        """
        Calculates optimized entry points based on strategy.
        """
        vwap = ta.get("vwap_val", 0)
        ema_200 = ta.get("ema_200_val", 0)
        ema_50 = ta.get("ema_50_val", 0)
        supports = ta.get("levels", {}).get("support", [])
        
        entry = price
        typ = "Market"
        rationale = "Standard Entry"
        
        if mode == "intraday":
            if vwap > 0:
                entry = vwap
                typ = "Limit @ VWAP"
                rationale = "Institutional Liquidity Zone"
        
        elif mode == "longterm":
            if driver == "MOMENTUM":
                # Don't wait too long for momentum
                entry = price
                typ = "Market (Breakout)"
                rationale = "Momentum is active. Buy at Market to capture move."
            elif driver == "VALUE":
                # Hunt for deep support
                if supports:
                    s1 = supports[0]["price"]
                    entry = s1
                    typ = f"Limit @ Support ({supports[0]['label']})"
                    rationale = "Wait for deep value support test."
            else:
                 # Growth/Quality - Buy pullbacks
                 if ema_50 > 0:
                     entry = ema_50
                     typ = "Limit @ 50 EMA"
                     rationale = "Accumulate on structural trend pullback."

        # Safety: Ensure entry isn't wildly far from price (miss risk)
        if entry < price * 0.90 and driver != "VALUE":
             entry = price * 0.98 # Adjust to 2% discount
             typ = "Optimized Limit (-2%)"
             
        return {
            "entry_price": round(entry, 2),
            "entry_type": typ,
            "rationale": rationale,
            "confluence": 1
        }

    def _generate_scenarios(self, price, target, metrics, risk):
        """
        Simple 3-case scenario for UI.
        """
        upside = target
        downside_risk = risk.get("max_drawdown", 20) / 100
        downside = price * (1 - downside_risk)
        
        return [
            {"label": "Bull Case", "target": upside, "probability": "Optimistic"},
            {"label": "Base Case", "target": (upside+price)/2, "probability": "Likely"},
            {"label": "Bear Case", "target": downside, "probability": "Risk"}
        ]
    
    def _analyze_trend_slope(self, ta):
        score = ta.get("trend_score", 50)
        label = "Uptrend" if score > 60 else "Downtrend" if score < 40 else "Sideways"
        return {"slope": label, "action": "Hold" if score > 50 else "Watch"}

    def _format_horizon(self, months):
        if months < 12: return f"{months}-{months+2} Months"
        years = int(months/12)
        return f"{years}-{years+2} Years"

advisor_engine = AdvisorEngine()
