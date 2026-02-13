# BitNet 로컬 분석 환경 시작 가이드 (개인용)

> 목표: **BitNet 중심(웬만하면 BitNet만 사용)**으로 로컬 LLM 환경을 빠르게 띄우고,
> CSV/텍스트 요약 + 간단한 질의응답 + 분석 보조까지 바로 시작할 수 있게 구성합니다.

---

## 0) 이번 문서에서 바로 할 일

1. Ollama 설치 및 실행
2. BitNet 모델 1개 Pull
3. CLI로 동작 확인
4. Open WebUI 연결
5. JupyterLab에서 CSV 분석 + BitNet 해석 워크플로우 구성

---

## 1) 사전 확인 (10~20분)

- OS 확인
- RAM/VRAM 확인
- 디스크 여유 최소 30GB
- 목표를 “최고 성능”보다 “안정 동작”으로 설정

권장 기준:
- RAM 16GB 이하: BitNet의 작은 파라미터 모델 우선
- RAM 32GB 이상: 컨텍스트/토큰 여유를 조금 더 확대
- GPU가 없으면 컨텍스트를 짧게 유지(2048~4096)

---

## 2) Step-by-step 시작 절차 (BitNet 우선)

### Step 1. Ollama 설치
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
```

### Step 2. BitNet 모델 다운로드

아래 `bitnet-model-tag`는 실제 사용 가능한 태그로 바꿔 입력하세요.

```bash
ollama pull <bitnet-model-tag>
```

예:
```bash
ollama pull bitnet:latest
```

> 참고: 태그명은 시점/배포처에 따라 달라질 수 있으니 `ollama search bitnet` 또는 배포 페이지의 최신 태그를 우선 확인하세요.

### Step 3. CLI 동작 확인
```bash
ollama run <bitnet-model-tag> "다음 CSV 컬럼 설명을 5줄로 요약해줘: user_id, order_cnt, total_amount"
```

### Step 4. Open WebUI 연결 (Docker)
```bash
docker run -d \
  --name open-webui \
  -p 3000:8080 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -v open-webui:/app/backend/data \
  --restart unless-stopped \
  ghcr.io/open-webui/open-webui:main
```

접속: `http://localhost:3000`

### Step 5. JupyterLab 분석 환경
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install jupyterlab pandas matplotlib
jupyter lab
```

---

## 3) BitNet 기본 설정값 (안정성 우선)

- temperature: `0.2 ~ 0.5`
- top_p: `0.9`
- max_tokens: `512 ~ 1024`
- context: `2048 ~ 4096` (메모리 여유 있으면 확대)

시스템 프롬프트 권장:
- 모르면 모른다고 답하기
- 추정/사실 분리하기
- 표/수치 해석 시 근거 컬럼명을 명시하기

---

## 4) 데이터 분석 최소 워크플로우 (BitNet only)

1. JupyterLab에서 CSV 로딩
2. pandas로 결측/타입/기초통계 계산
3. 계산 결과를 텍스트로 정리
4. 정리된 텍스트를 BitNet에 입력해 인사이트/한계/추가 데이터 제안 받기

예시 프롬프트:

```text
너는 데이터 분석 보조자야.
아래 통계를 바탕으로
1) 핵심 인사이트 3개
2) 이상치 의심 포인트 2개
3) 추가로 필요한 데이터 3개
를 간결하게 제시해줘.
```

응답 형식 템플릿(권장):
- 핵심요약
- 근거
- 한계
- 다음행동

---

## 5) 운영 안정화 체크리스트

- [ ] BitNet 모델 1~2개만 유지
- [ ] 프롬프트 템플릿은 검증된 것만 유지
- [ ] 느릴 때: context/max_tokens 감소
- [ ] 품질 흔들릴 때: temperature 하향
- [ ] 메모리 부족 시: 더 작은 BitNet 모델로 전환

백업:
- Open WebUI 데이터 볼륨 주기적 백업
- Jupyter 노트북/원본 CSV 분리 보관

---

## 6) 지금 바로 실행할 최소 커맨드 모음

```bash
# 1) Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve

# 2) BitNet pull
ollama pull <bitnet-model-tag>

# 3) 테스트
ollama run <bitnet-model-tag> "샘플 매출 데이터를 요약해줘"
```

필요하면 다음 단계에서 환경(OS/CPU/RAM/GPU)에 맞춰
- 정확한 BitNet 태그
- 권장 context/max_tokens
- Open WebUI 프리셋 프롬프트 3종
까지 바로 좁혀서 제안할 수 있습니다.

---

## 7) GitHub 반영(적용) 절차

로컬에서 문서/설정을 수정한 뒤 아래 순서로 GitHub에 반영합니다.

```bash
git add README.md
git commit -m "docs: update BitNet setup guide"
git push origin <branch-name>
```

PR 생성 시 체크 포인트:
- 변경 목적(왜 바꿨는지) 1~2줄
- 실행/검증한 명령어
- 사용자 관점에서 달라진 점(BitNet 우선 흐름, 실행 순서 명확화 등)

