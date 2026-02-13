from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse

from .analysis import AnalysisError, build_analysis_payload_from_csv_text


UI_DIR = Path(__file__).parent / "ui"
MAX_CSV_TEXT_CHARS = 1_000_000


def run_ollama(model: str, prompt: str, timeout_s: int = 120) -> str:
    try:
        proc = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ollama run timed out after {timeout_s}s") from exc

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ollama run failed")
    return proc.stdout.strip()


class Handler(BaseHTTPRequestHandler):
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
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return self._send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)

        try:
            if route == "/api/analyze":
                csv_text = str(payload.get("csv_text", ""))
                question = str(payload.get("question", "")).strip()
                if not csv_text.strip():
                    return self._send_json({"error": "csv_text is required"}, HTTPStatus.BAD_REQUEST)
                if len(csv_text) > MAX_CSV_TEXT_CHARS:
                    return self._send_json(
                        {"error": f"csv_text too large (max {MAX_CSV_TEXT_CHARS} chars)"},
                        HTTPStatus.BAD_REQUEST,
                    )
                if not question:
                    question = "이 데이터의 핵심 인사이트를 알려줘"
                result = build_analysis_payload_from_csv_text(csv_text, question)
                return self._send_json(result)

            if route == "/api/run":
                model = str(payload.get("model", "")).strip()
                prompt = str(payload.get("prompt", "")).strip()
                timeout_s = int(payload.get("timeout", 120))
                if not model or not prompt:
                    return self._send_json({"error": "model and prompt are required"}, HTTPStatus.BAD_REQUEST)
                answer = run_ollama(model, prompt, timeout_s=timeout_s)
                return self._send_json({"answer": answer})

        except AnalysisError as exc:
            return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # runtime surface for UI
            return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        self.send_error(HTTPStatus.NOT_FOUND)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"BitNet UI running at http://{host}:{port}")
    server.serve_forever()
