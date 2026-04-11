#!/usr/bin/env python3
"""
Generate README.md from stars data.
"""

import json
from pathlib import Path
from datetime import datetime

CATEGORIES = [
    ("🤖 AI与大模型", ["llm", "langchain", "openai", "gpt", "chatgpt", "claude", "rag", "embedding", 
                "transformer", "huggingface", "ollama", "vllm", "llama", "mistral", "gemini", 
                "deepseek", "autogen", "crewai", "agno", "metagpt", "browserbase", "whisper",
                "stable-diffusion", "sdxl", "diffusion", "generative-ai"]),
    ("🦞 AI编码助手", ["claude", "openclaw", "openclaude", "cursor", "codex", "copilot", "opencode",
                "coding-agent", "code-agent", "superpowers", "agency-agents", "gstack", "airobor"]),
    ("🟢 前端框架", ["react", "vue", "angular", "svelte", "nextjs", "nuxt", "remix", "solid", "astro"]),
    ("🟨 Node/后端", ["nodejs", "express", "fastify", "nestjs", "koa", "deno", "bun", "electron"]),
    ("🐍 Python", ["python", "django", "flask", "fastapi", "pytorch", "pandas", "jupyter"]),
    ("⚙️ Go", ["golang", "/go", "-go", "/go/"]),
    ("🦀 Rust", ["rust", "/rust", "-rust"]),
    ("🍎 Apple开发", ["macos", "ios", "swift", "apple", "cocoa", "tvos", "watchos", "uikit", "swiftui"]),
    ("📱 跨平台", ["flutter", "react-native", "dart", "capacitor", "ionic", "multiplatform"]),
    ("🗄️ 数据库", ["postgresql", "mysql", "mongodb", "redis", "sqlite", "duckdb", "dolt", "database"]),
    ("☸️ DevOps", ["kubernetes", "docker", "container", "helm", "terraform", "ansible", "ci/cd"]),
    ("🔧 工具集", ["cli", "terminal", "tool", "vscode", "cursor", "vim", "neovim", "tmux", "lazygit", "fzf"]),
    ("🔐 安全", ["security", "hack", "ctf", "penetration", "vulnerability", "exploit", "malware", "reverse", "cryptography"]),
    ("📊 数据科学", ["pandas", "numpy", "scipy", "sklearn", "matplotlib", "plotly", "data-analysis"]),
    ("🌐 网络", ["api", "rest", "graphql", "grpc", "proxy", "gateway", "nginx", "caddy"]),
    ("🧠 知识管理", ["knowledge", "notes", "note-taking", "wiki", "obsidian", "notion", "second-brain"]),
    ("🚀 效率工具", ["productivity", "saas", "automation", "workflow", "n8n"]),
    ("🇨🇳 中文项目", "cn"),
    ("📚 教程资源", ["tutorial", "learn", "course", "awesome", "curriculum", "education", "free-programming"]),
]

def classify(repo, categories):
    """Classify a repo into categories."""
    name = repo['name'].lower()
    desc = (repo.get('desc') or '').lower()
    topics = ' '.join(repo.get('topics', [])).lower()
    combined = name + ' ' + desc + ' ' + topics
    
    for cat in categories:
        cat_name = cat[0]
        cat_data = cat[1]
        
        if cat_data == "cn":
            desc_text = repo.get('desc') or ''
            if desc_text and any('\u4e00' <= c <= '\u9fff' for c in desc_text):
                return cat_name
        elif isinstance(cat_data, list):
            for kw in cat_data:
                if kw in combined:
                    return cat_name
    return None

def generate_readme():
    data_dir = Path("data")
    stars_file = data_dir / "stars.json"
    stats_file = data_dir / "stats.json"
    
    with open(stars_file, "r", encoding="utf-8") as f:
        repos = json.load(f)
    
    with open(stats_file, "r", encoding="utf-8") as f:
        stats = json.load(f)
    
    repos.sort(key=lambda x: -x['stars'])
    
    # Categorize
    categorized = {}
    for repo in repos:
        cat = classify(repo, CATEGORIES) or "📦 其他"
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(repo)
    
    # Build README
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        "# ⭐ My GitHub Stars\n",
        f"> 📋 {stats['total']} starred repositories • Synced at {now}\n",
        f"> Last updated: `{stats['synced_at']}`\n",
        "---\n",
    ]
    
    # Top 20
    lines.append("\n## 🏆 Top 20 Stars\n\n")
    for i, r in enumerate(repos[:20], 1):
        lang = r.get('lang') or '-'
        desc = (r.get('desc') or '').strip()[:60] or '暂无描述'
        lines.append(f"{i:>2}. ⭐ {r['stars']:,} │ [{r['name']}](https://github.com/{r['name']}) `({lang})`\n")
        lines.append(f"    └─ {desc}\n")
    
    # By category
    lines.append("\n## 📂 Categories\n\n")
    
    sorted_cats = sorted(categorized.items(), key=lambda x: -len(x[1]))
    for cat_name, cat_repos in sorted_cats:
        count = len(cat_repos)
        top5 = sorted(cat_repos, key=lambda x: -x['stars'])[:5]
        
        lines.append(f"### {cat_name} ({count})\n\n")
        for r in top5:
            lang = r.get('lang') or '-'
            lines.append(f"- ⭐ {r['stars']:,} │ [{r['name']}](https://github.com/{r['name']}) `({lang})`\n")
        if count > 5:
            safe_cat = cat_name.replace(' ', '-').replace('🧠', '')
            lines.append(f"- [... 查看全部 {count} 个](#{safe_cat})\n")
        lines.append("\n")
    
    # Languages
    lines.append("\n## 💻 Languages\n\n")
    langs = sorted(stats['by_language'].items(), key=lambda x: -x[1])
    for lang, count in langs[:20]:
        pct = count / stats['total'] * 100
        bar = '█' * int(pct / 2)
        lines.append(f"- {lang:<20} {count:>4} ({pct:4.1f}%) {bar}\n")
    
    # Data link
    lines.append("\n---\n\n")
    lines.append(f"📁 [data/stars.json](data/stars.json) - Full raw data\n")
    lines.append(f"📊 [data/stats.json](data/stats.json) - Statistics\n")
    
    lines.append("\n*Auto-generated by [stars-archive](https://github.com/gandli/stars-archive)*\n")
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    print(f"✅ Generated README.md with {len(repos)} repos")

if __name__ == "__main__":
    generate_readme()
