from __future__ import annotations

from http import HTTPStatus
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
from typing import Any
from urllib.parse import urlparse

from .analysis import build_analysis_payload_from_csv_text
from .multi_csv import analyze_multiple_csv
from .visualize import create_multi_charts


UI_DIR = Path(__file__).parent / "ui"


CHART_JOB_DIR = Path('.bitnet_cache') / 'chart_jobs'
_CHART_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_CHART_JOBS: dict[str, Future] = {}
_CHART_LOCK = threading.Lock()


def _run_chart_job(job_id: str, files: list[dict[str, str]]) -> dict[str, Any]:
    CHART_JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_input_dir = CHART_JOB_DIR / f"{job_id}_input"
    out_dir = CHART_JOB_DIR / f"{job_id}_charts"
    job_input_dir.mkdir(parents=True, exist_ok=True)

    csv_paths: list[Path] = []
    for i, item in enumerate(files):
        name = str(item.get('name', f'file_{i}.csv'))
        text = str(item.get('csv_text', ''))
        if not text.strip():
            continue
        if not name.endswith('.csv'):
            name = f"{name}.csv"
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
    def _error_payload(self, message: str, detail: str | None = None) -> dict[str, str]:
        return {"error": message, "error_detail": detail or message}

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
            if route == "/api/analyze":
                csv_text = str(payload.get("csv_text", ""))
                question = str(payload.get("question", "")).strip()
                if not csv_text.strip():
                    return self._send_json(self._error_payload('csv_text is required'), HTTPStatus.BAD_REQUEST)
                if not question:
                    question = "이 데이터의 핵심 인사이트를 알려줘"
                result = build_analysis_payload_from_csv_text(csv_text, question)
                return self._send_json(result)


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
                        name = str(f.get("name", f"file_{i}.csv"))
                        text = str(f.get("csv_text", ""))
                        if not text.strip():
                            continue
                        if not name.endswith('.csv'):
                            name = f"{name}.csv"
                        path = Path(td) / name
                        path.write_text(text, encoding="utf-8")
                        tmp_paths.append(path)

                    if not tmp_paths:
                        return self._send_json(self._error_payload('valid csv_text files are required'), HTTPStatus.BAD_REQUEST)

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
            return self._send_json(self._error_payload('request failed', str(exc)), HTTPStatus.BAD_REQUEST)

        self.send_error(HTTPStatus.NOT_FOUND)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"BitNet UI running at http://{host}:{port}")
    server.serve_forever()
