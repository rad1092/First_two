from __future__ import annotations

import base64
import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}


@dataclass
class ExtractedTable:
    table_id: str
    source: str
    rows: list[list[str]]
    header_inferred: bool
    missing_ratio: float
    confidence: float

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def to_csv(self) -> str:
        if not self.rows:
            return ""
        max_len = self.column_count
        output = io.StringIO()
        writer = csv.writer(output)
        for row in self.rows:
            padded = row + [""] * (max_len - len(row))
            writer.writerow(padded)
        return output.getvalue()

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "source": self.source,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "header_inferred": self.header_inferred,
            "missing_ratio": round(self.missing_ratio, 4),
            "confidence": round(self.confidence, 4),
            "preview": self.rows[:5],
        }


@dataclass
class DocumentExtractResult:
    input_type: str
    source_name: str
    tables: list[ExtractedTable]
    failure_reason: str | None = None
    failure_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input_type": self.input_type,
            "source_name": self.source_name,
            "tables": [t.to_dict() for t in self.tables],
        }
        if self.failure_reason:
            payload["failure_reason"] = self.failure_reason
            payload["failure_detail"] = self.failure_detail or self.failure_reason
        return payload


def extract_document_tables_from_base64(file_base64: str, source_name: str) -> DocumentExtractResult:
    try:
        raw = base64.b64decode(file_base64)
    except Exception as exc:
        raise ValueError(f"invalid document base64: {exc}") from exc
    return extract_document_tables_from_bytes(raw, source_name)


def extract_document_tables(path: str | Path) -> DocumentExtractResult:
    file_path = Path(path)
    return extract_document_tables_from_bytes(file_path.read_bytes(), file_path.name)


def extract_document_tables_from_bytes(raw: bytes, source_name: str) -> DocumentExtractResult:
    ext = Path(source_name).suffix.lower()
    if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError(f"unsupported document format: {ext or '<none>'}")

    if ext == ".docx":
        tables = _extract_docx_tables(raw)
    elif ext == ".pptx":
        tables = _extract_pptx_tables(raw)
    else:
        tables_or_failure = _extract_pdf_tables(raw)
        if isinstance(tables_or_failure, tuple):
            reason, detail = tables_or_failure
            return DocumentExtractResult(
                input_type="document",
                source_name=source_name,
                tables=[],
                failure_reason=reason,
                failure_detail=detail,
            )
        tables = tables_or_failure

    if not tables:
        return DocumentExtractResult(
            input_type="document",
            source_name=source_name,
            tables=[],
            failure_reason="표 없음",
            failure_detail="문서에서 테이블 구조를 찾지 못했습니다.",
        )
    return DocumentExtractResult(input_type="document", source_name=source_name, tables=tables)


def table_to_analysis_request(result: DocumentExtractResult, table_index: int) -> dict[str, Any]:
    if not result.tables:
        raise ValueError(result.failure_detail or result.failure_reason or "표 없음")
    if table_index < 0 or table_index >= len(result.tables):
        raise ValueError(f"table_index out of range: {table_index}")
    table = result.tables[table_index]
    return {
        "input_type": "document",
        "source_name": result.source_name,
        "normalized_csv_text": table.to_csv(),
        "meta": {
            "table_id": table.table_id,
            "table_index": table_index,
            "row_count": table.row_count,
            "column_count": table.column_count,
            "header_inferred": table.header_inferred,
            "missing_ratio": table.missing_ratio,
            "confidence": table.confidence,
        },
    }


def _extract_docx_tables(raw: bytes) -> list[ExtractedTable]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        if "word/document.xml" not in zf.namelist():
            return []
        root = ET.fromstring(zf.read("word/document.xml"))

    tables: list[ExtractedTable] = []
    for ti, tbl in enumerate(root.findall(".//w:tbl", ns), start=1):
        rows: list[list[str]] = []
        for tr in tbl.findall("w:tr", ns):
            row: list[str] = []
            for tc in tr.findall("w:tc", ns):
                text = "".join((t.text or "") for t in tc.findall(".//w:t", ns)).strip()
                row.append(text)
            if any(c.strip() for c in row):
                rows.append(row)
        normalized = _normalize_rows(rows)
        if normalized:
            tables.append(_build_table(f"docx_table_{ti}", "docx", normalized))
    return tables


