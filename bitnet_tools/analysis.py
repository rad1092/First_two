from __future__ import annotations

from dataclasses import dataclass
import csv
from datetime import datetime
import io
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


@dataclass
class DataSummary:
    row_count: int
    column_count: int
    columns: list[str]
    dtypes: dict[str, str]
    missing_counts: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]
    top_values: dict[str, list[tuple[str, int]]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": self.columns,
            "dtypes": self.dtypes,
            "missing_counts": self.missing_counts,
            "numeric_stats": self.numeric_stats,
            "top_values": self.top_values,
        }


def _to_float(value: str) -> float | None:
    v = value.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(value: str) -> int | None:
    v = value.strip()
    if not v:
        return None
    try:
        if any(ch in v for ch in ".eE"):
            return None
        return int(v)
    except ValueError:
        return None


def _to_iso_date(value: str) -> datetime | None:
    v = value.strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("values cannot be empty")
    idx = (len(ordered) - 1) * p
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _parse_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    sample = csv_text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("CSV header not found")

    columns = [str(c) for c in reader.fieldnames]
    rows = list(reader)
    return columns, rows


def summarize_rows(rows: list[dict[str, str]], columns: list[str]) -> DataSummary:
    missing_counts = {col: 0 for col in columns}
    numeric_values: dict[str, list[float]] = {col: [] for col in columns}
    value_counts: dict[str, dict[str, int]] = {col: {} for col in columns}
    seen_non_missing: dict[str, list[str]] = {col: [] for col in columns}

    for row in rows:
        for col in columns:
            raw = (row.get(col) or "").strip()
            if raw == "":
                missing_counts[col] += 1
                continue
            seen_non_missing[col].append(raw)
            value_counts[col][raw] = value_counts[col].get(raw, 0) + 1
            num = _to_float(raw)
            if num is not None:
                numeric_values[col].append(num)

    dtypes: dict[str, str] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    top_values: dict[str, list[tuple[str, int]]] = {}

    for col in columns:
        non_missing = seen_non_missing[col]
        values = numeric_values[col]

        if non_missing and all(_to_int(v) is not None for v in non_missing):
            dtypes[col] = "int"
        elif non_missing and len(values) == len(non_missing):
            dtypes[col] = "float"
        elif non_missing and all(_to_iso_date(v) is not None for v in non_missing):
            dtypes[col] = "date"
        else:
            dtypes[col] = "string"

        if values and len(values) == len(non_missing):
            stats = {
                "count": float(len(values)),
                "mean": float(mean(values)),
                "min": float(min(values)),
                "q1": float(_percentile(values, 0.25)),
                "median": float(_percentile(values, 0.5)),
                "q3": float(_percentile(values, 0.75)),
                "max": float(max(values)),
            }
            stats["std"] = float(pstdev(values)) if len(values) > 1 else 0.0
            numeric_stats[col] = stats

        ranked = sorted(value_counts[col].items(), key=lambda x: (-x[1], x[0]))
        top_values[col] = ranked[:5]

    return DataSummary(
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
        dtypes=dtypes,
        missing_counts=missing_counts,
        numeric_stats=numeric_stats,
        top_values=top_values,
    )


def build_analysis_payload_from_csv_text(csv_text: str, question: str) -> dict[str, Any]:
    columns, rows = _parse_csv_text(csv_text)
    summary = summarize_rows(rows, columns)
    prompt = build_prompt(summary.to_dict(), question)
    return {
        "question": question,
        "summary": summary.to_dict(),
        "prompt": prompt,
    }


def build_prompt(summary: dict[str, Any], question: str) -> str:
    return (
        "너는 BitNet 기반 데이터 분석 보조자야.\n"
        "아래 데이터 요약을 바탕으로 답변해.\n"
        "출력 형식: 핵심요약 / 근거 / 한계 / 다음행동\n\n"
        f"사용자 질문: {question}\n\n"
        f"데이터 요약(JSON):\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


def build_analysis_payload(csv_path: str | Path, question: str) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    columns, rows = _parse_csv_text(raw)
    summary = summarize_rows(rows, columns).to_dict()

    return {
        "csv_path": str(path),
        "question": question,
        "summary": summary,
        "prompt": build_prompt(summary, question),
    }
