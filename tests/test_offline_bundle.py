import json
from pathlib import Path

from bitnet_tools.offline_bundle import verify_bundle


def test_verify_bundle_success(tmp_path):
    bundle = tmp_path / ".offline_bundle"
    wheels = bundle / "wheels"
    meta = bundle / "meta"
    wheels.mkdir(parents=True)
    meta.mkdir(parents=True)

    wheel = wheels / "sample.whl"
    wheel.write_bytes(b"demo-wheel")

    import hashlib

    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    policy = {
        "allowlist": ["wheels/sample.whl"],
        "allowed_licenses": ["MIT"],
        "assets": [
            {"path": "wheels/sample.whl", "sha256": digest, "license": "MIT"}
        ],
    }
    policy_path = meta / "offline_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    result = verify_bundle(bundle, policy_path)

    assert result["ok"] is True
    assert result["violations"] == []


def test_verify_bundle_policy_violation_blocks(tmp_path):
    bundle = tmp_path / ".offline_bundle"
    wheels = bundle / "wheels"
    meta = bundle / "meta"
    wheels.mkdir(parents=True)
    meta.mkdir(parents=True)

    wheel = wheels / "sample.whl"
    wheel.write_bytes(b"demo-wheel")

    policy = {
        "allowlist": [],
        "allowed_licenses": ["Apache-2.0"],
        "assets": [
            {"path": "wheels/sample.whl", "sha256": "bad", "license": "UNKNOWN"}
        ],
    }
    policy_path = meta / "offline_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    result = verify_bundle(bundle, policy_path)

    assert result["ok"] is False
    assert any("allowlist violation" in x for x in result["violations"])
    assert any("license violation" in x for x in result["violations"])
    assert any("hash mismatch" in x for x in result["violations"])
