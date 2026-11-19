"""Benchmark pydash.get on a real GitHub API corpus.

Usage:
  PYTHONPATH=src python benchmark/bench.py --impl baseline --records 500
Writes benchmark/<impl>.json and benchmark/raw/<impl>-<scale>-<i>.json.
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time

import pydash as pyd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmark", "corpus", "github-repos-500.json")
SCALES = {"small": 50, "medium": 200, "large": 500}
PATHS = ["owner.login", "license.spdx_id", "permissions.push", "owner.site_admin", "topics.0"]
SEED = 20261119
WARMUP = 3
TIMED = 7


def one_pass(records):
    checksum = hashlib.sha256()
    hits = 0
    for rec in records:
        for path in PATHS:
            value = pyd.get(rec, path)
            hits += value is not None
            checksum.update(repr(value).encode("utf-8", "replace"))
    return hits, checksum.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--records", type=int, default=500)
    args = ap.parse_args()

    records = json.load(open(CORPUS, encoding="utf-8"))[: args.records]
    scales = {}
    for name, n in SCALES.items():
        subset = records[:n]
        hits, digest = one_pass(subset)  # also validates determinism
        for _ in range(WARMUP):
            one_pass(subset)
        samples = []
        for i in range(TIMED):
            t0 = time.perf_counter()
            h, d = one_pass(subset)
            dt = time.perf_counter() - t0
            assert h == hits and d == digest, "nondeterministic result"
            raw = {
                "impl": args.impl, "scale": name, "i": i, "duration_s": dt,
                "records": n, "gets": n * len(PATHS), "seed": SEED,
                "python": platform.python_version(), "pydash": pyd.__version__,
                "hits": h, "result_sha256": d,
            }
            samples.append(dt)
            os.makedirs(os.path.join(ROOT, "benchmark", "raw"), exist_ok=True)
            with open(os.path.join(ROOT, "benchmark", "raw", f"{args.impl}-{name}-{i}.json"), "w") as fh:
                json.dump(raw, fh, sort_keys=True)
        s = sorted(samples)
        med = statistics.median(s)
        p25 = s[len(s) // 4]
        p75 = s[(3 * len(s)) // 4]
        scales[name] = {
            "records": n, "gets": n * len(PATHS), "samples_s": samples,
            "median_s": med, "p25_s": p25, "p75_s": p75,
            "rsd_pct": 100 * statistics.pstdev(s) / statistics.fmean(s),
            "hits": hits, "result_sha256": digest,
        }
        print(f"{args.impl:9s} {name:6s} n={n:4d} median={med:.5f}s p25={p25:.5f} p75={p75:.5f} rsd={scales[name]['rsd_pct']:.2f}%")
    out = {
        "impl": args.impl, "corpus": "benchmark/corpus/github-repos-500.json",
        "corpus_origin": "live GitHub REST API /repositories paginated, fetched 2026-11-19, unmodified",
        "paths": PATHS, "seed": SEED, "warmup": WARMUP, "timed": TIMED,
        "python": platform.python_version(), "pydash": pyd.__version__,
        "scales": scales,
    }
    with open(os.path.join(ROOT, "benchmark", f"{args.impl}.json"), "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
