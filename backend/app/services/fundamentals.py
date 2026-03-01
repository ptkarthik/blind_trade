
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List

class FundamentalAnalysisEngine:
    """
    Analyzes company fundamentals using data from Yahoo Finance (via MarketDataService).
    Scoring Philosophy:
    - 0-10 Scale for each metric.
    - Robustness: Handle None/Null values gracefully (neutral score).
    """
    
    def analyze(self, info: Dict[str, Any], hist_financials: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Main entry point.
        """
        if not info:
             return {"score": 0, "rating": "Unknown", "details": [{"text": "Data Unavailable", "type": "neutral", "label": "DATA", "value": "Missing"}], "metrics": {}}

        # 1. Extract & Clean Data
        data = self._clean_data(info)
        
        # 2. Historical CAGR (Phase 29)
        cagr_metrics = self._calculate_cagr(hist_financials)
        if cagr_metrics:
            data.update(cagr_metrics)
        
        # 2. Calculate Sub-Scores (0-10)
        profit_score = self._score_profitability(data)
        valuation_score = self._score_valuation(data)
        health_score = self._score_health(data)
        growth_score = self._score_growth(data)
        fcf_score = self._calculate_fcf_score(data)
        piotroski_score = self._calculate_piotroski_score(data)
        
        # Phase 33: Strategic Moat Proxy
        moat_score = self._calculate_moat_score(hist_financials)
        data["moat_score"] = moat_score
        
        # 2.5 New Institutional Filters (Phase 32)
        earnings_res = self._score_earnings_quality(data, hist_financials)
        earnings_quality = earnings_res["score"]
        red_flags = earnings_res["red_flags"]
        
        val_bands = self._calculate_valuation_bands(data, hist_financials)
        # Update data with historical means if found
        if val_bands:
            data.update(val_bands)
        
        # 3. DCF Calculation (New - Phase 12)
        dcf_data = self._calculate_intrinsic_value(data)
        val_gap = dcf_data["gap_pct"]
        
        # Phase 33 Core Adjustments: Junk Filters (ROCE & Sales Growth)
        roce = data.get("roce")
        rev_growth = data.get("revenue_growth")
        rev_cagr = data.get("rev_cagr") if data.get("rev_cagr") is not None else rev_growth
        
        sector = data.get("sector", "Unknown")
        pb = data.get("pb")
        pb_mean = data.get("pb_mean", 2.5)
        
        # Cyclical Exemption: Metals/Energy etc. at cyclical bottoms (deep value)
        cyclical_sectors = ["Metal", "Energy", "Infrastructure", "Mining", "Commodities"]
        is_cyclical = any(s in sector for s in cyclical_sectors)
        cyclical_exemption = is_cyclical and pb is not None and (pb < 1.2 or pb < (pb_mean * 0.8))
        
        junk_flags = []
        if not cyclical_exemption:
            if roce is not None and roce < 0.12:
                junk_flags.append(f"Low Capital Efficiency (ROCE < 12%)")
            if rev_cagr is not None and rev_cagr <= 0:
                junk_flags.append("Stagnant/Negative Sales Growth")
            
        is_junk = len(junk_flags) > 0
        
        # 4. Weighted Aggregate
        # Re-weight: Growth(20), Profit(20), Value(15), Health(15), FCF(15), Piotroski(15)
        # Plus a bonus/penalty for DCF Gap
        final_score = (profit_score * 2.0) + (growth_score * 2.0) + (valuation_score * 1.5) + \
                      (health_score * 1.5) + (fcf_score * 1.5) + (piotroski_score * 1.5)
        
        # Add Moat Bonus (Max 5 points)
        final_score += (moat_score / 2)
        
        # DCF Bonus: If undervalued by > 20%, add up to 10 points
        if val_gap > 20: final_score += min(10, (val_gap - 20) / 2)
        elif val_gap < -20: final_score -= min(10, abs(val_gap + 20) / 2)
        
        # Apply Junk Penalty (Structural Invalidation)
        if is_junk:
            final_score = min(final_score, 40.0) # Cap score in HOLD territory to neutralize technical fakeouts
        
        # 5. Generate Insight
        details = self._generate_insights(data, profit_score, valuation_score, health_score, growth_score)
        
        # Add FCF/Piotroski/DCF insights
        if fcf_score >= 7: details.append({"text": "Positive Free Cash Flow (Cash Engine)", "type": "positive", "label": "CASH", "value": "Strong"})
        if piotroski_score >= 8: details.append({"text": "High Financial Quality (Piotroski)", "type": "positive", "label": "QUAL", "value": "Bulls Eye"})
        
        if dcf_data["label"] != "Unknown":
            details.append({
                "text": f"Intrinsic Valuation: {dcf_data['label']}", 
                "type": "positive" if val_gap > 0 else "negative",
                "label": "VAL",
                "value": f"{val_gap}% {'Undervalued' if val_gap > 0 else 'Premium'}"
            })

        # Phase 32: Earnings Quality Red-Flags
        if red_flags:
            for flag in red_flags:
                details.append({"text": flag, "type": "negative", "label": "QUALITY", "value": "Red Flag"})
                
        if is_junk:
            for flag in junk_flags:
                details.append({"text": flag, "type": "negative", "label": "JUNK FILTER", "value": "Failed"})

        rating = "HOLD"
        if final_score >= 80: rating = "STRONG BUY 💎"
        elif final_score >= 65: rating = "BUY ✅"
        elif final_score <= 30: rating = "SELL ❌"
        
        return {
            "score": round(final_score, 1),
            "rating": rating,
            "details": details,
            "intrinsic_value": dcf_data["value"],
            "valuation_gap": val_gap,
            "components": {
                "profitability": round(profit_score * 10, 1), 
                "valuation": round(valuation_score * 10, 1),
                "financial_health": round(health_score * 10, 1),
                "growth": round(growth_score * 10, 1),
                "quality": round(piotroski_score * 10, 1)
            },
            "raw_metrics": data 
        }

    def _clean_data(self, info: Dict) -> Dict:
        """Extracts relevant keys and handles None."""
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "sector_pe": 25.0, 
            "peg": info.get("pegRatio"),
            "pb": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "profit_margin": info.get("profitMargins"),
            "op_margin": info.get("operatingMargins"),
            "debt_to_equity": info.get("debtToEquity") if info.get("debtToEquity") is not None else self._calculate_de(info),
            "current_ratio": info.get("currentRatio"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "beta": info.get("beta"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector", "Unknown"),
            "operating_cashflow": info.get("operatingCashflow"),
            "free_cashflow": info.get("freeCashflow"),
            "net_income": info.get("netIncomeToCommon") or info.get("netIncome"),
            "promoter_holding": info.get("heldPercentInsiders", 0) * 100, # Convert to %
            "insider_buying": info.get("insiderPurchasePercent", 0),
            "roce": info.get("returnOnCapitalEmployed") or info.get("returnOnEquity") 
        }

    def _calculate_de(self, info: Dict) -> float:
        """Fallback to calculate D/E if API misses it (Common for Banks)"""
        try:
            total_debt = info.get("totalDebt")
            total_equity = info.get("totalStockholderEquity")
            if total_debt and total_equity and total_equity > 0:
                return round((total_debt / total_equity) * 100, 2)
            return None
        except: 
            return None

    def _score_profitability(self, d: Dict) -> float:
        """Score based on Margins and ROE."""
        score = 5.0 # Neutral start
        
        # Profit Margin
        pm = d["profit_margin"]
        if pm is not None:
            if pm > 0.20: score += 2 # >20% is excellent
            elif pm > 0.10: score += 1
            elif pm < 0.05: score -= 1
            elif pm < 0: score -= 3 # Loss making
            
        # ROE (Return on Equity)
        roe = d["roe"]
        if roe is not None:
            if roe > 0.20: score += 2
            elif roe > 0.15: score += 1
            elif roe < 0.05: score -= 1
            
        # Operating Margin (Core business)
        om = d["op_margin"]
        if om is not None:
            if om > 0.15: score += 1
            elif om < 0.05: score -= 1
            
        # Time-Consistency Bonus (Phase 33)
        # Check if ROE > 15% for 4 of last 5 years
        roe_history = d.get("roe_history", [])
        if len(roe_history) >= 4:
            consistent = sum(1 for r in roe_history if r > 0.15)
            if consistent >= 4:
                score += 1 # Consistent performer bonus
                
        return max(0, min(10, score))

    def _score_valuation(self, d: Dict) -> float:
        """
        Score based on P/E, PEG, P/B. (Phase 32: Historical Bands Integrated)
        """
        score = 5.0
        
        # 1. P/E Ratio (Relative to Sector)
        pe = d["pe"]
        sector_pe = d.get("sector_pe", 25.0)
        hist_pe_mean = d.get("hist_pe_mean")
        
        if pe is not None:
            # Sector Relative
            if pe < sector_pe * 0.7: score += 1 
            elif pe > sector_pe * 2.0: score -= 1
            
            # Phase 32: Historical Mean Reversion
            if hist_pe_mean:
                if pe < hist_pe_mean * 0.8: 
                    score += 2 # Undervalued vs its own history
                elif pe > hist_pe_mean * 1.5:
                    score -= 2 # Historically overextended
            
        # 2. PEG Ratio (The Growth Equalizer)
        peg = d["peg"]
        if peg is not None:
            if peg < 1.0: score += 2
            elif peg > 2.5: score -= 2
            
        # 3. P/B Ratio
        pb = d["pb"]
        hist_pb_mean = d.get("hist_pb_mean")
        if pb is not None:
            if pb < 1.0: score += 1
            if hist_pb_mean and pb < hist_pb_mean * 0.8:
                score += 1
            
        return max(0, min(10, score))


    def _calculate_fcf_score(self, d: Dict) -> float:
        """
        Score Free Cash Flow (FCF).
        FCF = Operating Cash Flow - CapEx.
        If we don't have CapEx, we use Operating Cash Flow as proxy.
        """
        score = 5.0
        ocf = d.get("operating_cashflow")
        
        if ocf is None: return 5.0 # Neutral if unknown
        
        # Logic: Positive FCF is King. Negative is valid for high growth, but risky.
        if ocf > 0:
            score += 2
            # Check FCF Yield if Market Cap is known
            mcap = d.get("market_cap")
            if mcap and mcap > 0:
                yield_ratio = ocf / mcap
                if yield_ratio > 0.05: score += 2 # >5% Yield is excellent value
                elif yield_ratio > 0.02: score += 1
        elif ocf < 0:
            score -= 2 # Cash burn is dangerous long term
            
        return max(0, min(10, score))

    def _calculate_intrinsic_value(self, d: Dict) -> Dict:
        """
        Implements a simple 2-Stage Discounted Cash Flow (DCF) model.
        Returns intrinsic value and comparison to current price.
        """
        fcf = d.get("free_cashflow") or d.get("operating_cashflow")
        growth = d.get("earnings_growth") or d.get("revenue_growth") or 0.10
        price = d.get("price", 0)
        
        if not fcf or fcf <= 0 or not price:
            return {"value": 0, "gap_pct": 0, "label": "Unknown"}

        # Cap growth at 20% for conservative estimate
        growth_rate = min(growth, 0.20)
        discount_rate = 0.12 # 12% WACC (Standard for India)
        terminal_growth = 0.04 # 4% Terminal Growth
        
        # 1. Project FCF for 5 years
        fcf_projections = []
        temp_fcf = fcf
        for i in range(1, 6):
            temp_fcf *= (1 + growth_rate)
            fcf_projections.append(temp_fcf / ((1 + discount_rate) ** i))
            
        # 2. Terminal Value
        terminal_fcf = temp_fcf * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        terminal_value_pv = terminal_value / ((1 + discount_rate) ** 5)
        
        # 3. Total Intrinsic Value (Enterprise Value proxy)
        # Divid by shares outstanding if available, else use MCAP ratio
        total_value = sum(fcf_projections) + terminal_value_pv
        mcap = d.get("market_cap")
        
        if not mcap: return {"value": 0, "gap_pct": 0, "label": "Unknown"}
        
        # Ratio of Intrinsic Market Cap to Current Market Cap
        ratio = total_value / mcap
        intrinsic_price = price * ratio
        gap_pct = ((intrinsic_price - price) / price) * 100
        
        label = "Fair Value"
        if gap_pct > 30: label = "Undervalued"
        elif gap_pct < -20: label = "Overvalued"
        
        return {
            "value": round(intrinsic_price, 2),
            "gap_pct": round(gap_pct, 1),
            "label": label
        }

    def _calculate_piotroski_score(self, d: Dict) -> int:
        """
        Calculates Simplified Piotroski F-Score (0-9).
        Since we only have 'current' info snapshot for now (no historical table passed here yet),
        we use robust proxies for the 'Change' metrics or default them.
        To do this properly, we need historical financials.
        
        For now, we implement the STATIC components (4/9) relative to sector norms.
        1. ROA > 0
        2. CFO > 0
        3. CFO > Net Income (Quality of Earnings)
        4. Long Term Debt/Assets Ratio (Low)
        """
        f_score = 0
        
        roa = d.get("roa")
        if roa and roa > 0: f_score += 1
        
        cfo = d.get("operating_cashflow")
        if cfo and cfo > 0: f_score += 1
        
        # Clean Net Income (Not always in info, implied from EPS * Shares or just assume)
        # Better: User Profit Margin * Revenue?
        # Let's skip complex comparative ones without full history dataframe.
        
        # Liquidity: Current Ratio > 1
        curr = d.get("current_ratio")
        if curr and curr > 1.0: f_score += 1
        
        # Leverage: Debt/Equity < 1 (Proxy for "Low Debt")
        de = d.get("debt_to_equity")
        if de and de < 100: f_score += 1 # < 1.0 ratio
        
        # Gross Margin (Proxy: Profit Margin > 0)
        pm = d.get("profit_margin")
        if pm and pm > 0: f_score += 1
        
        # Asset Turnover (Revenue / Assets? We don't have Assets easily in info).
        
        # Return scaled score (0-9 range but output matches 0-10 scale flow)
        # We scored 5 points max here. 5/5 = 10/10.
        return (f_score / 5) * 10


    def _calculate_cagr(self, df: pd.DataFrame) -> Dict:
        """
        Calculates 5-year CAGR for Revenue and Net Profit (Phase 29).
        """
        if df is None or df.empty: return {}
        
        try:
            results = {}
            # Yfinance index names vary, using common keys
            rev_keys = ['Total Revenue', 'TotalRevenue']
            prof_keys = ['Net Income', 'NetIncome', 'NetProfitAfterTaxes']
            
            # 1. Revenue CAGR
            revs = None
            for k in rev_keys:
                if k in df.index:
                    revs = df.loc[k].dropna()
                    break
            
            if revs is not None and len(revs) >= 2:
                final_val = revs.iloc[0] # YFinance returns [Current -> Hist]
                initial_val = revs.iloc[-1]
                n = len(revs) - 1
                if initial_val > 0 and final_val > 0:
                    results["rev_cagr"] = (final_val / initial_val)**(1/n) - 1
            
            # 2. Profit CAGR
            profs = None
            for k in prof_keys:
                if k in df.index:
                    profs = df.loc[k].dropna()
                    break
            
            if profs is not None and len(profs) >= 2:
                final_val = profs.iloc[0]
                initial_val = profs.iloc[-1]
                n = len(profs) - 1
                if initial_val > 0 and final_val > 0:
                    results["profit_cagr"] = (final_val / initial_val)**(1/n) - 1
            
            return results
        except: return {}

    def _score_health(self, d: Dict) -> float:
        """Score based on Debt and Liquidity."""
        score = 5.0
        
        # Debt to Equity (Provided as percentage often)
        de = d["debt_to_equity"]
        sector = d.get("sector", "Unknown")
        is_finance = sector in ["Banking", "Finance", "Financial Services"]

        if de is not None:
            if is_finance:
                if de < 600: score += 2 
                elif de < 850: score += 1
                elif de > 1000: score -= 2
            else:
                # Standard Companies (Professional criteria: < 0.5 is Good)
                if de < 50: score += 3 # Low Debt (<0.5) - Increased reward
                elif de < 100: score += 1
                elif de > 200: score -= 3
            
        cr = d["current_ratio"]
        if cr is not None:
            if cr > 1.5: score += 1
            elif cr < 1.0: score -= 2
            
        return max(0, min(10, score))

    def _score_growth(self, d: Dict) -> float:
        """Score based on Revenue and Earnings Growth (Favors CAGR in Phase 29)."""
        score = 5.0
        
        # Use CAGR if available, fallback to info.growth
        rev_growth = d.get("rev_cagr") if d.get("rev_cagr") is not None else d.get("revenue_growth")
        if rev_growth is not None:
            if rev_growth > 0.15: score += 3 # >15% CAGR is professional target
            elif rev_growth > 0.08: score += 1
            elif rev_growth < 0: score -= 3
            
        earn_growth = d.get("profit_cagr") if d.get("profit_cagr") is not None else d.get("earnings_growth")
        if earn_growth is not None:
            if earn_growth > 0.15: score += 2
            elif earn_growth > 0.05: score += 1
            elif earn_growth < 0: score -= 2
            
        return max(0, min(10, score))

    def _generate_insights(self, d, p_score, v_score, h_score, g_score) -> List[Dict[str, str]]:
        insights = []
        
        # Helper to safely format percentages or numbers
        import math
        def fmt_pct(val):
            if val is None or (isinstance(val, float) and math.isnan(val)): return "0.0%"
            return f"{round(val * 100, 1)}%"
            
        def fmt_num(val):
            if val is None or (isinstance(val, float) and math.isnan(val)): return "0.0"
            return f"{round(val, 1)}"

        # Positives (Strengths)
        if p_score >= 7: 
            insights.append({"text": "Strong Profitability", "type": "positive", "label": "PRO", "value": f"Margin: {fmt_pct(d['profit_margin'])}"})
        elif p_score <= 5:
            insights.append({"text": "Lackluster Profitability", "type": "negative", "label": "PRO", "value": f"Margin: {fmt_pct(d['profit_margin'])}"})
        
        if v_score >= 7: 
            insights.append({"text": "Attractive Valuation", "type": "positive", "label": "VAL", "value": f"P/E: {fmt_num(d['pe'])}"})
            
        if h_score >= 7: 
            de_val = d['debt_to_equity']
            insights.append({"text": "Robust Financial Health", "type": "positive", "label": "SAFE", "value": f"D/E: {fmt_num(de_val)}"})
            
        if g_score >= 7: 
            insights.append({"text": "High Growth Trajectory", "type": "positive", "label": "GROW", "value": f"Rev: {fmt_pct(d['revenue_growth'])}"})
        elif g_score <= 5:
            insights.append({"text": "Sluggish Growth Pattern", "type": "negative", "label": "GROW", "value": f"Rev: {fmt_pct(d['revenue_growth'])}"})
        
        # New Detailed Quality Indicators
        ocf = d.get("operating_cashflow")
        if ocf and ocf > 0:
            insights.append({"text": "Cash Flow Engine", "type": "positive", "label": "CASH", "value": "Positive FCF"})

        # Phase 32: Promoter & Insider Signals
        ph = d.get("promoter_holding")
        if ph and ph > 50:
            insights.append({"text": "Strong Promoter Skin-in-game", "type": "positive", "label": "MGMT", "value": f"{fmt_num(ph)}%"})
        
        ins = d.get("insider_buying")
        if ins and ins > 0:
             insights.append({"text": "Active Insider Buying Detected", "type": "positive", "label": "ALPHA", "value": "Bullish"})

        # Negatives (Weaknesses)
        if p_score <= 3: 
            insights.append({"text": "Weak Profitability", "type": "negative", "label": "RISK", "value": f"Margin: {fmt_pct(d['profit_margin'])}"})
            
        if v_score <= 3: 
            insights.append({"text": "Expensive Valuation", "type": "negative", "label": "EXP", "value": f"P/E: {fmt_num(d['pe'])}"})
            
        if h_score <= 3: 
            de_val = d['debt_to_equity']
            if de_val is not None and de_val > 200:
                insights.append({"text": "High Debt Levels", "type": "negative", "label": "DEBT", "value": f"D/E: {fmt_num(de_val)}"})
            else:
                insights.append({"text": "Weak Liquidity", "type": "negative", "label": "RISK", "value": f"Ratio: {fmt_num(d['current_ratio'])}"})
                
        if g_score <= 3: 
            insights.append({"text": "Stagnant Growth", "type": "negative", "label": "SLOW", "value": f"Rev: {fmt_pct(d['revenue_growth'])}"})
        
        return insights

    def _calculate_moat_score(self, hist_financials: pd.DataFrame) -> float:
        """
        Moat Proxy: High pricing power is signaled by Gross Margin Stability (Phase 33).
        """
        if hist_financials is None or hist_financials.empty: return 0.0
        
        try:
            # 1. Look for Gross Margin in financials
            # Yfinance financials often have 'Gross Profit' and 'Total Revenue'
            # Or some providers provide 'grossProfitMargin'
            # Let's hope for 'Gross Profit' & 'Total Revenue'
            idx = hist_financials.index
            gp_key = next((k for k in ['Gross Profit', 'GrossProfit'] if k in idx), None)
            rev_key = next((k for k in ['Total Revenue', 'TotalRevenue'] if k in idx), None)
            
            if gp_key and rev_key:
                margins = hist_financials.loc[gp_key] / hist_financials.loc[rev_key]
                std = margins.std()
                # Stability Score: Low std = High Score (Max 10)
                # If std is 0.02 (2% fluctuation), score is high.
                return max(0, min(10, 10 - (std * 100))) 
            
            # Fallback to a neutral 5 if we can't calculate but company exists
            return 5.0
        except:
            return 2.0

    def _score_earnings_quality(self, data: Dict, hist: pd.DataFrame) -> Dict:
        """
        Phase 32: Detects accounting illusions (OCF vs Net Income / Accruals).
        """
        red_flags = []
        ocf = data.get("operating_cashflow")
        ni = data.get("net_income") 
        
        if ocf and ni:
            if ocf < ni * 0.8:
                red_flags.append("Accrual Risk: OCF < 80% of Net Income (Potential aggressive accounting).")
            elif ocf < 0 and ni > 0:
                red_flags.append("Warning: Profitable on paper, but burning operational cash.")
        
        # Accrual Ratio (Total Assets - [Cash + Liab])? Too complex for info snapshot.
        # Simple Proxy: OCF / Net Income
        quality_score = 10
        if ocf and ni and ni > 0:
            ratio = ocf / ni
            if ratio < 0.5: quality_score -= 5
            elif ratio < 0.8: quality_score -= 2
            
        return {"red_flags": red_flags, "score": quality_score}

    def _calculate_valuation_bands(self, data: Dict, hist: pd.DataFrame) -> Dict:
        """
        Phase 32: Estimates Historical Mean P/E and P/B from price history (Approx).
        """
        if hist is None or hist.empty:
            return {"pe_mean": 25.0, "pb_mean": 3.0}
        
        try:
            # Estimate EPS from info (info.trailingEps)
            # If we had historical EPS, we could do proper PE bands.
            # Without historical financials with EPS, we use Sector Norms as mean.
            return {"pe_mean": 22.0, "pb_mean": 2.5}
        except:
            return {"pe_mean": 25.0, "pb_mean": 3.0}

fundamental_engine = FundamentalAnalysisEngine()
