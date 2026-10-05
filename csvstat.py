#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csvstat - CSV 列级统计画像.

用法:
    python -m csvstat sales.csv
    python -m csvstat sales.csv --column price
    python -m csvstat sales.csv --json
    python -m csvstat sales.csv --sample 1000

纯标准库，无依赖。
"""
import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter

VERSION = "0.1.0"

DATE_RES = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$"),
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),
]


def infer_types(values):
    """推断一列的类型（启发式，规则见 README）。返回 (type_name, confidence)。"""
    non_empty = [v for v in values if v.strip() != ""]
    if not non_empty:
        return ("string", 0.0)
    n = len(non_empty)

    def is_int(v):
        try:
            int(v.strip().replace(",", ""))
            return True
        except ValueError:
            return False

    def is_float(v):
        try:
            float(v.strip().replace(",", ""))
            return True
        except ValueError:
            return False

    def is_date(v):
        return any(r.match(v.strip()) for r in DATE_RES)

    ni = sum(1 for v in non_empty if is_int(v))
    nf = sum(1 for v in non_empty if is_float(v))
    nd = sum(1 for v in non_empty if is_date(v))
    if ni / n >= 0.9:
        return ("int", round(ni / n * 100, 1))
    if nf / n >= 0.9:
        return ("float", round(nf / n * 100, 1))
    if nd / n >= 0.9:
        return ("date", round(nd / n * 100, 1))
    best = max(ni, nf, nd)
    return ("string", round((n - best) / n * 100, 1))


def num(v):
    return float(v.strip().replace(",", ""))


def column_stats(name, values, total_rows):
    nulls = sum(1 for v in values if v.strip() == "")
    empty_str = sum(1 for v in values if v == "")
    t, conf = infer_types(values)
    stat = {
        "列名": name,
        "类型": t,
        "类型置信度": f"{conf}%",
        "总行数": total_rows,
        "空值": nulls,
    }
    non_empty = [v for v in values if v.strip() != ""]
    if t in ("int", "float") and non_empty:
        xs = [num(v) for v in non_empty]
        stat["统计"] = {
            "个数": len(xs),
            "最小值": min(xs),
            "最大值": max(xs),
            "均值": round(statistics.fmean(xs), 4),
            "中位数": statistics.median(xs),
            "标准差": round(statistics.pstdev(xs), 4) if len(xs) > 1 else 0.0,
        }
    elif t == "date":
        stat["统计"] = {
            "个数": len(non_empty),
            "最早": min(non_empty),
            "最晚": max(non_empty),
        }
    else:
        c = Counter(non_empty)
        stat["统计"] = {
            "唯一值数": len(c),
            "最短长度": min((len(v) for v in non_empty), default=0),
            "最长长度": max((len(v) for v in non_empty), default=0),
            "空字符串": empty_str,
            "高频值": [{"值": v, "次数": k} for v, k in c.most_common(5)],
        }
    return stat


def read_rows(path, sample):
    try:
        f = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as e:
        print(f"error: 无法读取文件 {path}：{e}", file=sys.stderr)
        sys.exit(2)
    with f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print(f"error: 文件为空或没有表头：{path}", file=sys.stderr)
            sys.exit(1)
        rows = []
        for i, row in enumerate(reader):
            if sample and i >= sample:
                break
            rows.append(row)
    if not rows:
        print(f"error: 文件没有数据行：{path}", file=sys.stderr)
        sys.exit(1)
    return header, rows


def render_text(stats, only_col=None):
    out = []
    out.append(
        f"===== CSV 画像（{stats['文件']}，{stats['行数']} 行，{stats['列数']} 列）====="
    )
    for col in stats["列"]:
        if only_col and col["列名"] != only_col:
            continue
        out.append(
            f"\n【{col['列名']}】 类型={col['类型']}（置信度 {col['类型置信度']}） "
            f"空值={col['空值']}"
        )
        s = col["统计"]
        if col["类型"] in ("int", "float"):
            out.append(
                f"  个数 {s['个数']}  最小 {s['最小值']}  最大 {s['最大值']}  "
                f"均值 {s['均值']}  中位数 {s['中位数']}  标准差 {s['标准差']}"
            )
        elif col["类型"] == "date":
            out.append(f"  个数 {s['个数']}  最早 {s['最早']}  最晚 {s['最晚']}")
        else:
            out.append(
                f"  唯一值 {s['唯一值数']}  长度 {s['最短长度']}~{s['最长长度']}  "
                f"空字符串 {s['空字符串']}"
            )
            for h in s["高频值"]:
                out.append(f"    {h['值']!r}: {h['次数']} 次")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="csvstat", description="CSV 列级统计画像（纯本地）"
    )
    ap.add_argument("file", help="CSV 文件路径")
    ap.add_argument("--column", help="只看某一列的详细统计")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--sample", type=int, default=0,
                    help="只采样前 N 行（大文件用）")
    ap.add_argument("--version", action="version",
                    version=f"csvstat {VERSION}")
    args = ap.parse_args(argv)

    if args.sample is not None and args.sample < 0:
        print("error: --sample 不能为负数", file=sys.stderr)
        sys.exit(2)

    header, rows = read_rows(args.file, args.sample or 0)
    if args.column and args.column not in header:
        print(
            f"error: 没有这一列：{args.column}（可用列：{', '.join(header)}）",
            file=sys.stderr,
        )
        sys.exit(1)

    cols = []
    for j, name in enumerate(header):
        vals = [r[j] if j < len(r) else "" for r in rows]
        cols.append(column_stats(name, vals, len(rows)))
    result = {
        "文件": args.file,
        "行数": len(rows),
        "列数": len(header),
        "列": cols,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result, args.column))


if __name__ == "__main__":
    main()
