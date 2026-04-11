#!/usr/bin/env python3
"""
Detect changes between previous and current stars.
"""

import json
from pathlib import Path

def main():
    data_dir = Path("data")
    current = data_dir / "stars.json"
    previous = data_dir / "stars-previous.json"
    changes_file = data_dir / "changes.json"
    
    with open(current, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    
    with open(previous, "r", encoding="utf-8") as f:
        previous_data = json.load(f)
    
    current_ids = {r["id"] for r in current_data}
    previous_ids = {r["id"] for r in previous_data}
    
    added = [r for r in current_data if r["id"] in (current_ids - previous_ids)]
    removed = [r for r in previous_data if r["id"] in (previous_ids - current_ids)]
    
    changes = {
        "added": sorted(added, key=lambda x: -x["stars"]),
        "removed": sorted(removed, key=lambda x: -x["stars"]),
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "net_change": len(added) - len(removed),
        }
    }
    
    with open(changes_file, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Changes detected:")
    print(f"   + New: {len(added)}")
    print(f"   - Removed: {len(removed)}")
    
    # Update previous
    import shutil
    shutil.copy(current, previous)
    
    return changes

if __name__ == "__main__":
    main()
