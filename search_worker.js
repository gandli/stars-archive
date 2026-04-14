/**
 * search_worker.js v2
 *
 * Multi-modal search engine for stars-archive:
 *  - Semantic: transformers.js + multilingual ONNX model → text → vector → cosine KNN
 *  - Keyword:  BM25 with Chinese-aware tokenization (regex + n-gram)
 *  - Hybrid:   Reciprocal Rank Fusion of semantic + BM25 scores
 *
 * Binary formats:
 *   vectors.bin:  [num_vectors: uint32][dim: uint32][float32[row-major]]
 *   knn_index.bin: [K: uint32][N*K uint32 indices][N*K float32 distances]
 *
 * Transformer model: paraphrase-multilingual-MiniLM-L12-v2 (ONNX, 384-dim, ~83MB)
 *   Loaded lazily on first semantic search. Cached in IndexedDB after first load.
 */

'use strict';

// ================================================================
// State
// ================================================================
let baseUrl = null;  // set via 'setBaseUrl' message from main page

const state = {
  numVectors: 0,
  dim: 0,            // 384 (MiniLM)
  ids: [],           // string repo IDs, ordered to match vector index
  vectors: null,     // Float32Array, flat row-major

  // Pre-computed k-NN (O(1) similar repo lookup)
  knnK: 0,
  knnIndices: null,
  knnDistances: null,

  // Reverse lookup: repo ID string → vector index
  idToIdx: new Map(),

  // Transformers.js model (loaded lazily)
  encoder: null,
  modelReady: false,
  modelLoading: false,
  modelLoadingResolve: null,

  // BM25 index (built lazily)
  bm25: null,
  bm25Ready: false,

  // Enriched repo text for BM25 (lazy build)
  bm25Texts: null,  // [{id, tokens, raw}] in same order as vectors
};

// ================================================================
// Cosine KNN
// ================================================================
function cosineDist(a, offsetA, b) {
  let dot = 0;
  for (let i = 0; i < state.dim; i++) {
    dot += a[offsetA + i] * b[i];
  }
  // Vectors are pre-normalized, so cos_dist ≈ 1 - dot
  return 1 - dot;
}

/**
 * Full-scan KNN. Returns top-k most similar (lowest cosine distance).
 * @param {Float32Array} queryVec - normalized query vector, length = dim
 * @param {number} k
 * @returns {Array<{id, idx, dist}>}
 */
function knnSearch(queryVec, k) {
  const { numVectors, dim, vectors, ids } = state;
  // Min-heap of size k
  const heap = [];
  for (let i = 0; i < k; i++) heap.push({ idx: 0, dist: Infinity });

  for (let v = 0; v < numVectors; v++) {
    const dist = cosineDist(vectors, v * dim, queryVec);
    if (dist < heap[k - 1].dist) {
      let pos = k - 1;
      while (pos > 0 && heap[pos - 1].dist > dist) {
        heap[pos] = heap[pos - 1];
        pos--;
      }
      heap[pos] = { idx: v, dist };
    }
  }

  heap.sort((a, b) => a.dist - b.dist);
  return heap.map(h => ({ id: ids[h.idx], idx: h.idx, dist: h.dist }));
}

// ================================================================
// BM25 Keyword Search (Chinese-aware)
// ================================================================

/** Simple Chinese tokenizer using regex n-gram + English word splitting */
function tokenize(text) {
  if (!text) return [];
  text = text.toLowerCase();
  // Split: Chinese chars (1-gram + 2-gram sliding), English/alphanumeric words
  const chinese = text.match(/[\u4e00-\u9fff]/g) || [];
  const bigrams = [];
  for (let i = 0; i < chinese.length - 1; i++) bigrams.push(chinese[i] + chinese[i + 1]);
  const english = (text.match(/[a-z0-9]{2,}/g) || []);
  // Deduplicate bigrams
  const bgSet = new Set(bigrams);
  const enSet = new Set(english);
  return [...enSet, ...chinese, ...bgSet];
}

