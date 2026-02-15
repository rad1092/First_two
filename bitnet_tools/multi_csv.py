from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .analysis import _to_float
from .explain import generate_reason_candidates

CACHE_DIR = Path('.bitnet_cache')
UNIQUE_BITMAP_SIZE = 65536
TOP_VALUE_TRACK_CAP = 5000
CACHE_ENTRY_TTL_SECONDS = 60 * 60 * 24
CACHE_MAX_TOTAL_BYTES = 256 * 1024 * 1024


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


def _reservoir_sample(values: list[float], new_value: float, seen: int, cap: int) -> None:
    if cap <= 0:
        return
    if len(values) < cap:
        values.append(new_value)
        return
    idx = random.randint(0, seen - 1)
    if idx < cap:
        values[idx] = new_value


def _reservoir_sample_str(values: list[str], new_value: str, seen: int, cap: int) -> None:
    if cap <= 0:
        return
    if len(values) < cap:
        values.append(new_value)
        return
    idx = random.randint(0, seen - 1)
    if idx < cap:
        values[idx] = new_value


def _finalize_group_ratio_table(table: dict[str, Counter[str]], group_col: str, target_col: str) -> dict[str, Any]:
    ratio_table: dict[str, Any] = {}
    for g, counter in table.items():
        total = sum(counter.values())
        ratio_table[g] = {
            k: {
                'count': v,
                'ratio': round(v / total, 6) if total else 0.0,
            }
            for k, v in counter.items()
        }
    return {'group_column': group_col, 'target_column': target_col, 'groups': ratio_table}


def _looks_like_date(value: str) -> bool:
    candidates = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"]
    for fmt in candidates:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


def _infer_semantic_type(col: str, dtype: str, samples: list[str], unique_ratio: float) -> str:
    lower = col.lower()
    if dtype == 'float' and ('lat' in lower or '위도' in col):
        return 'geo_latitude'
    if dtype == 'float' and ('lon' in lower or '경도' in col or 'lng' in lower):
        return 'geo_longitude'
    if dtype == 'string':
        non_empty = [s for s in samples if s]
        if non_empty:
            date_hits = sum(1 for s in non_empty if _looks_like_date(s))
            if date_hits / len(non_empty) >= 0.7:
                return 'date'
        if unique_ratio <= 0.2:
            return 'category'
    if dtype == 'float':
        return 'numeric'
    return 'text'


