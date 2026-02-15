import os

log_path = r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\advisor_output.log"

def read_log():
    if not os.path.exists(log_path):
        print("Log file not found.")
        return
    
    try:
        with open(log_path, "r", encoding="utf-16-le") as f:
            content = f.read()
            print(content[-2000:]) # Last 2000 chars
    except Exception as e:
        print(f"Error reading log: {e}")

if __name__ == "__main__":
    read_log()