/** Build BM25 index from an array of token arrays */
function buildBM25(tokenArrays, k1 = 1.5, b = 0.75) {
  const N = tokenArrays.length;
  const avgdl = tokenArrays.reduce((s, t) => s + t.length, 0) / N;

  // Document frequencies
  const df = new Map();
  for (const tokens of tokenArrays) {
    const seen = new Set(tokens);
    for (const t of seen) df.set(t, (df.get(t) || 0) + 1);
  }

  // Pre-compute IDF
  const idf = new Map();
  for (const [term, freq] of df) {
    idf.set(term, Math.log((N - freq + 0.5) / (freq + 0.5) + 1));
  }

  // Store doc lengths
  const docLens = tokenArrays.map(t => t.length);

  return {
    k1, b, avgdl, docLens, idf, N, tokenArrays,
    /** Score a single token array against the index */
    score(tokens) {
      const score = new Array(N).fill(0);
      const tfMap = new Map();
      for (const t of tokens) tfMap.set(t, (tfMap.get(t) || 0) + 1);

      for (const [term, tf] of tfMap) {
        const idfVal = idf.get(term) || 0;
        if (idfVal <= 0) continue;
        for (let i = 0; i < N; i++) {
          // FIX: use tokenArrays (document tokens), not search tokens
          const docTf = this.tokenArrays[i].filter(t => t === term).length;
          score[i] += idfVal * (docTf * (k1 + 1)) / (docTf + k1 * (1 - b + b * docLens[i] / avgdl));
        }
      }
      return score;
    }
  };
}

/* Build BM25 index from an array of token arrays */
/**
 * Build the BM25 index from loaded repo data.
 * Sends progress updates via postMessage.
 */
async function buildBm25Index() {
  self.postMessage({ type: 'status', text: '构建关键词索引...' });

  const ids = state.ids;
  const texts = new Array(ids.length);

  // Load enriched data for BM25 text fields
  try {
    const resp = await fetch(baseUrl + 'data/stars-enriched.json');
    if (!resp.ok) throw new Error('Failed to load stars-enriched.json');
    const repos = await resp.json();

    // Build id→repo lookup
    const repoMap = new Map();
    for (const r of repos) repoMap.set(String(r.id), r);

    for (let i = 0; i < ids.length; i++) {
      const repo = repoMap.get(ids[i]);
      if (!repo) {
        texts[i] = [];
        continue;
      }
      // Combine searchable fields
      const raw = [
        repo.name || '',
        repo.desc || '',
        repo.desc_cn || '',
        (repo.topics || []).join(' '),
        (repo.auto_tags || []).join(' '),
        repo.lang || '',
        repo.lang_category || '',
      ].join(' ');
      texts[i] = tokenize(raw);
    }
  } catch (err) {
    console.warn('[Worker] BM25: could not load repo text, using empty tokens', err);
    for (let i = 0; i < ids.length; i++) texts[i] = [];
  }

  state.bm25Texts = texts;
  state.bm25 = buildBM25(texts);
  state.bm25Ready = true;
  self.postMessage({ type: 'status', text: '关键词索引就绪' });
}

/** Detect Chinese character ratio in text */
function cnRatio(text) {
  const cnMatch = text.match(/[\u4e00-\u9fff]/g) || [];
  const enMatch = text.match(/[a-zA-Z]+/g) || [];
  const cnChars = cnMatch.join('').length;
  const enChars = (enMatch.join('').match(/[a-zA-Z]/g) || []).length;
  if (cnChars + enChars === 0) return 0;
  return cnChars / (cnChars + enChars);
}

/** Keyword search using BM25 */
function bm25Search(query, k = 100) {
  if (!state.bm25Ready || !query.trim()) return [];
  const tokens = tokenize(query);
  if (tokens.length === 0) return [];

  const scores = state.bm25.score(tokens);
  const results = [];
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] > 0) results.push({ idx: i, id: state.ids[i], score: scores[i] });
  }
  // Sort descending by score
  results.sort((a, b) => b.score - a.score);
  return results.slice(0, k);
}

// ================================================================
// Transformers.js Text Encoding
// ================================================================

/**
 * Load transformers.js and the multilingual ONNX model lazily.
 * Uses X-HuggingFace-Private-Token header for higher rate limits.
 * Model is fetched from Hugging Face CDN (Xenova/m站-base ≈ 83MB).
 * After first load, browser caches it (HTTP cache + IndexedDB via @huggingface/core).
 */
