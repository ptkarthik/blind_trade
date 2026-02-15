
import pandas as pd
from typing import Dict, Any, List
import numpy as np

class SectorPerformanceEngine:
    """
    Analyzes how a stock is performing relative to its specific sector index.
    Professional Creed: "Don't fight the sector trend."
    """

    def analyze(self, stock_df: pd.DataFrame, index_df: pd.DataFrame, sector_name: str) -> Dict[str, Any]:
        """
        Compares Stock returns vs Index returns over multiple timeframes.
        """
        if stock_df is None or stock_df.empty or index_df is None or index_df.empty:
            return {"score": 5.0, "details": [], "relative_strength": "Neutral"}

        try:
            # 1. Align Dates
            # ... simple alignment logic for now
            
            # 2. Calculate Returns (1Yr)
            stock_ret = self._calc_return(stock_df, "1y")
            index_ret = self._calc_return(index_df, "1y")
            
            # 3. Relative Alpha
            alpha = stock_ret - index_ret
            
            score = 5.0
            label = "Market Performer"
            details = []
            
            if alpha > 0.10: # Outperforming by 10%+
                score = 8.5
                label = "Outperformer"
                details.append({
                    "text": f"Sector Alpha: Strongest in {sector_name}", 
                    "type": "positive", 
                    "label": "SECT", 
                    "value": f"+{round(alpha*100, 1)}%"
                })
            elif alpha < -0.10: # Underperforming
                score = 2.5
                label = "Underperformer"
                details.append({
                    "text": f"Sector Lag: Weak vs {sector_name}", 
                    "type": "negative", 
                    "label": "SECT", 
                    "value": f"{round(alpha*100, 1)}%"
                })
            else:
                details.append({
                    "text": f"Sector Alignment: Tracking {sector_name}", 
                    "type": "positive", 
                    "label": "SECT", 
                    "value": "Neutral"
                })

            return {
                "score": score,
                "relative_strength": label,
                "alpha": alpha,
                "details": details
            }
        except Exception as e:
            return {"score": 5.0, "details": [], "relative_strength": "Error"}

    def _calc_return(self, df: pd.DataFrame, period: str) -> float:
        try:
            # Ensure price columns are clean
            df.columns = [c.lower() for c in df.columns]
            start_price = df['close'].iloc[0]
            end_price = df['close'].iloc[-1]
            return (end_price / start_price) - 1
        except:
            return 0.0

sector_engine = SectorPerformanceEngine()
