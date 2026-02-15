from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_bundle(bundle_dir: Path, policy_path: Path) -> dict[str, Any]:
    violations: list[str] = []
    checked_assets: list[dict[str, Any]] = []

    if not bundle_dir.exists():
        return {
            "ok": False,
            "violations": [f"bundle directory not found: {bundle_dir}"],
            "checked_assets": [],
        }

    if not policy_path.exists():
        return {
            "ok": False,
            "violations": [f"policy file not found: {policy_path}"],
            "checked_assets": [],
        }

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    allowlist = set(policy.get("allowlist", []))
    allowed_licenses = set(policy.get("allowed_licenses", []))
    assets = policy.get("assets", [])

    if not assets:
        violations.append("policy has no assets")

    for asset in assets:
        rel_path = asset.get("path")
        expected_hash = (asset.get("sha256") or "").lower()
        license_name = asset.get("license", "UNKNOWN")
        target = bundle_dir / rel_path if rel_path else bundle_dir

        asset_result = {
            "path": rel_path,
            "exists": False,
            "hash_ok": False,
            "allowlisted": False,
            "license_ok": False,
            "license": license_name,
        }

        if not rel_path:
            violations.append("asset.path is required")
            checked_assets.append(asset_result)
            continue

        if rel_path in allowlist:
            asset_result["allowlisted"] = True
        else:
            violations.append(f"allowlist violation: {rel_path}")

        if license_name in allowed_licenses:
            asset_result["license_ok"] = True
        else:
            violations.append(f"license violation: {rel_path} ({license_name})")

        if target.exists() and target.is_file():
            asset_result["exists"] = True
            digest = _sha256(target)
            asset_result["sha256"] = digest
            if expected_hash and digest == expected_hash:
                asset_result["hash_ok"] = True
            else:
                violations.append(
                    f"hash mismatch: {rel_path} expected={expected_hash or '<empty>'} actual={digest}"
                )
        else:
            violations.append(f"missing file: {rel_path}")

        checked_assets.append(asset_result)

    return {
        "ok": not violations,
        "violations": violations,
        "checked_assets": checked_assets,
        "policy_file": str(policy_path),
        "bundle_dir": str(bundle_dir),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline bundle verification helper")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="verify offline bundle policy/hash/license checks")
    verify.add_argument("--bundle-dir", type=Path, required=True)
    verify.add_argument("--policy", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "verify":
        report = verify_bundle(args.bundle_dir, args.policy)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
