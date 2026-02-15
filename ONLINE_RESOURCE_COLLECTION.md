# Online tool/reference collection

인터넷이 열려 있는 턴에서 Python wheelhouse, 모델, 런타임 자산을 **공식 경로**에서만 수집하기 위한 작업 문서.

## Source catalog
- `resources/online_sources.json`
  - `wheelhouse`: `name` + `version`(고정)으로 수집할 Python 패키지 목록
  - `model_assets`: 모델 관련 자산 URL + `official_base`
  - `runtime_assets`: 런타임 자산 URL + `official_base`

## Collector
- `scripts/collect_online_assets.py`
  - wheelhouse 다운로드 (`.online_assets/wheelhouse`)
    - PyPI 공식 인덱스(`https://pypi.org/simple`)로만 다운로드
  - 모델 자산 다운로드 (`.online_assets/models`)
  - 런타임 자산 다운로드 (`.online_assets/runtime`)
  - SHA256 + 버전 고정 정보를 담은 manifest 생성
    - `.online_assets/meta/collection_manifest.json`
  - 수집 리포트 생성
    - `.online_assets/meta/collection_report.json`
    - 설치 가능(`installable`) / 불가(`blocked_or_failed`) / 보류(`defer`) 분리

## Run
```bash
python scripts/collect_online_assets.py
```
