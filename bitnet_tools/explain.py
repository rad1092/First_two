from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"]


def _parse_date(value: str) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _extract_unit(value: str) -> str | None:
    text = str(value or '').strip()
    if not text or not any(ch.isdigit() for ch in text):
        return None
    m = re.search(r'([A-Za-z가-힣/%]+)$', text)
    if not m:
        return None
    unit = m.group(1)
    if len(unit) > 8:
        return None
    return unit.lower()


def _rule_missing_concentration(path: str, profiles: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    targets = [(col, p.get('missing_ratio', 0.0)) for col, p in profiles.items() if p.get('missing_ratio', 0.0) >= 0.2]
    if not targets:
        return None
    col, ratio = max(targets, key=lambda x: x[1])
    score = round(min(100.0, ratio * 100.0), 2)
    return {
        'rule': '결측 집중',
        'score': score,
        'reason': f"{Path(path).name}:{col} 결측이 집중됨 (결측비율 {ratio:.1%})",
        'evidence': {'column': col, 'missing_ratio': ratio},
    }


def _rule_category_bias(path: str, profiles: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    best: tuple[str, dict[str, Any]] | None = None
    for col, p in profiles.items():
        if p.get('dtype') != 'string' and p.get('semantic_type') != 'category':
            continue
        dom = float(p.get('dominant_value_ratio', 0.0))
        if dom < 0.65:
            continue
        if best is None or dom > float(best[1].get('dominant_value_ratio', 0.0)):
            best = (col, p)
    if best is None:
        return None
    col, p = best
    top_values = p.get('top_values') or []
    top_val = top_values[0]['value'] if top_values else '(unknown)'
    dom = float(p.get('dominant_value_ratio', 0.0))
    score = round(min(100.0, dom * 100.0), 2)
    return {
        'rule': '특정 카테고리 편중',
        'score': score,
        'reason': f"{Path(path).name}:{col} 값 '{top_val}' 편중 ({dom:.1%})",
        'evidence': {'column': col, 'dominant_value_ratio': dom, 'top_value': top_val},
    }


def _rule_unit_mismatch(path: str, profiles: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    best_candidate: dict[str, Any] | None = None

    for col, p in profiles.items():
        top_values = p.get('top_values') or []
        units: dict[str, float] = {}
        for item in top_values:
            unit = _extract_unit(item.get('value', ''))
            if not unit:
                continue
            units[unit] = units.get(unit, 0.0) + float(item.get('ratio', 0.0))

        if len(units) < 2:
            continue
        coverage = sum(units.values())
        if coverage < 0.2:
            continue
        score = round(min(100.0, (len(units) - 1) * 18 + coverage * 50), 2)
        candidate = {
            'rule': '단위 불일치',
            'score': score,
            'reason': f"{Path(path).name}:{col} 다중 단위 혼재 ({', '.join(sorted(units.keys()))})",
            'evidence': {'column': col, 'units': sorted(units.keys()), 'coverage': round(coverage, 4)},
        }
        if best_candidate is None or candidate['score'] > best_candidate['score']:
            best_candidate = candidate

    return best_candidate


def _rule_recent_change(path: str, csv_path: Path, profiles: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    date_cols = [col for col, p in profiles.items() if p.get('semantic_type') == 'date']
    num_cols = [col for col, p in profiles.items() if p.get('dtype') == 'float']
    if not date_cols or not num_cols:
        return None

    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))

    best: dict[str, Any] | None = None
    for date_col in date_cols:
        series: list[tuple[datetime, dict[str, float]]] = []
        for row in rows:
            dt = _parse_date(row.get(date_col, ''))
            if dt is None:
                continue
            values: dict[str, float] = {}
            for ncol in num_cols:
                raw = str(row.get(ncol, '')).strip().replace(',', '')
                if not raw:
                    continue
                try:
                    values[ncol] = float(raw)
                except ValueError:
                    continue
            if values:
                series.append((dt, values))

        if len(series) < 6:
            continue

        series.sort(key=lambda x: x[0])
        window = max(3, len(series) // 5)
        prev = series[-2 * window:-window]
        recent = series[-window:]
        if not prev or not recent:
            continue

        for ncol in num_cols:
            prev_vals = [v[ncol] for _, v in prev if ncol in v]
            recent_vals = [v[ncol] for _, v in recent if ncol in v]
            if len(prev_vals) < 2 or len(recent_vals) < 2:
                continue
            prev_mean = sum(prev_vals) / len(prev_vals)
            recent_mean = sum(recent_vals) / len(recent_vals)
            baseline = max(abs(prev_mean), 1e-9)
            change_ratio = abs(recent_mean - prev_mean) / baseline
            if change_ratio < 0.5:
                continue
            score = round(min(100.0, change_ratio * 100.0), 2)
            candidate = {
                'rule': '최근 급변',
                'score': score,
                'reason': f"{Path(path).name}:{ncol} 최근 평균 급변 ({change_ratio:.1%})",
                'evidence': {
                    'date_column': date_col,
                    'column': ncol,
                    'prev_mean': round(prev_mean, 4),
                    'recent_mean': round(recent_mean, 4),
                    'change_ratio': round(change_ratio, 4),
                },
            }
            if best is None or candidate['score'] > best['score']:
                best = candidate
    return best


def generate_reason_candidates(path: str, csv_path: Path, profiles: dict[str, dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    candidates = [
        _rule_missing_concentration(path, profiles),
        _rule_category_bias(path, profiles),
        _rule_unit_mismatch(path, profiles),
        _rule_recent_change(path, csv_path, profiles),
    ]
    filtered = [c for c in candidates if c is not None]
    filtered.sort(key=lambda x: (x.get('score', 0.0), x.get('rule', '')), reverse=True)
    return filtered[:top_k]
