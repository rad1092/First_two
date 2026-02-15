const UI = {
  csvFile: document.getElementById('csvFile'),
  csvText: document.getElementById('csvText'),
  question: document.getElementById('question'),
  intent: document.getElementById('intent'),
  intentActions: document.getElementById('intentActions'),
  model: document.getElementById('model'),
  analyzeBtn: document.getElementById('analyzeBtn'),
  quickAnalyzeBtn: document.getElementById('quickAnalyzeBtn'),
  runBtn: document.getElementById('runBtn'),
  summary: document.getElementById('summary'),
  prompt: document.getElementById('prompt'),
  answer: document.getElementById('answer'),
  statusBox: document.getElementById('statusBox'),
  modeGuide: document.getElementById('modeGuide'),
  errorUser: document.getElementById('errorUser'),
  errorDetails: document.getElementById('errorDetails'),
  errorDetailText: document.getElementById('errorDetailText'),
  multiCsvFiles: document.getElementById('multiCsvFiles'),
  groupColumn: document.getElementById('groupColumn'),
  targetColumn: document.getElementById('targetColumn'),
  multiAnalyzeBtn: document.getElementById('multiAnalyzeBtn'),
  dashboardJson: document.getElementById('dashboardJson'),
  dashboardCards: document.getElementById('dashboardCards'),
  dashboardInsights: document.getElementById('dashboardInsights'),
  renderDashboardBtn: document.getElementById('renderDashboardBtn'),
  copyPromptBtn: document.getElementById('copyPrompt'),
};

const STATUS = {
  quickReady: '빠른 시작: 입력 → 요청 확인 → 바로 분석',
  advancedReady: '고급 모드: 모델 실행/멀티 분석/대시보드를 사용할 수 있습니다.',
  analyzing: '분석 중...',
  analyzeDone: '분석 완료',
  modelRunning: 'BitNet 실행 중...',
  modelDone: 'BitNet 실행 완료',
  multiRunning: '멀티 분석 중...',
  multiDone: '멀티 분석 완료',
  dashboardDone: '대시보드 렌더 완료',
};

const USER_ERROR = {
  noPrompt: '먼저 분석을 실행해 프롬프트를 생성하세요.',
  noModel: '모델 태그를 입력하세요. 예: bitnet:latest',
  invalidDashboardJson: '대시보드 JSON 형식이 올바르지 않습니다.',
  noMultiFiles: '멀티 CSV 파일을 먼저 선택하세요.',
  unknownIntent: '의도 해석이 불명확합니다. 아래 추천 액션 중 하나를 선택하세요.',
};

const appState = {
  latestPrompt: '',
  currentMode: 'quick',
  busyCount: 0,
  request: { question: '', intent: '', route: 'analyze' },
};

function setStatus(message) {
  if (UI.statusBox) UI.statusBox.textContent = message;
}

function showError(userMessage, detail = '') {
  if (UI.errorUser) UI.errorUser.textContent = userMessage || '';
  if (!UI.errorDetails || !UI.errorDetailText) return;
  UI.errorDetailText.textContent = detail || '';
  UI.errorDetails.open = false;
  UI.errorDetails.style.display = detail ? '' : 'none';
}

function clearError() {
  showError('', '');
}

function toggleBusy(isBusy) {
  appState.busyCount += isBusy ? 1 : -1;
  if (appState.busyCount < 0) appState.busyCount = 0;
  const disabled = appState.busyCount > 0;
  const targets = [
    UI.csvFile,
    UI.analyzeBtn,
    UI.quickAnalyzeBtn,
    UI.runBtn,
    UI.multiAnalyzeBtn,
    UI.renderDashboardBtn,
    ...document.querySelectorAll('.mode-btn'),
    ...document.querySelectorAll('.chip'),
  ];
  targets.forEach((el) => {
    if (el) el.disabled = disabled;
  });
}

async function postJson(url, body, context) {
  let res;
  let data = null;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    data = await res.json();
  } catch (err) {
    throw {
      userMessage: `${context} 중 네트워크 오류가 발생했습니다.`,
      detail: err instanceof Error ? err.message : String(err),
    };
  }

  if (!res.ok) {
    throw {
      userMessage: `${context}에 실패했습니다.`,
      detail: data?.error_detail || data?.error || JSON.stringify(data || {}),
    };
  }
  return data;
}

function saveRequestState(route) {
  appState.request.question = UI.question?.value || '';
  appState.request.intent = UI.intent?.value || '';
  appState.request.route = route;
}

function classifyIntent(intentText) {
  const text = String(intentText || '').toLowerCase().trim();
  if (!text) return { route: 'analyze' };
  if (/(멀티|여러|복수|비교|비교분석|multi)/.test(text)) return { route: 'multi' };
  if (/(시각화|차트|그래프|plot|대시보드)/.test(text)) return { route: 'visualize' };
  if (/(분석|요약|인사이트|이상치|진단|핵심)/.test(text)) return { route: 'analyze' };
  return { route: 'unknown' };
}

