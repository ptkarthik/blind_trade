
import sqlite3
import os

db_path = "backend/blind_trade.db"
if os.path.exists(db_path):
    print(f"--- 🛰️ Checking DB Health: {db_path} ---")
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        
        # 1. Check Accounts
        cursor.execute("SELECT balance, total_pnl FROM accounts LIMIT 1")
        acc = cursor.fetchone()
        print(f"💰 Account: Bal={acc[0]}, PnL={acc[1]}" if acc else "❌ No Account found.")
        
        # 2. Check Open Trades
        cursor.execute("SELECT id, symbol, qty FROM paper_trades WHERE status='OPEN'")
        trades = cursor.fetchall()
        print(f"📈 Open Trades: {len(trades)}")
        for t in trades:
            print(f"   - {t[1]} (ID: {t[0]})")
            
    except sqlite3.OperationalError as e:
        print(f"🚨 DB Error (Locked?): {e}")
    except Exception as e:
        print(f"❌ Diagnostic Error: {e}")
    finally:
        conn.close()
else:
    print(f"❌ DB not found at {db_path}")
