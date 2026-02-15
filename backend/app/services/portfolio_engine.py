
import pandas as pd
import numpy as np
from typing import Dict, Any, List

class PortfolioEngine:
    """
    Analyzes a collection of stocks to ensure professional diversification.
    "Concentration builds wealth, but diversification preserves it."
    """

    def analyze_portfolio(self, stocks_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Inputs: List of results from ScannerEngine.analyze_stock
        """
        if not stocks_data:
            return {"score": 0, "details": [], "correlation_matrix": {}}

        # 1. Diversification Score (Sector Spread)
        sectors = [s.get("sector", "Other") for s in stocks_data]
        sector_counts = pd.Series(sectors).value_counts()
        
        # Max concentration check
        max_sector_pct = sector_counts.max() / len(stocks_data)
        div_score = 100 * (1 - (max_sector_pct - (1/len(sector_counts)))) if len(sector_counts) > 1 else 30
        
        details = []
        if max_sector_pct > 0.4:
            details.append({
                "text": "High Sector Concentration", 
                "type": "negative", 
                "label": "RISK", 
                "value": f"{round(max_sector_pct * 100, 1)}% in {sector_counts.idxmax()}"
            })
        else:
            details.append({
                "text": "Excellent Sector Diversification", 
                "type": "positive", 
                "label": "SAFE", 
                "value": f"{len(sector_counts)} Sectors"
            })

        # 2. Risk Allocation Suggestions
        # Weighted by Final Score and Inverse Beta
        allocations = {}
        total_conviction = sum(s.get("score", 50) for s in stocks_data)
        
        for s in stocks_data:
            sym = s.get("symbol")
            score = s.get("score", 50)
            beta = s.get("alpha_intel", {}).get("risk_level", "Medium")
            
            # Simple weight based on conviction
            weight = (score / total_conviction) * 100
            
            # Cap weight at 25% for safety
            final_weight = min(25.0, weight)
            allocations[sym] = f"{round(final_weight, 1)}%"

        return {
            "diversification_score": round(div_score, 1),
            "details": details,
            "risk_allocations": allocations,
            "sector_spread": sector_counts.to_dict()
        }

    async def calculate_correlation_matrix(self, price_dfs: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Calculates correlation between multiple stock price series.
        """
        if len(price_dfs) < 2: return {}
        
        try:
            # Combine all 'close' columns into one DF
            combined = pd.DataFrame()
            for sym, df in price_dfs.items():
                if not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    combined[sym] = df['close']
            
            # Calculate daily returns correlation
            corr_matrix = combined.pct_change().corr().round(2)
            return corr_matrix.to_dict()
        except:
            return {}

portfolio_engine = PortfolioEngine()
