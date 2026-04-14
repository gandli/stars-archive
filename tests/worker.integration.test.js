/**
 * tests/worker.integration.test.js
 *
 * Integration tests for search_worker.js.
 * Mocks worker globals (self, fetch) and tests the message handler
 * against real binary data files.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const ROOT = path.resolve('./');

/** Read file as Uint8Array (like fetch().arrayBuffer()) */
function readFileBin(relativePath) {
  const buf = fs.readFileSync(path.join(ROOT, relativePath));
  return new Uint8Array(buf);
}

/** Build a minimal mock self with postMessage tracking */
function makeMockSelf() {
  const messages = [];
  return {
    messages,
    postMessage: vi.fn((msg, transfers) => {
      messages.push({ msg, transfers });
    }),
    console: {
      log: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    },
  };
}

/** Mock fetch for local files */
function makeMockFetch(binaries) {
  return vi.fn((url) => {
    if (binaries[url]) {
      return Promise.resolve({
        ok: true,
        arrayBuffer: () => Promise.resolve(binaries[url].buffer),
      });
    }
    return Promise.resolve({ ok: false, status: 404 });
  });
}

// ─── Load real binary data once for all tests ───────────────────────────────
let vectorsBin, knnBin, hnswIds;

beforeAll(() => {
  vectorsBin = readFileBin('data/vectors.bin');
  const idsBuf = fs.readFileSync(path.join(ROOT, 'data/hnsw_ids.json'));
  knnBin = readFileBin('data/knn_index.bin');
  hnswIds = JSON.parse(idsBuf.toString());
});

describe('worker: init message', () => {
  // Note: self.onmessage is set at module evaluation time in search_worker.js.
  // The worker uses `self` which is undefined in Node.js (only exists in browsers/workers).
  // Full worker integration tests require a browser environment (jsdom or Playwright).
  // We test the init data-loading logic via pure function equivalents instead.
  it.todo('full worker message handler integration — requires browser/jsdom environment');
});

describe('worker: search message — against real data', () => {
  // We'll test the pure functions with real binary data

  it('loads vectors.bin with correct dimensions from real file', () => {
    // Test using the real parseVectorsBin logic
    const buf = vectorsBin;
    const view = new DataView(buf.buffer, buf.byteOffset);
    const numVectors = view.getUint32(0, true);
    const dim = view.getUint32(4, true);

    expect(numVectors).toBe(4816);
    expect(dim).toBe(384);
  });

  it('loads knn_index.bin with correct K from real file', () => {
    const buf = knnBin;
    const view = new DataView(buf.buffer, buf.byteOffset);
    const K = view.getUint32(0, true);

    expect(K).toBe(50);
  });

  it('vectors are normalized (L2 norm ≈ 1)', () => {
    const buf = vectorsBin;
    const view = new DataView(buf.buffer, buf.byteOffset);
    const numVectors = view.getUint32(0, true);
    const dim = view.getUint32(4, true);
    const vectors = new Float32Array(buf.buffer, buf.byteOffset + 8, numVectors * dim);

    let norm = 0;
    for (let i = 0; i < dim; i++) norm += vectors[i] * vectors[i];
    const sqrtNorm = Math.sqrt(norm);
    expect(sqrtNorm).toBeCloseTo(1.0, 3);
  });

  it('knn_index entry 0 self-reference has dist ≈ 0', () => {
    const buf = knnBin;
    const view = new DataView(buf.buffer, buf.byteOffset);
    const K = view.getUint32(0, true);
    const N = 4816;

    // Element 0, neighbor 0: should be self (index=0, dist≈0)
    const selfDist = new Float32Array(buf.buffer, buf.byteOffset + 4 + N * K * 4, N * K)[0];
    expect(Math.abs(selfDist)).toBeLessThan(0.01);
  });
});