def _update_unique_bitmap(bitmap: bytearray, value: str) -> None:
    h = hashlib.sha1(value.encode('utf-8')).digest()
    idx = int.from_bytes(h[:8], 'big') % UNIQUE_BITMAP_SIZE
    bitmap[idx // 8] |= 1 << (idx % 8)


def _estimate_unique_count(bitmap: bytearray) -> int:
    set_bits = sum(bin(b).count('1') for b in bitmap)
    if set_bits <= 0:
        return 0
    if set_bits >= UNIQUE_BITMAP_SIZE:
        return UNIQUE_BITMAP_SIZE
    zero_bits = UNIQUE_BITMAP_SIZE - set_bits
    return max(1, int(round(-UNIQUE_BITMAP_SIZE * math.log(zero_bits / UNIQUE_BITMAP_SIZE))))


def _update_bounded_counter(counter: Counter[str], value: str, other_holder: dict[str, int], cap: int) -> None:
    if value in counter:
        counter[value] += 1
        return
    if len(counter) < cap:
        counter[value] += 1
        return
    other_holder['count'] += 1


def _profile_csv_stream(
    path: Path,
    group_column: str | None = None,
    target_column: str | None = None,
    outlier_sample_cap: int = 20000,
    value_sample_cap: int = 300,
) -> dict[str, Any]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f'CSV header not found: {path}')
        columns = [str(c) for c in reader.fieldnames]

        missing = {c: 0 for c in columns}
        non_missing = {c: 0 for c in columns}
        unique_bitmaps: dict[str, bytearray] = {c: bytearray(UNIQUE_BITMAP_SIZE // 8) for c in columns}
        value_counts: dict[str, Counter[str]] = {c: Counter() for c in columns}
        value_overflow: dict[str, dict[str, int]] = {c: {'count': 0} for c in columns}
        value_samples: dict[str, list[str]] = {c: [] for c in columns}

        numeric_positive = {c: 0 for c in columns}
        numeric_zero = {c: 0 for c in columns}
        numeric_negative = {c: 0 for c in columns}
        numeric_counts = {c: 0 for c in columns}
        numeric_sums = {c: 0.0 for c in columns}
        numeric_mins: dict[str, float] = {}
        numeric_maxs: dict[str, float] = {}
        text_seen = {c: False for c in columns}
        numeric_outlier_samples: dict[str, list[float]] = {c: [] for c in columns}

        group_target_counter: dict[str, Counter[str]] = defaultdict(Counter)
        row_count = 0

        for row in reader:
            row_count += 1
            if group_column and target_column and group_column in columns and target_column in columns:
                g = (row.get(group_column) or '').strip()
                t = (row.get(target_column) or '').strip()
                if g and t:
                    group_target_counter[g][t] += 1

            for col in columns:
                raw = (row.get(col) or '').strip()
                if raw == '':
                    missing[col] += 1
                    continue
                non_missing[col] += 1
                _update_unique_bitmap(unique_bitmaps[col], raw)
                _update_bounded_counter(value_counts[col], raw, value_overflow[col], TOP_VALUE_TRACK_CAP)
                _reservoir_sample_str(value_samples[col], raw, non_missing[col], value_sample_cap)

                num = _to_float(raw)
                if num is None:
                    text_seen[col] = True
                    continue

                numeric_counts[col] += 1
                numeric_sums[col] += num
                if col not in numeric_mins or num < numeric_mins[col]:
                    numeric_mins[col] = num
                if col not in numeric_maxs or num > numeric_maxs[col]:
                    numeric_maxs[col] = num

                if num > 0:
                    numeric_positive[col] += 1
                elif num < 0:
                    numeric_negative[col] += 1
                else:
                    numeric_zero[col] += 1

                _reservoir_sample(numeric_outlier_samples[col], num, numeric_counts[col], outlier_sample_cap)

    dtypes: dict[str, str] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    profiles: dict[str, Any] = {}

    for col in columns:
        count = numeric_counts[col]
        if count > 0 and not text_seen[col]:
            dtypes[col] = 'float'
            numeric_stats[col] = {
                'count': float(count),
                'mean': float(numeric_sums[col] / count),
                'min': float(numeric_mins[col]),
                'max': float(numeric_maxs[col]),
            }
        else:
            dtypes[col] = 'string'

        nn = non_missing[col]
        top = value_counts[col].most_common(5)
        if value_overflow[col]['count'] > 0:
            top.append(('__OTHER__', value_overflow[col]['count']))
            top = sorted(top, key=lambda x: x[1], reverse=True)[:5]
        top_values = [
            {'value': v, 'count': cnt, 'ratio': round(cnt / row_count, 6) if row_count else 0.0}
            for v, cnt in top
        ]

        numeric_total = numeric_positive[col] + numeric_zero[col] + numeric_negative[col]
        numeric_distribution: dict[str, float] = {}
        if numeric_total:
            numeric_distribution = {
                'positive_ratio': round(numeric_positive[col] / numeric_total, 6),
                'zero_ratio': round(numeric_zero[col] / numeric_total, 6),
                'negative_ratio': round(numeric_negative[col] / numeric_total, 6),
                'outlier_ratio': _outlier_ratio(numeric_outlier_samples[col]),
            }

        unique_count = _estimate_unique_count(unique_bitmaps[col])
        unique_ratio = round(min(unique_count, nn) / nn, 6) if nn else 0.0
        dominant_value_ratio = top_values[0]['ratio'] if top_values else 0.0
        profiles[col] = {
            'missing_count': missing[col],
            'missing_ratio': round(missing[col] / row_count, 6) if row_count else 0.0,
            'non_missing_count': nn,
            'unique_count': unique_count,
            'unique_ratio': unique_ratio,
            'dominant_value_ratio': dominant_value_ratio,
            'top_values': top_values,
            'numeric_distribution': numeric_distribution,
            'dtype': dtypes[col],
            'semantic_type': _infer_semantic_type(col, dtypes[col], value_samples[col], unique_ratio),
            'top_values_capped': value_overflow[col]['count'] > 0,
        }

    summary = {
        'row_count': row_count,
        'column_count': len(columns),
        'columns': columns,
        'dtypes': dtypes,
        'missing_counts': missing,
        'numeric_stats': numeric_stats,
    }

    group_target_ratio: dict[str, Any] | None = None
    if group_column and target_column and group_column in columns and target_column in columns:
        group_target_ratio = _finalize_group_ratio_table(group_target_counter, group_column, target_column)

    return {'summary': summary, 'column_profiles': profiles, 'group_target_ratio': group_target_ratio}


def _schema_drift(files: list[dict[str, Any]], shared_columns: list[str]) -> dict[str, Any]:
    drift: dict[str, Any] = {}
    for col in shared_columns:
        dtypes = [f['column_profiles'][col]['dtype'] for f in files if col in f['column_profiles']]
        missing_ratios = [f['column_profiles'][col]['missing_ratio'] for f in files if col in f['column_profiles']]
        dominant_ratios = [f['column_profiles'][col]['dominant_value_ratio'] for f in files if col in f['column_profiles']]

        means = []
        for f in files:
            stats = f['summary']['numeric_stats'].get(col)
            if stats:
                means.append(stats['mean'])

        drift[col] = {
            'dtype_changed': len(set(dtypes)) > 1,
            'missing_ratio_range': round(max(missing_ratios) - min(missing_ratios), 6) if missing_ratios else 0.0,
            'dominant_value_ratio_range': round(max(dominant_ratios) - min(dominant_ratios), 6) if dominant_ratios else 0.0,
            'mean_range': round(max(means) - min(means), 6) if means else 0.0,
        }
    return drift


def _cache_key(path: Path, group_column: str | None, target_column: str | None) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{st.st_mtime_ns}|{group_column}|{target_column}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _cache_path(path: Path, group_column: str | None, target_column: str | None) -> Path:
    return CACHE_DIR / f"{_cache_key(path, group_column, target_column)}.json"


def _cache_index_path() -> Path:
    return CACHE_DIR / 'multi_csv_cache_index.json'


def _load_cache_index() -> dict[str, Any]:
    index_path = _cache_index_path()
    if not index_path.exists():
        return {'entries': {}}
    try:
        with index_path.open('r', encoding='utf-8') as f:
            loaded = json.load(f)
        entries = loaded.get('entries')
        if isinstance(entries, dict):
            return {'entries': entries}
    except Exception:
        pass
    return {'entries': {}}


def _save_cache_index(index: dict[str, Any]) -> None:
    index_path = _cache_index_path()
    tmp_path = index_path.with_name(f"{index_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    tmp_path.replace(index_path)


def _record_cache_access(cache_path: Path, size_bytes: int, kind: str = 'profile') -> None:
    now = datetime.utcnow().timestamp()
    index = _load_cache_index()
    entries = index.setdefault('entries', {})
    entries[str(cache_path)] = {
        'last_access': now,
        'size_bytes': int(size_bytes),
        'kind': kind,
    }
    _save_cache_index(index)


def _remove_cache_entry(cache_path: Path, index: dict[str, Any] | None = None) -> None:
    should_save = index is None
    if cache_path.exists():
        cache_path.unlink(missing_ok=True)
    if index is None:
        index = _load_cache_index()
    entries = index.setdefault('entries', {})
    entries.pop(str(cache_path), None)
    if should_save:
        _save_cache_index(index)


def _cleanup_rebuildable_intermediates(index: dict[str, Any]) -> None:
    candidates = [
        *CACHE_DIR.glob('*.tmp'),
        *CACHE_DIR.glob('*.partial'),
        *CACHE_DIR.glob('*.bak'),
    ]
    for p in candidates:
        _remove_cache_entry(p, index=index)


def _enforce_cache_limits() -> None:
    index = _load_cache_index()
    entries = index.setdefault('entries', {})
    _cleanup_rebuildable_intermediates(index)

    now = datetime.utcnow().timestamp()
    total_size = 0
    stale_paths: list[Path] = []
    existing_entries: list[tuple[Path, dict[str, Any]]] = []

    for raw_path, meta in list(entries.items()):
        p = Path(raw_path)
        if not p.exists():
            entries.pop(raw_path, None)
            continue
        last_access = float(meta.get('last_access', 0.0))
        if CACHE_ENTRY_TTL_SECONDS > 0 and now - last_access > CACHE_ENTRY_TTL_SECONDS:
            stale_paths.append(p)
            continue
        size_bytes = p.stat().st_size
        meta['size_bytes'] = size_bytes
        total_size += size_bytes
        existing_entries.append((p, meta))

    for p in stale_paths:
        _remove_cache_entry(p, index=index)

    if CACHE_MAX_TOTAL_BYTES > 0 and total_size > CACHE_MAX_TOTAL_BYTES:
        # LRU eviction: 오래 사용하지 않은 항목부터 제거
        existing_entries.sort(key=lambda item: float(item[1].get('last_access', 0.0)))
        for p, meta in existing_entries:
            if total_size <= CACHE_MAX_TOTAL_BYTES:
                break
            total_size -= int(meta.get('size_bytes', p.stat().st_size if p.exists() else 0))
            _remove_cache_entry(p, index=index)

    _save_cache_index(index)


def _write_json_maybe_stream(path: Path, data: dict[str, Any]) -> None:
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(',', ':'))
    tmp_path = path.with_suffix('.tmp')
    with tmp_path.open('w', encoding='utf-8') as f:
        for piece in encoder.iterencode(data):
            f.write(piece)
    tmp_path.replace(path)


def _load_cached_profile(path: Path, group_column: str | None, target_column: str | None) -> dict[str, Any] | None:
    CACHE_DIR.mkdir(exist_ok=True)
    cp = _cache_path(path, group_column, target_column)
    if not cp.exists():
        return None
    try:
        stat = cp.stat()
        if CACHE_ENTRY_TTL_SECONDS > 0:
            age_seconds = datetime.utcnow().timestamp() - stat.st_mtime
            if age_seconds > CACHE_ENTRY_TTL_SECONDS:
                _remove_cache_entry(cp)
                return None
        with cp.open('r', encoding='utf-8') as f:
            loaded = json.load(f)
        _record_cache_access(cp, stat.st_size)
        return loaded
    except Exception:
        return None


def _save_cached_profile(path: Path, group_column: str | None, target_column: str | None, data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    cp = _cache_path(path, group_column, target_column)
    # 대용량 캐시 직렬화 시 메모리 급증을 피하기 위해 스트리밍 쓰기 기본 사용
    if os.getenv('BITNET_CACHE_STREAM_WRITE', '1') != '0':
        _write_json_maybe_stream(cp, data)
    else:
        cp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    _record_cache_access(cp, cp.stat().st_size)
    _enforce_cache_limits()


def _generate_insights(files: list[dict[str, Any]], schema_drift: dict[str, Any]) -> list[str]:
    insights: list[str] = []
    for f in files:
        for col, prof in f['column_profiles'].items():
            if prof['missing_ratio'] >= 0.2:
                insights.append(f"{f['path']}:{col} 결측비율이 높음({prof['missing_ratio']:.2%})")
            out_ratio = prof['numeric_distribution'].get('outlier_ratio', 0.0)
            if out_ratio >= 0.1:
                insights.append(f"{f['path']}:{col} 이상치 비율이 높음({out_ratio:.2%})")
    for col, drift in schema_drift.items():
        if drift['dtype_changed']:
            insights.append(f"공통 컬럼 {col}의 타입이 파일 간 다르게 탐지됨")
        if drift['mean_range'] > 0:
            insights.append(f"공통 컬럼 {col}의 평균 범위 변화: {drift['mean_range']:.4f}")
    for f in files:
        for reason in f.get('reason_candidates', [])[:3]:
            insights.append(f"{f['path']} 이유후보[{reason['rule']}] {reason['reason']}")
    return insights[:30]


def _load_or_profile_file(
    path: Path,
    group_column: str | None,
    target_column: str | None,
    use_cache: bool,
) -> dict[str, Any]:
    profiled = _load_cached_profile(path, group_column, target_column) if use_cache else None
    if profiled is None:
        profiled = _profile_csv_stream(path, group_column=group_column, target_column=target_column)
        if use_cache:
            _save_cached_profile(path, group_column, target_column, profiled)
    return profiled


def analyze_multiple_csv(
    csv_paths: list[Path],
    question: str,
    group_column: str | None = None,
    target_column: str | None = None,
    use_cache: bool = True,
    max_workers: int | None = None,
) -> dict[str, Any]:
    if not csv_paths:
        raise ValueError('at least one CSV path is required')

    for path in csv_paths:
        if not path.exists():
            raise FileNotFoundError(f'CSV file not found: {path}')

    worker_count = max_workers if (max_workers is not None and max_workers > 0) else min(4, len(csv_paths))

    if worker_count == 1 or len(csv_paths) == 1:
        profiled_list = [
            _load_or_profile_file(path, group_column, target_column, use_cache)
            for path in csv_paths
        ]
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            profiled_list = list(
                executor.map(
                    lambda p: _load_or_profile_file(p, group_column, target_column, use_cache),
                    csv_paths,
                )
            )

    files: list[dict[str, Any]] = []
    all_columns: list[set[str]] = []
    total_rows = 0

    for path, profiled in zip(csv_paths, profiled_list):
        total_rows += profiled['summary']['row_count']
        all_columns.append(set(profiled['summary']['columns']))
        files.append(
            {
                'path': str(path),
                'question': question,
                'summary': profiled['summary'],
                'column_profiles': profiled['column_profiles'],
                'group_target_ratio': profiled['group_target_ratio'],
                'reason_candidates': generate_reason_candidates(
                    str(path),
                    path,
                    profiled['column_profiles'],
                ),
            }
        )

    shared_columns = sorted(set.intersection(*all_columns)) if all_columns else []
    union_columns = sorted(set.union(*all_columns)) if all_columns else []
    schema_drift = _schema_drift(files, shared_columns)
    all_reason_candidates: list[dict[str, Any]] = []
    for f in files:
        for reason in f.get('reason_candidates', []):
            all_reason_candidates.append({'file': f['path'], **reason})
    all_reason_candidates.sort(key=lambda x: x.get('score', 0.0), reverse=True)

    return {
        'question': question,
        'file_count': len(files),
        'total_row_count': total_rows,
        'shared_columns': shared_columns,
        'union_columns': union_columns,
        'files': files,
        'schema_drift': schema_drift,
        'insights': _generate_insights(files, schema_drift),
        'reason_candidates': all_reason_candidates[:3],
        'code_guidance': build_code_guidance(shared_columns, group_column, target_column),
    }


def build_code_guidance(shared_columns: list[str], group_column: str | None = None, target_column: str | None = None) -> dict[str, str]:
    join_key = shared_columns[0] if shared_columns else '공통키컬럼'
    group_block = ''
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
        'recommended_steps': (
            '1) 공통 키 컬럼 확인 후 병합\n'
            '2) 컬럼별 결측/고유값/상위값 비율 확인\n'
            '3) 수치형 컬럼 비율(양수/0/음수), 이상치 비율, 분포 확인\n'
            '4) 그룹 컬럼 기준 타깃 비율 분석(예: 시도명-세차유형)\n'
            '5) 파일 간 스키마 변화/평균 변화 범위 확인'
        ),
        'pandas_example': pandas_code,
    }


def build_multi_csv_markdown(result: dict[str, Any]) -> str:
    lines = [
        '# 다중 CSV 분석 리포트',
        '',
        f"- 질문: {result['question']}",
        f"- 파일 수: {result['file_count']}",
        f"- 전체 행 수: {result['total_row_count']}",
        f"- 공통 컬럼: {', '.join(result['shared_columns']) if result['shared_columns'] else '(없음)'}",
        '',
    ]

    if result.get('insights'):
        lines.extend(['## 핵심 인사이트', ''])
        for it in result['insights'][:10]:
            lines.append(f"- {it}")
        lines.append('')

    for file_info in result['files']:
        lines.extend(
            [
                f"## 파일: {file_info['path']}",
                '',
                f"- 행 수: {file_info['summary']['row_count']}",
                f"- 열 수: {file_info['summary']['column_count']}",
                '',
                '| 컬럼 | 타입 | 의미타입 | 결측비율 | 고유비율 | 대표값비율 |',
                '|---|---|---|---:|---:|---:|',
            ]
        )
        for col in file_info['summary']['columns']:
            prof = file_info['column_profiles'][col]
            lines.append(
                f"| {col} | {prof['dtype']} | {prof.get('semantic_type','')} | {prof['missing_ratio']:.4f} | {prof['unique_ratio']:.4f} | {prof['dominant_value_ratio']:.4f} |"
            )
        if file_info.get('group_target_ratio'):
            gtr = file_info['group_target_ratio']
            lines.extend(['', f"- 그룹비율: {gtr['group_column']} x {gtr['target_column']}"])
        lines.append('')

    lines.extend(['## 파일 간 스키마/분포 변화', '', '| 컬럼 | 타입변화 | 결측비율범위 | 대표값비율범위 | 평균범위 |', '|---|---|---:|---:|---:|'])
    for col, drift in result['schema_drift'].items():
        lines.append(
            f"| {col} | {drift['dtype_changed']} | {drift['missing_ratio_range']:.4f} | {drift['dominant_value_ratio_range']:.4f} | {drift['mean_range']:.4f} |"
        )

    charts = result.get('charts')
    if charts:
        lines.extend(['', '## 생성된 차트 파일', ''])
        for file_path, chart_paths in charts.items():
            lines.append(f"- {file_path}")
            for c in chart_paths:
                lines.append(f"  - {c}")

    lines.extend([
        '',
        '## 코드 가이드',
        '',
        '```text',
        result['code_guidance']['recommended_steps'],
        '```',
        '',
        '```python',
        result['code_guidance']['pandas_example'],
        '```',
    ])

    return '\n'.join(lines)


def result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
