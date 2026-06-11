import urllib.request
import json
import sys

token = "8860047698:AAGDBoo0zdqlLGNmbahfzpzKxeeijy-eYKo"
url = f"https://api.telegram.org/bot{token}/getUpdates"

try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
        if data.get("ok"):
            results = data.get("result", [])
            if results:
                chat_id = results[-1]["message"]["chat"]["id"]
                print(f"FOUND CHAT ID: {chat_id}")
            else:
                print("NO MESSAGES FOUND")
        else:
            print("ERROR", data)
except Exception as e:
    print("FAILED", e)
