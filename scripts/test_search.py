#!/usr/bin/env python3
"""Test BM25 and semantic search in multiple languages."""

import json
import numpy as np
from sentence_transformers import SentenceTransformer
import time

DATA_DIR = '/Users/user/.hermes/hermes-agent/stars-archive/data'

# Load repos and ensure consistent ordering
with open(f'{DATA_DIR}/stars.json') as f:
    stars_raw = json.load(f)
# Build id -> repo map
id_to_repo = {str(r['id']): r for r in stars_raw}
# Use hnsw_ids ordering (matches vectors.bin order)
hnsw_ids = json.load(open(f'{DATA_DIR}/hnsw_ids.json'))
repos = [id_to_repo[rid] for rid in hnsw_ids if rid in id_to_repo]
ids = hnsw_ids[:len(repos)]
print(f"Loaded {len(repos)} repos (ordered by hnsw_ids)\n")

def tokenize(text):
    if not text: return []
    text = text.lower()
    chinese = list(text)
    bigrams = [chinese[i]+chinese[i+1] for i in range(len(chinese)-1)]
    english = text.split()
    return list(set(bigrams + english))

def get_search_text(repo):
    parts = [
        repo.get('name', ''),
        repo.get('desc', ''),
        repo.get('desc_cn') or '',
        repo.get('lang_category', ''),
        ' '.join(repo.get('topics', [])),
        ' '.join(repo.get('auto_tags', [])),
    ]
    return ' '.join(p for p in parts if p).strip()

def buildBM25(tokenArrays, k1=1.5, b=0.75):
    N = len(tokenArrays)
    docLens = [len(t) for t in tokenArrays]
    avgdl = sum(docLens) / N
    df = {}
    for tokens in tokenArrays:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    idf = {t: max(np.log((N - n + 0.5) / (n + 0.5) + 1), 0) for t, n in df.items()}
    tokenArrays_ref = tokenArrays
    docLens_ref = docLens
    idf_ref = idf
    avgdl_ref = avgdl
    N_ref = N
    def score_fn(tokens):
        score = [0.0] * N_ref
        tf_map = {}
        for t in tokens: tf_map[t] = tf_map.get(t, 0) + 1
        for term, tf in tf_map.items():
            idf_val = idf_ref.get(term, 0)
            if idf_val <= 0: continue
            for i in range(N_ref):
                doc_tf = tokenArrays_ref[i].count(term)
                score[i] += idf_val * (doc_tf * (k1 + 1)) / (doc_tf + k1 * (1 - b + b * docLens_ref[i] / avgdl_ref))
        return score
    return {'score': score_fn}

# Build BM25 index
print("Building BM25 index...")
texts = [tokenize(get_search_text(r)) for r in repos]
bm25 = buildBM25(texts)
print("BM25 ready\n")

# Load sentence transformer for semantic search
print("Loading multilingual model...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
vectors = np.frombuffer(open(f'{DATA_DIR}/vectors.bin', 'rb').read()[8:], dtype=np.float32).reshape(len(repos), -1).copy()
norms = np.linalg.norm(vectors, axis=1, keepdims=True)
vectors /= (norms + 1e-8)
print("Model loaded\n")


def bm25_search(query, k=5):
    tokens = tokenize(query)
    scores = bm25['score'](tokens)
    results = [(i, ids[i], scores[i]) for i in range(len(scores)) if scores[i] > 0]
    results.sort(key=lambda x: -x[2])
    return results[:k]


def semantic_search(query, k=5):
    qvec = model.encode([query]).astype(np.float32).ravel()  # (384,)
    qvec /= np.linalg.norm(qvec)
    sims = vectors @ qvec  # (N,) cosine similarity
    topk = np.argpartition(sims, -k)[-k:]
    topk = topk[np.argsort(-sims[topk])]
    return [(int(i), ids[int(i)], float(sims[int(i)])) for i in topk]


queries = [
    ("中文关键词", "机器学习 python"),
    ("英文关键词", "web framework"),
    ("混排关键词", "React UI component"),
    ("中文语义", "帮我找一个命令行工具"),
    ("英文语义", "terminal cli tool"),
    ("中文语义", "好看的前端UI组件库"),
]

print("=" * 60)
for label, query in queries:
    mode = "BM25" if "关键词" in label else "语义"
    print(f"[{mode}] {label}: \"{query}\"")

    start = time.time()
    if "BM25" in label:
        results = bm25_search(query)
    else:
        results = semantic_search(query)
    elapsed = time.time() - start

    if not results:
        print("  (no results)\n")
        continue

    for rank, (idx, rid, score) in enumerate(results):
        repo = repos[idx]
        lang = repo.get('lang', '-')
        name = repo.get('name', '-')
        desc = (repo.get('desc_cn') or repo.get('desc', ''))[:60]
        print(f"  {rank+1}. [{score:.3f}] {name} (lang={lang})")
        print(f"      {desc}")
    print(f"  ⏱ {elapsed*1000:.1f}ms\n")
