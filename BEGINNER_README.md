# 왕초보용 실행 가이드 A to Z (VSCode + uv + BitNet CSV Analyzer)

이 문서는 **완전 처음부터** 기준입니다.
요청하신 대로 **VSCode에서 폴더 만드는 단계부터**, **uv 가상환경 생성/불러오기**, **터미널에서 먼저 할 것**, **다음 진행 스텝**까지 한 번에 정리했습니다.

---

## A. 시작 전에 딱 3가지만 확인

1. VSCode 설치
2. Git 설치
3. Python 3.12.12 설치(이미 사용 중이면 그대로 OK)

확인 명령(터미널):
```bash
python --version
git --version
```

---

## B. VSCode에서 작업 폴더 만들기

1) VSCode 실행
2) 상단 메뉴 `File` → `Open Folder...`
3) 원하는 위치에 새 폴더 생성 (예: `First_two`)
4) 그 폴더를 VSCode로 열기

> 이미 저장소가 있으면, 기존 폴더를 열어도 됩니다.

---

## C. VSCode 터미널 먼저 열기 (중요)

1) VSCode에서 `Terminal` → `New Terminal`
2) 아래 명령으로 현재 위치 확인

```bash
pwd
```

출력이 프로젝트 폴더(예: `.../First_two`)인지 먼저 확인하세요.

---

## D. 저장소 가져오기(처음 1회)

### 방법 1) 빈 폴더에서 바로 clone
```bash
git clone <YOUR_REPO_URL> .
```

### 방법 2) 이미 clone 되어 있으면
```bash
git pull
```

---

## E. uv 설치 확인 + 가상환경 만들기

요청하신 uv 기준으로 진행합니다.

1) uv 설치 확인
```bash
uv --version
```

2) 가상환경 생성 (`.venv`)
```bash
uv venv .venv
```

3) 가상환경 불러오기(활성화)

Linux/macOS:
```bash
source .venv/bin/activate
```

Windows PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

4) 정상 활성화 확인
```bash
python --version
which python
```

> 프롬프트 앞에 `(.venv)`가 보이면 정상입니다.

---

## F. 패키지 설치 (uv 환경에서)

가상환경이 활성화된 상태에서 실행:

```bash
uv pip install -e . --no-build-isolation
```

설치 확인:
```bash
bitnet-analyze --help
```

---

## G. Ollama 준비 (BitNet 실행용)

1) 설치
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2) 서버 실행 (별도 터미널 탭/창)
```bash
ollama serve
```

3) 모델 받기
```bash
ollama pull bitnet:latest
```

4) 모델 확인
```bash
ollama list
```

---

## H. 가장 먼저 터미널에서 해야 할 최소 순서 (핵심 요약)

아래 순서 그대로 하면 됩니다.

```bash
# 1) 폴더 확인
pwd

# 2) uv 가상환경 생성/활성화
uv venv .venv
source .venv/bin/activate

# 3) 프로젝트 설치
uv pip install -e . --no-build-isolation

# 4) CLI 확인
bitnet-analyze --help

# 5) (별도 터미널) Ollama 서버
ollama serve

# 6) 모델 다운로드
ollama pull bitnet:latest
```

---

## I. CLI로 A to Z 실행 (처음 성공 루트)

1) 샘플 CSV 만들기
```bash
cat > sample.csv <<'CSV'
id,amount,category
1,120,A
2,80,B
3,300,A
CSV
```

2) 분석 payload 만들기
```bash
bitnet-analyze analyze sample.csv --question "핵심 인사이트 3개 알려줘" --out payload.json
```

3) 결과 확인
```bash
cat payload.json
```

4) BitNet까지 바로 실행(선택)
```bash
bitnet-analyze analyze sample.csv --question "핵심 인사이트 3개 알려줘" --model bitnet:latest
```

---

## J. 웹 UI로 실행하기 (VSCode 사용자에게 추천)

1) UI 서버 실행
```bash
bitnet-analyze ui --host 127.0.0.1 --port 8765
```

2) 브라우저 접속
- `http://127.0.0.1:8765`

3) 화면에서 순서
- CSV 업로드 또는 붙여넣기
- 질문 입력
- `1) 분석`
- 모델 태그 입력(`bitnet:latest`)
- `2) BitNet 실행`

---

## K. 테스트/검증 (문제 생기기 전에 미리)

```bash
pytest -q
python -m bitnet_tools.cli --help
```

### 2) 모델 실행이 오래 걸림
- 질문 길이/CSV 크기를 줄이기
- 먼저 `analyze`만 실행해 payload 생성이 되는지 분리 확인

### 3) 모델 실행 실패
- `ollama serve`가 켜져 있는지 확인
- 모델 태그 오타 확인 (`ollama list`)

### 2) `bitnet-analyze: command not found`
- 가상환경 미활성화일 가능성 큼
```bash
source .venv/bin/activate
```
- 그리고 재설치
```bash
uv pip install -e . --no-build-isolation
```

### 3) 모델 실행 실패
- Ollama 서버 상태 확인
```bash
ollama list
```
- 서버가 꺼져 있으면 다시 실행
```bash
ollama serve
```

### 4) 응답이 너무 느림
- CSV를 작게
- 질문을 짧게
- 먼저 `analyze`만 실행해서 payload 생성 확인

---

## M. 매번 작업 시작 루틴 (실전)

프로젝트 다시 열 때는 보통 이 4개만 하면 됩니다.

```bash
cd <YOUR_PROJECT_PATH>/First_two
source .venv/bin/activate
uv pip install -e . --no-build-isolation
bitnet-analyze --help
```

그리고 필요 시:
```bash
ollama serve
bitnet-analyze ui --host 127.0.0.1 --port 8765
```

---

## N. A to Z 완료 체크리스트

- [ ] VSCode에서 프로젝트 폴더 열기 완료
- [ ] `uv venv .venv` 완료
- [ ] `source .venv/bin/activate` 완료
- [ ] `uv pip install -e . --no-build-isolation` 완료
- [ ] `bitnet-analyze --help` 확인
- [ ] `sample.csv` 분석 성공
- [ ] `payload.json` 생성 확인
- [ ] `http://127.0.0.1:8765` 접속 확인
- [ ] UI에서 BitNet 응답 확인

여기까지 되면 진짜 A to Z 끝입니다.
