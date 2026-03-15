import pandas as pd
from datetime import datetime
import sys
import os
import unittest
from unittest.mock import MagicMock

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mocking modules that trigger side effects
from app.core.config import settings
settings.MARKET_TIMEZONE = "Asia/Kolkata"

from app.services.ta_intraday import IntradayTechnicalAnalysis
from app.services.intraday_engine import IntradayEngine

class TestV4Logic(unittest.TestCase):
    def test_module_3_reentry(self):
        print("\n--- Testing Module 3 (Stop Hunt Re-entry) ---")
        # Creating a DF where breakout_level should be 100
        data = {
            'open': [99]*25,
            'high': [100]*20 + [102, 102, 101, 102, 102],
            'low': [98]*25,
            'close': [99]*20 + [101, 101, 99, 101, 101], # 2 closes above at the end
            'volume': [1000]*25
        }
        df = pd.DataFrame(data)
        
        # Scenario 1: Only 2 candles above (Not enough)
        res = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df)
        self.assertEqual(res['candle_hold_count'], 2)
        self.assertFalse(res['price_reclaim'])
        print("Scen 1 (2 candles): SUCCESS (Expected False)")

        # Scenario 2: 3 candles above
        data2 = {
            'open': [99]*30,
            'high': [100]*25 + [102, 102, 102, 102, 102],
            'low': [98]*30,
            'close': [99]*25 + [101, 101, 101, 101, 101], # 5 closes above
            'volume': [1000]*30
        }
        df2 = pd.DataFrame(data2)
        res2 = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df2)
        self.assertEqual(res2['candle_hold_count'], 5)
        self.assertTrue(res2['price_reclaim'])
        print("Scen 2 (5 candles): SUCCESS (Expected True)")

    def test_module_10_timing(self):
        print("\n--- Testing Module 10 (Timing Windows) ---")
        engine = IntradayEngine()
        
        # Test Optimal Window (09:30)
        t_opt = datetime(2026, 3, 15, 9, 30)
        w_opt = engine._is_optimal_window(t_opt)
        self.assertEqual(w_opt, "OPTIMAL")
        
        # Test Normal Window (12:00)
        t_norm = datetime(2026, 3, 15, 12, 0)
        w_norm = engine._is_optimal_window(t_norm)
        self.assertEqual(w_norm, "NORMAL")
        print("Timing Logic: SUCCESS")

if __name__ == "__main__":
    unittest.main()
