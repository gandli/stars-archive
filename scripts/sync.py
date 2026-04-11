#!/usr/bin/env python3
"""
GitHub Stars Sync Script
Fetches all starred repositories for the authenticated user.
"""

import os
import json
import time
import requests
from pathlib import Path

GITHUB_API = "https://api.github.com"
REPO = os.environ.get("REPO", "gandli/stars-archive")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_username():
    """Get authenticated username."""
    resp = requests.get(f"{GITHUB_API}/user", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["login"]

def fetch_all_stars(username):
    """Fetch all starred repos with pagination."""
    repos = []
    page = 1
    per_page = 100
    
    print(f"Fetching stars for @{username}...")
    
    while True:
        url = f"{GITHUB_API}/users/{username}/starred"
        params = {"page": page, "per_page": per_page, "sort": "updated"}
        
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        
        data = resp.json()
        if not data:
            break
            
        for repo in data:
            repos.append({
                "id": repo["id"],
                "name": repo["full_name"],
                "full_name": repo["full_name"],
                "description": repo.get("description") or "",
                "stars": repo["stargazers_count"],
                "language": repo.get("language") or "",
                "topics": repo.get("topics", []),
                "url": repo["html_url"],
                "homepage": repo.get("homepage") or "",
                "fork": repo["fork"],
                "created_at": repo["created_at"],
                "updated_at": repo["updated_at"],
                "pushed_at": repo["pushed_at"],
                "owner": {
                    "login": repo["owner"]["login"],
                    "type": repo["owner"]["type"],
                    "avatar_url": repo["owner"]["avatar_url"],
                },
                "license": repo.get("license", {}).get("spdx_id") or "",
                "forks_count": repo.get("forks_count", 0),
                "open_issues_count": repo.get("open_issues_count", 0),
                "watchers": repo.get("watchers_count", 0),
            })
        
        print(f"  Page {page}: fetched {len(data)} repos (total: {len(repos)})")
        
        # Check pagination headers
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.5)  # Rate limit friendly
    
    print(f"\n✅ Total starred repos: {len(repos)}")
    return repos

def main():
    # Check for previous data
    data_dir = Path("data")
    previous_file = data_dir / "stars-previous.json"
    current_file = data_dir / "stars.json"
    
    # Backup previous
    if previous_file.exists():
        previous_file.rename(data_dir / "stars-previous-backup.json")
    
    # Save new data
    username = get_username()
    repos = fetch_all_stars(username)
    
    with open(current_file, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)
    
    # Generate stats
    stats = {
        "total": len(repos),
        "username": username,
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "by_language": {},
        "top_stars": sorted([r["stars"] for r in repos], reverse=True)[:10],
    }
    
    for r in repos:
        lang = r.get("language") or "Unknown"
        stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
    
    with open(data_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 Stats: {stats['total']} repos, {len(stats['by_language'])} languages")

if __name__ == "__main__":
    main()
