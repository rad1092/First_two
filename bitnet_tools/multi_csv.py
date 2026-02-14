from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analysis import _to_float, summarize_reader


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return sorted_values[low]
    weight = pos - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def _outlier_ratio(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    sorted_values = sorted(values)
    q1 = _quantile(sorted_values, 0.25)
    q3 = _quantile(sorted_values, 0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0.0
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    outliers = sum(1 for v in sorted_values if v < low or v > high)
    return round(outliers / len(sorted_values), 6)


def _group_ratio_table(rows: list[dict[str, str]], group_col: str, target_col: str) -> dict[str, Any]:
    table: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        g = (row.get(group_col) or "").strip()
        t = (row.get(target_col) or "").strip()
        if g and t:
            table[g][t] += 1

    ratio_table: dict[str, Any] = {}
    for g, counter in table.items():
        total = sum(counter.values())
        ratio_table[g] = {
            k: {
                "count": v,
                "ratio": round(v / total, 6) if total else 0.0,
            }
            for k, v in counter.items()
        }

    return {
        "group_column": group_col,
        "target_column": target_col,
        "groups": ratio_table,
    }


def _profile_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    group_column: str | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    row_count = len(rows)
    missing = {c: 0 for c in columns}
    non_missing = {c: 0 for c in columns}
    uniques: dict[str, set[str]] = {c: set() for c in columns}
    value_counts: dict[str, Counter[str]] = {c: Counter() for c in columns}

    numeric_positive = {c: 0 for c in columns}
    numeric_zero = {c: 0 for c in columns}
    numeric_negative = {c: 0 for c in columns}
    numeric_values: dict[str, list[float]] = {c: [] for c in columns}

    for row in rows:
        for col in columns:
            raw = (row.get(col) or "").strip()
            if not raw:
                missing[col] += 1
                continue
            non_missing[col] += 1
            uniques[col].add(raw)
            value_counts[col][raw] += 1

            num = _to_float(raw)
            if num is not None:
                numeric_values[col].append(num)
                if num > 0:
                    numeric_positive[col] += 1
                elif num < 0:
                    numeric_negative[col] += 1
                else:
                    numeric_zero[col] += 1

    summary = summarize_reader(rows, columns)
    profiles: dict[str, Any] = {}
    for col in columns:
        nn = non_missing[col]
        top = value_counts[col].most_common(5)
        top_values = [
            {
                "value": v,
                "count": cnt,
                "ratio": round(cnt / row_count, 6) if row_count else 0.0,
            }
            for v, cnt in top
        ]

        numeric_total = numeric_positive[col] + numeric_zero[col] + numeric_negative[col]
        numeric_distribution: dict[str, float] = {}
        if numeric_total:
            numeric_distribution = {
                "positive_ratio": round(numeric_positive[col] / numeric_total, 6),
                "zero_ratio": round(numeric_zero[col] / numeric_total, 6),
                "negative_ratio": round(numeric_negative[col] / numeric_total, 6),
                "outlier_ratio": _outlier_ratio(numeric_values[col]),
            }

        dominant_value_ratio = top_values[0]["ratio"] if top_values else 0.0
        profiles[col] = {
            "missing_count": missing[col],
            "missing_ratio": round(missing[col] / row_count, 6) if row_count else 0.0,
            "non_missing_count": nn,
            "unique_count": len(uniques[col]),
            "unique_ratio": round(len(uniques[col]) / nn, 6) if nn else 0.0,
            "dominant_value_ratio": dominant_value_ratio,
            "top_values": top_values,
            "numeric_distribution": numeric_distribution,
            "dtype": summary.dtypes[col],
        }

    group_target_ratio: dict[str, Any] | None = None
    if group_column and target_column and group_column in columns and target_column in columns:
        group_target_ratio = _group_ratio_table(rows, group_column, target_column)

    return {
        "summary": summary.to_dict(),
        "column_profiles": profiles,
        "group_target_ratio": group_target_ratio,
    }


def _schema_drift(files: list[dict[str, Any]], shared_columns: list[str]) -> dict[str, Any]:
    drift: dict[str, Any] = {}
    for col in shared_columns:
        dtypes = [f["column_profiles"][col]["dtype"] for f in files if col in f["column_profiles"]]
        missing_ratios = [f["column_profiles"][col]["missing_ratio"] for f in files if col in f["column_profiles"]]
        dominant_ratios = [f["column_profiles"][col]["dominant_value_ratio"] for f in files if col in f["column_profiles"]]

        means = []
        for f in files:
            stats = f["summary"]["numeric_stats"].get(col)
            if stats:
                means.append(stats["mean"])

        drift[col] = {
            "dtype_changed": len(set(dtypes)) > 1,
            "missing_ratio_range": round(max(missing_ratios) - min(missing_ratios), 6) if missing_ratios else 0.0,
            "dominant_value_ratio_range": round(max(dominant_ratios) - min(dominant_ratios), 6) if dominant_ratios else 0.0,
            "mean_range": round(max(means) - min(means), 6) if means else 0.0,
        }
    return drift


def analyze_multiple_csv(
    csv_paths: list[Path],
    question: str,
    group_column: str | None = None,
    target_column: str | None = None,
) -> dict[str, Any]:
    if not csv_paths:
        raise ValueError("at least one CSV path is required")

    files: list[dict[str, Any]] = []
    all_columns: list[set[str]] = []
    total_rows = 0

    for path in csv_paths:
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"CSV header not found: {path}")
            columns = [str(c) for c in reader.fieldnames]
            rows = list(reader)

        profiled = _profile_rows(rows, columns, group_column=group_column, target_column=target_column)
        total_rows += profiled["summary"]["row_count"]
        all_columns.append(set(columns))

        files.append(
            {
                "path": str(path),
                "question": question,
                "summary": profiled["summary"],
                "column_profiles": profiled["column_profiles"],
                "group_target_ratio": profiled["group_target_ratio"],
            }
        )

    shared_columns = sorted(set.intersection(*all_columns)) if all_columns else []
    union_columns = sorted(set.union(*all_columns)) if all_columns else []

    return {
        "question": question,
        "file_count": len(files),
        "total_row_count": total_rows,
        "shared_columns": shared_columns,
        "union_columns": union_columns,
        "files": files,
        "schema_drift": _schema_drift(files, shared_columns),
        "code_guidance": build_code_guidance(shared_columns, group_column, target_column),
    }


def build_code_guidance(
    shared_columns: list[str],
    group_column: str | None = None,
    target_column: str | None = None,
) -> dict[str, str]:
    join_key = shared_columns[0] if shared_columns else "공통키컬럼"

    group_block = ""
    if group_column and target_column:
        group_block = (
            f"ratio_tbl = (merged.groupby('{group_column}')['{target_column}'].value_counts(normalize=True)"
            ".rename('ratio').reset_index())\n"
            "print('그룹-타깃 비율표:\n', ratio_tbl.head(20))\n\n"
        )

    pandas_code = (
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n\n"
        "paths = ['file1.csv', 'file2.csv', 'file3.csv']\n"
        "dfs = [pd.read_csv(p) for p in paths]\n\n"
        f"key = '{join_key}'\n"
        "merged = dfs[0]\n"
        "for df in dfs[1:]:\n"
        "    if key in merged.columns and key in df.columns:\n"
        "        merged = merged.merge(df, on=key, how='outer', suffixes=('', '_r'))\n\n"
        "missing_ratio = merged.isna().mean().sort_values(ascending=False)\n"
        "print('결측 비율 상위:\n', missing_ratio.head(10))\n\n"
        "numeric_cols = merged.select_dtypes(include='number').columns\n"
        "if len(numeric_cols) > 0:\n"
        "    ratio = (merged[numeric_cols] > 0).mean().sort_values(ascending=False)\n"
        "    print('양수 비율 상위:\n', ratio.head(10))\n"
        "    ratio.head(10).plot(kind='bar', title='양수 비율 상위 10개 컬럼')\n"
        "    plt.tight_layout(); plt.show()\n\n"
        f"{group_block}"
    )

    return {
        "recommended_steps": (
            "1) 공통 키 컬럼 확인 후 병합\n"
            "2) 컬럼별 결측/고유값/상위값 비율 확인\n"
            "3) 수치형 컬럼 비율(양수/0/음수), 이상치 비율, 분포 확인\n"
            "4) 그룹 컬럼 기준 타깃 비율 분석(예: 시도명-세차유형)\n"
            "5) 파일 간 스키마 변화/평균 변화 범위 확인"
        ),
        "pandas_example": pandas_code,
    }


def build_multi_csv_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 다중 CSV 분석 리포트",
        "",
        f"- 질문: {result['question']}",
        f"- 파일 수: {result['file_count']}",
        f"- 전체 행 수: {result['total_row_count']}",
        f"- 공통 컬럼: {', '.join(result['shared_columns']) if result['shared_columns'] else '(없음)'}",
        "",
    ]

    for file_info in result["files"]:
        lines.extend(
            [
                f"## 파일: {file_info['path']}",
                "",
                f"- 행 수: {file_info['summary']['row_count']}",
                f"- 열 수: {file_info['summary']['column_count']}",
                "",
                "| 컬럼 | 타입 | 결측비율 | 고유비율 | 대표값비율 |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for col in file_info["summary"]["columns"]:
            prof = file_info["column_profiles"][col]
            lines.append(
                f"| {col} | {prof['dtype']} | {prof['missing_ratio']:.4f} | {prof['unique_ratio']:.4f} | {prof['dominant_value_ratio']:.4f} |"
            )
        if file_info.get("group_target_ratio"):
            gtr = file_info["group_target_ratio"]
            lines.extend(["", f"- 그룹비율: {gtr['group_column']} x {gtr['target_column']}"])
        lines.append("")

    lines.extend(["## 파일 간 스키마/분포 변화", "", "| 컬럼 | 타입변화 | 결측비율범위 | 대표값비율범위 | 평균범위 |", "|---|---|---:|---:|---:|"])
    for col, drift in result["schema_drift"].items():
        lines.append(
            f"| {col} | {drift['dtype_changed']} | {drift['missing_ratio_range']:.4f} | {drift['dominant_value_ratio_range']:.4f} | {drift['mean_range']:.4f} |"
        )

    charts = result.get("charts")
    if charts:
        lines.extend(["", "## 생성된 차트 파일", ""])
        for file_path, chart_paths in charts.items():
            lines.append(f"- {file_path}")
            for c in chart_paths:
                lines.append(f"  - {c}")

    lines.extend(
        [
            "",
            "## 코드 가이드",
            "",
            "```text",
            result["code_guidance"]["recommended_steps"],
            "```",
            "",
            "```python",
            result["code_guidance"]["pandas_example"],
            "```",
        ]
    )

    return "\n".join(lines)


def result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
