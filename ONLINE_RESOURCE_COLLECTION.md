# Online tool/reference collection

인터넷이 열려 있는 턴에서 필요한 툴 패키지(wheel)와 UI/접근성 레퍼런스를 로컬로 저장하기 위한 작업 기록 문서.

## Source catalog
- `resources/online_sources.json`
  - `tool_packages`: 다운로드 대상 pip 패키지 목록
  - `reference_urls`: 저장 대상 웹 레퍼런스 URL 목록

## Collector
- `scripts/collect_online_assets.py`
  - pip wheel 다운로드 시도 (`.online_assets/wheels`)
  - 레퍼런스 HTML 다운로드 시도 (`.online_assets/references`)
  - 결과 리포트 생성 (`.online_assets/meta/collection_report.json`)

## Run
```bash
python scripts/collect_online_assets.py
```
