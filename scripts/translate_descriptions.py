#!/usr/bin/env python3
"""
translate_descriptions.py

批量翻译 stars-enriched.json 中所有项目的英文描述为中文。
使用 MyMemory API（免费，无需 key，10秒最多5个请求）。

输出: data/desc-cn.json
  {
    "repo_id": "translated_chinese_description",
    ...
  }

使用方法:
    source .venv/bin/activate
    python scripts/translate_descriptions.py

增量运行: 只翻译尚未有中文描述的仓库，已翻译的跳过。
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).parent.parent
ENRICHED_FILE = ROOT / 'data' / 'stars-enriched.json'
DESC_CN_FILE = ROOT / 'data' / 'desc-cn.json'
META_FILE = ROOT / 'data' / 'translations-meta.json'

# MyMemory API (free, no key required)
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# Rate limiting: max 5 requests per 10 seconds
REQUEST_INTERVAL = 2.0  # seconds between requests

def truncate(text, max_chars=500):
    """截断过长的文本"""
    if not text:
        return ''
    if len(text) > max_chars:
        return text[:max_chars-3] + '...'
    return text

def translate(text, src_lang='en', dst_lang='zh'):
    """调用 MyMemory API 翻译单段文本"""
    if not text or not text.strip():
        return ''
    
    text = truncate(text, 500)
    
    params = {
        'q': text,
        'langpair': f'{src_lang}|{dst_lang}',
    }
    
    url = f"{MYMEMORY_URL}?{urlencode(params)}"
    
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        if data.get('responseStatus') == 200:
            return data['responseData']['translatedText']
        else:
            print(f"   ⚠️ API error {data.get('responseStatus')}: {text[:50]}")
            return ''
    except Exception as e:
        print(f"   ⚠️ Request failed: {e}")
        return ''

def translate_batch(texts, dst_lang='zh'):
    """批量翻译（利用 MyMemory 的批量特性）"""
    results = []
    for text in texts:
        result = translate(text, dst_lang=dst_lang)
        results.append(result)
        time.sleep(REQUEST_INTERVAL)
    return results

def main():
    print(f"\n🌐 Chinese Translation for stars-archive")
    print("=" * 50)
    
    # Load enriched data
    if not ENRICHED_FILE.exists():
        print(f"❌ Error: {ENRICHED_FILE} not found!")
        sys.exit(1)
    
    print("\n📖 Loading stars-enriched.json...")
    with open(ENRICHED_FILE, 'r', encoding='utf-8') as f:
        repos = json.load(f)
    print(f"   Loaded {len(repos)} repos")
    
    # Load existing translations
    existing = {}
    if DESC_CN_FILE.exists():
        print("\n📂 Found existing desc-cn.json, loading...")
        with open(DESC_CN_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing_count = sum(1 for r in repos if str(r['id']) in existing and existing[str(r['id'])])
        print(f"   Already translated: {existing_count}/{len(repos)}")
    
    # Find repos needing translation
    to_translate = []
    to_translate_indices = []
    
    # Strategy: sort by stars, only translate top N
    # Top 500 by stars covers most-used repos
    MAX_TRANSLATE = int(os.environ.get('TRANSLATE_LIMIT', '500'))
    print(f"\n📊 Strategy: translate top {MAX_TRANSLATE} repos by stars (most impactful)")
    
    # Sort repos by stars descending
    repos_with_desc = [
        (idx, repo) for idx, repo in enumerate(repos)
        if repo.get('desc', '').strip()
        and len(repo.get('desc', '').strip()) >= 10
        and not re.search(r'[\u4e00-\u9fff]', repo.get('desc', ''))
        and not (repo.get('desc_cn') or '').strip()
        and str(repo['id']) not in existing
    ]
    repos_with_desc.sort(key=lambda x: x[1].get('stars', 0) or 0, reverse=True)
    
    # Take top MAX_TRANSLATE
    repos_with_desc = repos_with_desc[:MAX_TRANSLATE]
    
    for idx, repo in repos_with_desc:
        repo_id = str(repo['id'])
        desc = repo.get('desc', '')
        to_translate.append((repo_id, desc))
        to_translate_indices.append(idx)
    
    if not to_translate:
        print("\n✅ All repos already have Chinese descriptions!")
    else:
        print(f"\n📝 Need to translate {len(to_translate)} repos")
        print(f"   (This will take ~{len(to_translate) * REQUEST_INTERVAL / 60:.0f} minutes at {REQUEST_INTERVAL}s/req)")
        
        print("\n🗣️ Starting translation...")
        translated_count = 0
        
        for i, (repo_id, desc) in enumerate(to_translate):
            cn = translate(desc)
            if cn:
                existing[repo_id] = cn
                translated_count += 1
            
            # Progress
            if (i + 1) % 10 == 0 or i == len(to_translate) - 1:
                elapsed = (i + 1) * REQUEST_INTERVAL
                eta = (len(to_translate) - i - 1) * REQUEST_INTERVAL
                print(f"   [{i+1}/{len(to_translate)}] {translated_count} ok | elapsed: {elapsed/60:.1f}m | ETA: {eta/60:.1f}m")
            
            time.sleep(REQUEST_INTERVAL)
        
        print(f"\n✅ Translated {translated_count} descriptions!")
    
    # Stats
    total_cn = sum(1 for r in repos if (r.get('desc_cn') or '').strip() or str(r['id']) in existing)
    print(f"\n📊 Total with Chinese: {total_cn}/{len(repos)} ({100*total_cn/len(repos):.1f}%)")
    
    # Save
    print("\n💾 Saving desc-cn.json...")
    with open(DESC_CN_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    meta = {
        'total_translated': len(existing),
        'total_repos': len(repos),
        'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'api': 'MyMemory (free, no key)',
    }
    with open(META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    
    print("\n✅ desc-cn.json saved!")
    print("   Next: upload to GitHub and update search.html to use desc_cn")

if __name__ == '__main__':
    main()