async function ensureEncoder() {
  if (state.encoder) return;
  if (state.modelLoading) {
    // Wait for in-progress load
    return new Promise(resolve => { state.modelLoadingResolve = resolve; });
  }

  state.modelLoading = true;

  try {
    self.postMessage({ type: 'status', text: '加载语义模型 (~83MB, 首次约30s)...' });

    // Import transformers.js from CDN
    const { pipeline, env } = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.1');

    // Allow CORS for CDN model files
    env.allowLocalModels = false;
    env.useBrowserCache = true;

    // Xenova/m站-base: multilingual MiniLM, 384-dim, ONNX (fp32)
    // Intended for sentence embeddings — supports 50+ languages including Chinese
    self.postMessage({ type: 'status', text: '下载模型权重 (Xenova/m站-base)...' });

    state.encoder = await pipeline('feature-extraction', 'Xenova/m站-base', {
      progress_callback: (progress) => {
        if (progress.status === 'progress' && progress.file) {
          const pct = Math.round(progress.progress || 0);
          self.postMessage({
            type: 'modelProgress',
            file: progress.file,
            pct,
            loaded: progress.loaded,
            total: progress.total,
          });
        }
      }
    });

    state.modelReady = true;
    state.modelLoading = false;

    if (state.modelLoadingResolve) {
      state.modelLoadingResolve();
      state.modelLoadingResolve = null;
    }

    self.postMessage({
      type: 'modelReady',
      model: 'Xenova/m站-base',
      dim: state.dim,
    });

  } catch (err) {
    state.modelLoading = false;
    console.error('[Worker] Failed to load encoder:', err);
    self.postMessage({
      type: 'modelError',
      error: '语义模型加载失败: ' + err.message,
    });
    throw err;
  }
}

/**
 * Encode a text query into a normalized Float32 vector (384-dim).
 */
async function encodeText(text) {
  await ensureEncoder();
  if (!state.encoder) throw new Error('Encoder not available');

  // transformers.js pipeline returns a 2D array [[...dims]]
  const result = await state.encoder(text, { pooling: 'mean', normalize: true });
  const arr = result[0];

  if (!arr || arr.length !== state.dim) {
    throw new Error(`Invalid embedding: got ${arr ? arr.length : 0}-dim, expected ${state.dim}`);
  }
  return new Float32Array(arr);
}

// ================================================================
// Data Loading
// ================================================================

async function loadVectors() {
  const resp = await fetch(baseUrl + 'data/vectors.bin');
  if (!resp.ok) throw new Error('Failed to load vectors.bin');

  const buf = await resp.arrayBuffer();
  const view = new DataView(buf);

  let offset = 0;
  const numVectors = view.getUint32(offset, true); offset += 4;
  const dim = view.getUint32(offset, true); offset += 4;

  if (numVectors === 0 || dim === 0) throw new Error('Invalid vector file');
  if (dim !== 384) throw new Error(`Unsupported dim: ${dim} (expected 384)`);

  const vectors = new Float32Array(buf, offset, numVectors * dim);

  state.numVectors = numVectors;
  state.dim = dim;
  state.vectors = vectors;

  // Load IDs (ordered to match vector index)
  const idsResp = await fetch(baseUrl + 'data/hnsw_ids.json');
  if (!idsResp.ok) throw new Error('Failed to load hnsw_ids.json');
  const ids = await idsResp.json();
  state.ids = ids;

  // Build reverse lookup
  const idToIdx = new Map();
  for (let i = 0; i < ids.length; i++) idToIdx.set(String(ids[i]), i);
  state.idToIdx = idToIdx;

  return { numVectors, dim };
}

async function loadKnnIndex() {
  try {
    // Try new knn.bin first (multilingual k-NN), fallback to knn_index.bin
    let resp = await fetch(baseUrl + 'data/knn.bin');
    if (!resp.ok) {
      resp = await fetch(baseUrl + 'data/knn_index.bin');
    }
    if (!resp.ok) {
      console.warn('[Worker] knn.bin / knn_index.bin not found');
      return false;
    }

    const buf = await resp.arrayBuffer();
    const view = new DataView(buf);
    let offset = 0;
    const K = view.getUint32(offset, true); offset += 4;

    // New format includes N header; old format doesn't — detect by file size
    const expectedOld = 4 + state.numVectors * K * (4 + 4);
    if (buf.byteLength === 4 + K * 4 + state.numVectors * K * 8) {
      // Old format: [K][indices][distances] — N is implicit from state
      // offset stays at 4, use state.numVectors
    } else {
      // New format: [K][N][indices][distances] — skip N header
      offset += 4;
    }

    const totalEntries = state.numVectors * K;

    // Uint32 indices
    const indices = new Uint32Array(buf, offset, totalEntries);
    offset += totalEntries * 4;

    // Float32 distances
    const distBuf = buf.slice(offset);
    const distances = new Float32Array(distBuf, 0, totalEntries);

    state.knnK = K;
    state.knnIndices = indices;
    state.knnDistances = distances;

    return true;
  } catch (e) {
    console.warn('[Worker] Failed to load knn index:', e);
    return false;
  }
}

