#!/usr/bin/env python3
"""
translator.py - 统一翻译模块

功能:
- 并发翻译 (ThreadPoolExecutor + 12 workers)
- 指数退避重试 (429 / 503 限流)
- 增量缓存 (只翻译未翻译的)
- 中英文混合描述智能跳过

输出: data/desc-cn.json {repo_id: chinese_description}

用法:
    python scripts/translator.py                # 运行完整翻译
    python scripts/translator.py --max-workers 12 --rate-limit 0.3
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

ENRICHED_FILE = DATA_DIR / "stars-enriched.json"
OUTPUT_FILE = DATA_DIR / "desc-cn.json"
META_FILE = DATA_DIR / "translation-meta.json"

# MyMemory API (免费, 无需 key, 限流 5 请求/10 秒)
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
DEFAULT_RATE_LIMIT = 0.3  # 秒/请求 (12 workers × 0.3s ≈ 3.6 请求/秒, 安全)
MAX_WORKERS = 12
MAX_RETRIES = 3


def truncate(text: str, max_chars: int = 500) -> str:
    """截断过长文本"""
    if not text:
        return ""
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def is_chinese(text: str) -> bool:
    """检查是否包含中文字符"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def translate_single(text: str, src: str = "en", dst: str = "zh") -> str:
    """翻译单段文本, 带指数退避重试"""
    if not text or len(text.strip()) < 10:
        return ""

    if is_chinese(text):
        return text

    text = truncate(text, 500)
    params = urlencode({"q": text, "langpair": f"{src}|{dst}"})

    for attempt in range(MAX_RETRIES):
        try:
            req = Request(
                f"{MYMEMORY_URL}?{params}",
                headers={"User-Agent": "StarsArchive/2.0"},
            )
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                translated = result.get("responseData", {}).get("translatedText", "")
                # 过滤明显失败的返回 (MyMemory 有时返回原文)
                if translated and translated != text:
                    return translated
                return ""
        except HTTPError as e:
            if e.code == 429:
                wait = min(2 ** attempt * 5, 60)
                print(f"  429限流, 等待 {wait}s (尝试 {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
            elif e.code >= 500:
                wait = 2 ** attempt * 2
                print(f"  {e.code}错误, 等待 {wait}s")
                time.sleep(wait)
            else:
                break
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(1)

    return ""


def load_existing() -> dict:
    """加载已翻译的缓存"""
    if OUTPUT_FILE.exists():
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    return {}


def save_results(results: dict, meta: Optional[dict] = None):
    """增量保存翻译结果"""
    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if meta:
        META_FILE.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="批量翻译星标仓库描述")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--rate-limit", type=float, default=DEFAULT_RATE_LIMIT)
    parser.add_argument("--dry-run", action="store_true", help="只显示统计, 不翻译")
    args = parser.parse_args(argv)

    # 加载数据
    with open(ENRICHED_FILE, "r", encoding="utf-8") as f:
        repos = json.load(f)
    print(f"📊 加载 {len(repos)} 个仓库")

    # 加载已有翻译
    existing = load_existing()
    print(f"💾 已缓存翻译: {len(existing)} 条")

    # 筛选待翻译列表
    candidates = []
    for repo in repos:
        repo_id = str(repo.get("id") or repo.get("full_name", ""))
        if repo_id in existing:
            continue
        desc = repo.get("desc") or ""
        if len(desc.strip()) < 10:
            continue
        if is_chinese(desc):
            existing[repo_id] = desc
            continue
        candidates.append(repo)

    print(f"🎯 待翻译: {len(candidates)} 个仓库")

    if args.dry_run:
        print("dry-run 模式, 不实际翻译")
        return

    if not candidates:
        print("✅ 所有仓库已有翻译")
        return

    # 并发翻译
    results = dict(existing)
    done = 0
    start_time = time.time()
    rate_limiter = RateLimiter(args.rate_limit)

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                translate_single_with_limiter, repo, rate_limiter
            ): repo
            for repo in candidates
        }

        for future in as_completed(futures):
            repo = futures[future]
            repo_id = str(repo.get("id") or repo.get("full_name", ""))
            try:
                cn = future.result()
                if cn:
                    results[repo_id] = cn
            except Exception as e:
                print(f"  ❌ {repo_id}: {e}")

            done += 1
            if done % 50 == 0 or done == len(candidates):
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                print(
                    f"  [{done}/{len(candidates)}] {100*done/len(candidates):.0f}% "
                    f"({rate:.1f}/s, 已用时 {elapsed:.0f}s"
                )
                # 每 50 次增量保存
                save_results(results)

    # 最终保存
    meta = {
        "total_translated": len(results),
        "total_candidates": len(candidates),
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workers": args.max_workers,
        "rate_limit": args.rate_limit,
    }
    save_results(results, meta)

    elapsed = time.time() - start_time
    print(f"\n✅ 翻译完成:")
    print(f"   总缓存: {len(results)} 条")
    print(f"   本次新增: {len(results) - len(existing)} 条")
    print(f"   耗时: {elapsed:.1f}s ({elapsed/max(len(candidates),1)*1000:.0f}ms/条)")


class RateLimiter:
    """简单令牌桶限流"""

    def __init__(self, interval: float):
        self.interval = interval
        self.last_call = 0
        self._lock = __import__("threading").Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            wait_time = self.interval - (now - self.last_call)
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_call = time.time()


def translate_single_with_limiter(repo: dict, limiter: RateLimiter) -> str:
    """带限流的单条翻译"""
    limiter.wait()
    desc = repo.get("desc") or ""
    return translate_single(desc)


if __name__ == "__main__":
    main()
