#!/usr/bin/env python3
"""
阶段3：基于历史模式做静态扫描狩猎。

用法:
  python3 03_pattern_scan.py --source-dir <postgres源码目录> --pattern <模式名>
  python3 03_pattern_scan.py --list-patterns

所有内置模式只做“粗筛”，产出的候选点必须人工复核后才能写入 candidates.md，
脚本本身不判断真假阳性。
"""
import argparse
import os
import re
import sys
from pathlib import Path

# 内置模式：名称 -> (说明, 正则规则列表, 提示语)
# 规则采用简单的“启发式行级/邻近行”匹配，替代 coccinelle/semgrep 的语义匹配，
# 优点是零依赖，缺点是误报率更高——必须人工复核。
BUILTIN_PATTERNS = {
    "missing-pfree-on-error": {
        "desc": "错误处理路径（ereport(ERROR,...) 之前）可能遗漏对之前 palloc 分配的资源做 pfree/清理",
        "trigger_re": r"\bereport\s*\(\s*ERROR\b",
        "context_lines": 25,
        "flag_if_absent_re": r"\bpfree\s*\(",
        "hint": "检查该 ereport(ERROR) 之前的函数体内是否有 palloc 分配但未在此错误路径释放的资源；"
                "注意：很多情况下依赖内存上下文自动回收是正常设计，不是 bug，需要结合上下文判断。",
    },
    "missing-check-for-interrupts": {
        "desc": "长循环/持锁循环中可能缺少 CHECK_FOR_INTERRUPTS()，存在无法响应取消/终止信号的风险",
        "trigger_re": r"\bfor\s*\(|\bwhile\s*\(",
        "context_lines": 30,
        "flag_if_absent_re": r"CHECK_FOR_INTERRUPTS\s*\(\s*\)",
        "hint": "长时间运行的循环体内如果既不调用 CHECK_FOR_INTERRUPTS 也没有其他让出点，"
                "可能导致该会话无法被 cancel/terminate；需人工确认循环是否可能长时间运行。",
    },
    "lock-without-matching-unlock": {
        "desc": "获取锁（LWLockAcquire/LockBuffer 等）后，在存在提前 return/goto 的路径上可能遗漏解锁",
        "trigger_re": r"\bLWLockAcquire\s*\(|\bLockBuffer\s*\([^,]+,\s*BUFFER_LOCK_(EXCLUSIVE|SHARE)",
        "context_lines": 40,
        "flag_if_absent_re": r"\bLWLockRelease\s*\(|\bLockBuffer\s*\([^,]+,\s*BUFFER_LOCK_UNLOCK",
        "hint": "确认加锁后的所有 return/goto/ereport(ERROR) 路径是否都能走到对应的解锁，"
                "特别关注异常路径；PG_TRY/PG_CATCH 块中常见此类隐患。",
    },
    "integer-overflow-in-size-calc": {
        "desc": "内存/缓冲区大小计算中使用了乘法但未做溢出检查",
        "trigger_re": r"\b(palloc|repalloc|malloc)\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\*\s*[A-Za-z_]",
        "context_lines": 10,
        "flag_if_absent_re": r"overflow|MemoryContextAllocHuge|AllocSizeIsValid",
        "hint": "变量 * 变量 形式的大小计算若来自不受信任的输入（如用户提供的数组长度/字符串长度），"
                "存在整数溢出后分配过小缓冲区的风险，需人工核实输入来源与边界检查。",
    },
    "signal-handler-non-async-safe": {
        "desc": "信号处理函数中调用了非 async-signal-safe 的函数（如 palloc/elog/ereport）",
        "trigger_re": r"^static\s+void\s+\w*(SigHandler|_handler|handle_sig)\w*\s*\(",
        "context_lines": 30,
        "flag_if_absent_re": r"^(?!.*\b(palloc|elog|ereport|malloc|free)\b)",
        "hint": "信号处理函数中出现 palloc/elog/ereport/malloc/free 等非异步信号安全调用，"
                "在信号打断关键区时可能导致状态损坏或死锁，需人工确认。",
    },
}


def list_patterns():
    print("内置模式列表：\n")
    for name, meta in BUILTIN_PATTERNS.items():
        print(f"  {name}\n    {meta['desc']}\n")


def scan_file(path: Path, pattern_meta: dict):
    findings = []
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return findings
    lines = text.splitlines()
    trigger_re = re.compile(pattern_meta["trigger_re"])
    absent_re = re.compile(pattern_meta["flag_if_absent_re"])
    ctx = pattern_meta["context_lines"]

    for i, line in enumerate(lines):
        if trigger_re.search(line):
            window = lines[max(0, i - ctx): i]
            window_text = "\n".join(window)
            if not absent_re.search(window_text):
                findings.append({
                    "file": str(path),
                    "line": i + 1,
                    "trigger": line.strip(),
                })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir")
    ap.add_argument("--pattern")
    ap.add_argument("--list-patterns", action="store_true")
    ap.add_argument("--ext", default=".c", help="扫描的文件后缀，默认 .c")
    ap.add_argument("--max-findings", type=int, default=200)
    args = ap.parse_args()

    if args.list_patterns:
        list_patterns()
        return

    if not args.source_dir or not args.pattern:
        print("错误: 需要 --source-dir 和 --pattern，或使用 --list-patterns 查看可用模式", file=sys.stderr)
        sys.exit(1)

    if args.pattern not in BUILTIN_PATTERNS:
        print(f"未知模式: {args.pattern}，可用模式见 --list-patterns", file=sys.stderr)
        sys.exit(1)

    meta = BUILTIN_PATTERNS[args.pattern]
    src_root = Path(args.source_dir) / "src"
    if not src_root.exists():
        src_root = Path(args.source_dir)

    all_findings = []
    for path in src_root.rglob(f"*{args.ext}"):
        # 跳过测试代码与第三方 vendor 代码，减少噪音
        if any(seg in str(path) for seg in ("/test/", "/tests/", "/contrib/", "/tmp_")):
            continue
        all_findings.extend(scan_file(path, meta))
        if len(all_findings) >= args.max_findings:
            break

    artifact_dir = Path(args.source_dir) / "find-bug-artifacts"
    artifact_dir.mkdir(exist_ok=True)
    out_path = artifact_dir / f"scan_{args.pattern}.md"

    with out_path.open("w") as f:
        f.write(f"# 模式扫描结果: {args.pattern}\n\n")
        f.write(f"说明: {meta['desc']}\n\n")
        f.write(f"提示: {meta['hint']}\n\n")
        f.write(f"共 {len(all_findings)} 处候选点（未经人工复核，误报率可能较高）\n\n")
        for fnd in all_findings:
            f.write(f"- `{fnd['file']}:{fnd['line']}`  `{fnd['trigger']}`\n")

    print(f"扫描完成，共 {len(all_findings)} 处候选点，结果写入 {out_path}")
    print("下一步：逐条人工复核，排除误报后写入 find-bug-artifacts/candidates.md")


if __name__ == "__main__":
    main()