async function loadEnrichedData() {
  try {
    const resp = await fetch(baseUrl + 'data/stars-enriched.json');
    if (!resp.ok) return null;
    return await resp.json();
  } catch { return null; }
}

// ================================================================
// Message Handler
// ================================================================
self.onmessage = async (e) => {
  const { type, ...data } = e.data;

  switch (type) {

    // ── Base URL (from main page) ─────────────────────────────────
    case 'setBaseUrl':
      baseUrl = data.baseUrl;
      break;

    // ── Init ────────────────────────────────────────────────────────
    case 'init': {
      try {
        self.postMessage({ type: 'status', text: '加载向量数据...' });

        const [vecResult, knnLoaded, enriched] = await Promise.all([
          loadVectors(),
          loadKnnIndex(),
          loadEnrichedData(),
        ]);

        const { numVectors, dim } = vecResult;

        // Build BM25 index (non-blocking after vectors load)
        buildBm25Index().catch(err => {
          console.warn('[Worker] BM25 index build failed:', err);
          state.bm25Ready = false;
        });

        // Extract repo text for BM25
        if (enriched) {
          const repoMap = new Map();
          for (const r of enriched) repoMap.set(String(r.id), r);
          // Store text indexed by repo id (for bm25 lookup later)
          // The buildBm25Index function loads this itself, so we don't need this
        }

        self.postMessage({
          type: 'ready',
          count: numVectors,
          dim,
          hasKnn: knnLoaded,
          knnK: state.knnK,
          bm25Ready: false, // will update when built
        });

      } catch (err) {
        self.postMessage({ type: 'error', error: err.message });
      }
      break;
    }

    // ── Semantic Search (text → vector → KNN) ──────────────────────
    case 'semantic': {
      try {
        const { query, k = 50 } = data;
        const startMs = performance.now();

        if (!state.vectors) throw new Error('Vectors not loaded');
        if (!query || !query.trim()) {
          self.postMessage({ type: 'semanticResults', repoIds: [], indices: [], distances: [], queryMs: 0 });
          break;
        }

        // Encode text → vector
        const queryVec = await encodeText(query);
        const results = knnSearch(queryVec, Math.min(k, state.numVectors));
        const endMs = performance.now();

        const repoIds = new Array(results.length);
        const indices = new Uint32Array(results.length);
        const distances = new Float32Array(results.length);
        for (let i = 0; i < results.length; i++) {
          repoIds[i] = results[i].id;
          indices[i] = results[i].idx;
          distances[i] = results[i].dist;
        }

        self.postMessage({
          type: 'semanticResults',
          repoIds,
          indices,
          distances,
          queryMs: endMs - startMs,
        }, [indices.buffer, distances.buffer]);

      } catch (err) {
        console.error('[Worker] Semantic search error:', err);
        self.postMessage({ type: 'semanticResults', error: err.message, repoIds: [], indices: [], distances: [], queryMs: 0 });
      }
      break;
    }

    // ── Keyword Search (BM25) ───────────────────────────────────────
    case 'keyword': {
      try {
        const { query, k = 100 } = data;
        const startMs = performance.now();

        if (!query || !query.trim()) {
          self.postMessage({ type: 'keywordResults', repoIds: [], indices: [], scores: [], queryMs: 0 });
          break;
        }

        const results = bm25Search(query, k);
        const endMs = performance.now();

        const repoIds = new Array(results.length);
        const indices = new Uint32Array(results.length);
        const scores = new Float32Array(results.length);
        for (let i = 0; i < results.length; i++) {
          repoIds[i] = results[i].id;
          indices[i] = results[i].idx;
          scores[i] = results[i].score;
        }

        self.postMessage({
          type: 'keywordResults',
          repoIds,
          indices,
          scores,
          queryMs: endMs - startMs,
        }, [indices.buffer, scores.buffer]);

      } catch (err) {
        console.error('[Worker] Keyword search error:', err);
        self.postMessage({ type: 'keywordResults', error: err.message, repoIds: [], indices: [], scores: [], queryMs: 0 });
      }
      break;
    }

    // ── Hybrid Search (RRF fusion of semantic + BM25) ───────────────
    case 'hybrid': {
      try {
        const { query, k = 50 } = data;
        const startMs = performance.now();

        if (!state.vectors) throw new Error('Vectors not loaded');
        if (!query || !query.trim()) {
          self.postMessage({ type: 'hybridResults', repoIds: [], indices: [], distances: [], queryMs: 0 });
          break;
        }

        // Run semantic + BM25 in parallel
        const [semResults, kwResults] = await Promise.all([
          (async () => {
            try {
              const queryVec = await encodeText(query);
              return knnSearch(queryVec, Math.min(k * 2, state.numVectors));
            } catch { return []; }
          })(),
          (async () => {
            if (!state.bm25Ready) return [];
            return bm25Search(query, k * 2);
          })(),
        ]);

        // Language-aware RRF weights
        // Chinese-dominant queries (cn > 30%): trust BM25 more since multilingual model
        // encodes "Chinese text" as a language feature, causing false positives.
        // Pure/English queries: trust semantic more since model understands intent.
        const ratio = cnRatio(query);
        const bm25Weight = ratio > 0.3 ? 0.7 : ratio > 0.1 ? 0.5 : 0.3;
        const semWeight = 1.0 - bm25Weight;

        // RRF fusion: kRRF = 60 (standard constant)
        const kRRF = 60;
        const rrfScores = new Map();

        semResults.forEach((r, rank) => {
          rrfScores.set(r.id, {
            rrf: semWeight / (kRRF + rank + 1),
            semDist: r.dist,
            semIdx: r.idx,
          });
        });

        kwResults.forEach((r, rank) => {
          const existing = rrfScores.get(r.id);
          if (existing) {
            existing.rrf += bm25Weight / (kRRF + rank + 1);
          } else {
            rrfScores.set(r.id, {
              rrf: bm25Weight / (kRRF + rank + 1),
              semDist: 1,
              semIdx: -1,
            });
          }
        });

        // Sort by RRF score, take top k
        const fused = Array.from(rrfScores.entries())
          .sort((a, b) => b[1].rrf - a[1].rrf)
          .slice(0, k);

        const endMs = performance.now();
        const repoIds = new Array(fused.length);
        const indices = new Uint32Array(fused.length);
        const distances = new Float32Array(fused.length);

        for (let i = 0; i < fused.length; i++) {
          repoIds[i] = fused[i][0];
          indices[i] = fused[i][1].semIdx;
          distances[i] = fused[i][1].semDist;
        }

        self.postMessage({
          type: 'hybridResults',
          repoIds,
          indices,
          distances,
          queryMs: endMs - startMs,
        }, [indices.buffer, distances.buffer]);

      } catch (err) {
        console.error('[Worker] Hybrid search error:', err);
        self.postMessage({ type: 'hybridResults', error: err.message, repoIds: [], indices: [], distances: [], queryMs: 0 });
      }
      break;
    }

    // ── Similar Repos (O(1) pre-computed k-NN) ──────────────────────
    case 'similar': {
      try {
        const { repoId, k = 20 } = data;
        const startMs = performance.now();

        if (!state.knnIndices) throw new Error('k-NN index not loaded');

        const idx = state.idToIdx.get(String(repoId));
        if (idx === undefined) throw new Error(`Repo ID not found: ${repoId}`);

        const { knnK, knnIndices, knnDistances, ids } = state;
        const kActual = Math.min(k, knnK);
        const offset = idx * knnK;

        const results = [];
        for (let i = 0; i < kActual; i++) {
          const nIdx = knnIndices[offset + i];
          const nDist = knnDistances[offset + i];
          if (nDist <= 0 || nIdx === idx) continue;
          results.push({ id: ids[nIdx], idx: nIdx, dist: nDist });
          if (results.length >= k) break;
        }

        const endMs = performance.now();
        const rIds = new Array(results.length);
        const rIdx = new Uint32Array(results.length);
        const rDist = new Float32Array(results.length);
        for (let i = 0; i < results.length; i++) {
          rIds[i] = results[i].id;
          rIdx[i] = results[i].idx;
          rDist[i] = results[i].dist;
        }

        self.postMessage({
          type: 'similarResults',
          repoId,
          repoIds: rIds,
          indices: rIdx,
          distances: rDist,
          queryMs: endMs - startMs,
        }, [rIdx.buffer, rDist.buffer]);

      } catch (err) {
        console.error('[Worker] Similar repos error:', err);
        self.postMessage({ type: 'similarResults', error: err.message, repoId: data.repoId, repoIds: [], indices: [], distances: [], queryMs: 0 });
      }
      break;
    }

    default:
      console.warn('[Worker] Unknown message type:', type);
  }
};
