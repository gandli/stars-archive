# 项目清单 — Stars Archive

## 项目概览

| 属性 | 值 |
|------|-----|
| **仓库** | gandli/stars-archive |
| **版本** | 2.0.0 (pyproject.toml) / 1.0.0 (package.json) |
| **许可证** | ISC (声明) / 无 LICENSE 文件 |
| **语言** | Python, JavaScript |
| **代码行数** | ~4,514 (源文件) |
| **测试数量** | 128 (115 Python + 13 E2E) |
| **最后有效同步** | 2026-04-12 04:44 UTC |
| **当前数据状态** | 空 (stars.json = []) |

---

## 目录结构

```
stars-archive/
├── .github/workflows/
│   ├── sync.yml          # 每日同步 GitHub Stars (cron 02:00 UTC)
│   └── e2e.yml           # Playwright E2E 测试 (push/PR to main)
├── data/
│   ├── stars.json              # [空] 当前同步的仓库数据
│   ├── stars-enriched.json     # [空] 增强数据（分类、标签、中文翻译）
│   ├── stars-previous.json     # 上一次同步的数据（备份，4.4MB）
│   ├── stars-previous-backup.json  # 上上次备份（4.4MB）
│   ├── desc-cn.json            # 中文翻译缓存（411KB）
│   ├── vectors.bin             # 向量嵌入二进制（7.4MB, 384-dim）
│   ├── vectors-meta.json       # 向量元数据
│   ├── knn.bin                 # 预计算 k-NN 索引（771KB）
│   ├── knn_index.bin           # 同上（旧格式，771KB）
│   ├── knn_debug.json          # [应移除] 调试用（1.9MB）
│   ├── hnsw_index.bin          # HNSW 近似最近邻索引（8.1MB）
│   ├── hnsw_ids.json           # HNSW ID 映射（62KB）
│   ├── hnsw-meta.json          # HNSW 参数元数据
│   ├── ids.json                # 仓库 ID 列表（62KB）
│   ├── vectors_for_test.npy    # [应移除] 测试用（7.4MB）
│   ├── stats.json              # 语言分布统计
│   ├── changes.json            # 上次变更记录
│   └── enrichment-progress.json # 翻译进度缓存
├── scripts/
│   ├── sync.py                 # 从 GitHub API 拉取 Stars
│   ├── enrich.py               # AI 分类、标签生成、翻译
│   ├── translator.py           # 并发翻译 + 限流 + 重试
│   ├── translate_fast.py       # 快速翻译脚本（未使用）
│   ├── translate_descriptions.py # 批量翻译脚本（未使用）
│   ├── generate_vectors.py     # 向量嵌入生成 + HNSW 索引
│   ├── export_for_web.py       # 导出二进制格式给前端
│   ├── generate_readme.py      # 生成 README.md
│   ├── detect_changes.py       # 检测新增/删除的仓库
│   └── test_search.py          # 搜索调试脚本（本地）
├── src/
│   └── search_utils.mjs        # 前端工具函数（纯函数）
├── tests/
│   ├── algorithm.test.js       # Vitest 算法测试
│   ├── utils.test.js           # Vitest 工具函数测试
│   ├── worker.integration.test.js # Vitest Worker 集成测试
│   ├── test_100_percent.py     # 覆盖率冲刺测试
│   ├── test_edge_cases.py      # 边界情况测试
│   ├── test_enrich.py          # enrich 模块测试
│   ├── test_enrich_coverage.py # enrich 覆盖率测试
│   ├── test_final_5_percent.py # 最后 5% 覆盖率测试
│   ├── test_full_coverage.py   # 全量覆盖率测试
│   ├── test_last_3_lines.py    # 最后 3 行覆盖测试
│   ├── test_main_flow.py       # 主流流程测试
│   ├── test_main_guards.py     # `__main__` guard 覆盖测试
│   ├── test_main_integration.py # main() 集成测试
│   ├── test_main_paths.py      # 条件分支覆盖测试
│   └── test_translator.py      # 翻译模块测试
├── e2e/
│   └── search.spec.mjs         # Playwright E2E 测试 (13 tests)
├── search_worker.js            # Web Worker（BM25/Semantic/Hybrid）
├── index.html                  # 主页面（搜索 UI + 内联 JS）
├── pyproject.toml              # Python 项目配置
├── package.json                # Node 项目配置
├── playwright.config.mjs       # Playwright 配置
├── vitest.config.js            # Vitest 配置
├── .gitignore                  # Git 忽略规则
└── README.md                   # 项目说明
```

---

## 脚本职责明细

### 后端脚本 (scripts/*.py)

| 脚本 | 输入 | 输出 | 依赖 | 工时估算 |
|------|------|------|------|----------|
| `sync.py` | GH_TOKEN | `stars.json`, `stats.json` | 无外部依赖 | O(n) API 调用 |
| `enrich.py` | `stars.json` | `stars-enriched.json` | translator.py (可选) | 即时 |
| `translator.py` | `stars-enriched.json` | `desc-cn.json` | MyMemory API | O(n) HTTP 请求 |
| `generate_vectors.py` | `stars-enriched.json` | `vectors.bin`, HNSW 索引 | sentence-transformers, hnswlib | GPU/CPU 密集 |
| `export_for_web.py` | `vectors.json`, `knn_index.bin` | `vectors.bin`, `knn.bin`, `ids.json` | numpy | 即时 |
| `generate_readme.py` | `stars.json`, `stats.json` | `README.md` | 无 | 即时 |
| `detect_changes.py` | `stars.json`, `stars-previous.json` | `changes.json` | 无 | O(n) |

