from __future__ import annotations

from dataclasses import dataclass, field
import csv
import io
import random
import re
from typing import Any


@dataclass
class AnalysisIntent:
    question: str
    top_n: int | None = None
    sample_n: int | None = None
    threshold: float | None = None
    threshold_column: str | None = None
    region: str | None = None
    region_column: str | None = None
    compare_periods: bool = False
    metric_column: str | None = None


@dataclass
class AnalysisPlan:
    intent: AnalysisIntent
    nodes: list[dict[str, Any]]
    fallback: bool = False
    warnings: list[str] = field(default_factory=list)


def _schema_columns(schema: dict[str, Any]) -> list[str]:
    cols = schema.get("columns", [])
    if isinstance(cols, list):
        return [str(c) for c in cols]
    return []


def _schema_dtypes(schema: dict[str, Any]) -> dict[str, str]:
    dtypes = schema.get("dtypes", {})
    if isinstance(dtypes, dict):
        return {str(k): str(v) for k, v in dtypes.items()}
    return {}


def _first_numeric_column(schema: dict[str, Any]) -> str | None:
    dtypes = _schema_dtypes(schema)
    for col, dtype in dtypes.items():
        if dtype in {"float", "int", "number", "numeric"}:
            return col
    return None


def _first_text_column(schema: dict[str, Any]) -> str | None:
    dtypes = _schema_dtypes(schema)
    for col in _schema_columns(schema):
        if dtypes.get(col, "string") == "string":
            return col
    return _schema_columns(schema)[0] if _schema_columns(schema) else None


def _safe_float(value: Any) -> float | None:
    try:
        return float(str(value).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def parse_question_to_intent(question: str, schema: dict[str, Any]) -> AnalysisIntent:
    text = (question or "").strip()
    lower = text.lower()
    intent = AnalysisIntent(question=text)

    top_m = re.search(r"(?:top|상위)\s*(\d+)", lower)
    if top_m:
        intent.top_n = int(top_m.group(1))

    sample_m = re.search(r"(?:sample|샘플)\s*(\d+)", lower)
    if sample_m:
        intent.sample_n = int(sample_m.group(1))

    th_m = re.search(r"(?:threshold|임계값)\s*(\d+(?:\.\d+)?)", lower)
    if th_m:
        intent.threshold = float(th_m.group(1))

    if intent.threshold is None:
        above_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:이상|초과)", text)
        if above_m:
            intent.threshold = float(above_m.group(1))

    if any(token in text for token in ["전후", "전/후", "이전", "이후", "before", "after", "대비"]):
        intent.compare_periods = True

    columns = _schema_columns(schema)
    for col in columns:
        if col.lower() in lower and intent.threshold is not None:
            intent.threshold_column = col
            break

    if intent.threshold is not None and not intent.threshold_column:
        intent.threshold_column = _first_numeric_column(schema)

    region_col_candidates = [c for c in columns if any(k in c.lower() for k in ["region", "city", "area", "지역", "도시"])]
    if region_col_candidates:
        intent.region_column = region_col_candidates[0]

    known_regions = schema.get("region_values", [])
    if not isinstance(known_regions, list):
        known_regions = []
    for rg in known_regions:
        if str(rg) and str(rg).lower() in lower:
            intent.region = str(rg)
            break

    if intent.region is None and intent.region_column:
        tokens = [t for t in re.split(r"\s+", text) if t]
        for tok in tokens:
            if re.fullmatch(r"[가-힣A-Za-z][가-힣A-Za-z0-9_-]+", tok):
                if tok.lower() not in {"top", "sample", "threshold", "임계값", "상위", "샘플"}:
                    if tok in columns:
                        continue
                    intent.region = tok
                    break

    intent.metric_column = _first_numeric_column(schema)
    return intent


