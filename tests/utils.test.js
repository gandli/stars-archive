/**
 * tests/utils.test.js
 * Unit tests for binary parsing utilities.
 * Tests vectors.bin and knn_index.bin format parsing.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { parseVectorsBin, parseKnnBin } from '../src/search_utils.mjs';

describe('parseVectorsBin', () => {
  it('parses valid vectors.bin header (num_vectors, dim)', () => {
    // vectors.bin format: 4 bytes num_vectors + 4 bytes dim + N*dim*4 float32 data
    const buf = new ArrayBuffer(8 + 3 * 4 * 4); // header + 3 vectors × 4 dim × 4 bytes
    const view = new DataView(buf);
    view.setUint32(0, 3, true);  // num_vectors = 3
    view.setUint32(4, 4, true);  // dim = 4

    // Fill with some float32 values (normalized)
    const fv = new Float32Array(buf, 8, 3 * 4);
    fv[0] = 1; fv[1] = 0; fv[2] = 0; fv[3] = 0; // [1,0,0,0]
    fv[4] = 0; fv[5] = 1; fv[6] = 0; fv[7] = 0; // [0,1,0,0]
    fv[8] = 0; fv[9] = 0; fv[10] = 1; fv[11] = 0; // [0,0,1,0]

    const result = parseVectorsBin(new Uint8Array(buf));

    expect(result.numVectors).toBe(3);
    expect(result.dim).toBe(4);
    expect(result.vectors).toBeInstanceOf(Float32Array);
    expect(result.vectors.length).toBe(12); // 3 × 4
  });

  it('extracts correct vector values', () => {
    const buf = new ArrayBuffer(8 + 2 * 3 * 4);
    const view = new DataView(buf);
    view.setUint32(0, 2, true);  // 2 vectors
    view.setUint32(4, 3, true);  // dim 3

    const fv = new Float32Array(buf, 8, 6);
    // v0: [0.5, -0.5, 0.0]
    fv[0] = 0.5; fv[1] = -0.5; fv[2] = 0.0;
    // v1: [0.0, 0.0, 1.0]
    fv[3] = 0.0; fv[4] = 0.0; fv[5] = 1.0;

    const result = parseVectorsBin(new Uint8Array(buf));

    expect(result.vectors[0]).toBeCloseTo(0.5);
    expect(result.vectors[1]).toBeCloseTo(-0.5);
    expect(result.vectors[2]).toBeCloseTo(0.0);
    expect(result.vectors[3]).toBeCloseTo(0.0);
    expect(result.vectors[4]).toBeCloseTo(0.0);
    expect(result.vectors[5]).toBeCloseTo(1.0);
  });

  it('throws on file too small for num_vectors', () => {
    const buf = new Uint8Array([0x01]); // only 1 byte
    expect(() => parseVectorsBin(buf)).toThrow('File too small');
  });

  it('throws on file too small for dim', () => {
    const buf = new Uint8Array([0x03, 0x00, 0x00, 0x00]); // only num_vectors, no dim
    expect(() => parseVectorsBin(buf)).toThrow('File too small');
  });

  it('throws on data size mismatch', () => {
    const buf = new ArrayBuffer(8 + 1 * 4); // claims 2 vectors × 4 dim, but only 1 float32
    const view = new DataView(buf);
    view.setUint32(0, 2, true);  // num_vectors = 2
    view.setUint32(4, 4, true);  // dim = 4

    expect(() => parseVectorsBin(new Uint8Array(buf))).toThrow('File too small');
  });
});

describe('parseKnnBin', () => {
  // N=2, K=3 → 4 (K header) + 6 uint32 indices + 6 float32 distances = 52 bytes
  const N = 2, K = 3;
  const TOTAL = 4 + N * K * 4 + N * K * 4;

  it('parses valid knn_index.bin header (K)', () => {
    const buf = new ArrayBuffer(TOTAL);
    const view = new DataView(buf);
    view.setUint32(0, K, true);  // K = 3

    const indices = new Uint32Array(buf, 4, N * K);
    indices[0] = 0; indices[1] = 1; indices[2] = 2;
    indices[3] = 1; indices[4] = 0; indices[5] = 2;

    const dists = new Float32Array(buf, 4 + N * K * 4, N * K);
    dists[0] = -0.0; dists[1] = 0.5; dists[2] = 0.7;
    dists[3] = -0.0; dists[4] = 0.5; dists[5] = 0.8;

    const result = parseKnnBin(new Uint8Array(buf));

    expect(result.K).toBe(3);
    expect(result.indices).toBeInstanceOf(Uint32Array);
    expect(result.distances).toBeInstanceOf(Float32Array);
    expect(result.indices.length).toBe(6);  // N*K
    expect(result.distances.length).toBe(6);
  });

  it('extracts correct indices and distances', () => {
    const buf = new ArrayBuffer(TOTAL);
    const view = new DataView(buf);
    view.setUint32(0, K, true);

    const indices = new Uint32Array(buf, 4, N * K);
    indices[0] = 99; indices[1] = 42; indices[2] = 7;

    const dists = new Float32Array(buf, 4 + N * K * 4, N * K);
    dists[0] = -0.0; dists[1] = 0.123; dists[2] = 0.456;

    const result = parseKnnBin(new Uint8Array(buf));

    expect(result.indices[0]).toBe(99);
    expect(result.indices[1]).toBe(42);
    expect(result.indices[2]).toBe(7);
    expect(result.distances[0]).toBeCloseTo(-0.0);
    expect(result.distances[1]).toBeCloseTo(0.123);
    expect(result.distances[2]).toBeCloseTo(0.456);
  });

  it('throws on file too small for K header', () => {
    const buf = new Uint8Array([0x03]); // only 1 byte
    expect(() => parseKnnBin(buf)).toThrow('File too small');
  });
});
