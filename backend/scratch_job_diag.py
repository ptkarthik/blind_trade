import asyncio
import json
import os

def check_jobs():
    cache_dir = os.path.join(os.path.dirname(__file__), "app", "data")
    jobs_file = os.path.join(cache_dir, "jobs_db.json")
    
    if not os.path.exists(jobs_file):
        print("No jobs_db.json found.")
        return
        
    with open(jobs_file, "r") as f:
        jobs = json.load(f)
        
    print(f"Total jobs in DB: {len(jobs)}")
    
    # Sort by start_time descending
    sorted_jobs = sorted(jobs.values(), key=lambda x: x.get("start_time", ""), reverse=True)
    
    print("\nRecent 5 Jobs:")
    for j in sorted_jobs[:5]:
        print(f"ID: {j.get('id')} | Type: {j.get('job_type')} | Status: {j.get('status')} | Start: {j.get('start_time')} | End: {j.get('end_time')}")
        
    # Check for stuck PENDING/RUNNING jobs
    stuck = [j for j in jobs.values() if j.get('status') in ['PENDING', 'RUNNING']]
    print(f"\nCurrently Active/Stuck Jobs: {len(stuck)}")
    for j in stuck:
        print(f"ID: {j.get('id')} | Status: {j.get('status')} | Start: {j.get('start_time')}")

if __name__ == "__main__":
    check_jobs()