function renderIntentActions(actions = []) {
  if (!UI.intentActions) return;
  UI.intentActions.innerHTML = '';
  actions.forEach((item) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.textContent = item.label;
    btn.addEventListener('click', item.onClick);
    UI.intentActions.appendChild(btn);
  });
}

function showFallbackIntentActions() {
  renderIntentActions([
    {
      label: '기본 분석 실행',
      onClick: () => {
        setMode('quick');
        UI.quickAnalyzeBtn?.focus();
        setStatus('추천 액션: 기본 분석 실행');
      },
    },
    {
      label: '멀티 분석으로 전환',
      onClick: () => {
        setMode('advanced');
        UI.multiCsvFiles?.focus();
        setStatus('추천 액션: 멀티 분석 파일을 선택하세요.');
      },
    },
    {
      label: '시각화 안내 보기',
      onClick: () => {
        setMode('advanced');
        UI.dashboardJson?.focus();
        setStatus('추천 액션: 멀티 분석 결과 JSON을 붙여넣고 대시보드를 렌더링하세요.');
      },
    },
  ]);
}

function renderModeGuide(mode) {
  if (!UI.modeGuide) return;
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
  UI.modeGuide.innerHTML = steps.map((step) => `<li>${step}</li>`).join('');
}

function setMode(mode) {
  appState.currentMode = mode;
  document.querySelectorAll('.advanced-only').forEach((el) => {
    el.style.display = mode === 'advanced' ? '' : 'none';
  });
  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  setStatus(mode === 'quick' ? STATUS.quickReady : STATUS.advancedReady);
  renderModeGuide(mode);
}

