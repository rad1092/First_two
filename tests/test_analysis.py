import argparse
from pathlib import Path

import pytest

from bitnet_tools.analysis import (
    AnalysisError,
    build_analysis_payload,
    build_analysis_payload_from_csv_text,
    summarize_rows,
)
from bitnet_tools.cli import run_analyze, run_doctor, run_quickstart
from bitnet_tools.web import parse_timeout


def test_summarize_rows_basic():
    rows = [
        {"user_id": "1", "amount": "10.0", "segment": "a", "dt": "2026-01-01"},
        {"user_id": "2", "amount": "20.5", "segment": "b", "dt": "2026-01-02"},
        {"user_id": "3", "amount": "5.0", "segment": "", "dt": "2026-01-03"},
    ]
    summary = summarize_rows(rows, ["user_id", "amount", "segment", "dt"])

    assert summary.row_count == 3
    assert summary.column_count == 4
    assert summary.missing_counts["segment"] == 1
    assert "amount" in summary.numeric_stats
    assert summary.numeric_stats["amount"]["median"] == 10.0
    assert "std" in summary.numeric_stats["amount"]
    assert "outlier_count" in summary.numeric_stats["amount"]
    assert summary.dtypes["segment"] == "string"
    assert summary.dtypes["user_id"] == "int"
    assert summary.dtypes["dt"] == "date"
    assert summary.top_values["segment"][0] == ("a", 1)


def test_build_analysis_payload(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,10\n2,20\n", encoding="utf-8")

    payload = build_analysis_payload(p, "평균 b를 설명해줘")

    assert payload["csv_path"].endswith("sample.csv")
    assert payload["summary"]["row_count"] == 2
    assert "핵심요약 / 근거 / 한계 / 다음행동" in payload["prompt"]


def test_build_analysis_payload_from_csv_text_with_semicolon():
    payload = build_analysis_payload_from_csv_text("x;y\n1;2\n3;4\n", "질문")
    assert payload["summary"]["column_count"] == 2
    assert payload["summary"]["numeric_stats"]["y"]["max"] == 4.0


def test_empty_csv_raises_error():
    with pytest.raises(AnalysisError):
        build_analysis_payload_from_csv_text("   \n", "질문")


def test_mixed_type_column_has_no_numeric_stats():
    payload = build_analysis_payload_from_csv_text("x\n1\ntext\n", "질문")
    assert payload["summary"]["dtypes"]["x"] == "string"
    assert "x" not in payload["summary"]["numeric_stats"]


def test_run_analyze_missing_file_returns_user_error(tmp_path):
    args = argparse.Namespace(
        csv=Path("/tmp/does-not-exist.csv"),
        question="점검",
        out=tmp_path / "out.json",
        model=None,
        timeout=30,
    )
    with pytest.raises(SystemExit, match="analysis error: CSV file not found"):
        run_analyze(args)


def test_parse_timeout_bounds_and_type():
    assert parse_timeout(120) == 120
    with pytest.raises(ValueError, match="integer"):
        parse_timeout("abc")
    with pytest.raises(ValueError, match="between"):
        parse_timeout(0)
    with pytest.raises(ValueError, match="between"):
        parse_timeout(601)


def test_run_quickstart_non_web(tmp_path):
    csv = tmp_path / "sample.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    out = tmp_path / "payload.json"
    args = argparse.Namespace(
        csv=csv,
        question=None,
        preset="insight",
        model=None,
        ask_model=False,
        timeout=30,
        out=out,
    )

    code = run_quickstart(args)
    assert code == 0
    assert out.exists()


def test_run_doctor_prints_summary(capsys):
    code = run_doctor(argparse.Namespace())
    captured = capsys.readouterr().out
    assert code == 0
    assert "[BitNet doctor]" in captured
