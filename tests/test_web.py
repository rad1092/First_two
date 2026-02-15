import time
import threading
import urllib.request
import urllib.error
import json
from pathlib import Path

import base64
import io
import zipfile

import bitnet_tools.web as web
from http.server import ThreadingHTTPServer


def _xlsx_sheet_xml(rows):
    row_nodes = []
    for r_idx, row in enumerate(rows, start=1):
        cell_nodes = []
        for c_idx, val in enumerate(row, start=1):
            col = chr(ord('A') + c_idx - 1)
            ref = f"{col}{r_idx}"
            if val is None:
                continue
            if isinstance(val, (int, float)):
                cell_nodes.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                escaped = str(val).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                cell_nodes.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        row_nodes.append(f'<row r="{r_idx}">{"".join(cell_nodes)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_nodes)}</sheetData>'
        '</worksheet>'
    )


def _make_xlsx_b64(sheet_map):
    workbook_sheets = []
    rels = []
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w') as zf:
        for idx, (name, rows) in enumerate(sheet_map.items(), start=1):
            rid = f'rId{idx}'
            workbook_sheets.append(f'<sheet name="{name}" sheetId="{idx}" r:id="{rid}"/>')
            rels.append(
                f'<Relationship Id="{rid}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
            )
            zf.writestr(f'xl/worksheets/sheet{idx}.xml', _xlsx_sheet_xml(rows))

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(workbook_sheets)}</sheets>'
            '</workbook>'
        )
        rel_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(rels)}'
            '</Relationships>'
        )
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', rel_xml)
    return base64.b64encode(mem.getvalue()).decode('ascii')


def _run_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode('utf-8'))


def test_submit_and_get_chart_job_done(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "CHART_JOB_DIR", tmp_path / "jobs")

    def fake_create_multi_charts(csv_paths, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for p in csv_paths:
            chart = out_dir / f"{Path(p).stem}.png"
            chart.write_text("ok", encoding="utf-8")
            outputs[str(p)] = [str(chart)]
        return outputs

    monkeypatch.setattr(web, "create_multi_charts", fake_create_multi_charts)

    job_id = web.submit_chart_job([{"name": "a.csv", "csv_text": "x\n1\n"}])
    result = web.get_chart_job(job_id)
    for _ in range(20):
        if result["status"] != "running":
            break
        time.sleep(0.01)
        result = web.get_chart_job(job_id)

    assert result["status"] == "done"
    assert result["chart_count"] == 1
    assert result["output_dir"].endswith("_charts")


def test_get_chart_job_not_found():
    result = web.get_chart_job("missing")
    assert result["status"] == "not_found"


def test_submit_and_get_preprocess_job_done(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "PREPROCESS_JOB_DIR", tmp_path / "prep")

    job_id = web.submit_preprocess_job({
        "input_type": "csv",
        "name": "sample.csv",
        "normalized_csv_text": "a,b\n1,2\n",
        "question": "요약",
    })

    result = web.get_preprocess_job(job_id)
    for _ in range(30):
        if result["status"] != "queued" and result["status"] != "running":
            break
        time.sleep(0.01)
        result = web.get_preprocess_job(job_id)

    assert result["status"] == "done"
    assert result["input_type"] == "csv"
    assert "normalized_csv" in result["artifacts"]


def test_preprocess_job_failed_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "PREPROCESS_JOB_DIR", tmp_path / "prep")

    def broken(payload):
        raise ValueError("memory allocation failed")

    monkeypatch.setattr(web, "_run_preprocess_job", lambda *_args, **_kwargs: broken(None))
    job_id = web.submit_preprocess_job({"input_type": "csv", "normalized_csv_text": "x\n1\n"})

    result = web.get_preprocess_job(job_id)
    for _ in range(30):
        if result["status"] != "queued" and result["status"] != "running":
            break
        time.sleep(0.01)
        result = web.get_preprocess_job(job_id)

    assert result["status"] == "failed"
    assert result["failure_reason"] == "memory_limit"