def _extract_pptx_tables(raw: bytes) -> list[ExtractedTable]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        slide_paths = sorted(
            p for p in zf.namelist() if p.startswith("ppt/slides/slide") and p.endswith(".xml")
        )
        tables: list[ExtractedTable] = []
        for slide_idx, slide_path in enumerate(slide_paths, start=1):
            root = ET.fromstring(zf.read(slide_path))
            tbl_nodes = root.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}tbl')
            for tbl_idx, tbl in enumerate(tbl_nodes, start=1):
                rows: list[list[str]] = []
                for tr in tbl.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}tr'):
                    row: list[str] = []
                    for tc in tr.findall('{http://schemas.openxmlformats.org/drawingml/2006/main}tc'):
                        text = ''.join((t.text or '') for t in tc.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t')).strip()
                        row.append(text)
                    if any(c.strip() for c in row):
                        rows.append(row)
                normalized = _normalize_rows(rows)
                if normalized:
                    table_id = f"pptx_s{slide_idx}_t{tbl_idx}"
                    tables.append(_build_table(table_id, "pptx", normalized))
    return tables


def _extract_pdf_tables(raw: bytes) -> list[ExtractedTable] | tuple[str, str]:
    if b"/Encrypt" in raw:
        return ("암호화", "암호화된 PDF는 텍스트 추출이 제한됩니다.")

    if b"/Subtype /Image" in raw and b"BT" not in raw:
        return ("스캔 이미지", "스캔 이미지 기반 PDF로 감지되어 OCR 없이는 표 추출이 어렵습니다.")

    text = raw.decode("latin-1", errors="ignore")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates: list[list[str]] = []
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif line.count(",") >= 2:
            parts = [p.strip() for p in line.split(",")]
        else:
            continue
        if len(parts) >= 2:
            candidates.append(parts)

    if not candidates:
        return ("표 없음", "PDF에서 테이블 형태 텍스트를 찾지 못했습니다.")

    normalized = _normalize_rows(candidates)
    if not normalized:
        return ("표 없음", "PDF 테이블 후보를 정규화하지 못했습니다.")
    return [_build_table("pdf_table_1", "pdf", normalized)]


def _normalize_rows(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return []
    width = max(len(r) for r in rows)
    if width == 0:
        return []
    normalized = [r + [""] * (width - len(r)) for r in rows]
    if not any(any(c.strip() for c in r) for r in normalized):
        return []
    return normalized


def _estimate_header(row: list[str]) -> bool:
    filled = [c for c in row if c.strip()]
    if not filled:
        return False
    numeric_like = 0
    for cell in filled:
        v = cell.strip().replace(",", "")
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", v):
            numeric_like += 1
    unique_ratio = len(set(filled)) / len(filled)
    numeric_ratio = numeric_like / len(filled)
    return unique_ratio >= 0.8 and numeric_ratio <= 0.4


def _calc_missing_ratio(rows: list[list[str]]) -> float:
    if not rows:
        return 1.0
    total = len(rows) * max(len(r) for r in rows)
    if total == 0:
        return 1.0
    missing = sum(1 for row in rows for cell in row if not str(cell).strip())
    return missing / total


def _calc_confidence(row_count: int, col_count: int, header_inferred: bool, missing_ratio: float) -> float:
    row_factor = min(row_count / 8.0, 1.0)
    col_factor = min(col_count / 6.0, 1.0)
    header_bonus = 1.0 if header_inferred else 0.55
    missing_penalty = max(0.0, 1.0 - min(missing_ratio, 1.0))
    score = (0.3 * row_factor) + (0.25 * col_factor) + (0.25 * header_bonus) + (0.2 * missing_penalty)
    return max(0.0, min(score, 1.0))


def _build_table(table_id: str, source: str, rows: list[list[str]]) -> ExtractedTable:
    header_inferred = _estimate_header(rows[0]) if rows else False
    missing_ratio = _calc_missing_ratio(rows)
    confidence = _calc_confidence(len(rows), max((len(r) for r in rows), default=0), header_inferred, missing_ratio)
    return ExtractedTable(
        table_id=table_id,
        source=source,
        rows=rows,
        header_inferred=header_inferred,
        missing_ratio=missing_ratio,
        confidence=confidence,
    )
