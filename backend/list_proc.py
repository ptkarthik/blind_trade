
import psutil
import json

processes = []
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if 'python' in proc.info['name'].lower():
            processes.append(proc.info)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

with open("ps_list.json", "w", encoding="utf-8") as f:
    json.dump(processes, f, indent=2)
print(f"Listed {len(processes)} python processes.")
