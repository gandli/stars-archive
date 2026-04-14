/**
 * tests/algorithm.test.js
 * Unit tests for core search algorithms.
 * Pure functions — no worker globals needed.
 */
import { describe, it, expect } from 'vitest';
import { cosineDist, knnSearch, getSimilarRepos } from '../src/search_utils.mjs';

describe('cosineDist', () => {
  it('returns 0 for identical normalized vectors', () => {
    // a = [1, 0], b = [1, 0]
    const a = new Float32Array([1, 0]);
    const b = new Float32Array([1, 0]);
    const dist = cosineDist(a, 0, b);
    expect(dist).toBeCloseTo(0, 4);
  });

  it('returns ~2 for opposite vectors', () => {
    // a = [1, 0], b = [-1, 0]
    const a = new Float32Array([1, 0]);
    const b = new Float32Array([-1, 0]);
    const dist = cosineDist(a, 0, b);
    expect(dist).toBeCloseTo(2, 4);
  });

  it('returns 1 for orthogonal vectors', () => {
    // a = [1, 0], b = [0, 1]
    const a = new Float32Array([1, 0]);
    const b = new Float32Array([0, 1]);
    const dist = cosineDist(a, 0, b);
    expect(dist).toBeCloseTo(1, 4);
  });

  it('handles 3D vectors correctly', () => {
    const a = new Float32Array([1, 1, 1]);
    const b = new Float32Array([1, 1, 1]);
    const dist = cosineDist(a, 0, b);
    expect(dist).toBeCloseTo(0, 4);

    const a2 = new Float32Array([1, 0, 0]);
    const b2 = new Float32Array([0, 1, 0]);
    const dist2 = cosineDist(a2, 0, b2);
    expect(dist2).toBeCloseTo(1, 4);
  });

  it('handles flat array offset for stored vectors', () => {
    // Flat array: [v0d0, v0d1, v0d2, v1d0, v1d1, v1d2]
    const a = new Float32Array([1, 0, 0,  0, 1, 0]);
    const b = new Float32Array([1, 0, 0]);  // same as v0

    expect(cosineDist(a, 0, b)).toBeCloseTo(0, 4);  // v0 matches query
    expect(cosineDist(a, 3, b)).toBeCloseTo(1, 4);   // v1 (0,1,0) orthogonal to query
  });

  it('returns 1 for zero vectors', () => {
    const a = new Float32Array([0, 0]);
    const b = new Float32Array([1, 0]);
    expect(cosineDist(a, 0, b)).toBeCloseTo(1, 4);

    const a2 = new Float32Array([1, 0]);
    const b2 = new Float32Array([0, 0]);
    expect(cosineDist(a2, 0, b2)).toBeCloseTo(1, 4);
  });
});

describe('knnSearch', () => {
  // 3 repos, dim=4, normalized vectors
  const makeState = (vectors, ids) => ({
    vectors,
    numVectors: vectors.length / 4,
    dim: 4,
    ids
  });

  it('returns k nearest neighbors sorted by distance', () => {
    // 3 repos: v0=[1,0,0,0], v1=[0,1,0,0], v2=[0,0,1,0]
    const vectors = new Float32Array([
      1, 0, 0, 0,  // v0: identical to query → dist=0
      0, 1, 0, 0,  // v1: orthogonal → dist=1
      0, 0, 1, 0   // v2: orthogonal → dist=1
    ]);
    const state = makeState(vectors, ['repo0', 'repo1', 'repo2']);
    const query = new Float32Array([1, 0, 0, 0]);

    const results = knnSearch(state, query, 3);

    expect(results).toHaveLength(3);
    expect(results[0].id).toBe('repo0');
    expect(results[0].dist).toBeCloseTo(0, 4);
    expect(results[1].dist).toBeLessThanOrEqual(results[2].dist);
  });

  it('returns top-k only when k < numVectors', () => {
    const vectors = new Float32Array([
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1
    ]);
    const state = makeState(vectors, ['r0', 'r1', 'r2', 'r3']);
    const query = new Float32Array([1, 0, 0, 0]);

    const results = knnSearch(state, query, 2);

    expect(results).toHaveLength(2);
    expect(results[0].id).toBe('r0');
    expect(results[1].dist).toBeGreaterThan(0);
  });

  it('handles query same as all vectors (all zero distance)', () => {
    const vectors = new Float32Array([
      0.5, 0.5, 0, 0,
      0.5, 0.5, 0, 0
    ]);
    const state = makeState(vectors, ['r0', 'r1']);
    const query = new Float32Array([0.5, 0.5, 0, 0]);

    const results = knnSearch(state, query, 2);

    expect(results).toHaveLength(2);
    expect(results[0].dist).toBeCloseTo(0, 4);
    expect(results[1].dist).toBeCloseTo(0, 4);
  });

  it('includes idx in result objects', () => {
    const vectors = new Float32Array([1,0,0,0,  0,1,0,0]);
    const state = makeState(vectors, ['r0', 'r1']);
    const results = knnSearch(state, new Float32Array([1,0,0,0]), 2);

    expect(results[0]).toHaveProperty('idx');
    expect(results[0]).toHaveProperty('id');
    expect(results[0]).toHaveProperty('dist');
    expect(results[0].idx).toBe(0);
    expect(results[1].idx).toBe(1);
  });
});

