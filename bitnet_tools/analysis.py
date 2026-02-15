from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import json
from pathlib import Path
from typing import Any


VALID_INPUT_TYPES = {"csv", "excel", "document"}


@dataclass
class NormalizedAnalysisInput:
    input_type: str
    source_name: str
    normalized_csv_text: str
    meta: dict[str, Any]
    preprocessing_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_type": self.input_type,
            "source_name": self.source_name,
            "normalized_csv_text": self.normalized_csv_text,
            "meta": self.meta,
            "preprocessing_steps": self.preprocessing_steps,
        }


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

    negative_by_parentheses = v.startswith("(") and v.endswith(")")
    if negative_by_parentheses:
        v = v[1:-1].strip()

    # normalize frequent human-entered numeric formats
    v = (
        v.replace(",", "")
        .replace("₩", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .replace("%", "")
        .strip()
    )

    if not v:
        return None

    try:
        parsed = float(v)
    except ValueError:
        return None

    return -parsed if negative_by_parentheses else parsed


def summarize_rows(rows: list[dict[str, str]], columns: list[str]) -> DataSummary:
    return summarize_reader(rows, columns)


def summarize_reader(rows: Any, columns: list[str]) -> DataSummary:
    missing_counts = {col: 0 for col in columns}
    numeric_counts: dict[str, int] = {col: 0 for col in columns}
    numeric_sums: dict[str, float] = {col: 0.0 for col in columns}
    numeric_mins: dict[str, float] = {}
    numeric_maxs: dict[str, float] = {}
    text_seen: dict[str, bool] = {col: False for col in columns}
    row_count = 0

    for row in rows:
        row_count += 1
        for col in columns:
            raw = (row.get(col) or "").strip()
            if raw == "":
                missing_counts[col] += 1
                continue
            num = _to_float(raw)
            if num is None:
                text_seen[col] = True
            else:
                numeric_counts[col] += 1
                numeric_sums[col] += num
                if col not in numeric_mins or num < numeric_mins[col]:
                    numeric_mins[col] = num
                if col not in numeric_maxs or num > numeric_maxs[col]:
                    numeric_maxs[col] = num

    dtypes: dict[str, str] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    for col in columns:
        count = numeric_counts[col]
        if count > 0 and not text_seen[col]:
            dtypes[col] = "float"
            numeric_stats[col] = {
                "count": float(count),
                "mean": float(numeric_sums[col] / count),
                "min": float(numeric_mins[col]),
                "max": float(numeric_maxs[col]),
            }
        else:
            dtypes[col] = "string"

    return DataSummary(
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        dtypes=dtypes,
        missing_counts=missing_counts,
        numeric_stats=numeric_stats,
    )


def build_prompt(summary: DataSummary, question: str) -> str:
    return (
        "너는 BitNet 기반 데이터 분석 보조자야.\n"
        "아래 데이터 요약을 바탕으로 답변해.\n"
        "출력 형식: 핵심요약 / 근거 / 한계 / 다음행동\n\n"
        f"사용자 질문: {question}\n\n"
        f"데이터 요약(JSON):\n{json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)}"
    )


def build_markdown_report(summary: DataSummary, question: str) -> str:
    lines = [
        "# BitNet CSV 분석 보고서",
        "",
        f"- 질문: {question}",
        f"- 행 수: {summary.row_count}",
        f"- 열 수: {summary.column_count}",
        "",
        "## 컬럼 정보",
        "",
        "| 컬럼 | 타입 | 결측 수 |",
        "|---|---|---:|",
    ]
    for col in summary.columns:
        lines.append(f"| {col} | {summary.dtypes.get(col, 'string')} | {summary.missing_counts.get(col, 0)} |")

    if summary.numeric_stats:
        lines.extend(["", "## 수치형 통계", "", "| 컬럼 | count | mean | min | max |", "|---|---:|---:|---:|---:|"])
        for col, stats in summary.numeric_stats.items():
            lines.append(
                f"| {col} | {stats['count']:.0f} | {stats['mean']:.4f} | {stats['min']:.4f} | {stats['max']:.4f} |"
            )

    return "\n".join(lines)


def normalize_analysis_input(payload: dict[str, Any]) -> NormalizedAnalysisInput:
    preprocessing_steps: list[str] = []

    raw_type = str(payload.get("input_type", "csv")).strip().lower() or "csv"
    if raw_type not in VALID_INPUT_TYPES:
        raise ValueError(f"unsupported input_type: {raw_type}")

    source_name = str(payload.get("source_name", "")).strip() or "<inline_csv>"

    meta = payload.get("meta", {})
    if not isinstance(meta, dict):
        meta = {"raw_meta": str(meta)}
        preprocessing_steps.append("meta_coerced_to_dict")

    normalized_csv_text = str(payload.get("normalized_csv_text", ""))
    if normalized_csv_text.strip():
        preprocessing_steps.append("use_normalized_csv_text")
    else:
        legacy_csv_text = str(payload.get("csv_text", ""))
        if not legacy_csv_text.strip():
            raise ValueError("normalized_csv_text is required")
        normalized_csv_text = legacy_csv_text
        preprocessing_steps.append("promote_legacy_csv_text")
        meta = {**meta, "legacy_csv_text": True}

    return NormalizedAnalysisInput(
        input_type=raw_type,
        source_name=source_name,
        normalized_csv_text=normalized_csv_text,
        meta=meta,
        preprocessing_steps=preprocessing_steps,
    )


def build_analysis_payload_from_request(
    payload: dict[str, Any], question: str, *, csv_path_override: str | None = None
) -> dict[str, Any]:
    normalized_input = normalize_analysis_input(payload)
    return build_analysis_payload_from_normalized_input(
        normalized_input,
        question,
        csv_path_override=csv_path_override,
    )


def build_analysis_payload_from_normalized_input(
    normalized_input: NormalizedAnalysisInput,
    question: str,
    *,
    csv_path_override: str | None = None,
) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(normalized_input.normalized_csv_text))
    if reader.fieldnames is None:
        raise ValueError("CSV header not found")

    columns = [str(c) for c in reader.fieldnames]
    summary = summarize_reader(reader, columns)
    csv_path = csv_path_override or normalized_input.source_name

    return {
        "csv_path": csv_path,
        "question": question,
        "summary": summary.to_dict(),
        "prompt": build_prompt(summary, question),
        "input": normalized_input.to_dict(),
    }


def build_analysis_payload(csv_path: str | Path, question: str) -> dict[str, Any]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    payload = {
        "input_type": "csv",
        "source_name": path.name,
        "normalized_csv_text": path.read_text(encoding="utf-8"),
        "meta": {"csv_path": str(path)},
    }
    return build_analysis_payload_from_request(payload, question, csv_path_override=str(path))


def build_analysis_payload_from_csv_text(csv_text: str, question: str) -> dict[str, Any]:
    return build_analysis_payload_from_request({"csv_text": csv_text}, question)
