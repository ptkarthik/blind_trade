import sqlite3
db = sqlite3.connect('blind_trade.db')
cursor = db.cursor()
cursor.execute("SELECT id, type, status, created_at, updated_at FROM jobs ORDER BY created_at DESC LIMIT 10")
rows = cursor.fetchall()

with open('jobs_output.txt', 'w', encoding='utf-8') as f:
    f.write(f"{'ID':<34} | {'TYPE':<15} | {'STATUS':<10} | {'CREATED':<20} | {'UPDATED':<20}\n")
    f.write("-" * 110 + "\n")
    for r in rows:
        f.write(f"{r[0]:<34} | {r[1]:<15} | {r[2]:<10} | {str(r[3])[:19]:<20} | {str(r[4])[:19]:<20}\n")
