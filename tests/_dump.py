"""Run pydash ops over a pickled case list and emit canonical JSON results."""
import json
import pickle
import sys

import pydash as pyd


def run(case):
    op = case["op"]
    try:
        if op == "get":
            return {"ok": True, "v": repr(pyd.get(case["obj"], case["path"], case["default"]))}
        if op == "has":
            return {"ok": True, "v": repr(pyd.has(case["obj"], case["path"]))}
        if op == "to_path":
            return {"ok": True, "v": repr(pyd.to_path(case["path"]))}
        raise AssertionError(op)
    except Exception as exc:  # noqa: BLE001 - exact exception identity is part of the diff
        return {"ok": False, "e": f"{type(exc).__name__}: {exc}"}


cases = pickle.load(open(sys.argv[1], "rb"))
json.dump([run(c) for c in cases], sys.stdout, sort_keys=True)
