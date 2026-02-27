import sqlite3, json
db = sqlite3.connect('blind_trade.db')
cursor = db.cursor()
cursor.execute("SELECT status, result FROM jobs WHERE id='329847d014a24aa284aeb6591d157d55'")
row = cursor.fetchone()
if row:
    status, result = row
    if result:
        try:
            res_dict = json.loads(result)
            print(f"Status: {status}")
            print(f"Progress: {res_dict.get('progress')}/{res_dict.get('total_steps')}")
            print(f"Status Msg: {res_dict.get('status_msg')}")
            print(f"Success Count: {len(res_dict.get('data', []))}, Failed Count: {len(res_dict.get('failed_symbols', []))}")
        except Exception as e:
            print(f"Status: {status}, parse error: {e}")
    else:
        print(f"Status: {status}, Result: None")
else:
    print("Job not found")
