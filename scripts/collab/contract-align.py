#!/usr/bin/env python3
"""contract-align.py <task_id> --endpoints '<json>' [--aligned-with @bot]
[--version M.m] [--dir REPO_DIR]

spec 3.2.3 阶段 0 的对齐写快照：把群里双方确认过的契约端点固化成
<repo>/.ai-devflow/<task_id>/contract.json，并把本地状态机（contract-state.json）
置为 aligned、ack_version=<version>。

contract.json 结构沿用现有 contract_checker.py 的约定：顶层对象含 "api" 数组，
每个端点为 {path, method} + 可选附加字段（如 response.fields，供 checker 的字段级
引用检查，见 spec 7.15 / contract_checker.py）。顶层再加 meta 记录对齐元数据；
结构校验只要求 path/method，meta 与附加字段都被现有 checker 容忍，不破坏其语义。

结构先于写入校验（path+method 必填），无效即 exit 1，不落任何文件。
"""
import argparse
import json
import os
import sys
import time

REQUIRED = {"path", "method"}


def contract_path(task_id, base):
    return os.path.join(base, ".ai-devflow", task_id, "contract.json")


def state_path(task_id, base):
    return os.path.join(base, ".ai-devflow", task_id, "contract-state.json")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task_id")
    p.add_argument("--endpoints", required=True, help="JSON 数组：[{path, method, ...}]")
    p.add_argument("--aligned-with", default="")
    p.add_argument("--version", default="1.0")
    p.add_argument("--dir", default=os.getcwd())
    args = p.parse_args()

    try:
        endpoints = json.loads(args.endpoints)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"contract-align: bad --endpoints JSON: {e}\n")
        sys.exit(1)
    if not isinstance(endpoints, list):
        sys.stderr.write("contract-align: --endpoints must be a JSON array\n")
        sys.exit(1)
    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict):
            sys.stderr.write(f"contract-align: endpoints[{i}] must be an object\n")
            sys.exit(1)
        missing = REQUIRED - set(ep.keys())
        if missing:
            sys.stderr.write(f"contract-align: endpoints[{i}] missing fields: {sorted(missing)}\n")
            sys.exit(1)

    contract = {
        "api": endpoints,
        "meta": {
            "version": args.version,
            "aligned_with": args.aligned_with,
            "aligned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    base = args.dir
    cp = contract_path(args.task_id, base)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    state = {
        "task_id": args.task_id,
        "status": "aligned",
        "ack_version": args.version,
        "pending_version": None,
        "last_cursor_ms": 0,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    sp = state_path(args.task_id, base)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(json.dumps({"task_id": args.task_id, "version": args.version,
                      "contract": cp, "state": sp, "endpoints": len(endpoints)},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
