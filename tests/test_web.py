import time
from pathlib import Path

import base64
import io
import zipfile

import bitnet_tools.web as web


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
