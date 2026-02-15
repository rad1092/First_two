const csvFile = document.getElementById('csvFile');
const csvText = document.getElementById('csvText');
const question = document.getElementById('question');
const model = document.getElementById('model');
const analyzeBtn = document.getElementById('analyzeBtn');
const quickAnalyzeBtn = document.getElementById('quickAnalyzeBtn');
const runBtn = document.getElementById('runBtn');
const summary = document.getElementById('summary');
const prompt = document.getElementById('prompt');
const answer = document.getElementById('answer');
const statusBox = document.getElementById('statusBox');
const modeGuide = document.getElementById('modeGuide');

const multiCsvFiles = document.getElementById('multiCsvFiles');
const groupColumn = document.getElementById('groupColumn');
const targetColumn = document.getElementById('targetColumn');
const multiAnalyzeBtn = document.getElementById('multiAnalyzeBtn');
const dashboardJson = document.getElementById('dashboardJson');
const dashboardCards = document.getElementById('dashboardCards');
const dashboardInsights = document.getElementById('dashboardInsights');

let latestPrompt = '';

function setStatus(message) {
  if (statusBox) statusBox.textContent = message;
}

function renderModeGuide(mode) {
  if (!modeGuide) return;
  const steps = mode === 'quick'
    ? [
        '1) CSV 파일을 선택하거나 CSV 텍스트를 붙여넣기',
        '2) 요청 문장을 확인(칩 버튼으로 빠르게 선택 가능)',
        '3) "바로 분석" 클릭 후 요약 결과 확인',
      ]
    : [
        '1) 기본 분석을 먼저 실행해 프롬프트 생성',
        '2) 필요 시 모델 태그 입력 후 BitNet 실행',
        '3) 멀티 CSV/대시보드 고급 기능 활용',
      ];
  modeGuide.innerHTML = steps.map((step) => `<li>${step}</li>`).join('');
}

function setMode(mode) {
  const advancedOnly = document.querySelectorAll('.advanced-only');
  advancedOnly.forEach((el) => {
    el.style.display = mode === 'advanced' ? '' : 'none';
  });

  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  if (mode === 'quick') {
    setStatus('빠른 시작: 입력 → 요청 확인 → 바로 분석');
  } else {
    setStatus('고급 모드: 모델 실행/멀티 분석/대시보드를 사용할 수 있습니다.');
  }

  renderModeGuide(mode);
}

document.querySelectorAll('.mode-btn').forEach((btn) => {
  btn.addEventListener('click', () => setMode(btn.dataset.mode));
});

if (csvFile) {
  csvFile.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    csvText.value = await file.text();
    setStatus(`파일 로드 완료: ${file.name}`);
  });
}

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    question.value = chip.dataset.q;
    if (quickAnalyzeBtn) quickAnalyzeBtn.focus();
  });
});

const copyPromptBtn = document.getElementById('copyPrompt');
if (copyPromptBtn) {
  copyPromptBtn.addEventListener('click', async () => {
    if (!latestPrompt) return;
    await navigator.clipboard.writeText(latestPrompt);
    setStatus('프롬프트가 복사되었습니다.');
  });
}

async function runAnalyze() {
  setStatus('분석 중...');
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
    setStatus(`분석 실패: ${data.error || 'error'}`);
    return;
  }

  latestPrompt = data.prompt;
  summary.textContent = JSON.stringify(data.summary, null, 2);
  if (prompt) prompt.textContent = data.prompt;
  if (answer) answer.textContent = '';
  setStatus('분석 완료');
}

if (analyzeBtn) analyzeBtn.addEventListener('click', runAnalyze);
if (quickAnalyzeBtn) quickAnalyzeBtn.addEventListener('click', runAnalyze);

if (runBtn) {
  runBtn.addEventListener('click', async () => {
    if (!latestPrompt) {
      if (answer) answer.textContent = '먼저 분석을 실행해 프롬프트를 생성하세요.';
      setStatus('모델 실행 중단: 프롬프트가 없습니다.');
      return;
    }
    if (!model.value.trim()) {
      if (answer) answer.textContent = '모델 태그를 입력하세요. 예: bitnet:latest';
      setStatus('모델 실행 중단: 모델 태그가 없습니다.');
      return;
    }

    setStatus('BitNet 실행 중...');
    if (answer) answer.textContent = 'BitNet 실행 중...';
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: model.value.trim(), prompt: latestPrompt }),
    });
    const data = await res.json();
    if (answer) answer.textContent = res.ok ? data.answer : (data.error || 'error');
    setStatus(res.ok ? 'BitNet 실행 완료' : `BitNet 실행 실패: ${data.error || 'error'}`);
  });
}

const renderDashboardBtn = document.getElementById('renderDashboardBtn');
if (renderDashboardBtn) {
  renderDashboardBtn.addEventListener('click', () => {
    dashboardCards.innerHTML = '';
    dashboardInsights.textContent = '';

    let parsed;
    try {
      parsed = JSON.parse(dashboardJson.value || '{}');
    } catch {
      dashboardInsights.textContent = 'JSON 형식이 올바르지 않습니다.';
      setStatus('대시보드 렌더 실패: JSON 형식 오류');
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
    setStatus('대시보드 렌더 완료');
  });
}

if (multiAnalyzeBtn) {
  multiAnalyzeBtn.addEventListener('click', async () => {
    const files = [...(multiCsvFiles.files || [])];
    if (!files.length) {
      dashboardInsights.textContent = '멀티 CSV 파일을 먼저 선택하세요.';
      setStatus('멀티 분석 중단: 파일 없음');
      return;
    }

    setStatus('멀티 분석 중...');
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
      setStatus(`멀티 분석 실패: ${data.error || 'error'}`);
      return;
    }

    dashboardJson.value = JSON.stringify(data, null, 2);
    renderDashboardBtn.click();
    setStatus('멀티 분석 완료');
  });
}

setMode('quick');
