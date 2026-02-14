from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analysis import _to_float, summarize_reader


def _profile_rows(rows: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    row_count = len(rows)
    missing = {c: 0 for c in columns}
    non_missing = {c: 0 for c in columns}
    uniques: dict[str, set[str]] = {c: set() for c in columns}
    value_counts: dict[str, Counter[str]] = {c: Counter() for c in columns}

    numeric_positive = {c: 0 for c in columns}
    numeric_zero = {c: 0 for c in columns}
    numeric_negative = {c: 0 for c in columns}

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
            }

        profiles[col] = {
            "missing_count": missing[col],
            "missing_ratio": round(missing[col] / row_count, 6) if row_count else 0.0,
            "non_missing_count": nn,
            "unique_count": len(uniques[col]),
            "unique_ratio": round(len(uniques[col]) / nn, 6) if nn else 0.0,
            "top_values": top_values,
            "numeric_distribution": numeric_distribution,
            "dtype": summary.dtypes[col],
        }

    return {
        "summary": summary.to_dict(),
        "column_profiles": profiles,
    }


def analyze_multiple_csv(csv_paths: list[Path], question: str) -> dict[str, Any]:
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

        profiled = _profile_rows(rows, columns)
        total_rows += profiled["summary"]["row_count"]
        all_columns.append(set(columns))

        files.append(
            {
                "path": str(path),
                "question": question,
                "summary": profiled["summary"],
                "column_profiles": profiled["column_profiles"],
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
        "code_guidance": build_code_guidance(shared_columns),
    }


def build_code_guidance(shared_columns: list[str]) -> dict[str, str]:
    join_key = shared_columns[0] if shared_columns else "공통키컬럼"

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
        "    plt.tight_layout(); plt.show()\n"
    )

    return {
        "recommended_steps": (
            "1) 공통 키 컬럼 확인 후 병합\n"
            "2) 컬럼별 결측/고유값/상위값 비율 확인\n"
            "3) 수치형 컬럼 비율(양수/0/음수)과 분포 시각화\n"
            "4) 지역/유형 컬럼과 수치형 컬럼 교차 집계로 인사이트 도출"
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
                "| 컬럼 | 타입 | 결측비율 | 고유비율 |",
                "|---|---|---:|---:|",
            ]
        )
        for col in file_info["summary"]["columns"]:
            prof = file_info["column_profiles"][col]
            lines.append(
                f"| {col} | {prof['dtype']} | {prof['missing_ratio']:.4f} | {prof['unique_ratio']:.4f} |"
            )
        lines.append("")

    lines.extend(
        [
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
