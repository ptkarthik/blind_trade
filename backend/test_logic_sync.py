import asyncio
import time
import sys
import os

# Set up paths
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def test_sync_logic():
    print("🚀 Testing Incremental Sync Logic...")
    
    # Mocking a state object similar to what engines use
    state = {
        "results": [],
        "failed_symbols": [],
        "active": ["RELIANCE.NS"],
        "progress": 0,
        "is_running": True,
        "last_data_sync": 0,
        "last_sync_time": time.time()
    }
    
    total = 100
    
    def check_sync_condition(state, total):
        current_count = len(state.get("results", []))
        last_sync = state.get("last_data_sync", 0)
        last_sync_time = state.get("last_sync_time", 0)
        current_time = time.time()
        
        condition = (current_count - last_sync >= 5) or (current_count > last_sync and current_time - last_sync_time >= 10) or (current_count == total)
        return condition, current_count, last_sync, current_time - last_sync_time

    # Scenario 1: Only 2 results, but 0 seconds passed
    state["results"] = [{"symbol": "S1"}, {"symbol": "S2"}]
    cond, count, last, elapsed = check_sync_condition(state, total)
    print(f"Scenario 1 (2 results, 0s): Condition={cond}, Count={count}, LastSync={last}, Elapsed={elapsed:.1f}s")
    assert cond is False, "Should not sync yet"

    # Scenario 2: 6 results, 0 seconds passed
    state["results"] = [{"symbol": f"S{i}"} for i in range(6)]
    cond, count, last, elapsed = check_sync_condition(state, total)
    print(f"Scenario 2 (6 results, 0s): Condition={cond}, Count={count}, LastSync={last}, Elapsed={elapsed:.1f}s")
    assert cond is True, "Should sync because count >= 5"

    # Reset sync
    state["last_data_sync"] = 6
    state["last_sync_time"] = time.time()
    
    # Scenario 3: 7 results (1 new), 12 seconds passed
    print("Waiting 11 seconds for Scenario 3...")
    await asyncio.sleep(11)
    state["results"].append({"symbol": "S7"})
    cond, count, last, elapsed = check_sync_condition(state, total)
    print(f"Scenario 3 (1 new result, 11s): Condition={cond}, Count={count}, LastSync={last}, Elapsed={elapsed:.1f}s")
    assert cond is True, "Should sync because > 10s passed and we have new data"

    # Scenario 4: No new results, 12 seconds passed
    state["last_data_sync"] = 7
    state["last_sync_time"] = time.time()
    await asyncio.sleep(11)
    cond, count, last, elapsed = check_sync_condition(state, total)
    print(f"Scenario 4 (0 new results, 11s): Condition={cond}, Count={count}, LastSync={last}, Elapsed={elapsed:.1f}s")
    assert cond is False, "Should NOT sync because no NEW data even if time passed"

    print("\n✅ All Sync Logic Scenarios Passed!")

if __name__ == "__main__":
    asyncio.run(test_sync_logic())
