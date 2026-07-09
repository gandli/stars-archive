#!/usr/bin/env python3
"""
Enrich GitHub Stars with:
1. Language category tags (from lang + topics)
2. Auto-generated tags (from name + topics)
3. Chinese translation (delegated to translator.py)
4. Topic normalization
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ========== Common utilities ==========
def is_chinese(text: str) -> bool:
    """Check if text contains Chinese characters"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))

# Try to import unified translator
try:
    from translator import translate_single, RateLimiter
    HAS_UNIFIED_TRANSLATOR = True
except ImportError:
    HAS_UNIFIED_TRANSLATOR = False

# ... rest of existing code ...

# ========== Language Categories ==========
LANG_CATEGORIES = {
    "Python": ["python", "django", "flask", "fastapi", "pytorch", "tensorflow", "pandas", "jupyter"],
    "JavaScript": ["javascript", "js", "node", "nodejs", "express", "npm"],
    "TypeScript": ["typescript", "ts", "tsx", "jsx"],
    "Java": ["java", "spring", "maven", "gradle"],
    "Go": ["golang", "/go/", "go-", "-go"],
    "Rust": ["rust", "/rust/", "-rust"],
    "C++": ["c++", "cpp", "cplusplus"],
    "C": ["c/", "c\\", "/c/", "\\c/"],
    "C#": ["c#", "csharp", ".net", "dotnet"],
    "Swift": ["swift", "ios", "cocoa", "tvos", "watchos"],
    "Kotlin": ["kotlin", "android"],
    "Ruby": ["ruby", "rails", "rake"],
    "PHP": ["php", "laravel", "symfony"],
    "Shell": ["shell", "bash", "zsh", "fish", "powershell"],
    "Vue": ["vue", "vuejs"],
    "React": ["react", "reactjs"],
    "Angular": ["angular"],
    "Svelte": ["svelte"],
    "Next.js": ["nextjs", "next.js"],
    "Astro": ["astro"],
    "Solid": ["solid", "solidjs"],
    "HTML/CSS": ["html", "css", "scss", "sass", "tailwind"],
    "Docker": ["docker", "container"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Database": ["postgresql", "mysql", "mongodb", "redis", "sqlite", "duckdb"],
    "AI/ML": ["llm", "ai", "machine-learning", "deep-learning", "gpt", "nlp",
               "transformer", "huggingface", "ollama", "langchain", "rag", "embedding",
               "whisper", "stable-diffusion", "generative", "chatgpt", "claude", "openai"],
    "CLI": ["cli", "command-line", "terminal", "tui"],
    "API": ["api", "rest", "graphql", "grpc", "swagger"],
    "DevOps": ["devops", "ci/cd", "github-action", "gitlab-ci"],
    "Security": ["security", "hack", "ctf", "penetration", "vulnerability"],
    "Blockchain": ["blockchain", "ethereum", "solidity", "web3", "defi", "nft"],
}

def get_lang_category(name, desc, topics, orig_lang):
    """Infer category from lang + topics + name."""
    combined = ' '.join([name, desc, ' '.join(topics or [])]).lower()
    # Normalize: hyphens in keywords match spaces in text
    combined_normalized = combined.replace('-', ' ')

    # AI/ML: detect via keywords in AI/ML category
    ai_keywords = LANG_CATEGORIES.get("AI/ML", [])
    for kw in ai_keywords:
        kw_variants = [kw, kw.replace('-', ' ')]
        if any(v in combined or v in combined_normalized for v in kw_variants):
            return "🤖 AI/ML"

    # Check main language
    for category, keywords in LANG_CATEGORIES.items():
        if category == "AI/ML":
            continue
        for kw in keywords:
            kw_variants = [kw, kw.replace('-', ' ')]
            if any(v in combined or v in combined_normalized for v in kw_variants):
                return category
    
    # Fall back to GitHub language
    if orig_lang:
        return orig_lang
    return "Other"

# ========== Auto Tags ==========
TECH_KEYWORDS = {
    "Framework": ["framework", "framework"],
    "Library": ["library", "lib", "util"],
    "CLI Tool": ["cli", "command-line", "terminal", "tool"],
    "API": ["api", "rest", "graphql", "grpc", "endpoint"],
    "Database": ["database", "db", "orm", "sql", "nosql"],
    "Docker": ["docker", "container", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "helm"],
    "Machine Learning": ["machine-learning", "deep-learning", "neural", "model"],
    "Web": ["web", "frontend", "backend", "fullstack", "ssr"],
    "Mobile": ["mobile", "ios", "android", "react-native", "flutter"],
    "Blockchain": ["blockchain", "crypto", "web3", "defi", "smart-contract"],
    "Security": ["security", "vulnerability", "exploit", "penetration"],
    "Open Source": ["open-source", "open source", "oss"],
    "Beginner Friendly": ["beginner", "first-pr", "good-first-issue", "help-wanted"],
    "AI": ["ai", "gpt", "llm", "nlp", "generative", "whisper", "stable-diffusion"],
}

def extract_auto_tags(name, desc, topics, orig_lang):
    """Extract auto-tags from name, description, topics."""
    tags = set()
    combined = ' '.join([name, desc, ' '.join(topics or [])]).lower()
    
    for tag, keywords in TECH_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                tags.add(tag)
                break
    
    # From topics (clean and add)
    for t in (topics or []):
        t_clean = re.sub(r'[^a-z0-9-]', '', t.lower())
        if len(t_clean) > 2 and len(t_clean) < 30:
            tags.add(t_clean)
    
    return list(tags)[:10]  # Max 10 tags

# ========== Translation backend ==========
# Prefer unified translator.py (concurrent + retry); else fallback to single-shot
LIBRETRANSLATE_URL = os.environ.get("LIBRETRANSLATE_URL", "https://libretranslate.com")

def _translate_single_libretranslate(text: str) -> str:
    """Single-shot translation via LibreTranslate (fallback only)."""
    if not text or not text.strip():
        return ""
    if is_chinese(text):
        return text
    try:
        import urllib.request, urllib.parse
        url = f"{LIBRETRANSLATE_URL}/translate"
        data = urllib.parse.urlencode({
            "q": text[:1000], "source": "en", "target": "zh", "format": "text"
        }).encode()
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("translatedText", text)
    except Exception as e:
        print(f"  Translation error: {e}")
        return text

if HAS_UNIFIED_TRANSLATOR:
    print("✅ 使用统一翻译模块 translator.py (并发 + 重试)")
    def translate_to_chinese(text, target_lang="en"):
        return translate_single(text)
    def batch_translate(texts, batch_size=10):
        return texts
else:
    def translate_to_chinese(text, target_lang="en"):
        return _translate_single_libretranslate(text)
    def batch_translate(texts, batch_size=10):
        results = []
        for i, text in enumerate(texts):
            if text and not is_chinese(text):
                result = translate_to_chinese(text)
                time.sleep(0.3)
            else:
                result = text
            results.append(result)
            if (i + 1) % 10 == 0:
                print(f"  Translated {i + 1}/{len(texts)}")
        return results

# ========== Main Enrichment ==========
def enrich_repo(repo):
    """Enrich a single repo."""
    name = repo.get('name', '')
    desc = repo.get('desc', '') or ''
    topics = repo.get('topics', []) or []
    orig_lang = repo.get('lang') or ''
    
    return {
        # Original fields
        **{k: v for k, v in repo.items() if k not in ['auto_tags', 'lang_category', 'desc_cn']},
        # New enriched fields
        "lang_category": get_lang_category(name, desc, topics, orig_lang),
        "auto_tags": extract_auto_tags(name, desc, topics, orig_lang),
        "desc_cn": repo.get('desc_cn') or repo.get('desc', '') if any('\u4e00' <= c <= '\u9fff' for c in (repo.get('desc') or '')) else None,
    }

def load_progress():
    """Load enrichment progress."""
    progress_file = Path("data/enrichment-progress.json")
    if progress_file.exists():
        with open(progress_file) as f:
            return json.load(f)
    return {"translated_ids": [], "last_index": 0}

def save_progress(progress):
    """Save enrichment progress."""
    with open("data/enrichment-progress.json", "w") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def main():
    stars_file = Path("data/stars.json")
    enriched_file = Path("data/stars-enriched.json")
    
    with open(stars_file) as f:
        repos = json.load(f)
    
    print(f"Loaded {len(repos)} repos")
    
    # Load existing enriched data
    existing = {}
    if enriched_file.exists():
        with open(enriched_file) as f:
            existing_data = json.load(f)
            existing = {r['id']: r for r in existing_data}
        print(f"Loaded {len(existing)} existing enriched records")
    
    # Load progress
    progress = load_progress()
    translated_ids = set(progress.get('translated_ids', []))
    
    # Process repos
    batch_size = int(os.environ.get('BATCH_SIZE', 50))
    batch_repos = []
    
    for repo in repos:
        repo_id = repo.get('id') or repo.get('name')
        
        if repo_id in existing:
            # Already enriched, skip
            batch_repos.append(existing[repo_id])
            continue
        
        # Enrich new repo
        enriched = enrich_repo(repo)
        
        # Translate if needed (only for English descriptions)
        desc = repo.get('desc') or ''
        if desc and not any('\u4e00' <= c <= '\u9fff' for c in desc) and repo_id not in translated_ids:
            if len(batch_repos) < batch_size:
                print(f"Translating: {repo.get('name')}")
                enriched['desc_cn'] = translate_to_chinese(desc)
                translated_ids.add(repo_id)
                progress['translated_ids'] = list(translated_ids)
                save_progress(progress)
            else:
                enriched['desc_cn'] = None
        elif desc and any('\u4e00' <= c <= '\u9fff' for c in desc):
            enriched['desc_cn'] = desc
        else:
            enriched['desc_cn'] = None
        
        batch_repos.append(enriched)
        
        # Save progress every 100 repos
        if len(batch_repos) % 100 == 0:
            print(f"Processed {len(batch_repos)}/{len(repos)}")
    
    # Sort by stars
    batch_repos.sort(key=lambda x: -x.get('stars', 0))
    
    # Save
    with open(enriched_file, "w") as f:
        json.dump(batch_repos, f, ensure_ascii=False, indent=2)
    
    total_cn = sum(1 for r in batch_repos if r.get('desc_cn'))
    print(f"\n✅ Enriched {len(batch_repos)} repos")
    print(f"   Total with Chinese desc: {total_cn}")

if __name__ == "__main__":
    main()