def _make_docx_b64() -> str:
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>
<w:tr><w:tc><w:p><w:r><w:t>h1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>h2</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>v1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>v2</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl></w:body></w:document>"""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w') as zf:
        zf.writestr('word/document.xml', xml)
    return base64.b64encode(mem.getvalue()).decode('ascii')


def test_coerce_document_payload_to_csv_text():
    b64 = _make_docx_b64()
    source, csv_text, meta = web._coerce_csv_text_from_file_payload({
        'input_type': 'document',
        'name': 'sample.docx',
        'file_base64': b64,
        'table_index': 0,
    })

    assert source == 'sample.docx'
    assert 'h1,h2' in csv_text
    assert meta['table_id'] == 'docx_table_1'


def test_excel_single_sheet_normalization():
    b64 = _make_xlsx_b64({'Sales': [['region', 'amount'], ['seoul', 100], ['busan', 120]]})

    source, csv_text, meta = web._coerce_csv_text_from_file_payload({
        'input_type': 'excel',
        'name': 'sales.xlsx',
        'file_base64': b64,
    })

    assert source == 'sales.xlsx'
    assert 'region,amount' in csv_text
    assert 'seoul,100' in csv_text
    assert meta['sheet_name'] == '<first_sheet>'


def test_excel_multi_sheet_selection_uses_target_sheet():
    b64 = _make_xlsx_b64({
        'Raw': [['c1', 'c2'], ['a', 1]],
        'Summary': [['city', 'score'], ['busan', 9]],
    })

    csv_text = web._normalize_excel_base64_to_csv_text(b64, sheet_name='Summary')

    assert 'city,score' in csv_text
    assert 'busan,9' in csv_text
    assert 'c1,c2' not in csv_text


def test_excel_empty_sheet_raises_validation_error():
    import pytest

    b64 = _make_xlsx_b64({'Empty': []})

    with pytest.raises(ValueError, match='selected sheet has no non-empty rows'):
        web._normalize_excel_base64_to_csv_text(b64, sheet_name='Empty')


def test_excel_header_validation_rejects_empty_and_duplicate_columns():
    import pytest

    empty_header_b64 = _make_xlsx_b64({'BadHeader': [['id', ''], [1, 2]]})
    with pytest.raises(ValueError, match='empty header at index 1'):
        web._normalize_excel_base64_to_csv_text(empty_header_b64)

    dup_header_b64 = _make_xlsx_b64({'DupHeader': [['id', 'id'], [1, 2]]})
    with pytest.raises(ValueError, match='duplicated header'):
        web._normalize_excel_base64_to_csv_text(dup_header_b64)


def test_document_extract_api_success_and_failure_payload_contract():
    server, thread = _run_server()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        ok_code, ok_body = _post_json(base + '/api/document/extract', {
            'input_type': 'document',
            'source_name': 'ok.docx',
            'file_base64': _make_docx_b64(),
        })
        assert ok_code == 200
        assert ok_body['tables']

        fail_code, fail_body = _post_json(base + '/api/document/extract', {
            'input_type': 'document',
            'source_name': 'scan.pdf',
            'file_base64': base64.b64encode(b'%PDF-1.4\n<< /Subtype /Image >>\n').decode('ascii'),
        })
        assert fail_code == 200
        assert fail_body['tables'] == []
        assert fail_body['failure_reason'] == '스캔 이미지'
        assert fail_body['failure_detail']
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_analyze_document_fallback_error_uses_error_and_error_detail():
    server, thread = _run_server()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        code, body = _post_json(base + '/api/analyze', {
            'input_type': 'document',
            'source_name': 'locked.pdf',
            'file_base64': base64.b64encode(b'%PDF-1.4\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n').decode('ascii'),
            'question': '요약',
        })
        assert code == 400
        assert body['error'] == 'document table extraction failed'
        assert 'error_detail' in body
        assert body['preprocessing_stage'] == 'table_extraction'
    finally:
        server.shutdown()
        thread.join(timeout=1)
