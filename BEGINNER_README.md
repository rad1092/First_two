# 왕초보용 실행 가이드 A to Z (BitNet CSV Analyzer)

이 문서는 **혼자 쓰는 개인용** 기준으로, 처음부터 끝까지 그대로 따라하면
`CSV 분석 -> BitNet 실행`이 되는 최소 경로를 안내합니다.

---

## A. 준비물 확인

1. 운영체제: Linux / macOS / Windows(WSL 가능)
2. Python 3.10 이상
3. Ollama 설치 가능 환경
4. 터미널 사용 가능

확인 명령:
```bash
python --version
```

---

## B. 저장소 받기

```bash
git clone <YOUR_REPO_URL>
cd First_two
```

---

## C. 가상환경 만들기

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## D. 패키지 설치

```bash
pip install -e .
```

설치 확인:
```bash
bitnet-analyze --help
bitnet-analyze doctor
```

---

## E. Ollama 준비

1) 설치
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2) 서버 실행 (별도 터미널)
```bash
ollama serve
```

3) BitNet 모델 받기 (예시)
```bash
ollama pull bitnet:latest
```

---

## F. CLI로 먼저 성공하기 (웹 없이, 가장 추천)

1) 샘플 CSV 만들기
```bash
cat > sample.csv <<'CSV'
id,amount,category
1,120,A
2,80,B
3,300,A
CSV
```

2) 초간단 실행(프리셋 질문 자동 사용)
```bash
bitnet-analyze quickstart --csv sample.csv --preset insight --out payload.json
```

3) 또는 질문 직접 지정 실행
```bash
bitnet-analyze analyze sample.csv --question "핵심 인사이트 3개 알려줘" --out payload.json
```

4) 결과 확인
```bash
cat payload.json
```

5) 모델까지 바로 실행(선택)
```bash
bitnet-analyze analyze sample.csv --question "핵심 인사이트 3개 알려줘" --model bitnet:latest --timeout 120
```

---

## G. 웹 UI로 실행하기 (선택 사항)

1) 웹 UI 실행
```bash
bitnet-analyze ui --host 127.0.0.1 --port 8765
```

2) 브라우저 접속
- `http://127.0.0.1:8765`

3) 화면에서 순서대로
- CSV 파일 업로드 또는 붙여넣기
- 질문 입력(또는 프리셋 버튼)
- `1) 분석`
- 모델 태그 입력(`bitnet:latest`)
- `2) BitNet 실행`

---

## H. 자주 나는 오류와 해결

### 1) `analysis error: CSV file not found`
- 파일 경로가 잘못됨
- `pwd`, `ls`로 현재 위치/파일명 다시 확인

### 2) `timeout must be an integer`
- 웹에서 timeout 칸에 숫자만 입력

### 3) `ollama run timed out`
- timeout 늘리기(예: 180)
- 질문 길이/CSV 크기 줄이기

### 4) 모델 실행 실패
- `ollama serve`가 켜져 있는지 확인
- 모델 태그 오타 확인 (`ollama list`)

---

## I. 실전 사용 팁

- 처음엔 작은 CSV(수백~수천행)로 시작
- 질문은 짧고 명확하게
- 응답 품질이 흔들리면:
  - 질문 단순화
  - 컬럼 설명을 질문에 같이 넣기

---

## J. 업데이트/재실행 루틴

코드 최신 반영:
```bash
git pull
pip install -e .
python -m pytest -q
```

문제 없으면 다시:
```bash
bitnet-analyze ui --host 127.0.0.1 --port 8765
```

---

## K. 최소 성공 체크리스트

- [ ] `bitnet-analyze --help` 실행됨
- [ ] `bitnet-analyze quickstart --csv sample.csv --preset insight --out payload.json` 실행됨
- [ ] `payload.json` 생성됨
- [ ] `http://127.0.0.1:8765` 접속됨
- [ ] UI에서 BitNet 응답 받음

여기까지 되면 A to Z 완료입니다.
