#!/usr/bin/env python3
"""
GitHub Stars Sync Script
Fetches all starred repositories for the authenticated user.
Uses only stdlib - no external dependencies.
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_env_token():
    """Get token from env."""
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

def api_request(url, params=None):
    """Make authenticated GitHub API request."""
    token = get_env_token()
    if not token:
        raise Exception("No GitHub token found in GH_TOKEN or GITHUB_TOKEN env")
    
    headers = dict(HEADERS)
    headers["Authorization"] = f"Bearer {token}"
    
    if params:
        url += "?" + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise Exception(f"HTTP {e.code} for {url}: {body[:200]}")

def fetch_all_stars(username):
    """Fetch all starred repos with pagination."""
    repos = []
    page = 1
    per_page = 100
    
    print(f"Fetching stars for @{username}...")
    
    while True:
        params = {"page": page, "per_page": per_page, "sort": "updated"}
        url = f"{GITHUB_API}/users/{username}/starred"
        
        data = api_request(url, params)
        if not data:
            break
            
        for repo in data:
            repos.append({
                "id": repo["id"],
                "name": repo["full_name"],
                "full_name": repo["full_name"],
                "desc": repo.get("description") or "",
                "stars": repo["stargazers_count"],
                "lang": repo.get("language") or "",
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
        
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.5)  # Rate limit friendly
    
    print(f"\n✅ Total starred repos: {len(repos)}")
    return repos

def main():
    # Get username from env (set by workflow)
    username = os.environ.get("GITHUB_ACTOR") or os.environ.get("GH_USER", "gandli")
    print(f"Username: {username}")
    
    data_dir = Path("data")
    previous_file = data_dir / "stars-previous.json"
    current_file = data_dir / "stars.json"
    
    # Backup previous
    if previous_file.exists():
        import shutil
        shutil.copy(previous_file, data_dir / "stars-previous-backup.json")
    
    # Save new data
    repos = fetch_all_stars(username)
    
    with open(current_file, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)
    
    # Generate stats
    stats = {
        "total": len(repos),
        "username": username,
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "by_language": {},
        "top_stars": sorted(set([r["stars"] for r in repos]), reverse=True)[:10],
    }
    
    for r in repos:
        lang = r.get("lang") or "Unknown"
        stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
    
    with open(data_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 Stats: {stats['total']} repos, {len(stats['by_language'])} languages")

if __name__ == "__main__":
    main()
