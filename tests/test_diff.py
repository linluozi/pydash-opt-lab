"""Differential test: pristine pydash vs patched pydash, byte-for-byte.

The baseline tree is produced by copying ``src/pydash`` and reverse-applying
``patch.diff``, so the comparison uses the real upstream code, not a rewrite.
"""
import hashlib
import json
import os
import pickle
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20261119
ATTEMPTS = 1600


def make_obj(rng, depth=0):
    if depth >= 3:
        return rng.choice([None, 0, 1, -1, 2 ** 63, "x", "", "üñï", 3.14, True, False])
    kind = rng.random()
    if kind < 0.45:
        out = {}
        for _ in range(rng.randint(0, 5)):
            key = rng.choice(["a", "b", "c", "d", "", "键", "a.b", "0", 0, 1, "n", "owner"])
            out[key] = make_obj(rng, depth + 1)
        return out
    if kind < 0.72:
        return [make_obj(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return rng.choice([None, 0, 1, 2, "x", "", "üñï", 3.14, True, False])


def walk_paths(obj, prefix=None, acc=None):
    acc = acc if acc is not None else []
    if isinstance(obj, dict):
        for key, val in obj.items():
            token = f"[{key}]" if isinstance(key, int) else str(key).replace(".", r"\.")
            path = f"{prefix}.{token}" if prefix else token
            acc.append(path)
            walk_paths(val, path, acc)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            path = f"{prefix}[{i}]" if prefix else f"[{i}]"
            acc.append(path)
            walk_paths(val, path, acc)
    return acc


def make_path(rng, obj):
    roll = rng.random()
    valid = walk_paths(obj)
    if roll < 0.40 and valid:
        return rng.choice(valid)
    if roll < 0.50:
        return rng.choice([None, "", ".", "a..b", "[0]", "a[", "]b", "\\", "键.值"])
    if roll < 0.60:
        return ["a", 0, "b.c", 1, "键"]
    if roll < 0.68:
        return rng.choice([0, 1, -1, 2 ** 63])
    if roll < 0.86:
        return ".".join(rng.choice(["a", "b", "c", "0", "键", ""]) for _ in range(rng.randint(1, 6)))
    if roll < 0.93:
        return ".".join(["a"] * 200)
    return rng.choice(valid) if valid else "a"


def build_cases():
    rng = random.Random(SEED)
    seen, cases = set(), []
    for _ in range(ATTEMPTS):
        obj = make_obj(rng)
        for op in ("get", "has", "to_path"):
            path = make_path(rng, obj)
            case = {"op": op, "obj": obj, "path": path, "default": rng.choice([None, "D", 0])}
            digest = hashlib.sha256(pickle.dumps(case, protocol=4)).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            cases.append(case)
    return cases


def dump(pythonpath, cases_file):
    env = dict(os.environ, PYTHONPATH=pythonpath)
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "_dump.py"), cases_file],
        env=env, check=True, capture_output=True,
    )
    return out.stdout


def main():
    cases = build_cases()
    assert len(cases) >= 1000, f"only {len(cases)} unique cases"
    tmp = tempfile.mkdtemp(prefix="pydash-diff-")
    try:
        base_src = os.path.join(tmp, "src")
        shutil.copytree(os.path.join(ROOT, "src"), base_src)
        shutil.copy(os.path.join(ROOT, "patch.diff"), os.path.join(tmp, "patch.diff"))
        subprocess.run(
            ["git", "apply", "-R", "-p1", "patch.diff"], cwd=tmp, check=True,
            capture_output=True,
        )
        cases_file = os.path.join(tmp, "cases.pkl")
        pickle.dump(cases, open(cases_file, "wb"), protocol=4)
        base = dump(os.path.join(tmp, "src"), cases_file)
        opt = dump(os.path.join(ROOT, "src"), cases_file)
        mismatches = sum(1 for a, b in zip(base, opt) if a != b)
        print(f"unique cases: {len(cases)} (sha256-deduped from {ATTEMPTS} generated)")
        print(f"baseline bytes: {len(base)}  optimized bytes: {len(opt)}")
        print(f"result_sha256 base={hashlib.sha256(base).hexdigest()}")
        print(f"result_sha256 opt ={hashlib.sha256(opt).hexdigest()}")
        print(f"mismatches: {mismatches}")
        assert base == opt, "differential mismatch"
    finally:
        shutil.rmtree(tmp)

    # to_path must keep returning an independent list even on a cache hit.
    import pydash as pyd
    first, second = pyd.to_path("a.b.c"), pyd.to_path("a.b.c")
    assert first == second == ["a", "b", "c"] and first is not second
    first.append("mutated")
    assert pyd.to_path("a.b.c") == ["a", "b", "c"]
    print("to_path mutation isolation: OK")


if __name__ == "__main__":
    main()
