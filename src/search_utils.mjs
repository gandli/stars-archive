/**
 * src/search_utils.js
 *
 * Pure binary parsing and algorithm utilities.
 * These are shared between the main worker and test suite.
 * No DOM/WebAPI dependencies — all functions are synchronous and deterministic.
 */

/* ================================================================
   Binary Parsing
   ================================================================ */

/**
 * Parse vectors.bin format.
 * @param {Uint8Array} buf
 * @returns {{ numVectors: number, dim: number, vectors: Float32Array }}
 */
export function parseVectorsBin(buf) {
  if (buf.length < 8) throw new Error('File too small: no num_vectors or dim');
  const view = new DataView(buf.buffer, buf.byteOffset);
  let offset = 0;

  const numVectors = view.getUint32(offset, true);
  offset += 4;

  const dim = view.getUint32(offset, true);
  offset += 4;

  const expectedBytes = numVectors * dim * 4;
  // Check byte-level size before creating typed arrays
  const availableBytes = buf.byteLength - (buf.byteOffset + offset);
  if (availableBytes < expectedBytes) {
    throw new Error(`File too small: expected ${expectedBytes} bytes, got ${availableBytes}`);
  }

  const vectors = new Float32Array(buf.buffer, buf.byteOffset + offset, numVectors * dim);
  return { numVectors, dim, vectors };
}

/**
 * Parse knn_index.bin format.
 * @param {Uint8Array} buf
 * @returns {{ K: number, indices: Uint32Array, distances: Float32Array }}
 */
export function parseKnnBin(buf) {
  if (buf.length < 4) throw new Error('File too small: no K');
  const view = new DataView(buf.buffer, buf.byteOffset);
  let offset = 0;

  const K = view.getUint32(offset, true);
  offset += 4;

  // N is inferred as (total_bytes - 4) / (K * 8), but we only need totalEntries
  // We use the remaining bytes: N*K uint32 + N*K float32
  // Each entry pair = 4 + 4 = 8 bytes
  // But we don't know N — we derive it from the buffer size
  // After K header, the buffer has N*K uint32 indices + N*K float32 distances.
  // Each entry pair (one index + one distance) = 8 bytes (4+4).
  // So totalEntries = N*K = (total_bytes - 4) / 8
  const totalBytesAfterK = buf.byteLength - offset;
  if (totalBytesAfterK % 8 !== 0) {
    throw new Error(`knn_index.bin: invalid size. remaining_bytes=${totalBytesAfterK}`);
  }
  const totalEntries = totalBytesAfterK / 8;  // = N * K

  // indices: uint32 after K header
  const indices = new Uint32Array(buf.buffer, buf.byteOffset + offset, totalEntries);
  offset += totalEntries * 4;

  // distances: float32 after indices
  const distView = new DataView(buf.buffer, buf.byteOffset + offset, totalEntries * 4);
  const distances = new Float32Array(distView.buffer, distView.byteOffset, totalEntries);

  return { K, indices, distances };
}

/* ================================================================
   KNN Algorithm (pure — takes state as params)
   ================================================================ */

/**
 * Cosine distance between a stored vector (at flat array offset) and a query vector.
 * Both vectors must be the same dimension.
 * Returns 0 (identical) to 2 (opposite).
 */
export function cosineDist(a, offsetA, b) {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < b.length; i++) {
    const av = a[offsetA + i];
    const bv = b[i];
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  if (normA === 0 || normB === 0) return 1;
  return 1 - dot / Math.sqrt(normA * normB);
}

/**
 * Insertion-sort KNN — insert result into sorted array by dist.
 * Returns new array (does not mutate).
 */
function insertSorted(results, item, k) {
  if (results.length < k && item.dist < results[results.length - 1]?.dist) {
    // Find insertion point (insertion sort)
    let pos = results.length;
    while (pos > 0 && (results[pos - 1]?.dist ?? Infinity) > item.dist) {
      results[pos] = results[pos - 1];
      pos--;
    }
    results[pos] = item;
  }
  return results;
}

/**
 * Naive full-scan K-nearest neighbors search.
 * @param {object} searchState - { vectors, numVectors, dim, ids }
 * @param {Float32Array} queryVec - normalized query vector
 * @param {number} k - number of neighbors
 * @returns {Array<{id, idx, dist}>} sorted by ascending distance
 */
export function knnSearch({ vectors, numVectors, dim, ids }, queryVec, k) {
  const results = [];

  for (let v = 0; v < numVectors; v++) {
    const dist = cosineDist(vectors, v * dim, queryVec);
    results.push({ idx: v, dist });
  }

  // Sort top-k manually (O(N log k))
  results.sort((a, b) => a.dist - b.dist);
  return results.slice(0, k).map(r => ({ id: ids[r.idx], idx: r.idx, dist: r.dist }));
}

/**
 * O(1) similar repos lookup using pre-computed k-NN index.
 * Skips self-references (dist ≤ 0.001, includes float32 underflow of -0.0).
 * @param {object} knnState - { knnK, knnIndices, knnDistances, ids, idToIdx }
 * @param {string|number} repoId - GitHub repo ID
 * @param {number} k - max results
 * @returns {Array<{id, idx, dist}>}
 */
export function getSimilarRepos({ knnK, knnIndices, knnDistances, ids, idToIdx }, repoId, k) {
  const idx = idToIdx.get(String(repoId));
  if (idx === undefined) return [];

  const kActual = Math.min(k, knnK);
  const offset = idx * knnK;
  const results = [];

  for (let i = 0; i < kActual; i++) {
    const nIdx = knnIndices[offset + i];
    const nDist = knnDistances[offset + i];
    // Skip self-reference (dist≈0, includes float32 underflow -0.0) and invalid
    if (nDist <= 0.001 || nIdx === idx) continue;
    results.push({ id: ids[nIdx], idx: nIdx, dist: nDist });
    if (results.length >= k) break;
  }
  return results;
}
