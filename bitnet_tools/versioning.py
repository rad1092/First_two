from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

LINEAGE_DIR = Path('.bitnet_cache') / 'lineage'


@dataclass(frozen=True)
class DatasetVersion:
    fingerprint: str
    row_count: int
    column_count: int
    columns: list[str]


def build_dataset_fingerprint(csv_text: str, *, source_name: str = '<inline_csv>', meta: dict[str, Any] | None = None) -> DatasetVersion:
    lines = [line.rstrip() for line in csv_text.strip().splitlines() if line.strip()]
    header = lines[0].split(',') if lines else []
    row_count = max(len(lines) - 1, 0)
    payload = {
        'source_name': source_name,
        'columns': header,
        'row_count': row_count,
        'csv_text': '\n'.join(lines),
        'meta': meta or {},
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return DatasetVersion(
        fingerprint=digest,
        row_count=row_count,
        column_count=len(header),
        columns=header,
    )


def save_lineage_link(
    before: DatasetVersion,
    after: DatasetVersion,
    *,
    before_source: str,
    after_source: str,
    context: dict[str, Any] | None = None,
) -> Path:
    LINEAGE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        'created_at': now,
        'before': {
            'source_name': before_source,
            'fingerprint': before.fingerprint,
            'row_count': before.row_count,
            'column_count': before.column_count,
            'columns': before.columns,
        },
        'after': {
            'source_name': after_source,
            'fingerprint': after.fingerprint,
            'row_count': after.row_count,
            'column_count': after.column_count,
            'columns': after.columns,
        },
        'context': context or {},
    }
    out_path = LINEAGE_DIR / f"{before.fingerprint[:12]}__{after.fingerprint[:12]}.json"
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return out_path