describe('getSimilarRepos', () => {
  /**
   * Build a mock knn state with 3 repos.
   * knn_index for 3 repos, K=2:
   *   entry 0 → neighbors [0(dist=-0.0), 1(dist=0.3)]  (skip 0, include 1)
   *   entry 1 → neighbors [1(dist=-0.0), 2(dist=0.5)]  (skip 1, include 2)
   *   entry 2 → neighbors [2(dist=-0.0), 0(dist=0.7)]  (skip 2, include 0)
   */
  const makeKnnState = (knnK = 2, totalEntries = 3 * 2) => {
    const ids = ['repo0', 'repo1', 'repo2'];
    const idToIdx = new Map(ids.map((id, i) => [id, i]));

    // Indices: entry0=[0,1], entry1=[1,2], entry2=[2,0]
    const indices = new Uint32Array(totalEntries);
    indices[0] = 0; indices[1] = 1;  // entry 0 neighbors
    indices[2] = 1; indices[3] = 2;  // entry 1 neighbors
    indices[4] = 2; indices[5] = 0;  // entry 2 neighbors

    // Distances: self=-0.0, others=positive
    const distances = new Float32Array(totalEntries);
    distances[0] = -0.0; distances[1] = 0.3;   // entry 0
    distances[2] = -0.0; distances[3] = 0.5;   // entry 1
    distances[4] = -0.0; distances[5] = 0.7;   // entry 2

    return { knnK, knnIndices: indices, knnDistances: distances, ids, idToIdx };
  };

  it('returns similar repos for known ID', () => {
    const state = makeKnnState();
    const results = getSimilarRepos(state, 'repo0', 5);

    expect(results.length).toBeGreaterThan(0);
    expect(results[0].id).toBe('repo1'); // dist=0.3 is nearest non-self
    expect(results[0].dist).toBeCloseTo(0.3, 4);
  });

  it('skips self-reference (dist=-0.0)', () => {
    const state = makeKnnState();
    const results = getSimilarRepos(state, 'repo0', 5);

    // repo0 itself should NOT appear
    expect(results.some(r => r.id === 'repo0')).toBe(false);
  });

  it('respects k limit', () => {
    const state = makeKnnState();
    const results = getSimilarRepos(state, 'repo1', 1);

    expect(results.length).toBeLessThanOrEqual(1);
  });

  it('returns empty array for unknown repo ID', () => {
    const state = makeKnnState();
    const results = getSimilarRepos(state, 'nonexistent', 5);

    expect(results).toEqual([]);
  });

  it('handles numeric repo IDs (coerced to string)', () => {
    const state = makeKnnState();
    const results = getSimilarRepos(state, 6291090, 5);

    // Should not throw — numeric IDs are coerced to string
    expect(Array.isArray(results)).toBe(true);
  });

  it('sorts results by ascending distance (nearest first)', () => {
    const N = 5, K = 4;
    const ids = Array.from({ length: N }, (_, i) => `r${i}`);
    const idToIdx = new Map(ids.map((id, i) => [id, i]));

    // entry 0 neighbors: self(dist=-0.0), r1(0.2), r2(0.5), r3(0.9)
    const indices = new Uint32Array(N * K);
    const distances = new Float32Array(N * K);
    for (let i = 0; i < N; i++) {
      indices[i * K] = i;       // self
      distances[i * K] = -0.0; // self
    }
    indices[1] = 1; distances[1] = 0.2;
    indices[2] = 2; distances[2] = 0.5;
    indices[3] = 3; distances[3] = 0.9;

    const state = { knnK: K, knnIndices: indices, knnDistances: distances, ids, idToIdx };
    const results = getSimilarRepos(state, 'r0', 5);

    expect(results.length).toBe(3);
    expect(results[0].id).toBe('r1');
    expect(results[0].dist).toBeCloseTo(0.2, 4);
    expect(results[1].id).toBe('r2');
    expect(results[1].dist).toBeCloseTo(0.5, 4);
    expect(results[2].id).toBe('r3');
    expect(results[2].dist).toBeCloseTo(0.9, 4);
  });

  it('skips float32 underflow values (dist ≈ 0 but not exactly -0.0)', () => {
    // Simulate a case where dist is a tiny positive number
    const N = 2, K = 2;
    const ids = ['ra', 'rb'];
    const idToIdx = new Map(ids.map((id, i) => [id, i]));

    const indices = new Uint32Array([0, 1,  1, 0]);
    const distances = new Float32Array([-1e-7, 0.4,  -1e-7, 0.4]); // tiny negatives from float underflow

    const state = { knnK: K, knnIndices: indices, knnDistances: distances, ids, idToIdx };
    const results = getSimilarRepos(state, 'ra', 5);

    // Both self-refs skipped (dist=-1e-7 <= 0.001), ra's only neighbor is rb
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe('rb');
  });

  it('handles float32 underflow of -0.0 correctly', () => {
    const N = 2, K = 2;
    const ids = ['x', 'y'];
    const idToIdx = new Map(ids.map((id, i) => [id, i]));

    // -0.0 as float32 bits is 0x80000000
    const buf = new ArrayBuffer(4);
    new DataView(buf).setUint32(0, 0x80000000, false); // big-endian -0.0
    const negZero = new Float32Array(buf)[0];

    const indices = new Uint32Array([0, 1,  1, 0]);
    const distances = new Float32Array([negZero, 0.5,  negZero, 0.6]);

    const state = { knnK: K, knnIndices: indices, knnDistances: distances, ids, idToIdx };
    const results = getSimilarRepos(state, 'x', 5);

    expect(results).toHaveLength(1);
    expect(results[0].id).toBe('y');
    expect(results[0].dist).toBeCloseTo(0.5, 4);
  });
});
