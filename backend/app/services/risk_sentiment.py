
from typing import Dict, Any, List
import re

class RiskSentimentEngine:
    """
    Analyzes Market Sentiment and Risk Factors.
    - Sentiment: Derived from News Headlines (Simple Keyword NLP) and Institutional Holding.
    - Risk: Derived from Volatility (Beta) and Shareholding stability.
    """
    
    def analyze(self, extended_data: Dict[str, Any], fundamentals: Dict[str, Any], df: Any = None) -> Dict[str, Any]:
        """
        Returns: {
            "score": float (0-100),
            "risk_level": "Low" | "Medium" | "High",
            "sentiment_label": "Bullish" | "Bearish" | "Neutral",
            "accumulation_label": str,
            "details": List[str]
        }
        """
        holders = extended_data.get("holders", {})
        news = extended_data.get("news", [])
        current_price = fundamentals.get("price", 0)
        
        # 1. Institutional Sentiment
        inst_score = self._score_institutions(holders)
        
        # 2. News Sentiment
        news_score, news_summary = self._score_news(news)
        
        # 3. Structural Risk
        beta = fundamentals.get("beta")
        risk_score = self._score_risk_structure(beta)
        
        # 4. Insider Activity
        insider_data = extended_data.get("insider_transactions")
        insider_act_score, insider_msg = self._score_insider_activity(insider_data)
        
        # 5. Accumulation Analysis
        acc_score, acc_label = self._score_accumulation(df, current_price)
        
        # AGGREGATE SCORING (Phase 29 Granularity)
        # Volume Category: Accumulation + News + Inst Proxy
        vol_score = (acc_score * 0.60) + (news_score * 0.40)
        
        # Risk Category: Beta + Insiders + Inst Safety
        stability_score = (risk_score * 0.50) + (insider_act_score * 0.30) + (inst_score * 0.20)
        
        final_score = (vol_score + stability_score) / 2
        
        # Determine labels
        risk_level = "Medium"
        if beta and beta > 1.5: risk_level = "High"
        if beta and beta < 0.8: risk_level = "Low"
        
        sentiment_label = "Neutral"
        if final_score > 6.5: sentiment_label = "Bullish"
        if final_score < 3.5: sentiment_label = "Bearish"
        
        details = []
        inst_held = holders.get('institutionsPercentHeld', 0)
        # ... (cleaning logic)
        import math
        if inst_held is None or (isinstance(inst_held, float) and math.isnan(inst_held)): inst_held = 0.0
        if beta is None or (isinstance(beta, float) and math.isnan(beta)): beta = 0.0

        if inst_score > 7: 
            details.append({"text": "High Institutional Confidence", "type": "positive", "label": "SEC", "value": f"Hold: {round(inst_held*100, 1)}%"})
        elif inst_score < 4:
            details.append({"text": "Weak Institutional Trust", "type": "negative", "label": "SEC", "value": f"Hold: {round(inst_held*100, 1)}%"})

        if news_score > 7: 
            details.append({"text": "Positive News Flow", "type": "positive", "label": "SENT", "value": "Bullish Headlines"})
        elif news_score < 4:
            details.append({"text": "Negative Sentiment Overhang", "type": "negative", "label": "SENT", "value": "Bearish Headlines"})

        if beta and beta < 1.0: 
            details.append({"text": "Beta Stability", "type": "positive", "label": "SAFE", "value": f"Beta: {round(beta, 2)}"})
        elif beta and beta > 1.3:
            details.append({"text": "High Market Sensitivity", "type": "negative", "label": "RISK", "value": f"Beta: {round(beta, 2)}"})
        if acc_score > 7:
            details.append({"text": "Smart Money Accumulation", "type": "positive", "label": "ACC", "value": acc_label})
        elif acc_score < 4:
            details.append({"text": "Institutional Exit Detected", "type": "negative", "label": "EXIT", "value": acc_label})

        return {
            "score": round(final_score * 10, 1), # Scale to 0-100
            "volume_score": round(vol_score * 10, 1),
            "stability_score": round(stability_score * 10, 1),
            "risk_level": risk_level,
            "sentiment_label": sentiment_label,
            "accumulation_label": acc_label,
            "details": details,
            "components": {
                "volume_behavior": round(vol_score * 10, 1),
                "structural_stability": round(stability_score * 10, 1)
            }
        }

    def _score_institutions(self, holders: Dict) -> float:
        """Score based on % held by Institutions/Insiders."""
        score = 5.0
        
        # Extract keys (YF format varies)
        # Typical keys: 'insidersPercentHeld', 'institutionsPercentHeld'
        
        inst_held = holders.get('institutionsPercentHeld', 0)
        insider_held = holders.get('insidersPercentHeld', 0)
        
        # Handle if they are strings "20%" or floats 0.20
        # Convert to float 0.0-1.0
        try:
            if isinstance(inst_held, str): inst_held = float(inst_held.replace('%','')) / 100
            if isinstance(insider_held, str): insider_held = float(insider_held.replace('%','')) / 100
        except:
            inst_held = 0
            insider_held = 0
            
        # Logic:
        # High FII/DII is good (Validation)
        # High Promoter (Insider) is good (Skin in the game)
        
        if inst_held > 0.30: score += 2    # > 30% Institutional
        if inst_held > 0.50: score += 1    # > 50% Highly Trusted
        
        if insider_held > 0.50: score += 2 # > 50% Promoter
        if insider_held < 0.10: score -= 2 # Low promoter holding (Red Flag usually in India)
        
        return max(0, min(10, score))

    def _score_news(self, news: List[Dict]) -> tuple[float, str]:
        """Enhanced Keyword Sentiment Analysis on titles (Phase 30)."""
        if not news: return 5.0, ""
        
        score = 5.0
        positive_keywords = [
            "growth", "record", "profit", "jump", "buy", "surge", "acquisition", 
            "bonus", "dividend", "bull", "upgrade", "high", "buyback", "order",
            "patent", "positive", "beat", "expansion", "strategic", "deal"
        ]
        negative_keywords = [
            "loss", "fall", "drop", "sell", "bear", "warn", "crash", "down", "suit", 
            "fraud", "weak", "low", "probe", "regulatory", "fine", "penalty", 
            "layoff", "negative", "downgrade", "debt", "default"
        ]
        
        titles = [n.get("title", "").lower() for n in news[:8]] # Wider scan
        
        for t in titles:
            for w in positive_keywords:
                if w in t: score += 0.4
            for w in negative_keywords:
                if w in t: score -= 0.6 # Negatives weighed more (Risk Aversion)
        
        summary = news[0].get("title", "") if news else ""
        return max(0, min(10, score)), summary

    def _score_accumulation(self, df: Any, current_price: float) -> tuple[float, str]:
        """
        Detects 'Smart Money' accumulation using Volume/Price divergence.
        High Accumulation = High delivery proxy + Volume surges on up-days.
        """
        if df is None or (hasattr(df, 'empty') and df.empty): return 5.0, "Neutral"
        
        try:
            # Clean columns (ensure lowercase)
            df.columns = [c.lower() for c in df.columns]
            recent = df.tail(10) # Look at last 10 days
            
            # 1. Volume vs Average
            avg_vol = df['volume'].mean()
            recent_vol = recent['volume'].mean()
            vol_surge = recent_vol / avg_vol if avg_vol > 0 else 1.0
            
            # 2. Price Position (Close in Range) - Delivery Proxy
            # (Close - Low) / (High - Low) -> Closer to 1 means shares held/taken home
            recent['range_pos'] = (recent['close'] - recent['low']) / (recent['high'] - recent['low'])
            avg_pos = recent['range_pos'].mean()
            
            # 3. Up-Day Volume Bias
            # Do green days have more volume than red days?
            recent['change'] = recent['close'].diff()
            up_vol = recent[recent['change'] > 0]['volume'].sum()
            down_vol = recent[recent['change'] < 0]['volume'].sum()
            vol_bias = up_vol / down_vol if down_vol > 0 else 1.5
            
            score = 5.0
            label = "Normal"
            
            if avg_pos > 0.7 or (vol_surge > 1.3 and vol_bias > 1.2):
                score = 8.5
                label = "High Accumulation"
            elif avg_pos < 0.3 or (vol_surge > 1.3 and vol_bias < 0.8):
                score = 2.5
                label = "Institutional Exit"
            elif vol_surge > 1.5:
                label = "High Activity"
                
            return score, label
        except:
            return 5.0, "Analyzing..."

    def _score_risk_structure(self, beta: float) -> float:
        """Score Safety (Higher is Safer)."""
        score = 5.0
        if beta is None: return 5.0
        
        # High Beta = High Risk = Lower Safety Score
        if beta > 1.5: score = 2
        elif beta > 1.2: score = 4
        elif beta > 0.9: score = 6 # Closely correlated
        elif beta < 0.8: score = 8 # Low volatility
        elif beta < 0.5: score = 9 # Very Stable
        
        return score

    def _score_insider_activity(self, transactions: Any) -> tuple[float, str]:
        """
        Analyze recent insider trades.
        Input could be DataFrame/List or None.
        """
        score = 5.0 # Neutral
        msg = ""
        
        # If no data, neutral
        if transactions is None: return 5.0, ""
        
        try:
            # If it's a pandas dataframe (usual from yfinance)
            if hasattr(transactions, 'empty') and not transactions.empty:
                # Naive Check: Look at "Text" or "Value" column if available
                # Usually columns: ['Shares', 'Value', 'Text', 'Start Date']
                # Simplification: If rows exist, it's activity.
                # We need to distinguish Buy vs Sell.
                # Often "Purchase" or "Sale" in Text.
                
                # Let's convert to string for keyword search in last few rows
                recent_activity = str(transactions.head(3))
                
                buys = len(re.findall(r"(?i)purchase|buy|acquisition", recent_activity))
                sells = len(re.findall(r"(?i)sale|sell|disposal", recent_activity))
                
                if buys > sells:
                    score = 8.0
                    msg = "Recent Insider Buying Detected"
                elif sells > buys:
                    score = 3.0
                    msg = "Recent Insider Selling Detected"
                else:
                    msg = "Mixed Insider Activity"
                    
            elif isinstance(transactions, list) and transactions:
                # If list of dicts
                pass 
                
        except Exception as e:
            # print(f"Insider parsing error: {e}")
            pass
            
        return score, msg

risk_engine = RiskSentimentEngine()
