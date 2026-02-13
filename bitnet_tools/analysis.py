from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass
class DataSummary:
    row_count: int
    column_count: int
    columns: list[str]
    dtypes: dict[str, str]
    missing_counts: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": self.columns,
            "dtypes": self.dtypes,
            "missing_counts": self.missing_counts,
            "numeric_stats": self.numeric_stats,
        }


def _to_float(value: str) -> float | None:
    v = value.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def summarize_rows(rows: list[dict[str, str]], columns: list[str]) -> DataSummary:
    missing_counts = {col: 0 for col in columns}
    numeric_values: dict[str, list[float]] = {col: [] for col in columns}
    text_seen: dict[str, bool] = {col: False for col in columns}

    for row in rows:
        for col in columns:
            raw = (row.get(col) or "").strip()
            if raw == "":
                missing_counts[col] += 1
                continue
            num = _to_float(raw)
            if num is None:
                text_seen[col] = True
            else:
                numeric_values[col].append(num)

    dtypes: dict[str, str] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    for col in columns:
        values = numeric_values[col]
        if values and not text_seen[col]:
            dtypes[col] = "float"
            numeric_stats[col] = {
                "count": float(len(values)),
                "mean": float(mean(values)),
                "min": float(min(values)),
                "max": float(max(values)),
            }
        else:
            dtypes[col] = "string"

    return DataSummary(
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
        dtypes=dtypes,
        missing_counts=missing_counts,
        numeric_stats=numeric_stats,
    )


def build_analysis_payload(csv_path: str | Path, question: str) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV header not found")
        columns = [str(c) for c in reader.fieldnames]
        rows = list(reader)

    summary = summarize_rows(rows, columns)

    prompt = (
        "너는 BitNet 기반 데이터 분석 보조자야.\n"
        "아래 데이터 요약을 바탕으로 답변해.\n"
        "출력 형식: 핵심요약 / 근거 / 한계 / 다음행동\n\n"
        f"사용자 질문: {question}\n\n"
        f"데이터 요약(JSON):\n{json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)}"
    )

    return {
        "csv_path": str(path),
        "question": question,
        "summary": summary.to_dict(),
        "prompt": prompt,
    }
