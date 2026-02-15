from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "resources" / "online_sources.json"
OUT_DIR = ROOT / ".online_assets"
REF_DIR = OUT_DIR / "references"
WHEEL_DIR = OUT_DIR / "wheelhouse"
MODEL_DIR = OUT_DIR / "models"
RUNTIME_DIR = OUT_DIR / "runtime"
META_DIR = OUT_DIR / "meta"

OFFICIAL_WHEEL_INDEX = "https://pypi.org/simple"


@dataclass
class ManifestItem:
    category: str
    name: str
    version: str | None
    source: str
    path: str | None
    sha256: str | None
    status: str
    detail: str


@dataclass
class CollectionReport:
    created_at: str
    source_file: str
    installable: list[dict]
    blocked_or_failed: list[dict]
    defer: list[dict]
    summary: dict[str, int]


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    stem = (parsed.netloc + parsed.path).strip("/") or "index"
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem)
    return stem


def _hash_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_official_asset_url(url: str, official_base: str) -> bool:
    parsed = urlparse(url)
    official = urlparse(official_base)
    if parsed.scheme != "https":
        return False
    if parsed.netloc != official.netloc:
        return False
    return parsed.path.startswith(official.path)


def _extract_version_from_filename(filename: str) -> str | None:
    # wheel: {dist}-{version}-...whl
    if filename.endswith(".whl"):
        parts = filename.split("-")
        if len(parts) >= 2:
            return parts[1]
    # source dist: name-version.tar.gz | .zip
    m = re.match(r".+-([0-9][A-Za-z0-9_.!-]*)\.(tar\.gz|zip)$", filename)
    if m:
        return m.group(1)
    return None


def _download_wheel(pkg_name: str, version: str) -> list[ManifestItem]:
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    spec = f"{pkg_name}=={version}"
    before = {p.name for p in WHEEL_DIR.iterdir() if p.is_file()}
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        spec,
        "-d",
        str(WHEEL_DIR),
        "--index-url",
        OFFICIAL_WHEEL_INDEX,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "pip download failed"
        return [
            ManifestItem(
                category="wheelhouse",
                name=pkg_name,
                version=version,
                source=OFFICIAL_WHEEL_INDEX,
                path=None,
                sha256=None,
                status="defer",
                detail=detail.splitlines()[-1][:280],
            )
        ]

    added = [p for p in WHEEL_DIR.iterdir() if p.is_file() and p.name not in before]
    if not added:
        return [
            ManifestItem(
                category="wheelhouse",
                name=pkg_name,
                version=version,
                source=OFFICIAL_WHEEL_INDEX,
                path=None,
                sha256=None,
                status="defer",
                detail="download completed but no new files were added",
            )
        ]

    results: list[ManifestItem] = []
    for file_path in sorted(added):
        detected_version = _extract_version_from_filename(file_path.name)
        results.append(
            ManifestItem(
                category="wheelhouse",
                name=file_path.name,
                version=detected_version or version,
                source=OFFICIAL_WHEEL_INDEX,
                path=str(file_path.relative_to(ROOT)),
                sha256=_hash_sha256(file_path),
                status="collected",
                detail=f"requested={spec}",
            )
        )
    return results


def _download_asset(category: str, name: str, url: str, official_base: str, target_dir: Path) -> ManifestItem:
    target_dir.mkdir(parents=True, exist_ok=True)
    if not _is_official_asset_url(url, official_base):
        return ManifestItem(
            category=category,
            name=name,
            version=None,
            source=url,
            path=None,
            sha256=None,
            status="defer",
            detail=f"blocked: non-official URL (official_base={official_base})",
        )

    suffix = Path(urlparse(url).path).suffix or ".bin"
    out_path = target_dir / f"{_slug_from_url(url)}{suffix}"
    req = Request(url, headers={"User-Agent": "bitnet-tools/official-collector"})

    try:
        with urlopen(req, timeout=30) as resp:
            final_url = resp.geturl()
            if not _is_official_asset_url(final_url, official_base):
                return ManifestItem(
                    category=category,
                    name=name,
                    version=None,
                    source=url,
                    path=None,
                    sha256=None,
                    status="defer",
                    detail=f"blocked: redirected to non-official URL ({final_url})",
                )
            out_path.write_bytes(resp.read())
        return ManifestItem(
            category=category,
            name=name,
            version=None,
            source=url,
            path=str(out_path.relative_to(ROOT)),
            sha256=_hash_sha256(out_path),
            status="collected",
            detail="downloaded",
        )
    except HTTPError as exc:
        return ManifestItem(category, name, None, url, None, None, "defer", f"http_error:{exc.code}")
    except URLError as exc:
        return ManifestItem(category, name, None, url, None, None, "defer", f"url_error:{exc.reason}")
    except Exception as exc:  # pragma: no cover
        return ManifestItem(category, name, None, url, None, None, "defer", f"error:{exc}")


def _load_sources() -> dict:
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    data.setdefault("wheelhouse", [])
    data.setdefault("model_assets", [])
    data.setdefault("runtime_assets", [])
    return data


def main() -> int:
    if not SOURCES_FILE.exists():
        print(f"sources file not found: {SOURCES_FILE}", file=sys.stderr)
        return 1

    sources = _load_sources()

    OUT_DIR.mkdir(exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    items: list[ManifestItem] = []

    for pkg in sources["wheelhouse"]:
        name = pkg["name"]
        version = pkg["version"]
        print(f"[wheelhouse] {name}=={version}")
        items.extend(_download_wheel(name, version))

    for asset in sources["model_assets"]:
        print(f"[model] {asset['name']}")
        items.append(
            _download_asset(
                category="model_asset",
                name=asset["name"],
                url=asset["url"],
                official_base=asset["official_base"],
                target_dir=MODEL_DIR,
            )
        )

    for asset in sources["runtime_assets"]:
        print(f"[runtime] {asset['name']}")
        items.append(
            _download_asset(
                category="runtime_asset",
                name=asset["name"],
                url=asset["url"],
                official_base=asset["official_base"],
                target_dir=RUNTIME_DIR,
            )
        )

    manifest_path = META_DIR / "collection_manifest.json"
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(SOURCES_FILE.relative_to(ROOT)),
        "items": [asdict(item) for item in items],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    installable = [asdict(i) for i in items if i.status == "collected"]
    blocked_or_failed = [asdict(i) for i in items if i.status != "collected"]
    defer = [asdict(i) for i in items if i.status == "defer"]

    report = CollectionReport(
        created_at=datetime.now(timezone.utc).isoformat(),
        source_file=str(SOURCES_FILE.relative_to(ROOT)),
        installable=installable,
        blocked_or_failed=blocked_or_failed,
        defer=defer,
        summary={
            "total": len(items),
            "installable": len(installable),
            "blocked_or_failed": len(blocked_or_failed),
            "defer": len(defer),
        },
    )
    report_path = META_DIR / "collection_report.json"
    report_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"manifest saved: {manifest_path.relative_to(ROOT)}")
    print(f"report saved: {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