function renderDashboard(data) {
  if (!UI.dashboardCards || !UI.dashboardInsights) return;
  UI.dashboardCards.innerHTML = '';
  UI.dashboardInsights.textContent = '';

  const cardItems = [
    ['파일 수', data.file_count ?? '-'],
    ['총 행 수', data.total_row_count ?? '-'],
    ['공통 컬럼 수', (data.shared_columns || []).length],
    ['인사이트 수', (data.insights || []).length],
  ];

  cardItems.forEach(([k, v]) => {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<strong>${k}</strong><span>${v}</span>`;
    UI.dashboardCards.appendChild(div);
  });

  const insights = data.insights || [];
  UI.dashboardInsights.textContent = insights.length
    ? insights.map((x, i) => `${i + 1}. ${x}`).join('\n')
    : '인사이트 항목이 없습니다.';
  setStatus(STATUS.dashboardDone);
}

async function runAnalyze() {
  clearError();
  setStatus(STATUS.analyzing);
  UI.summary.textContent = STATUS.analyzing;
  toggleBusy(true);
  try {
    const data = await postJson('/api/analyze', {
      csv_text: UI.csvText.value,
      question: UI.question.value,
    }, '분석');
    appState.latestPrompt = data.prompt;
    UI.summary.textContent = JSON.stringify(data.summary, null, 2);
    if (UI.prompt) UI.prompt.textContent = data.prompt;
    if (UI.answer) UI.answer.textContent = '';
    setStatus(STATUS.analyzeDone);
  } catch (err) {
    UI.summary.textContent = err.userMessage || '오류';
    showError(err.userMessage || '분석 실패', err.detail || '');
    setStatus('분석 실패');
  } finally {
    toggleBusy(false);
  }
}

async function runMultiAnalyze() {
  clearError();
  const files = [...(UI.multiCsvFiles?.files || [])];
  if (!files.length) {
    UI.dashboardInsights.textContent = USER_ERROR.noMultiFiles;
    showError(USER_ERROR.noMultiFiles, 'input files is empty');
    setStatus('멀티 분석 중단');
    return false;
  }

  setStatus(STATUS.multiRunning);
  UI.dashboardInsights.textContent = STATUS.multiRunning;
  toggleBusy(true);
  try {
    const payloadFiles = [];
    for (const f of files) {
      payloadFiles.push({ name: f.name, csv_text: await f.text() });
    }

    const data = await postJson('/api/multi-analyze', {
      files: payloadFiles,
      question: UI.question.value,
      group_column: UI.groupColumn.value.trim(),
      target_column: UI.targetColumn.value.trim(),
    }, '멀티 분석');

    UI.dashboardJson.value = JSON.stringify(data, null, 2);
    renderDashboard(data);
    setStatus(STATUS.multiDone);
    return true;
  } catch (err) {
    UI.dashboardInsights.textContent = err.userMessage || '멀티 분석 실패';
    showError(err.userMessage || '멀티 분석 실패', err.detail || '');
    setStatus('멀티 분석 실패');
    return false;
  } finally {
    toggleBusy(false);
  }
}

async function runModel() {
  clearError();
  if (!appState.latestPrompt) {
    if (UI.answer) UI.answer.textContent = USER_ERROR.noPrompt;
    showError(USER_ERROR.noPrompt, 'latestPrompt is empty');
    setStatus('모델 실행 중단');
    return;
  }
  if (!UI.model.value.trim()) {
    if (UI.answer) UI.answer.textContent = USER_ERROR.noModel;
    showError(USER_ERROR.noModel, 'model input is empty');
    setStatus('모델 실행 중단');
    return;
  }

  setStatus(STATUS.modelRunning);
  if (UI.answer) UI.answer.textContent = STATUS.modelRunning;
  toggleBusy(true);
  try {
    const data = await postJson('/api/run', {
      model: UI.model.value.trim(),
      prompt: appState.latestPrompt,
    }, 'BitNet 실행');
    UI.answer.textContent = data.answer;
    setStatus(STATUS.modelDone);
  } catch (err) {
    UI.answer.textContent = err.userMessage || '모델 실행 실패';
    showError(err.userMessage || '모델 실행 실패', err.detail || '');
    setStatus('모델 실행 실패');
  } finally {
    toggleBusy(false);
  }
}

async function runByIntent() {
  clearError();
  renderIntentActions([]);
  const intentResult = classifyIntent(UI.intent?.value || '');
  saveRequestState(intentResult.route);

  if (intentResult.route === 'analyze') return runAnalyze();

  if (intentResult.route === 'multi') {
    setMode('advanced');
    const done = await runMultiAnalyze();
    if (!done) {
      renderIntentActions([
        { label: '멀티 파일 선택하기', onClick: () => UI.multiCsvFiles?.focus() },
        { label: '기본 분석으로 진행', onClick: () => { setMode('quick'); runAnalyze(); } },
      ]);
      setStatus('의도 라우팅: 멀티 비교 우선');
    }
    return;
  }

  if (intentResult.route === 'visualize') {
    setMode('advanced');
    renderIntentActions([
      { label: '대시보드 JSON 입력으로 이동', onClick: () => UI.dashboardJson?.focus() },
      { label: '먼저 멀티 분석 실행', onClick: () => UI.multiAnalyzeBtn?.focus() },
    ]);
    setStatus('의도 라우팅: 시각화 안내 우선');
    return;
  }

  showFallbackIntentActions();
  showError(USER_ERROR.unknownIntent, `intent="${UI.intent?.value || ''}"`);
  setStatus('의도 라우팅 실패');
}

function bindEvents() {
  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => setMode(btn.dataset.mode));
  });

  if (UI.csvFile) {
    UI.csvFile.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      UI.csvText.value = await file.text();
      setStatus(`파일 로드 완료: ${file.name}`);
    });
  }

  document.querySelectorAll('.chip[data-q]').forEach((chip) => {
    chip.addEventListener('click', () => {
      UI.question.value = chip.dataset.q;
      UI.quickAnalyzeBtn?.focus();
    });
  });

  UI.copyPromptBtn?.addEventListener('click', async () => {
    if (!appState.latestPrompt) return;
    await navigator.clipboard.writeText(appState.latestPrompt);
    setStatus('프롬프트가 복사되었습니다.');
  });

  UI.analyzeBtn?.addEventListener('click', runByIntent);
  UI.quickAnalyzeBtn?.addEventListener('click', runByIntent);
  UI.runBtn?.addEventListener('click', runModel);
  UI.multiAnalyzeBtn?.addEventListener('click', runMultiAnalyze);

  UI.renderDashboardBtn?.addEventListener('click', () => {
    clearError();
    try {
      const parsed = JSON.parse(UI.dashboardJson.value || '{}');
      renderDashboard(parsed);
    } catch (err) {
      UI.dashboardInsights.textContent = USER_ERROR.invalidDashboardJson;
      showError(USER_ERROR.invalidDashboardJson, err instanceof Error ? err.message : String(err));
      setStatus('대시보드 렌더 실패');
    }
  });

  UI.intent?.addEventListener('input', () => {
    if (!UI.intent.value.trim()) {
      renderIntentActions([]);
      return;
    }
    const { route } = classifyIntent(UI.intent.value);
    if (route === 'analyze') setStatus('의도 라우팅 후보: 분석 우선');
    else if (route === 'multi') setStatus('의도 라우팅 후보: 멀티 비교 우선');
    else if (route === 'visualize') setStatus('의도 라우팅 후보: 시각화 안내 우선');
    else setStatus('의도 라우팅 후보를 찾지 못했습니다. 실행 시 추천 액션을 제공합니다.');
  });
}

function init() {
  bindEvents();
  clearError();
  setMode(appState.currentMode);
}

init();