def build_plan(intent: AnalysisIntent, schema_profile: dict[str, Any]) -> AnalysisPlan:
    warnings: list[str] = []
    group_col = intent.region_column or _first_text_column(schema_profile)
    metric_col = intent.metric_column or _first_numeric_column(schema_profile)

    if metric_col is None:
        warnings.append("numeric metric column not found")

    nodes = [
        {
            "op": "filter",
            "enabled": bool(intent.region or intent.threshold is not None),
            "region_column": intent.region_column,
            "region": intent.region,
            "threshold_column": intent.threshold_column,
            "threshold": intent.threshold,
        },
        {
            "op": "groupby",
            "enabled": bool(group_col),
            "columns": [group_col] if group_col else [],
        },
        {
            "op": "agg",
            "enabled": bool(metric_col),
            "metric": metric_col,
            "fn": "sum",
        },
        {
            "op": "rank",
            "enabled": bool(intent.top_n),
            "top_n": intent.top_n,
            "order": "desc",
        },
        {
            "op": "sample",
            "enabled": bool(intent.sample_n),
            "sample_n": intent.sample_n,
            "seed": 42,
        },
        {
            "op": "export",
            "enabled": True,
            "include_meta": True,
        },
    ]

    return AnalysisPlan(intent=intent, nodes=nodes, fallback=False, warnings=warnings)


def _execute_filter(rows: list[dict[str, Any]], node: dict[str, Any]) -> list[dict[str, Any]]:
    out = rows
    region = node.get("region")
    region_col = node.get("region_column")
    if region and region_col:
        out = [r for r in out if str(r.get(region_col, "")).strip().lower() == str(region).strip().lower()]

    threshold = node.get("threshold")
    threshold_col = node.get("threshold_column")
    if threshold is not None and threshold_col:
        fth = float(threshold)
        filtered: list[dict[str, Any]] = []
        for r in out:
            num = _safe_float(r.get(threshold_col))
            if num is not None and num >= fth:
                filtered.append(r)
        out = filtered
    return out


def _execute_group_agg(rows: list[dict[str, Any]], group_col: str | None, metric_col: str | None) -> list[dict[str, Any]]:
    if not group_col or not metric_col:
        return rows
    grouped: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in rows:
        key = str(r.get(group_col, "<missing>"))
        val = _safe_float(r.get(metric_col))
        if val is None:
            continue
        grouped[key] = grouped.get(key, 0.0) + val
        counts[key] = counts.get(key, 0) + 1
    return [{group_col: k, f"sum_{metric_col}": v, "count": counts.get(k, 0)} for k, v in grouped.items()]


def execute_plan(plan: AnalysisPlan, data: list[dict[str, Any]]) -> dict[str, Any]:
    rows = list(data)
    meta: dict[str, Any] = {"node_count": len(plan.nodes), "warnings": list(plan.warnings)}

    try:
        grouped_rows = rows
        group_col: str | None = None
        metric_col: str | None = None

        for node in plan.nodes:
            if not node.get("enabled", False):
                continue
            op = node.get("op")
            if op == "filter":
                rows = _execute_filter(rows, node)
                grouped_rows = rows
            elif op == "groupby":
                cols = node.get("columns", [])
                group_col = cols[0] if cols else None
            elif op == "agg":
                metric_col = node.get("metric")
                grouped_rows = _execute_group_agg(rows, group_col, metric_col)
            elif op == "rank":
                top_n = int(node.get("top_n") or 0)
                if top_n > 0:
                    rank_key = f"sum_{metric_col}" if metric_col else None
                    if rank_key:
                        grouped_rows = sorted(grouped_rows, key=lambda r: _safe_float(r.get(rank_key)) or 0.0, reverse=True)[:top_n]
            elif op == "sample":
                sample_n = int(node.get("sample_n") or 0)
                if sample_n > 0 and rows:
                    rnd = random.Random(int(node.get("seed") or 42))
                    rows = rnd.sample(rows, k=min(sample_n, len(rows)))
            elif op == "export":
                pass
            else:
                raise ValueError(f"unsupported op: {op}")

        return {
            "table": grouped_rows,
            "sample": rows[: int(plan.intent.sample_n or 5)],
            "meta": {**meta, "fallback": False, "filtered_row_count": len(rows)},
        }
    except Exception as exc:
        return {
            "table": data[:10],
            "sample": data[:5],
            "meta": {**meta, "fallback": True, "error": str(exc)},
        }


def execute_plan_from_csv_text(plan: AnalysisPlan, csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    return execute_plan(plan, rows)
