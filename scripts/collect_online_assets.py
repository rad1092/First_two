from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "resources" / "online_sources.json"
OUT_DIR = ROOT / ".online_assets"
REF_DIR = OUT_DIR / "references"
WHEEL_DIR = OUT_DIR / "wheels"
META_DIR = OUT_DIR / "meta"


@dataclass
class DownloadResult:
    target: str
    category: str
    ok: bool
    path: str | None
    detail: str


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    stem = (parsed.netloc + parsed.path).strip("/") or "index"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem)
    return f"{stem}.html"


def _fetch_reference(url: str) -> DownloadResult:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REF_DIR / _slug_from_url(url)
    req = Request(url, headers={"User-Agent": "bitnet-tools/online-collector"})
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read()
        out_path.write_bytes(body)
        return DownloadResult(url, "reference", True, str(out_path.relative_to(ROOT)), "downloaded")
    except HTTPError as exc:
        return DownloadResult(url, "reference", False, None, f"http_error:{exc.code}")
    except URLError as exc:
        return DownloadResult(url, "reference", False, None, f"url_error:{exc.reason}")
    except Exception as exc:  # pragma: no cover
        return DownloadResult(url, "reference", False, None, f"error:{exc}")


def _download_wheel(pkg: str) -> DownloadResult:
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "download", pkg, "-d", str(WHEEL_DIR)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return DownloadResult(pkg, "tool_package", True, str(WHEEL_DIR.relative_to(ROOT)), "downloaded")
    detail = proc.stderr.strip() or proc.stdout.strip() or "pip download failed"
    return DownloadResult(pkg, "tool_package", False, None, detail.splitlines()[-1][:220])


def main() -> int:
    if not SOURCES_FILE.exists():
        print(f"sources file not found: {SOURCES_FILE}", file=sys.stderr)
        return 1

    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    tool_packages: list[str] = list(data.get("tool_packages", []))
    reference_urls: list[str] = list(data.get("reference_urls", []))

    OUT_DIR.mkdir(exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    results: list[DownloadResult] = []

    for pkg in tool_packages:
        print(f"[tool] {pkg}")
        results.append(_download_wheel(pkg))

    for url in reference_urls:
        print(f"[ref] {url}")
        results.append(_fetch_reference(url))

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "source_file": str(SOURCES_FILE.relative_to(ROOT)),
        "results": [asdict(r) for r in results],
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.ok),
            "failed": sum(1 for r in results if not r.ok),
        },
    }

    out = META_DIR / "collection_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
