import requests

TOKEN = "8860047698:AAGDBoo0zdqILGNmbahfzpzKxeeijy-eYKo"
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

try:
    response = requests.get(url)
    data = response.json()
    if data.get("ok") and data.get("result"):
        for update in data["result"]:
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
                print(f"FOUND_CHAT_ID:{chat_id}")
                break
        else:
            print("NO_MESSAGES_FOUND")
    else:
        print("NO_MESSAGES_FOUND")
except Exception as e:
    print(f"ERROR: {e}")
