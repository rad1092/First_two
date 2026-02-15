from bitnet_tools import doctor


def test_collect_offline_readiness_has_expected_keys(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/pip" if name == "pip" else None)

    result = doctor._collect_offline_readiness(models=["bitnet:latest"], model="bitnet:latest")

    assert "bundle_dir_exists" in result
    assert "dependencies" in result
    assert "files" in result
    assert "model" in result
    assert result["model"]["available"] is True


def test_collect_environment_without_ollama_has_offline_readiness(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)

    result = doctor.collect_environment(model="bitnet:latest")

    assert result["ollama_installed"] is False
    assert "offline_readiness" in result
    assert result["offline_readiness"]["model"]["requested"] == "bitnet:latest"
