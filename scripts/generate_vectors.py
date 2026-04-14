#!/usr/bin/env python3
"""
generate_vectors.py

Optimized vector embedding pipeline for stars-archive:

1. Generate embeddings using sentence-transformers (all-MiniLM-L6-v2)
2. Build HNSW approximate nearest neighbor index for fast search
3. Export binary vectors + HNSW index for browser consumption

Usage:
    source .venv/bin/activate
    python scripts/generate_vectors.py

Outputs:
    data/vectors.json       - Raw vectors (JSON, for backward compat)
    data/vectors.bin        - Binary Float32 vectors (new, ~3x smaller)
    data/hnsw_index.bin     - HNSW index for fast ANN search
    data/hnsw_ids.json      - ID mapping: index position -> repo id
    data/hnsw-meta.json      - Index metadata
    data/vectors-meta.json  - Vector metadata
"""

import json
import os
import sys
import time
import shutil
from pathlib import Path

import numpy as np

# Setup path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Model config — multilingual MiniLM: supports 50+ languages including Chinese
# Matches Xenova/m站-base (ONNX) used in browser for text encoding
MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
EMBEDDING_DIM = 384
BATCH_SIZE = 64

# HNSW config
HNSW_M = 16                    # connections per layer
HNSW_EF_CONSTRUCTION = 200   # build quality
HNSW_EF_SEARCH = 128          # search quality


