const csvFile = document.getElementById('csvFile');
const csvText = document.getElementById('csvText');
const question = document.getElementById('question');
const model = document.getElementById('model');
const analyzeBtn = document.getElementById('analyzeBtn');
const runBtn = document.getElementById('runBtn');
const summary = document.getElementById('summary');
const prompt = document.getElementById('prompt');
const answer = document.getElementById('answer');

let latestPrompt = '';

csvFile.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  csvText.value = await file.text();
});

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    question.value = chip.dataset.q;
  });
});

document.getElementById('copyPrompt').addEventListener('click', async () => {
  if (!latestPrompt) return;
  await navigator.clipboard.writeText(latestPrompt);
});

analyzeBtn.addEventListener('click', async () => {
  summary.textContent = '분석 중...';
  const res = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      csv_text: csvText.value,
      question: question.value,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    summary.textContent = data.error || 'error';
    return;
  }

  latestPrompt = data.prompt;
  summary.textContent = JSON.stringify(data.summary, null, 2);
  prompt.textContent = data.prompt;
  answer.textContent = '';
});

runBtn.addEventListener('click', async () => {
  if (!latestPrompt) {
    answer.textContent = '먼저 분석을 실행해 프롬프트를 생성하세요.';
    return;
  }
  if (!model.value.trim()) {
    answer.textContent = '모델 태그를 입력하세요. 예: bitnet:latest';
    return;
  }

  answer.textContent = 'BitNet 실행 중...';
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: model.value.trim(), prompt: latestPrompt }),
  });
  const data = await res.json();
  answer.textContent = res.ok ? data.answer : (data.error || 'error');
});
