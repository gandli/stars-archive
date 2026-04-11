#!/usr/bin/env python3
"""
Detect changes between previous and current stars.
"""

import json
from pathlib import Path

def get_repo_key(repo):
    """Get unique key for a repo - prefer 'id' fall back to 'name'."""
    return repo.get("id") or repo.get("name")

def main():
    data_dir = Path("data")
    current = data_dir / "stars.json"
    previous = data_dir / "stars-previous.json"
    changes_file = data_dir / "changes.json"
    
    with open(current, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    
    if not previous.exists():
        print("No previous data, skipping change detection")
        return {"added": [], "removed": [], "summary": {"added_count": 0, "removed_count": 0}}
    
    with open(previous, "r", encoding="utf-8") as f:
        previous_data = json.load(f)
    
    current_keys = {get_repo_key(r) for r in current_data}
    previous_keys = {get_repo_key(r) for r in previous_data}
    
    # Find added (in current but not in previous)
    added = [r for r in current_data if get_repo_key(r) in (current_keys - previous_keys)]
    # Find removed (in previous but not in current)
    removed = [r for r in previous_data if get_repo_key(r) in (previous_keys - current_keys)]
    
    changes = {
        "added": sorted(added, key=lambda x: -x.get("stars", 0)),
        "removed": sorted(removed, key=lambda x: -x.get("stars", 0)),
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
