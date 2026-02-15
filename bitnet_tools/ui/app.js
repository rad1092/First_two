const csvFile = document.getElementById('csvFile');
const csvText = document.getElementById('csvText');
const question = document.getElementById('question');
const intent = document.getElementById('intent');
const intentActions = document.getElementById('intentActions');
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
let currentMode = 'quick';
const requestState = { question: '', intent: '', route: 'analyze' };

function setStatus(message) {
  if (statusBox) statusBox.textContent = message;
}

function saveRequestState(route) {
  requestState.question = question?.value || '';
  requestState.intent = intent?.value || '';
  requestState.route = route;
}

function classifyIntent(intentText) {
  const text = String(intentText || '').toLowerCase().trim();
  if (!text) return { route: 'analyze', reason: 'empty_intent' };

  const hasMulti = /(멀티|여러|복수|비교|비교분석|multi)/.test(text);
  const hasVisual = /(시각화|차트|그래프|plot|대시보드)/.test(text);
  const hasAnalyze = /(분석|요약|인사이트|이상치|진단|핵심)/.test(text);

  if (hasMulti) return { route: 'multi', reason: 'keyword_multi' };
  if (hasVisual) return { route: 'visualize', reason: 'keyword_visualize' };
  if (hasAnalyze) return { route: 'analyze', reason: 'keyword_analyze' };
  return { route: 'unknown', reason: 'no_keyword_match' };
}

function renderIntentActions(actions = []) {
  if (!intentActions) return;
  intentActions.innerHTML = '';
  if (!actions.length) return;

  actions.forEach((item) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.textContent = item.label;
    btn.addEventListener('click', item.onClick);
    intentActions.appendChild(btn);
  });
}

function showFallbackIntentActions() {
  renderIntentActions([
    {
      label: '기본 분석 실행',
      onClick: () => {
        setMode('quick');
        if (quickAnalyzeBtn) quickAnalyzeBtn.focus();
        setStatus('추천 액션: 기본 분석 실행');
      },
    },
    {
      label: '멀티 분석으로 전환',
      onClick: () => {
        setMode('advanced');
        if (multiCsvFiles) multiCsvFiles.focus();
        setStatus('추천 액션: 멀티 분석 파일을 선택하세요.');
      },
    },
    {
      label: '시각화 안내 보기',
      onClick: () => {
        setMode('advanced');
        if (dashboardJson) dashboardJson.focus();
        setStatus('추천 액션: 멀티 분석 결과 JSON을 붙여넣고 대시보드를 렌더링하세요.');
      },
    },
  ]);
}

function renderModeGuide(mode) {
  if (!modeGuide) return;
  const steps = mode === 'quick'
    ? [
        '1) CSV 파일을 선택하거나 CSV 텍스트를 붙여넣기',
        '2) 질문(question)과 작업 요청(intent) 입력',
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
  currentMode = mode;
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

document.querySelectorAll('.chip[data-q]').forEach((chip) => {
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

async function runMultiAnalyze() {
  const files = [...(multiCsvFiles?.files || [])];
  if (!files.length) {
    dashboardInsights.textContent = '멀티 CSV 파일을 먼저 선택하세요.';
    setStatus('멀티 분석 중단: 파일 없음');
    return false;
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
    return false;
  }

  dashboardJson.value = JSON.stringify(data, null, 2);
  const renderDashboardBtn = document.getElementById('renderDashboardBtn');
  if (renderDashboardBtn) renderDashboardBtn.click();
  setStatus('멀티 분석 완료');
  return true;
}

async function runByIntent() {
  renderIntentActions([]);
  const intentResult = classifyIntent(intent?.value || '');
  saveRequestState(intentResult.route);

  if (intentResult.route === 'analyze') {
    return runAnalyze();
  }

  if (intentResult.route === 'multi') {
    setMode('advanced');
    const done = await runMultiAnalyze();
    if (!done) {
      renderIntentActions([
        {
          label: '멀티 파일 선택하기',
          onClick: () => multiCsvFiles?.focus(),
        },
        {
          label: '기본 분석으로 진행',
          onClick: () => {
            setMode('quick');
            runAnalyze();
          },
        },
      ]);
      setStatus('의도 라우팅: 멀티 비교 우선으로 판단했습니다. 파일 선택 후 다시 실행하세요.');
    } else {
      setStatus('의도 라우팅: 멀티 비교 우선 작업을 완료했습니다.');
    }
    return;
  }

  if (intentResult.route === 'visualize') {
    setMode('advanced');
    renderIntentActions([
      {
        label: '대시보드 JSON 입력으로 이동',
        onClick: () => dashboardJson?.focus(),
      },
      {
        label: '먼저 멀티 분석 실행',
        onClick: () => multiAnalyzeBtn?.focus(),
      },
    ]);
    setStatus('의도 라우팅: 시각화 안내 우선으로 판단했습니다. 대시보드/멀티 분석 경로를 이용하세요.');
    return;
  }

  showFallbackIntentActions();
  setStatus('의도 해석이 불명확합니다. 아래 추천 액션 중 하나를 선택하세요.');
}

if (analyzeBtn) analyzeBtn.addEventListener('click', runByIntent);
if (quickAnalyzeBtn) quickAnalyzeBtn.addEventListener('click', runByIntent);

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
  multiAnalyzeBtn.addEventListener('click', runMultiAnalyze);
}

if (intent) {
  intent.addEventListener('input', () => {
    if (!intent.value.trim()) {
      renderIntentActions([]);
      return;
    }
    const { route } = classifyIntent(intent.value);
    if (route === 'analyze') setStatus('의도 라우팅 후보: 분석 우선');
    else if (route === 'multi') setStatus('의도 라우팅 후보: 멀티 비교 우선');
    else if (route === 'visualize') setStatus('의도 라우팅 후보: 시각화 안내 우선');
    else setStatus('의도 라우팅 후보를 찾지 못했습니다. 실행 시 추천 액션을 제공합니다.');
  });
}

setMode(currentMode);
