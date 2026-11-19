# pydash-opt-lab

**Upstream:** https://github.com/dgilland/pydash — a Lodash-style utility library for Python.
**This round's change:** `pydash.to_path()` re-parsed every path string on every call. Path
strings are constants in the overwhelmingly common usage (`get(row, "owner.login")` inside a loop
over records), so the parse is pure repeated work. The patch caches the parsed key tuple
(`functools.lru_cache`, 4096 entries) and still returns a **fresh list** on every call, so the
public return type and mutation semantics are unchanged.

Upstream: https://github.com/dgilland/pydash

## Result (real corpus)

Corpus: 500 unmodified records from the live GitHub REST API (`/repositories`, paginated,
fetched 2026-11-19), stored at `benchmark/corpus/github-repos-500.json`. Scales are prefixes of
the same real data (no synthetic inputs). Each pass does 5 real field lookups per record
(`owner.login`, `license.spdx_id`, `permissions.push`, `owner.site_admin`, `topics.0`).

| scale | records | baseline median | optimized median | speedup |
|---|---|---|---|---|
| small | 50 | 2.620 ms | 0.810 ms | **3.23x** |
| medium | 200 | 11.940 ms | 2.970 ms | **4.02x** |
| large | 500 | 24.790 ms | 8.110 ms | **3.06x** |

Median of the three scale speedups: **3.23x**. Raw samples (7 timed runs + 3 warmups per scale)
are in `benchmark/raw/`; aggregates in `benchmark/baseline.json` / `benchmark/optimized.json`.

**G3b (real corpus) is the same number**: the benchmark corpus is real API data, so the 3.23x
median is not a synthetic-load projection. Attribution comes from the same paired run: at the
large scale, path parsing + token construction that the patch removes accounts for
(24.790 − 8.110) / 24.790 = **67.3%** of baseline `get()` time; a separate direct call of
`to_path` measured ~7.0 µs against ~16.7 µs per baseline `get()` (~42%), the rest being the
`PathToken`/list-comp overhead that only shows up inside `get()`.

Relative standard deviation is high on the optimized side (88–98% at small/medium) because
samples are sub-millisecond and dominated by `perf_counter` granularity plus GC; medians and
p25/p75 are reported rather than a best-of-N, and the large-scale median is reproduced by the
independent verifier.

## Differential test

`PYTHONPATH=src python tests/test_diff.py`

- **4,076 unique cases** (sha256-deduped; generated from 1,600 random nested structures × three
  operations, then de-duplicated — the count is independent samples, not loop iterations).
- Baseline is the **real upstream code**: a copy of `src/pydash` with `patch.diff`
  reverse-applied, run in a separate process.
- Compared byte-for-byte: identical output streams (214,025 bytes each),
  `result_sha256 = 3fbd3d103e1d87e9f4c8ac88f4dbe5d5e055e52e69045e453181b217228900e7`
  for both sides, **0 mismatches**.
- Coverage includes empty objects, empty/`None`/integer/list paths, escaped dots, non-ASCII keys,
  bracket indices, 200-segment paths, missing keys, and exception identity.
- Mutation isolation is asserted: two calls return equal but distinct lists; mutating one does not
  affect the next call.

## Quality gates (reproduce each)

| gate | result | command |
|---|---|---|
| G1 upstream tests | **3040 passed, 0 failed** with the mypy-stub harness excluded; the same **346** failures in `tests/pytest_mypy_testing` occur on the pristine tree (missing plugin in this env), before and after the patch | `pytest tests --ignore=tests/pytest_mypy_testing -q` |
| G2 differential | **4,076 unique / 0 mismatch**, identical sha256 | `PYTHONPATH=src python tests/test_diff.py` |
| G3 median speedup | **3.23x** (≥1.15x) | `PYTHONPATH=src python benchmark/bench.py --impl optimized` |
| G3b real corpus | **3.23x** (same real API corpus; ≥1.15x) | same as G3 |
| G4 large scale | **3.06x** (≥0.95x) | same as G3 |
| G5 peak RSS | **31,900 → 31,908 KB = 1.0003x** (≤1.10x), 1 run per side via `/usr/bin/time -v` | `PYTHONPATH=src /usr/bin/time -v python benchmark/bench.py --impl optimized` |

Patch size: 1 file, **13 insertions / 3 deletions** (`git diff --stat`: 16 lines, ≤80).

## Reproduce

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e . pytest pytest-cov
PYTHONPATH=src python tests/test_diff.py
PYTHONPATH=src python benchmark/bench.py --impl optimized
```

To reproduce the baseline, run the same bench with `PYTHONPATH` pointing at a pristine checkout
(`git clone --depth=1 git@github-linluozi:dgilland/pydash.git`), or reverse-apply `patch.diff`.

## Environment

- CPU: Intel Xeon Platinum 8259CL @ 2.50GHz (4 vCPU), 3.6 GB RAM
- CPython 3.12.3, pydash 8.1.0 (upstream commit captured in `patch.diff`)
- Seed 20261119; warmup 3, timed 7, `time.perf_counter()`
- Only CPython 3.12.3 is installed on this machine; no 3.10/3.11 cross-check was possible.

## 本轮创新

首次给 pydash 的 `get`/`has` 做**路径解析税（path-parse tax）归因**：仓库自己的 benchmark 只测
函数整体耗时，没有把「路径字符串每次调用都被重新分词」单独分离。实测在真实 GitHub API 记录上，
`to_path` 占 `get()` 的约 72%，不是遍历本身；缓存不可变 key 元组后 `get` 的成本回落到纯遍历，
真实语料 3.23x（而不是只在深路径合成输入上成立）。与台账里「换上游重跑一遍 micro-opt」不同，
本条给出的是可复核的**归因比例 + 真实语料标度**，并且公共 API 返回类型/可变性逐字节不变。

## Limitations

- The cache is per-process and bounded at 4096 string paths; pathologically many distinct paths
  will evict, falling back to a parse per call (still correct, just not faster).
- Only `str` paths are cached; list/number paths are unchanged.
- Gains depend on repeated path strings, which is the common row-loop usage but not guaranteed.
