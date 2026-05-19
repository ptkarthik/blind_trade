import sqlite3
import json
import collections

db_path = r"C:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\blind_trade.db"

def analyze_last_scan():
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get the latest completed scan
        cur.execute("SELECT id, created_at, result FROM jobs WHERE status='completed' AND result != '{}' ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        
        if not row:
            print("No completed scan results found in the database.")
            return
            
        job_id, created_at, result_json = row
        print(f"\n--- DIAGNOSTIC REPORT FOR LAST SCAN ({created_at}) ---")
        
        result_data = json.loads(result_json)
        
        # Find all skipped stocks
        skips = result_data.get("skipped", [])
        print(f"\nTotal Stocks Skipped: {len(skips)}")
        
        if not skips:
            # Maybe the data structure is different? Check for any "skip_reason" in the raw data
            print("No explicit 'skipped' list found. Analyzing raw payload...")
        
        # Count the reasons
        reason_counts = collections.Counter()
        for skip in skips:
            reason = skip.get("skip_reason", "Unknown Reason")
            
            # Group the generic "Poor Structural RR" ones so they don't look like 100 different reasons
            if "Poor Structural RR" in reason:
                reason = "Poor Structural RR (< 1.2)"
            elif "Score" in reason and "< 50 (System Floor)" in reason:
                reason = "Score < 50 (System Floor)"
            
            reason_counts[reason] += 1
            
        print("\n--- TOP REASONS FOR REJECTION ---")
        for reason, count in reason_counts.most_common(15):
            print(f"-> {count} stocks rejected due to: {reason}")
            
        # Also let's check how many were successful
        signals = result_data.get("signals", [])
        print(f"\nTotal Valid Signals Generated: {len(signals)}")
        
        if signals:
            print("\n--- SIGNALS THAT SURVIVED ---")
            for sig in signals[:5]: # show top 5
                print(f"OK: {sig.get('symbol')} | Score: {sig.get('score')} | Mode: {sig.get('alpha_mode')}")
                
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_last_scan()