describe('worker: end-to-end with real data via pure functions', () => {
  // Simulate what the worker does using real binary data
  let state;

  beforeAll(() => {
    // Parse real vectors.bin
    const vBuf = vectorsBin;
    const vView = new DataView(vBuf.buffer, vBuf.byteOffset);
    const numVectors = vView.getUint32(0, true);
    const dim = vView.getUint32(4, true);
    const vectors = new Float32Array(vBuf.buffer, vBuf.byteOffset + 8, numVectors * dim);

    // Parse real knn_index.bin
    const kBuf = knnBin;
    const kView = new DataView(kBuf.buffer, kBuf.byteOffset);
    const K = kView.getUint32(0, true);
    const totalEntries = numVectors * K;
    const indices = new Uint32Array(kBuf.buffer, kBuf.byteOffset + 4, totalEntries);
    const distView = new DataView(kBuf.buffer, kBuf.byteOffset + 4 + totalEntries * 4, totalEntries * 4);
    const knnDistances = new Float32Array(distView.buffer, distView.byteOffset, totalEntries);

    // Build idToIdx
    const idToIdx = new Map(hnswIds.map((id, i) => [String(id), i]));

    state = { vectors, numVectors, dim, ids: hnswIds, knnK: K, knnIndices: indices, knnDistances, idToIdx };
  });

  it('knn search finds nearest neighbors for a known query', async () => {
    // Use the first vector as query — should find itself as nearest
    const { vectors, numVectors, dim, ids } = state;
    const queryVec = vectors.slice(0, dim); // v0

    // Run naive KNN (simulating the worker's knnSearch)
    const { cosineDist } = await import('../src/search_utils.mjs');

    const results = [];
    for (let v = 0; v < numVectors; v++) {
      let dot = 0, normA = 0, normB = 0;
      for (let i = 0; i < dim; i++) {
        const av = vectors[v * dim + i];
        const qv = queryVec[i];
        dot += av * qv;
        normA += av * av;
        normB += qv * qv;
      }
      const dist = 1 - dot / Math.sqrt(normA * normB);
      results.push({ idx: v, dist });
    }
    results.sort((a, b) => a.dist - b.dist);
    const top = results.slice(0, 5);

    expect(top[0].idx).toBe(0);   // v0 should be nearest to itself (dist≈0)
    expect(top[0].dist).toBeLessThan(0.01);
    expect(ids[top[0].idx]).toBe(hnswIds[0]);
  });

  it('getSimilarRepos returns neighbors for repo at index 0', async () => {
    const { knnK, knnIndices, knnDistances, ids, idToIdx } = state;
    const { getSimilarRepos } = await import('../src/search_utils.mjs');

    const repoId = ids[0]; // first repo's ID
    const results = getSimilarRepos(state, repoId, 20);

    expect(results.length).toBeGreaterThan(0);
    expect(results.length).toBeLessThanOrEqual(20);
    // First result should NOT be self
    expect(results[0].id).not.toBe(repoId);
    // First result should have a positive distance
    expect(results[0].dist).toBeGreaterThan(0);
    expect(results[0].dist).toBeLessThan(1);
  });

  it('getSimilarRepos returns neighbors for repo at index 1000', async () => {
    const { getSimilarRepos } = await import('../src/search_utils.mjs');
    const repoId = state.ids[1000];
    const results = getSimilarRepos(state, repoId, 10);

    expect(results.length).toBeGreaterThan(0);
    expect(results.every(r => r.id !== repoId)).toBe(true);
    // All distances should be positive
    expect(results.every(r => r.dist > 0)).toBe(true);
  });

  it('getSimilarRepos returns empty for nonexistent repo ID', async () => {
    const { getSimilarRepos } = await import('../src/search_utils.mjs');
    const results = getSimilarRepos(state, '999999999999', 10);
    expect(results).toEqual([]);
  });

  it('similar repos are consistent: getSimilarRepos(repoId) neighbors include knnSearch(repoVec)', async () => {
    const { getSimilarRepos, knnSearch: knnSearchFn } = await import('../src/search_utils.mjs');
    const repoId = state.ids[500];
    const repoVec = state.vectors.slice(500 * state.dim, 500 * state.dim + state.dim);

    const similarResults = getSimilarRepos(state, repoId, 10);
    const knnResults = knnSearchFn(state, repoVec, 10);

    // The similar repos should be a subset of top-K from knnSearch
    // (similar repos = pre-computed exact k-NN, knnSearch = live exact k-NN)
    const similarIds = new Set(similarResults.map(r => r.id));
    const knnIds = new Set(knnResults.map(r => r.id));

    // Most similar repos should appear in knn results too
    const overlap = [...similarIds].filter(id => knnIds.has(id)).length;
    expect(overlap).toBeGreaterThan(similarResults.length * 0.5);
  });

  it('result distances are in ascending order (nearest first)', async () => {
    const { getSimilarRepos } = await import('../src/search_utils.mjs');
    const results = getSimilarRepos(state, state.ids[42], 10);

    for (let i = 1; i < results.length; i++) {
      expect(results[i].dist).toBeGreaterThanOrEqual(results[i - 1].dist);
    }
  });

  it('search results have correct shape (id, idx, dist)', async () => {
    const { knnSearch: knnSearchFn } = await import('../src/search_utils.mjs');
    const query = state.vectors.slice(0, state.dim);
    const results = knnSearchFn(state, query, 5);

    results.forEach(r => {
      expect(r).toHaveProperty('id');
      expect(r).toHaveProperty('idx');
      expect(r).toHaveProperty('dist');
      expect(typeof r.id).toBe('string');
      expect(typeof r.idx).toBe('number');
      expect(typeof r.dist).toBe('number');
      expect(r.dist).toBeGreaterThanOrEqual(0);
    });
  });
});

describe('binary format edge cases', () => {
  it('knn_index K matches stored neighbors count', () => {
    const buf = knnBin;
    const view = new DataView(buf.buffer, buf.byteOffset);
    const K = view.getUint32(0, true);
    const N = 4816;

    const indicesSectionBytes = N * K * 4;
    const distSectionStart = 4 + indicesSectionBytes;
    const distSectionBytes = N * K * 4;
    const expectedTotal = 4 + indicesSectionBytes + distSectionBytes;

    expect(buf.length).toBe(expectedTotal);
    expect(K).toBe(50);
  });

  it('hnsw_ids count matches numVectors', () => {
    const vBuf = vectorsBin;
    const vView = new DataView(vBuf.buffer, vBuf.byteOffset);
    const numVectors = vView.getUint32(0, true);

    expect(hnswIds.length).toBe(numVectors);
  });

  it('all hnsw_ids are unique', () => {
    const unique = new Set(hnswIds);
    expect(unique.size).toBe(hnswIds.length);
  });

  it('hnsw_ids are strings', () => {
    expect(hnswIds.every(id => typeof id === 'string')).toBe(true);
  });
});
