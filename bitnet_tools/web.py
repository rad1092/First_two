from __future__ import annotations

from http import HTTPStatus
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
from typing import Any

import re
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlparse

from .analysis import build_analysis_payload_from_request
from .document_extract import extract_document_tables_from_base64, table_to_analysis_request
from .geo import flag_geo_suspects, validate_lat_lon
from .multi_csv import analyze_multiple_csv
from .planner import build_plan, execute_plan_from_csv_text, parse_question_to_intent
from .visualize import create_multi_charts


UI_DIR = Path(__file__).parent / "ui"


CHART_JOB_DIR = Path('.bitnet_cache') / 'chart_jobs'
_CHART_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_CHART_JOBS: dict[str, Future] = {}
_CHART_LOCK = threading.Lock()

PREPROCESS_JOB_DIR = Path('.bitnet_cache') / 'preprocess_jobs'
PREPROCESS_JOB_TTL_SECONDS = 60 * 60
_PREPROCESS_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_PREPROCESS_JOBS: dict[str, dict[str, Any]] = {}
_PREPROCESS_LOCK = threading.Lock()




def _coerce_csv_text_from_file_payload(file_payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    input_type = str(file_payload.get('input_type', 'csv') or 'csv').strip().lower()
    source_name = str(file_payload.get('name', '<inline_csv>'))
    meta: dict[str, Any] = {'source_name': source_name, 'input_type': input_type}

    if input_type == 'document':
        raw_b64 = str(file_payload.get('file_base64', '')).strip()
        if not raw_b64:
            raise ValueError('document file_base64 is required')
        extract_result = extract_document_tables_from_base64(raw_b64, source_name)
        table_index = int(file_payload.get('table_index', 0) or 0)
        request_payload = table_to_analysis_request(extract_result, table_index)
        normalized_text = str(request_payload.get('normalized_csv_text', ''))
        meta.update(request_payload.get('meta', {}))
        return source_name, normalized_text, meta

    if input_type == 'excel':
        raw_b64 = str(file_payload.get('file_base64', '')).strip()
        if not raw_b64:
            raise ValueError('excel file_base64 is required')
        sheet_name = str(file_payload.get('sheet_name', '')).strip() or None
        normalized_text = _normalize_excel_base64_to_csv_text(raw_b64, sheet_name)
        meta['sheet_name'] = sheet_name or '<first_sheet>'
        return source_name, normalized_text, meta

    normalized = str(file_payload.get('normalized_csv_text', '')).strip()
    if not normalized:
        normalized = str(file_payload.get('csv_text', '')).strip()
    if not normalized:
        raise ValueError('normalized_csv_text is required')
    return source_name, normalized, meta


def _xlsx_col_to_index(cell_ref: str) -> int:
    letters = ''.join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return max(idx - 1, 0)


def _load_xlsx_from_base64(file_base64: str) -> tuple[zipfile.ZipFile, str]:
    try:
        raw = base64.b64decode(file_base64)
    except Exception as exc:
        raise ValueError(f'invalid excel base64: {exc}') from exc

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError(f'failed to read excel file: {exc}') from exc

    if 'xl/workbook.xml' not in zf.namelist():
        raise ValueError('지원하지 않는 Excel 형식입니다. .xlsx 파일을 사용하세요. | detail: only xlsx(OOXML) is supported')
    return zf, 'xl/workbook.xml'


def _get_xlsx_sheet_entries(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    wb_root = ET.fromstring(zf.read('xl/workbook.xml'))
    rel_root = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rel_map: dict[str, str] = {}
    for rel in rel_root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
        rel_map[rel.attrib.get('Id', '')] = rel.attrib.get('Target', '')

    sheets: list[tuple[str, str]] = []
    for sheet in wb_root.findall('x:sheets/x:sheet', ns):
        name = sheet.attrib.get('name', '')
        rid = sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', '')
        target = rel_map.get(rid, '')
        if target and not target.startswith('xl/'):
            target = f"xl/{target.lstrip('/')}"
        if name and target:
            sheets.append((name, target))
    return sheets


def _get_xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    values: list[str] = []
    for si in root.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
        text = ''.join(t.text or '' for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'))
        values.append(text)
    return values


def _read_xlsx_sheet_rows(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall('x:sheetData/x:row', ns):
        cells: list[str] = []
        for cell in row.findall('x:c', ns):
            ref = cell.attrib.get('r', '')
            cell_idx = _xlsx_col_to_index(ref)
            while len(cells) <= cell_idx:
                cells.append('')
            cell_type = cell.attrib.get('t', '')
            value = ''
            if cell_type == 'inlineStr':
                value = ''.join(t.text or '' for t in cell.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'))
            else:
                v = cell.find('x:v', ns)
                raw_v = v.text if v is not None and v.text is not None else ''
                if cell_type == 's' and raw_v.isdigit():
                    idx = int(raw_v)
                    value = shared_strings[idx] if 0 <= idx < len(shared_strings) else ''
                else:
                    value = raw_v
            cells[cell_idx] = value
        rows.append(cells)
    return rows


def _normalize_excel_base64_to_csv_text(file_base64: str, sheet_name: str | None = None) -> str:
    zf, _ = _load_xlsx_from_base64(file_base64)
    sheets = _get_xlsx_sheet_entries(zf)
    if not sheets:
        raise ValueError('시트가 비어 있습니다. 데이터를 포함한 시트를 선택하세요. | detail: workbook has no sheets')

    target_sheet = sheets[0]
    if sheet_name:
        matches = [s for s in sheets if s[0] == sheet_name]
        if not matches:
            raise ValueError(f'sheet not found: {sheet_name}')
        target_sheet = matches[0]

    shared_strings = _get_xlsx_shared_strings(zf)
    rows = _read_xlsx_sheet_rows(zf, target_sheet[1], shared_strings)
    non_empty_rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not non_empty_rows:
        raise ValueError('시트가 비어 있습니다. 데이터를 포함한 시트를 선택하세요. | detail: selected sheet has no non-empty rows')

    header = non_empty_rows[0]
    if not any(str(c).strip() for c in header):
        raise ValueError('헤더를 확인해주세요. 첫 행에 컬럼명이 필요합니다. | detail: header row is empty')

    seen: set[str] = set()
    for idx, name in enumerate(header):
        n = str(name).strip()
        if not n:
            raise ValueError(f'헤더를 확인해주세요. 빈 컬럼명이 있습니다. | detail: empty header at index {idx}')
        if n in seen:
            raise ValueError(f'헤더를 확인해주세요. 중복 컬럼명이 있습니다. | detail: duplicated header "{n}"')
        seen.add(n)

    output = io.StringIO()
    writer = csv.writer(output)
    max_len = max(len(r) for r in non_empty_rows)
    for row in non_empty_rows:
        padded = row + [''] * (max_len - len(row))
        writer.writerow(padded)
    return output.getvalue()


def _extract_sheet_names(file_base64: str) -> list[str]:
    zf, _ = _load_xlsx_from_base64(file_base64)
    return [name for name, _ in _get_xlsx_sheet_entries(zf)]


def _classify_preprocess_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(token in msg for token in ['memory', '메모리', 'out of memory', 'oom']):
        return 'memory_limit'
    if any(token in msg for token in ['base64', 'zip', 'corrupt', '손상', 'broken', 'unsupported excel format']):
        return 'file_corruption'
    return 'parser_error'


def _rows_from_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, Any]]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = [str(name) for name in (reader.fieldnames or []) if name is not None]
    if not fieldnames:
        raise ValueError('csv header is required')
    rows = [dict(row) for row in reader]
    return fieldnames, rows


def _build_geojson_feature_collection(rows: list[dict[str, Any]], lat_col: str, lon_col: str) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for row in rows:
        if not validate_lat_lon(row.get(lat_col), row.get(lon_col)):
            continue
        lon = float(row[lon_col])
        lat = float(row[lat_col])
        feature_props = {k: v for k, v in row.items() if k not in {lat_col, lon_col}}
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
            'properties': feature_props,
        })
    return {'type': 'FeatureCollection', 'features': features}


def _write_geo_suspect_artifacts(
    result_rows: list[dict[str, Any]],
    fieldnames: list[str],
    lat_col: str,
    lon_col: str,
    include_geojson: bool,
) -> dict[str, str]:
    out_dir = Path('.bitnet_cache') / 'geo_suspects' / uuid.uuid4().hex
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / 'geo_suspects.csv'
    json_path = out_dir / 'geo_suspects.json'
    geojson_path = out_dir / 'geo_suspects.geojson'

    ordered_fields = list(fieldnames)
    for col in ['is_suspect', 'suspect_reason', 'distance_km']:
        if col not in ordered_fields:
            ordered_fields.append(col)

    with csv_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        writer.writerows(result_rows)

    json_path.write_text(json.dumps(result_rows, ensure_ascii=False, indent=2), encoding='utf-8')

    artifacts = {'csv': str(csv_path), 'json': str(json_path)}
    if include_geojson:
        geojson = _build_geojson_feature_collection(result_rows, lat_col, lon_col)
        geojson_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding='utf-8')
        artifacts['geojson'] = str(geojson_path)
    return artifacts


