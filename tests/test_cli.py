from pathlib import Path

from bitnet_tools import cli


def test_cli_analyze_legacy_mode(tmp_path):
    csv_path = tmp_path / "sample.csv"
    out_path = tmp_path / "result.json"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    code = cli.main([str(csv_path), "--question", "요약해줘", "--out", str(out_path)])

    assert code == 0
    assert out_path.exists()


def test_cli_ui_mode(monkeypatch):
    called = {}

    def fake_serve(host: str, port: int):
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(cli, "serve", fake_serve)

    code = cli.main(["ui", "--host", "0.0.0.0", "--port", "9999"])

    assert code == 0
    assert called == {"host": "0.0.0.0", "port": 9999}


def test_cli_doctor_mode(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "collect_environment",
        lambda model=None: {"ollama_installed": True, "model_requested": model},
    )

    code = cli.main(["doctor", "--model", "bitnet:latest"])

    assert code == 0
    out = capsys.readouterr().out
    assert '"ollama_installed": true' in out
    assert '"model_requested": "bitnet:latest"' in out


def test_cli_report_mode(tmp_path):
    csv_path = tmp_path / "sample.csv"
    out_path = tmp_path / "report.md"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    code = cli.main(["report", str(csv_path), "--question", "요약", "--out", str(out_path)])

    assert code == 0
    assert out_path.exists()
    assert "BitNet CSV 분석 보고서" in out_path.read_text(encoding="utf-8")


def test_cli_multi_analyze_mode(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    p1.write_text("city,val\nseoul,1\nbusan,2\n", encoding="utf-8")
    p2.write_text("city,val2\nseoul,10\ndaegu,20\n", encoding="utf-8")

    code = cli.main([
        "multi-analyze",
        str(p1),
        str(p2),
        "--question",
        "다중 비교",
        "--out-json",
        str(out_json),
        "--out-report",
        str(out_md),
    ])

    assert code == 0
    assert out_json.exists()
    assert out_md.exists()
    assert "다중 CSV 분석 리포트" in out_md.read_text(encoding="utf-8")


def test_cli_multi_analyze_with_group_target(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    out_json = tmp_path / "out2.json"
    out_md = tmp_path / "out2.md"

    p1.write_text("city,type,val\nseoul,A,1\nseoul,B,2\n", encoding="utf-8")
    p2.write_text("city,type,val\nseoul,A,10\nbusan,A,20\n", encoding="utf-8")

    code = cli.main([
        "multi-analyze",
        str(p1),
        str(p2),
        "--question",
        "그룹비율",
        "--group-column",
        "city",
        "--target-column",
        "type",
        "--out-json",
        str(out_json),
        "--out-report",
        str(out_md),
    ])

    assert code == 0
    body = out_json.read_text(encoding="utf-8")
    assert "group_target_ratio" in body


def test_cli_multi_analyze_with_charts(tmp_path, monkeypatch):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    out_json = tmp_path / "out3.json"
    out_md = tmp_path / "out3.md"
    charts_dir = tmp_path / "charts"

    p1.write_text("city,val\nseoul,1\n", encoding="utf-8")
    p2.write_text("city,val\nbusan,2\n", encoding="utf-8")

    monkeypatch.setattr(cli, "create_multi_charts", lambda paths, out: {str(paths[0]): ["chart1.png"]})

    code = cli.main([
        "multi-analyze",
        str(p1),
        str(p2),
        "--question",
        "차트",
        "--charts-dir",
        str(charts_dir),
        "--out-json",
        str(out_json),
        "--out-report",
        str(out_md),
    ])

    assert code == 0
    body = out_json.read_text(encoding="utf-8")
    assert "charts" in body


def test_cli_multi_analyze_chart_error_fallback(tmp_path, monkeypatch):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    out_json = tmp_path / "out4.json"
    out_md = tmp_path / "out4.md"

    p1.write_text("city,val\nseoul,1\n", encoding="utf-8")
    p2.write_text("city,val\nbusan,2\n", encoding="utf-8")

    def boom(paths, out):
        raise RuntimeError("matplotlib is required for chart generation")

    monkeypatch.setattr(cli, "create_multi_charts", boom)

    code = cli.main([
        "multi-analyze",
        str(p1),
        str(p2),
        "--question",
        "차트실패",
        "--charts-dir",
        str(tmp_path / "charts"),
        "--out-json",
        str(out_json),
        "--out-report",
        str(out_md),
    ])

    assert code == 0
    body = out_json.read_text(encoding="utf-8")
    assert "charts_error" in body
