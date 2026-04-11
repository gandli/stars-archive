#!/usr/bin/env python3
"""
generate_vectors.py

使用 sentence-transformers 生成 stars-enriched.json 中每个项目的向量嵌入。
输出: data/vectors.json

使用:
    source .venv/bin/activate
    python scripts/generate_vectors.py

模型: all-MiniLM-L6-v2 (384维, ~90MB, 首次自动下载缓存)
索引字段: name + (desc_cn || desc) + topics + lang_category + auto_tags
"""

import json
import os
import sys
from pathlib import Path
from tqdm import tqdm

# Setup path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Model config
MODEL_NAME = 'all-MiniLM-L6-v2'
EMBEDDING_DIM = 384
BATCH_SIZE = 64

def get_search_text(repo):
    """组合可搜索文本"""
    parts = [
        repo.get('name', ''),
        repo.get('desc_cn') or repo.get('desc', ''),
        repo.get('lang_category', ''),
        ' '.join(repo.get('topics', [])),
        ' '.join(repo.get('auto_tags', [])),
    ]
    return ' '.join(p for p in parts if p).strip()

def normalize_text(text):
    """简单文本清理"""
    if not text:
        return ''
    text = text.lower()
    # 保留 Unicode 字母、数字、空格
    import re
    text = re.sub(r'[^a-z0-9\u4e00-\u9fff\s]', ' ', text)  # ASCII + CJK
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def cosine_similarity(a, b):
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)

def knn_search(query_vec, vectors, k=10):
    """朴素最近邻搜索"""
    scores = []
    for idx, vec in enumerate(vectors):
        score = cosine_similarity(query_vec, vec)
        scores.append((idx, score))
    scores.sort(key=lambda x: -x[1])
    return scores[:k]

def main():
    print(f"\n🚀 Vector Generator for stars-archive")
    print("=" * 50)
    
    enriched_file = ROOT / 'data' / 'stars-enriched.json'
    vectors_file = ROOT / 'data' / 'vectors.json'
    meta_file = ROOT / 'data' / 'vectors-meta.json'
    
    # Load data
    print("\n📖 Loading stars-enriched.json...")
    with open(enriched_file, 'r', encoding='utf-8') as f:
        repos = json.load(f)
    print(f"   Loaded {len(repos)} repos")
    
    # Load existing vectors for incremental update
    existing = {}
    if vectors_file.exists():
        print("\n📂 Found existing vectors.json, loading...")
        with open(vectors_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing_ids = set(existing.keys())
        current_ids = {str(r['id']) for r in repos}
        
        # Remove deleted repos
        removed = existing_ids - current_ids
        if removed:
            print(f"   Removing {len(removed)} deleted repos from index")
            for rid in removed:
                del existing[rid]
        
        up_to_date = sum(1 for r in repos if str(r['id']) in existing)
        print(f"   Already indexed: {up_to_date}/{len(repos)}")
    
    # Find repos needing embedding
    to_embed = []
    to_embed_indices = []
    for idx, repo in enumerate(repos):
        repo_id = str(repo['id'])
        if repo_id not in existing:
            to_embed.append(normalize_text(get_search_text(repo)))
            to_embed_indices.append(idx)
    
    if not to_embed:
        print("\n✅ All repos already indexed!")
    else:
        print(f"\n📝 Need to embed {len(to_embed)} new repos")
        
        # Import and load model
        print(f"\n📦 Loading model: {MODEL_NAME}")
        print("   (First run: ~90MB download, cached in ~/.cache/huggingface/)")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME)
        print("   Model loaded!")
        
        # Generate embeddings in batches
        print("\n🔢 Generating embeddings...")
        embeddings = model.encode(
            to_embed,
            batch_size=BATCH_SIZE,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        print(f"   Generated {len(embeddings)} embeddings, shape: {embeddings.shape}")
        
        # Merge into existing
        for i, data_idx in enumerate(to_embed_indices):
            repo_id = str(repos[data_idx]['id'])
            existing[repo_id] = embeddings[i].tolist()
        
        print(f"\n✅ {len(to_embed)} new repos indexed!")
    
    # Stats
    all_vectors = list(existing.values())
    print(f"\n📊 Total vectors indexed: {len(all_vectors)}")
    print(f"   Vector dimension: {EMBEDDING_DIM}")
    size_mb = len(all_vectors) * EMBEDDING_DIM * 4 / 1024 / 1024
    print(f"   Estimated size: {size_mb:.2f} MB")
    
    # Sanity check
    if all_vectors:
        print("\n🧪 Sanity check: test search...")
        from sentence_transformers import util
        test_queries = [
            'machine learning framework python',
            'cli tool for terminal',
            'web framework javascript',
        ]
        
        test_texts = [normalize_text(get_search_text(r)) for r in repos]
        test_embeddings = model.encode(test_queries, convert_to_numpy=True, normalize_embeddings=True)
        
        for qi, query in enumerate(test_queries):
            query_emb = test_embeddings[qi]
            cos_scores = util.cos_sim(query_emb, embeddings if to_embed else list(existing.values()))[0]
            top_indices = cos_scores.argsort(descending=True)[:3]
            print(f"\n   Query: '{query}'")
            for rank, data_idx in enumerate(top_indices):
                repo = repos[data_idx]
                print(f"     {rank+1}. [{cos_scores[data_idx]:.3f}] {repo.get('name', '?')}")
    
    # Save
    print("\n💾 Saving vectors.json...")
    with open(vectors_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f)
    
    meta = {
        'model': MODEL_NAME,
        'dimension': EMBEDDING_DIM,
        'count': len(all_vectors),
        'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'indexed_fields': ['name', 'desc_cn', 'desc', 'lang_category', 'topics', 'auto_tags'],
    }
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    
    print("\n✅ Done! vectors.json ready for upload.")
    print(f"   Run: git add data/ && git commit -m 'Add vector embeddings'")

if __name__ == '__main__':
    main()
