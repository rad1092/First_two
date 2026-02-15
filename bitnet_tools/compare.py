from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .versioning import build_dataset_fingerprint, save_lineage_link

EPS = 1e-9


def _read_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [{k: (v if v is not None else '') for k, v in row.items()} for row in reader]
    return list(reader.fieldnames or []), rows


def _safe_float(value: str) -> float | None:
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _is_numeric_column(before_rows: list[dict[str, str]], after_rows: list[dict[str, str]], col: str) -> bool:
    seen = False
    for row in before_rows + after_rows:
        raw = str(row.get(col, '')).strip()
        if not raw:
            continue
        seen = True
        if _safe_float(raw) is None:
            return False
    return seen


def _normalize_probs(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        return [1.0 / len(values)] * len(values)
    return [max(v / total, EPS) for v in values]


def _psi(before_prob: list[float], after_prob: list[float]) -> float:
    return sum((a - b) * math.log(a / b) for b, a in zip(before_prob, after_prob))


def _js_divergence(before_prob: list[float], after_prob: list[float]) -> float:
    m = [(b + a) / 2 for b, a in zip(before_prob, after_prob)]

    def _kl(p: list[float], q: list[float]) -> float:
        return sum(pi * math.log(pi / qi) for pi, qi in zip(p, q))

    return 0.5 * _kl(before_prob, m) + 0.5 * _kl(after_prob, m)


def _chi_square(before_counts: list[int], after_counts: list[int]) -> float:
    before_total = sum(before_counts)
    after_total = sum(after_counts)
    if before_total == 0 or after_total == 0:
        return 0.0
    score = 0.0
    for expected_raw, observed in zip(before_counts, after_counts):
        expected = max((expected_raw / before_total) * after_total, EPS)
        score += ((observed - expected) ** 2) / expected
    return score


def _categorical_distribution(rows: list[dict[str, str]], col: str, categories: list[str]) -> list[int]:
    counter = Counter(str(row.get(col, '')).strip() for row in rows)
    return [counter.get(cat, 0) for cat in categories]


def _numeric_distribution(rows: list[dict[str, str]], col: str, bins: list[float]) -> list[int]:
    counts = [0] * (len(bins) - 1)
    for row in rows:
        val = _safe_float(row.get(col, ''))
        if val is None:
            continue
        for i in range(len(bins) - 1):
            lower, upper = bins[i], bins[i + 1]
            if (i < len(bins) - 2 and lower <= val < upper) or (i == len(bins) - 2 and lower <= val <= upper):
                counts[i] += 1
                break
    return counts


def _make_bins(values: list[float], num_bins: int = 10) -> list[float]:
    v_min = min(values)
    v_max = max(values)
    if math.isclose(v_min, v_max):
        return [v_min - 0.5, v_max + 0.5]
    step = (v_max - v_min) / num_bins
    return [v_min + (step * i) for i in range(num_bins)] + [v_max]


def compare_csv_texts(before_csv_text: str, after_csv_text: str, *, before_source: str = 'before.csv', after_source: str = 'after.csv') -> dict[str, Any]:
    before_cols, before_rows = _read_csv_text(before_csv_text)
    after_cols, after_rows = _read_csv_text(after_csv_text)
    common_cols = sorted(set(before_cols) & set(after_cols))

    metrics: dict[str, Any] = {}
    for col in common_cols:
        if _is_numeric_column(before_rows, after_rows, col):
            before_values = [_safe_float(r.get(col, '')) for r in before_rows]
            after_values = [_safe_float(r.get(col, '')) for r in after_rows]
            all_values = [v for v in before_values + after_values if v is not None]
            if not all_values:
                continue
            bins = _make_bins(all_values)
            before_counts = _numeric_distribution(before_rows, col, bins)
            after_counts = _numeric_distribution(after_rows, col, bins)
            bucket_labels = [f'[{bins[i]:.4g}, {bins[i + 1]:.4g})' for i in range(len(bins) - 1)]
            bucket_labels[-1] = bucket_labels[-1].replace(')', ']')
            dist_type = 'numeric'
        else:
            categories = sorted({str(r.get(col, '')).strip() for r in before_rows + after_rows})
            if not categories:
                continue
            before_counts = _categorical_distribution(before_rows, col, categories)
            after_counts = _categorical_distribution(after_rows, col, categories)
            bucket_labels = categories
            dist_type = 'categorical'

        before_prob = _normalize_probs(before_counts)
        after_prob = _normalize_probs(after_counts)
        metrics[col] = {
            'type': dist_type,
            'buckets': bucket_labels,
            'before_counts': before_counts,
            'after_counts': after_counts,
            'psi': _psi(before_prob, after_prob),
            'js_divergence': _js_divergence(before_prob, after_prob),
            'chi_square': _chi_square(before_counts, after_counts),
        }

    before_version = build_dataset_fingerprint(before_csv_text, source_name=before_source)
    after_version = build_dataset_fingerprint(after_csv_text, source_name=after_source)
    lineage_path = save_lineage_link(
        before_version,
        after_version,
        before_source=before_source,
        after_source=after_source,
        context={'common_columns': common_cols},
    )

    return {
        'before': {
            'source_name': before_source,
            'fingerprint': before_version.fingerprint,
            'row_count': before_version.row_count,
            'column_count': before_version.column_count,
        },
        'after': {
            'source_name': after_source,
            'fingerprint': after_version.fingerprint,
            'row_count': after_version.row_count,
            'column_count': after_version.column_count,
        },
        'common_columns': common_cols,
        'column_metrics': metrics,
        'lineage_path': str(lineage_path),
    }


def compare_csv_files(before_path: Path, after_path: Path) -> dict[str, Any]:
    return compare_csv_texts(
        before_path.read_text(encoding='utf-8'),
        after_path.read_text(encoding='utf-8'),
        before_source=before_path.name,
        after_source=after_path.name,
    )


def result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