def get_search_text(repo):
    """Build multilingual search text including Chinese descriptions."""
    parts = [
        repo.get('name', ''),
        repo.get('desc', ''),
        repo.get('desc_cn') or '',        # ← include Chinese translation
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
    import re
    text = re.sub(r'[^a-z0-9\u4e00-\u9fff\s]', ' ', text)  # ASCII + CJK
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def build_hnsw_index(vectors_list, ids):
    """Build HNSW approximate nearest neighbor index.
    
    Args:
        vectors_list: List of float32 vectors
        ids: List of repo IDs (strings) corresponding to vectors
    
    Returns:
        HNSW index ready for search
    """
    try:
        import hnswlib
    except ImportError:
        print("  ⚠️  hnswlib not installed. Run: uv pip install hnswlib")
        return None

    print(f"\n  Building HNSW index ({len(vectors_list)} elements, dim={EMBEDDING_DIM})...")
    
    # Create index with cosine similarity
    index = hnswlib.Index(space='cosine', dim=EMBEDDING_DIM)
    index.init_index(
        max_elements=len(vectors_list),
        M=HNSW_M,
        ef_construction=HNSW_EF_CONSTRUCTION,
        random_seed=42,
    )
    index.set_ef(HNSW_EF_SEARCH)

    # Convert to normalized numpy array
    vectors_np = np.array(vectors_list, dtype=np.float32)
    norms = np.linalg.norm(vectors_np, axis=1, keepdims=True)
    vectors_np = vectors_np / (norms + 1e-10)

    start = time.time()
    index.add_items(vectors_np, np.arange(len(vectors_list)))
    print(f"  ✅ Added {len(vectors_list)} vectors in {time.time()-start:.2f}s")

    return index


def export_binary_vectors(vectors, ids):
    """Export vectors as binary Float32 array.
    
    Binary format: [num_vectors: uint32][dim: uint32][vectors: float32[num_vectors*dim]]
    This is ~3x smaller than JSON encoding.
    """
    data_dir = ROOT / 'data'
    binary_file = data_dir / 'vectors.bin'
    
    num_vectors = len(ids)
    
    # Build id -> index mapping
    id_to_idx = {str(id_): i for i, id_ in enumerate(ids)}
    
    # Create contiguous float32 array
    vec_array = np.zeros((num_vectors, EMBEDDING_DIM), dtype=np.float32)
    for i, id_ in enumerate(ids):
        vec_array[i] = vectors[id_]
    
    # Write binary file: header + data
    with open(binary_file, 'wb') as f:
        # Header: num_vectors (4 bytes) + dim (4 bytes)
        np.array([num_vectors], dtype=np.uint32).tofile(f)
        np.array([EMBEDDING_DIM], dtype=np.uint32).tofile(f)
        # Data: flat float32 array
        vec_array.astype('<f4').tofile(f)
    
    size_mb = os.path.getsize(binary_file) / 1024 / 1024
    json_size = sum(len(json.dumps(v)) for v in vectors.values()) / 1024 / 1024
    print(f"  📦 Binary vectors: {size_mb:.2f} MB (vs JSON: {json_size:.2f} MB, {json_size/size_mb:.1f}x smaller)")
    
    return binary_file


def build_knn_index(vectors_ordered, ids_ordered, k=20):
    """Build pre-computed exact k-NN index for O(1) similar-repo queries.

    Format: [K: uint32]
            [indices: uint32[N*K]]  — row-major, each row = k nearest indices
            [distances: float32[N*K]] — cosine distances, same layout

    Args:
        vectors_ordered: List (or np array) of normalized float32 vectors, shape (N, dim)
        ids_ordered: List of string repo IDs, length N
        k: Number of nearest neighbors per repo

    Returns:
        Tuple of (knn_indices: Uint32Array, knn_distances: Float32Array)
    """
    import time as time_
    data_dir = ROOT / 'data'
    knn_file = data_dir / 'knn_index.bin'

    print(f"\n  Building pre-computed k-NN index (k={k}, N={len(vectors_ordered)})...")

    # Normalize vectors
    vectors_np = np.array(vectors_ordered, dtype=np.float32)
    N = len(vectors_np)

    # cosine similarity = dot product (vectors are pre-normalized)
    # For exact k-NN we compute all pairwise similarities efficiently
    # Using chunks to avoid O(N²) memory spike
    chunk_size = 500
    all_indices = np.zeros((N, k), dtype=np.uint32)
    all_distances = np.zeros((N, k), dtype=np.float32)

    start = time_.time()

    for chunk_start in range(0, N, chunk_size):
        chunk_end = min(chunk_start + chunk_size, N)
        chunk = vectors_np[chunk_start:chunk_end]          # (chunk, dim)
        # (chunk, dim) @ (dim, N) = (chunk, N)
        sims = chunk @ vectors_np.T                         # cosine similarity

        # For each repo in chunk, find top-k
        for i_local, i_global in enumerate(range(chunk_start, chunk_end)):
            row = sims[i_local]
            # Exclude self (distance = 1.0 since normalized)
            row[i_global] = -np.inf
            topk_idx = np.argpartition(row, k - 1)[:k]       # partial sort O(N*k)
            topk_idx = topk_idx[np.argsort(-row[topk_idx])] # full sort
            all_indices[i_global] = topk_idx.astype(np.uint32)
            # cosine distance = 1 - cos_similarity; dot = similarity (pre-normalized)
            all_distances[i_global] = 1.0 - row[topk_idx]

        done = chunk_end
        elapsed = time_.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (N - done) / rate if rate > 0 else 0
        print(f"    {done}/{N} ({done/N*100:.0f}%) — {elapsed:.1f}s elapsed, ~{eta:.1f}s remaining")

    # Write binary: K(uint32) + indices(uint32[N*K]) + distances(float32[N*K])
    with open(knn_file, 'wb') as f:
        # K header
        np.array([k], dtype=np.uint32).tofile(f)
        # Indices: flat uint32
        all_indices.astype(np.uint32).tofile(f)
        # Distances: flat float32
        all_distances.astype(np.float32).tofile(f)

    size_mb = os.path.getsize(knn_file) / 1024 / 1024
    print(f"  ✅ k-NN index: {size_mb:.2f} MB (k={k}, N={N})")

    return all_indices, all_distances


def save_hnsw_index(index, ids):
    """Save HNSW index and metadata."""
    data_dir = ROOT / 'data'
    
    # Save index binary
    index_file = data_dir / 'hnsw_index.bin'
    start = time.time()
    index.save_index(str(index_file))
    print(f"  💾 HNSW index saved in {time.time()-start:.2f}s")

    # Save ID mapping (index position -> repo id)
    ids_file = data_dir / 'hnsw_ids.json'
    with open(ids_file, 'w', encoding='utf-8') as f:
        json.dump(ids, f, ensure_ascii=False)
    
    # Save metadata
    meta = {
        'model': MODEL_NAME,
        'dimension': EMBEDDING_DIM,
        'count': len(ids),
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'indexed_fields': ['name', 'desc_cn', 'desc', 'lang_category', 'topics', 'auto_tags'],
        'hnsw': {
            'M': HNSW_M,
            'ef_construction': HNSW_EF_CONSTRUCTION,
            'ef_search': HNSW_EF_SEARCH,
            'space': 'cosine',
            'normalized': True,
        }
    }
    meta_file = data_dir / 'hnsw-meta.json'
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    
    # Vector metadata
    vec_meta = {
        'model': MODEL_NAME,
        'dimension': EMBEDDING_DIM,
        'count': len(ids),
        'generated_at': meta['generated_at'],
        'indexed_fields': meta['indexed_fields'],
        'binary': True,
        'hnsw_available': True,
    }
    vec_meta_file = data_dir / 'vectors-meta.json'
    with open(vec_meta_file, 'w', encoding='utf-8') as f:
        json.dump(vec_meta, f, indent=2)
    
    size_mb = os.path.getsize(index_file) / 1024 / 1024
    print(f"  ✅ HNSW index: {size_mb:.2f} MB ({len(ids)} vectors)")


def main():
    print(f"\n🚀 Optimized Vector Generator for stars-archive")
    print(f"   Model: {MODEL_NAME} (dim={EMBEDDING_DIM})")
    print(f"   HNSW: M={HNSW_M}, ef_c={HNSW_EF_CONSTRUCTION}, ef_s={HNSW_EF_SEARCH}")
    print("=" * 60)
    
    data_dir = ROOT / 'data'
    enriched_file = data_dir / 'stars-enriched.json'
    vectors_file = data_dir / 'vectors.json'
    
    # Load data
    print(f"\n📖 Loading stars-enriched.json...")
    with open(enriched_file, 'r', encoding='utf-8') as f:
        repos = json.load(f)
    print(f"   Loaded {len(repos)} repos")
    
    # Load existing vectors for incremental update
    existing = {}
    if vectors_file.exists():
        print(f"\n📂 Loading existing vectors.json...")
        with open(vectors_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing_ids = set(str(k) for k in existing.keys())
        current_ids = {str(r['id']) for r in repos}
        
        # Remove deleted repos
        removed = existing_ids - current_ids
        if removed:
            print(f"   Removing {len(removed)} deleted repos from index")
            for rid in removed:
                del existing[str(rid)]
        
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
        print(f"\n✅ All repos already indexed!")
    else:
        print(f"\n📝 Need to embed {len(to_embed)} new repos")
        
        # Import and load model
        print(f"\n📦 Loading model: {MODEL_NAME}")
        print(f"   (First run: ~90MB download, cached in ~/.cache/huggingface/)")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL_NAME)
        print(f"   Model loaded!")
        
        # Generate embeddings in batches
        print(f"\n🔢 Generating embeddings...")
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
    
    # Ensure consistent ordering
    ids_ordered = [str(r['id']) for r in repos if str(r['id']) in existing]
    vectors_ordered = [existing[str(r['id'])] for r in repos if str(r['id']) in existing]
    
    # Stats
    all_vectors = list(existing.values())
    print(f"\n📊 Total vectors indexed: {len(all_vectors)}")
    print(f"   Vector dimension: {EMBEDDING_DIM}")
    size_mb = len(all_vectors) * EMBEDDING_DIM * 4 / 1024 / 1024
    print(f"   Float32 size: {size_mb:.2f} MB")
    
    # Save vectors.json (for backward compat)
    print(f"\n💾 Saving vectors.json...")
    with open(vectors_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f)
    
    # Export binary vectors
    export_binary_vectors(existing, ids_ordered)
    
    # Build HNSW index
    print(f"\n🗂️  Building HNSW index...")
    index = build_hnsw_index(vectors_ordered, ids_ordered)
    if index is not None:
        save_hnsw_index(index, ids_ordered)

    # Build pre-computed exact k-NN index for O(1) similar-repo queries
    print(f"\n🗂️  Building pre-computed k-NN index...")
    knn_indices, knn_distances = build_knn_index(vectors_ordered, ids_ordered, k=20)
    print(f"  ✅ Pre-computed k-NN index ready")

    if index is not None:
        # Benchmark
        print(f"\n⚡ Benchmarking HNSW search...")
        test_queries = [
            'machine learning framework python',
            'cli tool for terminal',
            'web framework javascript',
        ]

        for qi, q in enumerate(test_queries):
            query_vec = np.array([vectors_ordered[qi % len(vectors_ordered)]], dtype=np.float32)
            times = []
            for _ in range(30):
                start = time.time()
                labels, distances = index.knn_query(query_vec, k=10)
                times.append(time.time() - start)
            avg_ms = sum(times) / len(times) * 1000
            print(f"   Query {qi+1}: {avg_ms:.2f}ms/query ({q[:40]}...)")

        # Sanity check
        print(f"\n🧪 Sanity check - top-5 for first repo:")
        query_vec = np.array([vectors_ordered[0]], dtype=np.float32)
        labels, distances = index.knn_query(query_vec, k=5)
        for rank, (label, dist) in enumerate(zip(labels[0], distances[0])):
            repo = repos[int(label)] if int(label) < len(repos) else None
            name = repo['name'] if repo else f"idx:{label}"
            print(f"     {rank+1}. [{dist:+.4f}] {name}")
    
    print(f"\n✅ Done! All files ready for upload:")
    print(f"   data/vectors.json      - Raw vectors (backward compat)")
    print(f"   data/vectors.bin        - Binary vectors (new, faster load)")
    print(f"   data/hnsw_index.bin     - HNSW index (fast ANN search)")
    print(f"   data/hnsw_ids.json      - ID mapping")
    print(f"   data/hnsw-meta.json     - HNSW metadata")
    print(f"   data/vectors-meta.json  - Vector metadata")
    print(f"\n   Run: git add data/ && git commit -m 'Add HNSW index for fast search'")

if __name__ == '__main__':
    main()
