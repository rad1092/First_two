# Baseline plan (0단계)

이 문서는 개선 작업 전/후 비교를 위한 기준선 고정 절차를 정의한다.

## 고정 기준
- 테스트 전체 통과 여부 (`pytest -q`)
- 대표 입력 CSV 3종 결과 일관성
  - `tests/fixtures/small_numeric.csv`
  - `tests/fixtures/mixed_formats.csv`
  - `tests/fixtures/missing_heavy.csv`
- 핵심 요약 결과 스냅샷
  - row_count, column_count
  - dtypes
  - missing_counts
  - numeric_stats

## 운영 방법
1. 개선 전 baseline 테스트를 실행해 현재 결과를 확인
2. 개선 작업 후 동일 테스트를 재실행
3. 의도하지 않은 필드 변경이 있으면 원인 분석 후 수정
