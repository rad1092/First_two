from pathlib import Path


def _app_js_text() -> str:
    return (Path(__file__).resolve().parents[1] / 'bitnet_tools' / 'ui' / 'app.js').read_text(encoding='utf-8')


def test_api_error_detail_priority_is_consistent_for_post_and_get():
    text = _app_js_text()
    expected = "data?.error_detail || data?.error || JSON.stringify(data || {})"
    assert text.count(expected) >= 2


def test_ui_failure_status_messages_are_defined_consistently():
    text = _app_js_text()
    for phrase in [
        "setStatus('입력 전처리 실패')",
        "setStatus('차트 작업 실패')",
        "setStatus('분석 실패')",
        "setStatus('멀티 분석 실패')",
        "setStatus('모델 실행 실패')",
    ]:
        assert phrase in text
