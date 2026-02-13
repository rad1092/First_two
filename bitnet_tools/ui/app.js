const csvFile = document.getElementById('csvFile');
const csvText = document.getElementById('csvText');
const question = document.getElementById('question');
const model = document.getElementById('model');
const timeout = document.getElementById('timeout');
const analyzeBtn = document.getElementById('analyzeBtn');
const runBtn = document.getElementById('runBtn');
const statusEl = document.getElementById('status');
const summary = document.getElementById('summary');
const prompt = document.getElementById('prompt');
const answer = document.getElementById('answer');

let latestPrompt = '';

function setStatus(msg) {
  statusEl.textContent = msg;
}

async function safeJson(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`서버 응답이 JSON 형식이 아닙니다: ${text.slice(0, 120)}`);
  }
}

csvFile.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  csvText.value = await file.text();
  setStatus(`CSV 파일 로드 완료: ${file.name}`);
});

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    question.value = chip.dataset.q;
  });
});

document.getElementById('copyPrompt').addEventListener('click', async () => {
  if (!latestPrompt) {
    setStatus('복사할 프롬프트가 없습니다. 먼저 분석을 실행하세요.');
    return;
  }
  await navigator.clipboard.writeText(latestPrompt);
  setStatus('프롬프트를 클립보드에 복사했습니다.');
});

analyzeBtn.addEventListener('click', async () => {
  setStatus('분석 중...');
  summary.textContent = '분석 중...';

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        csv_text: csvText.value,
        question: question.value,
      }),
    });
    const data = await safeJson(res);

    if (!res.ok) {
      summary.textContent = data.error || 'error';
      setStatus(`분석 실패: ${data.error || '알 수 없는 오류'}`);
      return;
    }

    latestPrompt = data.prompt;
    summary.textContent = JSON.stringify(data.summary, null, 2);
    prompt.textContent = data.prompt;
    answer.textContent = '';
    setStatus('분석 완료');
  } catch (err) {
    summary.textContent = String(err.message || err);
    setStatus(`분석 실패: ${String(err.message || err)}`);
  }
});

runBtn.addEventListener('click', async () => {
  if (!latestPrompt) {
    answer.textContent = '먼저 분석을 실행해 프롬프트를 생성하세요.';
    setStatus('실행 실패: 먼저 분석을 실행하세요.');
    return;
  }
  if (!model.value.trim()) {
    answer.textContent = '모델 태그를 입력하세요. 예: bitnet:latest';
    setStatus('실행 실패: 모델 태그가 비어 있습니다.');
    return;
  }

  setStatus('BitNet 실행 중...');
  answer.textContent = 'BitNet 실행 중...';

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: model.value.trim(),
        prompt: latestPrompt,
        timeout: Number(timeout.value || 120),
      }),
    });
    const data = await safeJson(res);
    answer.textContent = res.ok ? data.answer : (data.error || 'error');
    setStatus(res.ok ? 'BitNet 실행 완료' : `실행 실패: ${data.error || '알 수 없는 오류'}`);
  } catch (err) {
    answer.textContent = String(err.message || err);
    setStatus(`실행 실패: ${String(err.message || err)}`);
  }
});
