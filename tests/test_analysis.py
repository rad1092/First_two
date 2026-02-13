from bitnet_tools.analysis import (
    build_analysis_payload,
    build_analysis_payload_from_csv_text,
    summarize_rows,
)


def test_summarize_rows_basic():
    rows = [
        {"user_id": "1", "amount": "10.0", "segment": "a"},
        {"user_id": "2", "amount": "20.5", "segment": "b"},
        {"user_id": "3", "amount": "5.0", "segment": ""},
    ]
    summary = summarize_rows(rows, ["user_id", "amount", "segment"])

    assert summary.row_count == 3
    assert summary.column_count == 3
    assert summary.missing_counts["segment"] == 1
    assert "amount" in summary.numeric_stats
    assert summary.numeric_stats["amount"]["median"] == 10.0
    assert summary.dtypes["segment"] == "string"
    assert summary.top_values["segment"][0] == ("a", 1)


def test_build_analysis_payload(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,10\n2,20\n", encoding="utf-8")

    payload = build_analysis_payload(p, "평균 b를 설명해줘")

    assert payload["csv_path"].endswith("sample.csv")
    assert payload["summary"]["row_count"] == 2
    assert "핵심요약 / 근거 / 한계 / 다음행동" in payload["prompt"]


def test_build_analysis_payload_from_csv_text():
    payload = build_analysis_payload_from_csv_text("x,y\n1,2\n3,4\n", "질문")
    assert payload["summary"]["column_count"] == 2
    assert payload["summary"]["numeric_stats"]["y"]["max"] == 4.0