def _cleanup_expired_preprocess_jobs() -> None:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(seconds=PREPROCESS_JOB_TTL_SECONDS)

    with _PREPROCESS_LOCK:
        expired = [
            job_id
            for job_id, rec in _PREPROCESS_JOBS.items()
            if datetime.fromisoformat(rec.get('expire_at', now.isoformat())) <= now
        ]
        for job_id in expired:
            _PREPROCESS_JOBS.pop(job_id, None)

    if PREPROCESS_JOB_DIR.exists():
        for path in PREPROCESS_JOB_DIR.iterdir():
            if not path.is_dir():
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime <= threshold:
                for child in path.glob('**/*'):
                    if child.is_file():
                        child.unlink(missing_ok=True)
                for child_dir in sorted(path.glob('**/*'), reverse=True):
                    if child_dir.is_dir():
                        child_dir.rmdir()
                path.rmdir()


def _run_preprocess_job(job_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    PREPROCESS_JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_dir = PREPROCESS_JOB_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_type = str(request_payload.get('input_type', 'csv') or 'csv').strip().lower()
    question = str(request_payload.get('question', '') or '').strip()
    source_name, normalized_csv_text, meta = _coerce_csv_text_from_file_payload(request_payload)

    artifact_csv = job_dir / 'normalized.csv'
    artifact_meta = job_dir / 'meta.json'
    artifact_csv.write_text(normalized_csv_text, encoding='utf-8')
    artifact_meta.write_text(
        json.dumps({'source_name': source_name, 'input_type': input_type, 'meta': meta}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    return {
        'job_id': job_id,
        'status': 'done',
        'question': question,
        'source_name': source_name,
        'input_type': input_type,
        'normalized_csv_text': normalized_csv_text,
        'meta': meta,
        'artifacts': {
            'job_dir': str(job_dir),
            'normalized_csv': str(artifact_csv),
            'meta_json': str(artifact_meta),
        },
    }


def _preprocess_job_worker(job_id: str, request_payload: dict[str, Any]) -> None:
    with _PREPROCESS_LOCK:
        rec = _PREPROCESS_JOBS.get(job_id)
        if rec is not None:
            rec['status'] = 'running'
            rec['started_at'] = datetime.now(timezone.utc).isoformat()
    try:
        result = _run_preprocess_job(job_id, request_payload)
        with _PREPROCESS_LOCK:
            rec = _PREPROCESS_JOBS.get(job_id)
            if rec is not None:
                rec['status'] = 'done'
                rec['result'] = result
                rec['finished_at'] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        with _PREPROCESS_LOCK:
            rec = _PREPROCESS_JOBS.get(job_id)
            if rec is not None:
                rec['status'] = 'failed'
                rec['error'] = str(exc)
                rec['failure_reason'] = _classify_preprocess_error(exc)
                rec['finished_at'] = datetime.now(timezone.utc).isoformat()


def submit_preprocess_job(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise ValueError('payload is required')
    _cleanup_expired_preprocess_jobs()
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with _PREPROCESS_LOCK:
        _PREPROCESS_JOBS[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'created_at': now.isoformat(),
            'expire_at': (now + timedelta(seconds=PREPROCESS_JOB_TTL_SECONDS)).isoformat(),
            'result': None,
        }
    _PREPROCESS_EXECUTOR.submit(_preprocess_job_worker, job_id, payload)
    return job_id


def get_preprocess_job(job_id: str) -> dict[str, Any]:
    _cleanup_expired_preprocess_jobs()
    with _PREPROCESS_LOCK:
        rec = _PREPROCESS_JOBS.get(job_id)
        if rec is None:
            return {'job_id': job_id, 'status': 'not_found'}
        status = rec.get('status', 'queued')
        if status == 'done' and isinstance(rec.get('result'), dict):
            return rec['result']
        if status == 'failed':
            return {
                'job_id': job_id,
                'status': 'failed',
                'error': rec.get('error', 'unknown error'),
                'failure_reason': rec.get('failure_reason', 'parser_error'),
            }
        return {'job_id': job_id, 'status': status}

def _run_chart_job(job_id: str, files: list[dict[str, str]]) -> dict[str, Any]:
    CHART_JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_input_dir = CHART_JOB_DIR / f"{job_id}_input"
    out_dir = CHART_JOB_DIR / f"{job_id}_charts"
    job_input_dir.mkdir(parents=True, exist_ok=True)

    csv_paths: list[Path] = []
    for i, item in enumerate(files):
        source_name, text, _ = _coerce_csv_text_from_file_payload(item)
        if not text.strip():
            continue
        name = source_name if source_name.endswith('.csv') else f"{source_name}.csv"
        path = job_input_dir / name
        path.write_text(text, encoding='utf-8')
        csv_paths.append(path)

    if not csv_paths:
        raise ValueError('valid csv_text files are required')

    charts = create_multi_charts(csv_paths, out_dir)
    return {
        'job_id': job_id,
        'status': 'done',
        'chart_count': sum(len(v) for v in charts.values()),
        'charts': charts,
        'output_dir': str(out_dir),
    }


def submit_chart_job(files: list[dict[str, str]]) -> str:
    if not isinstance(files, list) or not files:
        raise ValueError('files is required')
    job_id = uuid.uuid4().hex
    future = _CHART_EXECUTOR.submit(_run_chart_job, job_id, files)
    with _CHART_LOCK:
        _CHART_JOBS[job_id] = future
    return job_id


def get_chart_job(job_id: str) -> dict[str, Any]:
    with _CHART_LOCK:
        future = _CHART_JOBS.get(job_id)

    if future is None:
        return {'job_id': job_id, 'status': 'not_found'}
    if not future.done():
        return {'job_id': job_id, 'status': 'running'}
    try:
        return future.result()
    except Exception as exc:
        return {'job_id': job_id, 'status': 'failed', 'error': str(exc)}



def run_ollama(model: str, prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ollama run failed")
    return proc.stdout.strip()


class Handler(BaseHTTPRequestHandler):
    def _error_payload(
        self,
        message: str,
        detail: str | None = None,
        *,
        input_type: str | None = None,
        preprocessing_stage: str | None = None,
    ) -> dict[str, str]:
        data: dict[str, str] = {"error": message, "error_detail": detail or message}
        if input_type:
            data["input_type"] = input_type
        if preprocessing_stage:
            data["preprocessing_stage"] = preprocessing_stage
        return data

    def _send_json(self, data: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/" or route == "/index.html":
            return self._send_file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if route == "/app.js":
            return self._send_file(UI_DIR / "app.js", "application/javascript; charset=utf-8")
        if route == "/styles.css":
            return self._send_file(UI_DIR / "styles.css", "text/css; charset=utf-8")
        if route.startswith('/api/charts/jobs/'):
            job_id = route.split('/')[-1].strip()
            if not job_id:
                return self._send_json(self._error_payload('job id is required'), HTTPStatus.BAD_REQUEST)
            return self._send_json(get_chart_job(job_id))
        if route.startswith('/api/preprocess/jobs/'):
            job_id = route.split('/')[-1].strip()
            if not job_id:
                return self._send_json(self._error_payload('job id is required'), HTTPStatus.BAD_REQUEST)
            return self._send_json(get_preprocess_job(job_id))
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return self._send_json(self._error_payload('invalid json'), HTTPStatus.BAD_REQUEST)

        try:
            if route == '/api/sheets':
                input_type = str(payload.get('input_type', 'auto') or 'auto').strip().lower()
                if input_type != 'excel':
                    return self._send_json({'sheet_names': []})
                file_base64 = str(payload.get('file_base64', '')).strip()
                if not file_base64:
                    return self._send_json(self._error_payload('excel file is required', 'file_base64 is empty', input_type='excel', preprocessing_stage='input_validation'), HTTPStatus.BAD_REQUEST)
                sheet_names = _extract_sheet_names(file_base64)
                return self._send_json({'sheet_names': sheet_names})

            if route == '/api/document/extract':
                input_type = str(payload.get('input_type', 'document') or 'document').strip().lower()
                if input_type != 'document':
                    return self._send_json(self._error_payload('input_type must be document', input_type=input_type, preprocessing_stage='input_validation'), HTTPStatus.BAD_REQUEST)
                file_base64 = str(payload.get('file_base64', '')).strip()
                source_name = str(payload.get('source_name', 'document') or 'document')
                if not file_base64:
                    return self._send_json(self._error_payload('document file is required', 'file_base64 is empty', input_type='document', preprocessing_stage='input_validation'), HTTPStatus.BAD_REQUEST)
                result = extract_document_tables_from_base64(file_base64, source_name)
                return self._send_json(result.to_dict())

            if route == "/api/analyze":
                question = str(payload.get("question", "")).strip()
                if not question:
                    question = "이 데이터의 핵심 인사이트를 알려줘"
                use_planner = bool(payload.get("use_planner", False))

                input_type = str(payload.get("input_type", "csv") or "csv").strip().lower()
                normalized_csv_text = str(payload.get("normalized_csv_text", "") or "")
                source_name = str(payload.get("source_name", "<inline_csv>") or "<inline_csv>")
                meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
                if input_type == "excel":
                    normalized_csv_text = _normalize_excel_base64_to_csv_text(
                        str(payload.get("file_base64", "") or ""),
                        str(payload.get("sheet_name", "") or "").strip() or None,
                    )
                    meta = {**meta, "sheet_name": str(payload.get("sheet_name", "") or "").strip() or "<first_sheet>"}
                elif input_type == "document":
                    extract_result = extract_document_tables_from_base64(
                        str(payload.get("file_base64", "") or ""),
                        source_name,
                    )
                    if not extract_result.tables:
                        return self._send_json(
                            self._error_payload(
                                "document table extraction failed",
                                extract_result.failure_detail or extract_result.failure_reason or "표 추출 실패",
                                input_type="document",
                                preprocessing_stage="table_extraction",
                            ),
                            HTTPStatus.BAD_REQUEST,
                        )
                    selected_index = int(payload.get("table_index", 0) or 0)
                    request_payload_for_table = table_to_analysis_request(extract_result, selected_index)
                    normalized_csv_text = request_payload_for_table["normalized_csv_text"]
                    meta = {**meta, **request_payload_for_table.get("meta", {})}

                request_payload = {
                    "input_type": input_type,
                    "source_name": source_name,
                    "normalized_csv_text": normalized_csv_text,
                    "meta": meta,
                    "csv_text": payload.get("csv_text", ""),
                }
                try:
                    result = build_analysis_payload_from_request(request_payload, question)
                except Exception as exc:
                    input_type = str(request_payload.get("input_type", "csv") or "csv")
                    has_normalized = bool(str(request_payload.get("normalized_csv_text", "")).strip())
                    has_legacy = bool(str(request_payload.get("csv_text", "")).strip())
                    preprocessing_stage = "normalized_csv_text" if has_normalized else "legacy_csv_text" if has_legacy else "input_validation"
                    return self._send_json(
                        self._error_payload(
                            "analyze payload invalid",
                            str(exc),
                            input_type=input_type,
                            preprocessing_stage=preprocessing_stage,
                        ),
                        HTTPStatus.BAD_REQUEST,
                    )
                if use_planner:
                    intent = parse_question_to_intent(question, result.get("summary", {}))
                    plan = build_plan(intent, result.get("summary", {}))
                    result["planner"] = {
                        "intent": intent.__dict__,
                        "plan": {"nodes": plan.nodes, "warnings": plan.warnings, "fallback": plan.fallback},
                        "execution": execute_plan_from_csv_text(plan, str(request_payload.get("normalized_csv_text", "") or "")),
                    }
                return self._send_json(result)

            if route == '/api/preprocess/jobs':
                job_id = submit_preprocess_job(payload)
                return self._send_json({'job_id': job_id, 'status': 'queued'}, HTTPStatus.ACCEPTED)



            if route == '/api/geo/suspects':
                lat_col = str(payload.get('lat_col', '')).strip()
                lon_col = str(payload.get('lon_col', '')).strip()
                threshold_km = float(payload.get('threshold_km', 25) or 25)
                include_geojson = bool(payload.get('include_geojson', False))
                inline = bool(payload.get('inline', True))

                if not lat_col or not lon_col:
                    return self._send_json(self._error_payload('lat_col and lon_col are required'), HTTPStatus.BAD_REQUEST)

                file_payload = {
                    'input_type': str(payload.get('input_type', 'csv') or 'csv'),
                    'name': str(payload.get('source_name', '<inline_csv>') or '<inline_csv>'),
                    'normalized_csv_text': str(payload.get('normalized_csv_text', '') or ''),
                    'csv_text': str(payload.get('csv_text', '') or ''),
                    'file_base64': payload.get('file_base64', ''),
                    'sheet_name': payload.get('sheet_name', ''),
                    'table_index': payload.get('table_index', 0),
                }
                _, normalized_csv_text, _ = _coerce_csv_text_from_file_payload(file_payload)
                fieldnames, rows = _rows_from_csv_text(normalized_csv_text)

                if lat_col not in fieldnames or lon_col not in fieldnames:
                    return self._send_json(
                        self._error_payload('lat_col/lon_col not found in csv header', f'header={fieldnames}'),
                        HTTPStatus.BAD_REQUEST,
                    )

                result_rows = flag_geo_suspects(rows, lat_col=lat_col, lon_col=lon_col, threshold_km=threshold_km)
                suspect_count = sum(1 for row in result_rows if row.get('is_suspect'))
                normal_count = len(result_rows) - suspect_count
                artifacts = _write_geo_suspect_artifacts(
                    result_rows,
                    fieldnames,
                    lat_col=lat_col,
                    lon_col=lon_col,
                    include_geojson=include_geojson,
                )
                response = {
                    'count': len(result_rows),
                    'suspect_count': suspect_count,
                    'normal_count': normal_count,
                    'threshold_km': threshold_km,
                    'artifacts': artifacts,
                }
                if inline:
                    response['rows'] = result_rows
                return self._send_json(response)

            if route == "/api/multi-analyze":
                files = payload.get("files", [])
                question = str(payload.get("question", "")).strip() or "다중 CSV를 비교 분석해줘"
                group_column = str(payload.get("group_column", "")).strip() or None
                target_column = str(payload.get("target_column", "")).strip() or None
                if not isinstance(files, list) or not files:
                    return self._send_json(self._error_payload('files is required'), HTTPStatus.BAD_REQUEST)

                with tempfile.TemporaryDirectory(prefix="bitnet_multi_") as td:
                    tmp_paths = []
                    for i, f in enumerate(files):
                        if not isinstance(f, dict):
                            continue
                        name, text, _ = _coerce_csv_text_from_file_payload(f)
                        if not text.strip():
                            continue
                        out_name = name if name.endswith('.csv') else f"{name}.csv"
                        path = Path(td) / out_name
                        path.write_text(text, encoding="utf-8")
                        tmp_paths.append(path)

                    if not tmp_paths:
                        return self._send_json(self._error_payload('valid normalized_csv_text files are required'), HTTPStatus.BAD_REQUEST)

                    result = analyze_multiple_csv(
                        tmp_paths,
                        question,
                        group_column=group_column,
                        target_column=target_column,
                        use_cache=False,
                    )
                    return self._send_json(result)

            if route == "/api/charts/jobs":
                files = payload.get('files', [])
                job_id = submit_chart_job(files)
                return self._send_json({'job_id': job_id, 'status': 'queued'}, HTTPStatus.ACCEPTED)

            if route == "/api/run":
                model = str(payload.get("model", "")).strip()
                prompt = str(payload.get("prompt", "")).strip()
                if not model or not prompt:
                    return self._send_json(self._error_payload('model and prompt are required'), HTTPStatus.BAD_REQUEST)
                answer = run_ollama(model, prompt)
                return self._send_json({"answer": answer})

        except Exception as exc:  # runtime surface for UI
            input_type = str(payload.get('input_type', 'csv') or 'csv') if isinstance(payload, dict) else 'csv'
            return self._send_json(self._error_payload('request failed', str(exc), input_type=input_type, preprocessing_stage='runtime'), HTTPStatus.BAD_REQUEST)

        self.send_error(HTTPStatus.NOT_FOUND)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"BitNet UI running at http://{host}:{port}")
    server.serve_forever()