### 前端脚本

| 文件 | 职责 | 行数 |
|------|------|------|
| `index.html` | 搜索页面 UI + 状态管理 + Worker 通信 | 984 |
| `search_worker.js` | 多模态搜索引擎（BM25/Semantic/Hybrid） | 691 |
| `src/search_utils.mjs` | 纯函数工具（二进制解析、KNN） | 163 |

---

## 数据流图

```
┌─────────────┐
│  GitHub API  │
└──────┬──────┘
       │ (GH_TOKEN)
       ▼
┌─────────────┐
│  sync.py    │ ──→ stars.json
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ enrich.py   │ ──→ stars-enriched.json
│ (分类/标签)  │
└──────┬──────┘
       │
       ├──→ translator.py ──→ desc-cn.json (中文翻译)
       │
       ▼
┌──────────────────┐
│ generate_vectors.py │ ──→ vectors.bin, hnsw_index.bin
│ (嵌入 + HNSW)     │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ export_for_web.py │ ──→ knn.bin, ids.json (前端格式)
└──────────────────┘
       │
       ▼
┌──────────────────┐
│  Web Frontend    │
│ (index.html +    │
│  search_worker.js)│
└──────────────────┘
```

---

## 二进制格式规范

### vectors.bin
```
[num_vectors: uint32][dim: uint32][float32[num_vectors*dim]] (row-major, little-endian)
```

### knn.bin
```
[K: uint32][N: uint32][indices: uint32[N*K]][distances: float32[N*K]]
```

### knn_index.bin (旧格式，无 N 头)
```
[K: uint32][indices: uint32[N*K]][distances: float32[N*K]]
```

---

## 环境变量清单

| 变量 | 用途 | 必需 | 默认值 |
|------|------|------|--------|
| `GH_TOKEN` | GitHub API 认证 | sync.py 是 | 无 |
| `GITHUB_TOKEN` | 备选 Token | 否 | 无 |
| `GITHUB_ACTOR` | 用户名 | 否 | `gandli` |
| `GH_USER` | 备选用户名 | 否 | `gandli` |
| `LIBRETRANSLATE_URL` | LibreTranslate 实例 | 否 | `https://libretranslate.com` |
| `BATCH_SIZE` | 翻译批次大小 | 否 | `50` |
| `DATA_DIR` | 数据目录 | 否 | `data/` |

---

## 测试策略

### 单元测试 (tests/*.py)
- **运行方式**: `pytest tests/ -v`
- **框架**: pytest + coverage
- **覆盖率目标**: 60% (pyproject.toml fail_under)
- **实际覆盖率**: 未知 (.coverage SQLite 文件存在但未解析)

### 前端单元测试 (tests/*.test.js)
- **运行方式**: `npx vitest run`
- **框架**: vitest
- **包含**: `algorithm.test.js`, `utils.test.js`, `worker.integration.test.js`

### E2E 测试 (e2e/search.spec.mjs)
- **运行方式**: `npx playwright test`
- **框架**: Playwright (Chromium)
- **测试数量**: 13
- **超时**: 120s/测试
- **依赖**: 本地 HTTP server (python -m http.server 8080)

---

## CI/CD 流水线

### sync.yml (每日同步)
```
schedule: 0 2 * * * (每天 02:00 UTC)
  └── test job → sync job → commit & push
```

### e2e.yml (Push/PR)
```
on: push to main, pull_request to main
  └── checkout → install → run tests → upload artifacts
```

---

## 已知问题清单

| 问题 | 严重性 | 状态 |
|------|--------|------|
| stars.json 为空 | P0 | 未修复 |
| GH_TOKEN 401 | P0 | 未修复 |
| export_for_web.py 硬编码路径 | P0 | 未修复 |
| enrich.py batch_translate 返回原文 | P0 | 未修复 |
| CI 无失败通知 | P0 | 未修复 |
| translator.py 并发超限 | P1 | 未修复 |
| search_worker.js CDN 单点 | P1 | 未修复 |
| 大文件误提交 | P1 | 未修复 |
| 测试文件命名混乱 | P2 | 未修复 |
| 无 ARCHITECTURE.md | P2 | 未修复 |

---

## 恢复步骤

1. **刷新 GH_TOKEN**: 在 GitHub Secrets 中更新 `GH_TOKEN`
2. **修复脚本**: 应用 P0-02, P0-03 修复
3. **手动同步**: 运行 `python scripts/sync.py`
4. **验证数据**: 检查 `data/stars.json` 非空
5. **运行增强**: `python scripts/enrich.py && python scripts/generate_vectors.py`
6. **导出前端**: `python scripts/export_for_web.py`
7. **提交**: `git add data/ && git commit -m "Restore sync data"`
