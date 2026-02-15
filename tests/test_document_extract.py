import base64
import io
import zipfile

from bitnet_tools.document_extract import extract_document_tables_from_base64, table_to_analysis_request


def _make_docx_with_table() -> bytes:
    document_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>
<w:tr><w:tc><w:p><w:r><w:t>name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>score</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>10</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl></w:body></w:document>'''
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w') as zf:
        zf.writestr('word/document.xml', document_xml)
    return mem.getvalue()


def test_extract_docx_tables_and_request_payload():
    raw = _make_docx_with_table()
    b64 = base64.b64encode(raw).decode('ascii')

    result = extract_document_tables_from_base64(b64, 'sample.docx')

    assert len(result.tables) == 1
    table = result.tables[0]
    assert table.row_count == 2
    assert table.column_count == 2
    assert 0.0 <= table.confidence <= 1.0

    request = table_to_analysis_request(result, 0)
    assert request['input_type'] == 'document'
    assert 'name,score' in request['normalized_csv_text']
    assert request['meta']['table_id'] == 'docx_table_1'


def test_extract_pdf_failure_reason_encrypted():
    fake_pdf = b'%PDF-1.4\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n'
    b64 = base64.b64encode(fake_pdf).decode('ascii')

    result = extract_document_tables_from_base64(b64, 'locked.pdf')

    assert result.tables == []
    assert result.failure_reason == '암호화'


def test_extract_pdf_failure_reason_scan_image():
    fake_pdf = b'%PDF-1.4\n<< /Subtype /Image >>\n'
    b64 = base64.b64encode(fake_pdf).decode('ascii')

    result = extract_document_tables_from_base64(b64, 'scan.pdf')

    assert result.tables == []
    assert result.failure_reason == '스캔 이미지'
