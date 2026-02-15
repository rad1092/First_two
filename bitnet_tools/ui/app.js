const csvFile = document.getElementById('csvFile');
const csvText = document.getElementById('csvText');
const question = document.getElementById('question');
const model = document.getElementById('model');
const analyzeBtn = document.getElementById('analyzeBtn');
const runBtn = document.getElementById('runBtn');
const summary = document.getElementById('summary');
const prompt = document.getElementById('prompt');
const answer = document.getElementById('answer');

const multiCsvFiles = document.getElementById('multiCsvFiles');
const groupColumn = document.getElementById('groupColumn');
const targetColumn = document.getElementById('targetColumn');
const multiAnalyzeBtn = document.getElementById('multiAnalyzeBtn');
const dashboardJson = document.getElementById('dashboardJson');
const dashboardCards = document.getElementById('dashboardCards');
const dashboardInsights = document.getElementById('dashboardInsights');

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

document.getElementById('renderDashboardBtn').addEventListener('click', () => {
  dashboardCards.innerHTML = '';
  dashboardInsights.textContent = '';

  let parsed;
  try {
    parsed = JSON.parse(dashboardJson.value || '{}');
  } catch {
    dashboardInsights.textContent = 'JSON 형식이 올바르지 않습니다.';
    return;
  }

  const cardItems = [
    ['파일 수', parsed.file_count ?? '-'],
    ['총 행 수', parsed.total_row_count ?? '-'],
    ['공통 컬럼 수', (parsed.shared_columns || []).length],
    ['인사이트 수', (parsed.insights || []).length],
  ];

  cardItems.forEach(([k, v]) => {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<strong>${k}</strong><span>${v}</span>`;
    dashboardCards.appendChild(div);
  });

  const insights = parsed.insights || [];
  dashboardInsights.textContent = insights.length
    ? insights.map((x, i) => `${i + 1}. ${x}`).join('\n')
    : '인사이트 항목이 없습니다.';
});


multiAnalyzeBtn.addEventListener('click', async () => {
  const files = [...(multiCsvFiles.files || [])];
  if (!files.length) {
    dashboardInsights.textContent = '멀티 CSV 파일을 먼저 선택하세요.';
    return;
  }

  dashboardInsights.textContent = '멀티 분석 중...';
  const payloadFiles = [];
  for (const f of files) {
    payloadFiles.push({ name: f.name, csv_text: await f.text() });
  }

  const res = await fetch('/api/multi-analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: payloadFiles,
      question: question.value,
      group_column: groupColumn.value.trim(),
      target_column: targetColumn.value.trim(),
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    dashboardInsights.textContent = data.error || 'error';
    return;
  }

  dashboardJson.value = JSON.stringify(data, null, 2);
  document.getElementById('renderDashboardBtn').click();
});
