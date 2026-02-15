from bitnet_tools.analysis import (
    build_analysis_payload,
    build_analysis_payload_from_csv_text,
    summarize_rows,
    build_markdown_report,
)
from bitnet_tools.multi_csv import analyze_multiple_csv, build_multi_csv_markdown



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
    assert summary.dtypes["segment"] == "string"


def test_build_analysis_payload(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,10\n2,20\n", encoding="utf-8")

    payload = build_analysis_payload(p, "평균 b를 설명해줘")

    assert payload["csv_path"].endswith("sample.csv")
    assert payload["summary"]["row_count"] == 2
    assert "핵심요약 / 근거 / 한계 / 다음행동" in payload["prompt"]


def test_build_analysis_payload_from_csv_text():
    payload = build_analysis_payload_from_csv_text(
        "x,y\n1,2\n3,4\n", "합계를 설명해줘"
    )

    assert payload["csv_path"] == "<inline_csv>"
    assert payload["summary"]["row_count"] == 2


def test_streaming_summary_keeps_mixed_type_as_string(tmp_path):
    p = tmp_path / "mixed.csv"
    p.write_text("a,b\n1,10\n2,hello\n", encoding="utf-8")

    payload = build_analysis_payload(p, "검증")

    assert payload["summary"]["dtypes"]["b"] == "string"
    assert "b" not in payload["summary"]["numeric_stats"]


def test_build_markdown_report():
    rows = [{"a": "1", "b": "10"}, {"a": "2", "b": "20"}]
    summary = summarize_rows(rows, ["a", "b"])
    report = build_markdown_report(summary, "테스트 질문")

    assert "# BitNet CSV 분석 보고서" in report
    assert "| a |" in report
    assert "테스트 질문" in report


def test_multi_csv_report_builder(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    p1.write_text("city,v\nseoul,1\n", encoding="utf-8")
    p2.write_text("city,v2\nseoul,2\n", encoding="utf-8")

    result = analyze_multiple_csv([p1, p2], "비교")
    report = build_multi_csv_markdown(result)

    assert result["file_count"] == 2
    assert "city" in result["shared_columns"]
    assert "다중 CSV 분석 리포트" in report


def test_multi_csv_schema_drift_and_group_ratio(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    p1.write_text("city,type,val\nseoul,A,1\nseoul,B,2\n", encoding="utf-8")
    p2.write_text("city,type,val\nseoul,A,100\nbusan,A,200\n", encoding="utf-8")

    result = analyze_multiple_csv([p1, p2], "드리프트", group_column="city", target_column="type")

    assert "schema_drift" in result
    assert "val" in result["schema_drift"]
    assert result["schema_drift"]["val"]["mean_range"] > 0
    assert result["files"][0]["group_target_ratio"] is not None


def test_multi_csv_large_row_count(tmp_path):
    p = tmp_path / "big.csv"
    lines = ["city,val,type"]
    for i in range(5000):
        lines.append(f"seoul,{i % 100},A")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = analyze_multiple_csv([p], "대용량")

    assert result["total_row_count"] == 5000
    assert result["files"][0]["summary"]["row_count"] == 5000


def test_multi_csv_semantic_type_and_insights(tmp_path):
    p = tmp_path / "typed.csv"
    p.write_text("dt,lat,val,cat\n2024-01-01,37.5,1,A\n2024-01-02,37.6,1000,A\n", encoding="utf-8")

    result = analyze_multiple_csv([p], "의미타입")
    prof = result["files"][0]["column_profiles"]

    assert prof["dt"]["semantic_type"] == "date"
    assert prof["lat"]["semantic_type"] in {"geo_latitude", "numeric"}
    assert isinstance(result.get("insights"), list)


def test_multi_csv_cache_created(tmp_path, monkeypatch):
    import bitnet_tools.multi_csv as multi

    monkeypatch.setattr(multi, "CACHE_DIR", tmp_path / ".cache")
    p = tmp_path / "cache.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")

    result = multi.analyze_multiple_csv([p], "캐시")
    assert result["file_count"] == 1
    assert any((tmp_path / ".cache").glob("*.json"))


def test_multi_csv_top_values_capped_marker(monkeypatch, tmp_path):
    import bitnet_tools.multi_csv as multi

    monkeypatch.setattr(multi, "TOP_VALUE_TRACK_CAP", 3)
    p = tmp_path / "cardinality.csv"
    p.write_text("col\na\nb\nc\nd\na\n", encoding="utf-8")

    result = multi.analyze_multiple_csv([p], "카디널리티")
    prof = result["files"][0]["column_profiles"]["col"]

    assert prof["top_values_capped"] is True
    assert any(x["value"] == "__OTHER__" for x in prof["top_values"])


def test_multi_csv_with_parallel_workers(tmp_path):
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    p1.write_text("city,val\nseoul,1\n", encoding="utf-8")
    p2.write_text("city,val\nbusan,2\n", encoding="utf-8")

    result = analyze_multiple_csv([p1, p2], "병렬", max_workers=2)

    assert result["file_count"] == 2
    assert [f["path"] for f in result["files"]] == [str(p1), str(p2)]
