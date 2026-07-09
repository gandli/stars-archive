#!/usr/bin/env python3
"""Export multilingual vectors + knn index as binary ArrayBuffers for web worker.

Format (ArrayBuffer):
  vectors.bin:  [N:u32][dim:u32][float32[N*dim]]
  knn.bin:      [K:u32][N:u32][indices:u32[N*K]][distances:float32[N*K]]
  ids.json:     string[] — same order as vector rows
"""

import os, json, struct, numpy as np
from pathlib import Path

# 优先使用环境变量，其次使用相对于脚本的路径
DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent.parent / 'data'))
OUT = DATA_DIR

# ── 1. Load order from hnsw_ids.json ─────────────────────────────────────
hnsw_ids = json.load(open(f'{DATA_DIR}/hnsw_ids.json'))
N = len(hnsw_ids)
meta = json.load(open(f'{DATA_DIR}/vectors-meta.json'))
dim = meta.get('dim', 384)

# ── 2. Read multilingual vectors from vectors.bin ─────────────────────────
with open(f'{DATA_DIR}/vectors.bin', 'rb') as f:
    f.read(8)  # skip header
    vectors_flat = np.frombuffer(f.read(), dtype=np.float32).copy()

assert len(vectors_flat) == N * dim, f"{len(vectors_flat)} != {N}*{dim}"

# Write vectors.bin (N, dim, flat floats)
vec_bytes = struct.pack('<II', N, dim) + vectors_flat.astype(np.float32).tobytes()
with open(f'{OUT}/vectors.bin', 'wb') as f:
    f.write(vec_bytes)
print(f"✓ vectors.bin  {N}x{dim}  {len(vec_bytes)//1024} KB")

# ── 3. Read & re-export knn_index.bin ────────────────────────────────────
with open(f'{DATA_DIR}/knn_index.bin', 'rb') as f:
    k = struct.unpack('<I', f.read(4))[0]
    indices_flat = np.frombuffer(f.read(N * k * 4), dtype=np.uint32).copy()
    distances_flat = np.frombuffer(f.read(N * k * 4), dtype=np.float32).copy()

knn_bytes = struct.pack('<II', k, N) + indices_flat.astype(np.uint32).tobytes() + distances_flat.astype(np.float32).tobytes()
with open(f'{OUT}/knn.bin', 'wb') as f:
    f.write(knn_bytes)
print(f"✓ knn.bin       K={k}, N={N}  {len(knn_bytes)//1024} KB")

# ── 4. ids.json ───────────────────────────────────────────────────────────
with open(f'{OUT}/ids.json', 'w') as f:
    json.dump(hnsw_ids, f)
print(f"✓ ids.json      {N} ids")

# ── 5. Cleanup old JSON (optional) ───────────────────────────────────────
import os
for old in ['vectors.json', 'knn_index.json']:
    path = f'{OUT}/{old}'
    if os.path.exists(path):
        os.remove(path)
        print(f"  removed {old}")

print("\n✅ Binary web files ready!")
