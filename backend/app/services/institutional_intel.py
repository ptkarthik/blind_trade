
import pandas as pd
import numpy as np

class InstitutionalIntel:
    """
    Advanced Institutional Intelligence Service.
    Calculates "Paid App" metrics:
    1. RS Rating (0-99)
    2. VCP Pattern (Minervini)
    3. Institutional Accumulation/Distribution
    """

    def analyze(self, df: pd.DataFrame, market_df: pd.DataFrame = None) -> dict:
        """
        Main entry point for Institutional Analysis.
        """
        if df.empty or len(df) < 50: return {}
        
        # 1. Institutional Sponsorship (Accumulation/Distribution)
        sponsorship = self._analyze_sponsorship(df)
        
        # 2. Volatility Contraction Pattern (VCP)
        vcp = self._detect_vcp(df)
        
        # 3. RS Rating (Simulated for now, real implementation needs market-wide rank)
        # We will use a proxy based on Alpha and Slope
        rs_rating = self._calculate_rs_proxy(df)
        
        return {
            "rs_rating": rs_rating,
            "vcp_detected": vcp["detected"],
            "vcp_details": vcp["details"],
            "institutional_action": sponsorship["action"],
            "accumulation_score": sponsorship["score"], # 0-100
            "pivot_cheat": vcp["pivot_cheat"]
        }

    def _analyze_sponsorship(self, df: pd.DataFrame) -> dict:
        """
        Detects "Big Money" footprints.
        Logic:
        - Up Days on High Vol (> 1.25x avg) = Accumulation (+2)
        - Down Days on High Vol (> 1.25x avg) = Distribution (-2)
        - Up Days on Low Vol = Weak Buying (-1)
        """
        recent = df.tail(20).copy() # Last month
        avg_vol = recent['volume'].mean()
        
        score = 50 # Start neutral
        
        for i, row in recent.iterrows():
            change = row['close'] - row['open']
            is_up = change > 0
            is_high_vol = row['volume'] > (avg_vol * 1.25)
            
            if is_up and is_high_vol:
                score += 3 # Big Money Buy
            elif not is_up and is_high_vol:
                score -= 3 # Big Money Sell
            elif is_up and not is_high_vol:
                score -= 0.5 # Weak Rally (Retail?)
            elif not is_up and not is_high_vol:
                score += 0.5 # Dry Up (Good if consolidating)
                
        score = max(0, min(100, score))
        
        action = "Neutral"
        if score > 70: action = "Accumulation 🟢"
        elif score < 30: action = "Distribution 🔴"
        
        return {"action": action, "score": score}

    def _detect_vcp(self, df: pd.DataFrame) -> dict:
        """
        Detects Volatility Contraction Pattern (Minervini).
        Logic: Lower Highs + Lower Volatility in recent candles.
        """
        details = []
        recent = df.tail(15) 
        
        # 1. Volatility Dry Up
        vol_drying = recent['volume'].iloc[-1] < recent['volume'].mean() * 0.7
        price_tight = (recent['high'].max() - recent['low'].min()) / recent['low'].min() < 0.08 # <8% range in 15 days
        
        is_vcp = False
        pivot = 0
        
        if vol_drying and price_tight:
            is_vcp = True
            details.append("Volume Dry-up + Price Tightness (<8%)")
            pivot = recent['high'].max()
            
        return {
            "detected": is_vcp,
            "details": details,
            "pivot_cheat": pivot
        }

    def _calculate_rs_proxy(self, df: pd.DataFrame) -> int:
        """
        Simulates MarketSmith RS Rating (0-99).
        In a full system, we'd rank ALL stocks. Here we approximate using Slope + ROC.
        """
        # Weighted RS: 40% 3m, 20% 6m, 20% 9m, 20% 12m
        # Since we might not have 1y data always, we use a simpler proxy:
        # RS ~ (Price / EMA 200) * RSI * Slope
        
        try:
            close = df['close'].iloc[-1]
            ema_200 = df['close'].ewm(span=200).mean().iloc[-1]
            
            # 1. Trend Comp (0-50)
            trend_ratio = (close / ema_200)
            trend_score = min(50, (trend_ratio - 1) * 100) # +20% vs EMA = 20 pts
            if trend_score < 0: trend_score = 0
            
            # 2. RSI Comp (0-50)
            # RSI is already a relative strength metric of sorts
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs)).iloc[-1]
            rsi_score = rsi / 2 # Max 50 pts
            
            total = int(trend_score + rsi_score)
            return max(1, min(99, total))
        except:
            return 50

institutional_intel = InstitutionalIntel()
