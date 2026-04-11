#!/usr/bin/env python3
"""快速批量翻译脚本 - 前台运行版"""
import json, time, urllib.request, urllib.parse, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path('data')
ENRICHED = ROOT / 'stars-enriched.json'
OUTPUT = ROOT / 'desc-cn.json'
MAX_TRANSLATE = 500

def translate(text):
    if not text or len(text.strip()) < 10: return ''
    params = urllib.parse.urlencode({'q': text[:500], 'langpair': 'en|zh'})
    try:
        with urllib.request.urlopen(f'https://api.mymemory.translated.net/get?{params}', timeout=15) as r:
            return json.loads(r.read())['responseData']['translatedText']
    except Exception as e:
        return ''

def main():
    print(f"\n🌐 Translation - Top {MAX_TRANSLATE} by Stars")
    print("=" * 50)
    
    with open(ENRICHED) as f:
        repos = json.load(f)
    print(f"Loaded {len(repos)} repos")
    
    # Load existing
    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        print(f"Already translated: {len(existing)}")
    
    # Sort by stars, take top with English desc
    def needs_translate(repo):
        if str(repo['id']) in existing: return False
        d = repo.get('desc', '')
        return bool(d and len(d.strip()) >= 10 and not re.search(r'[\u4e00-\u9fff]', d))
    
    candidates = [r for r in repos if needs_translate(r)]
    candidates.sort(key=lambda r: r.get('stars', 0) or 0, reverse=True)
    candidates = candidates[:MAX_TRANSLATE]
    
    print(f"Translating top {len(candidates)} repos by stars")
    print(f"Estimated time: ~{len(candidates) * 2.2 / 60:.0f} minutes")
    
    done = 0
    for i, repo in enumerate(candidates):
        cn = translate(repo['desc'])
        if cn:
            existing[str(repo['id'])] = cn
        
        done += 1
        if done % 20 == 0 or done == len(candidates):
            print(f"  [{done}/{len(candidates)}] {100*done/len(candidates):.0f}%")
        
        time.sleep(2.0)  # MyMemory rate limit
    
    # Save
    OUTPUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    print(f"\n✅ Saved {len(existing)} translations to {OUTPUT}")
    print(f"   Next: git add + commit + push")

if __name__ == '__main__':
    main()
