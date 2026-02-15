# Online tool/reference collection

인터넷이 열려 있는 턴에서 Python wheelhouse, 모델, 런타임 자산을 **공식 경로**에서만 수집하기 위한 작업 문서.

## Source catalog
- `resources/online_sources.json`
  - `wheelhouse`: `name` + `version`(고정)으로 수집할 Python 패키지 목록
  - `model_assets`: 모델 관련 자산 URL + `official_base`
  - `runtime_assets`: 런타임 자산 URL + `official_base`

## 수집/설치 소스 거버넌스 규칙

### 1) 허용 소스(Allowlist) 정책
- 소스는 **공식 저장소(official repository)** 만 허용한다.
- 공식 저장소 정의:
  - 패키지: PyPI/npm/Maven Central 등 해당 생태계의 1차 레지스트리
  - 모델: 모델 제작자/조직의 공식 배포 채널(예: 공식 Hugging Face org, 공식 릴리스 페이지)
  - 도구(바이너리/앱): 공급자 공식 릴리스 저장소(예: vendor GitHub Releases, 공식 다운로드 페이지)
- 미러/개인 포크/출처 미상 아카이브는 기본 차단하며, 예외 승인 없이는 사용하지 않는다.

### 2) 차단 목록(Blocklist) 정책
아래 조건 중 하나라도 만족하면 수집·설치를 차단 목록으로 분류한다.
- `license`가 불명(unknown) 또는 누락
- 재배포 불가(내부 배포 정책상 금지 라이선스 포함)
- 고위험 취약점(High/Critical CVE) 포함

차단 목록에 들어간 항목은 즉시 설치 대상에서 제외하고, 필요 시 `deferred_install_manifest.json`으로 이관한다.

### 3) 메타데이터 필드 고정(패키지/모델/도구 공통)
패키지(package), 모델(model), 도구(tool)는 아래 기준 필드를 **동일 키 이름으로 고정**한다.
- `name`
- `version`
- `source`
- `license`
- `sha256`

권장: 타입 구분을 위해 `asset_type`(`package|model|tool`)를 추가할 수 있으나, 상기 5개 필드는 필수로 유지한다.

### 4) 누락 가능 항목 이관 정책 (`deferred_install_manifest.json`)
- 네트워크 오류, 접근 제한, 검증 지연, 정책 검토 대기 등으로 즉시 설치가 불가능한 항목은 `deferred_install_manifest.json`으로 이관한다.
- 이관 시 최소 기록 단위:
  - 고정 필드 5개(`name, version, source, license, sha256`)
  - `asset_type`
  - `defer_reason`
  - `deferred_at`(ISO-8601 UTC)
  - `status`(`deferred|reviewing|approved|rejected|installed`)
- 설치 파이프라인은 `status=approved` 항목만 재시도 대상으로 사용한다.

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
