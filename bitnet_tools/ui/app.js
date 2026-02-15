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
  startChartsJobBtn: document.getElementById('startChartsJobBtn'),
  retryChartsJobBtn: document.getElementById('retryChartsJobBtn'),
  chartsJobStatus: document.getElementById('chartsJobStatus'),
  dashboardJson: document.getElementById('dashboardJson'),
  dashboardCards: document.getElementById('dashboardCards'),
  dashboardInsights: document.getElementById('dashboardInsights'),
  renderDashboardBtn: document.getElementById('renderDashboardBtn'),
  copyPromptBtn: document.getElementById('copyPrompt'),
  filterFile: document.getElementById('filterFile'),
  filterColumn: document.getElementById('filterColumn'),
  filterType: document.getElementById('filterType'),
  insightList: document.getElementById('insightList'),
  insightDrilldown: document.getElementById('insightDrilldown'),
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
  latestMultiResult: null,
  structuredInsights: [],
  chartJob: { id: null, files: [], status: 'idle', pollTimer: null },
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
    UI.startChartsJobBtn,
    UI.retryChartsJobBtn,
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

async function getJson(url, context) {
  let res;
  let data = null;
  try {
    res = await fetch(url);
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

function parseInsightType(text) {
  const t = String(text || '');
  if (/결측/.test(t)) return 'missing';
  if (/이상치|outlier/.test(t)) return 'outlier';
  if (/드리프트|변화|drift/.test(t)) return 'drift';
  return 'general';
}

function buildStructuredInsights(data) {
  const list = [];
  const insights = Array.isArray(data?.insights) ? data.insights : [];
  insights.forEach((text, idx) => {
    const entry = {
      id: `insight-${idx + 1}`,
      text,
      type: parseInsightType(text),
      file: '전체',
      column: '-',
      evidence: { source: 'insights', raw: text },
    };

    const fileMatch = text.match(/([^\s]+\.csv)/);
    if (fileMatch) entry.file = fileMatch[1];
    const colMatch = text.match(/컬럼\s*[:=]?\s*([A-Za-z0-9_가-힣]+)/);
    if (colMatch) entry.column = colMatch[1];
    list.push(entry);
  });

  (data.files || []).forEach((f) => {
    const name = (f.path || '').split('/').pop() || 'unknown.csv';
    const profiles = f.column_profiles || {};
    Object.entries(profiles).forEach(([col, p]) => {
      if ((p.missing_ratio || 0) >= 0.2) {
        list.push({
          id: `missing-${name}-${col}`,
          text: `${name} / ${col}: 결측 비율 ${(p.missing_ratio * 100).toFixed(1)}%`,
          type: 'missing',
          file: name,
          column: col,
          evidence: p,
        });
      }
      const outlier = p.numeric_distribution?.outlier_ratio || 0;
      if (outlier >= 0.1) {
        list.push({
          id: `outlier-${name}-${col}`,
          text: `${name} / ${col}: 이상치 비율 ${(outlier * 100).toFixed(1)}%`,
          type: 'outlier',
          file: name,
          column: col,
          evidence: p,
        });
      }
    });
  });

  return list;
}

function renderFilters() {
  if (!UI.filterFile || !UI.filterType) return;

  const files = ['전체', ...new Set(appState.structuredInsights.map((x) => x.file).filter(Boolean))];
  UI.filterFile.innerHTML = files.map((f) => `<option value="${f}">${f}</option>`).join('');

  const types = ['all', ...new Set(appState.structuredInsights.map((x) => x.type).filter(Boolean))];
  const typeName = { all: '전체', missing: '결측', outlier: '이상치', drift: '드리프트', general: '일반' };
  UI.filterType.innerHTML = types.map((t) => `<option value="${t}">${typeName[t] || t}</option>`).join('');
}

function getFilteredInsights() {
  const fFile = UI.filterFile?.value || '전체';
  const fCol = (UI.filterColumn?.value || '').trim().toLowerCase();
  const fType = UI.filterType?.value || 'all';

  return appState.structuredInsights.filter((item) => {
    if (fFile !== '전체' && item.file !== fFile) return false;
    if (fType !== 'all' && item.type !== fType) return false;
    if (fCol && !String(item.column).toLowerCase().includes(fCol) && !String(item.text).toLowerCase().includes(fCol)) return false;
    return true;
  });
}

function renderDrilldown(item) {
  if (!UI.insightDrilldown) return;
  UI.insightDrilldown.textContent = JSON.stringify({
    id: item.id,
    file: item.file,
    column: item.column,
    type: item.type,
    evidence: item.evidence,
  }, null, 2);
}

function renderInsightList() {
  if (!UI.insightList) return;
  const rows = getFilteredInsights();
  UI.insightList.innerHTML = '';
  if (!rows.length) {
    UI.insightList.textContent = '필터 조건에 맞는 인사이트가 없습니다.';
    UI.insightDrilldown.textContent = '인사이트를 선택하면 근거 데이터가 표시됩니다.';
    return;
  }

  rows.forEach((item) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'insight-item';
    btn.textContent = `[${item.type}] ${item.text}`;
    btn.addEventListener('click', () => renderDrilldown(item));
    UI.insightList.appendChild(btn);
  });
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

  appState.structuredInsights = buildStructuredInsights(data);
  renderFilters();
  renderInsightList();

  setStatus(STATUS.dashboardDone);
}

function setChartsJobStatusText(text) {
  if (UI.chartsJobStatus) UI.chartsJobStatus.textContent = text;
}

function stopChartPolling() {
  if (appState.chartJob.pollTimer) {
    clearInterval(appState.chartJob.pollTimer);
    appState.chartJob.pollTimer = null;
  }
}

async function pollChartJobOnce() {
  if (!appState.chartJob.id) return;
  try {
    const result = await getJson(`/api/charts/jobs/${appState.chartJob.id}`, '차트 작업 조회');
    appState.chartJob.status = result.status;
    setChartsJobStatusText(`job=${result.job_id} status=${result.status}\n${JSON.stringify(result, null, 2)}`);

    if (result.status === 'done') {
      stopChartPolling();
      UI.retryChartsJobBtn.disabled = true;
      setStatus('차트 작업 완료');
    } else if (result.status === 'failed') {
      stopChartPolling();
      UI.retryChartsJobBtn.disabled = false;
      showError('차트 작업이 실패했습니다.', result.error || 'unknown');
      setStatus('차트 작업 실패');
    }
  } catch (err) {
    stopChartPolling();
    UI.retryChartsJobBtn.disabled = false;
    showError(err.userMessage || '차트 상태 조회 실패', err.detail || '');
    setStatus('차트 상태 조회 실패');
  }
}

function startChartPolling() {
  stopChartPolling();
  appState.chartJob.pollTimer = setInterval(() => {
    pollChartJobOnce();
  }, 1500);
}

function collectMultiFiles() {
  const files = [...(UI.multiCsvFiles?.files || [])];
  return files;
}

async function startChartsJob() {
  clearError();
  const files = collectMultiFiles();
  if (!files.length) {
    showError(USER_ERROR.noMultiFiles, 'input files is empty');
    setChartsJobStatusText('차트 작업 시작 실패: 파일이 없습니다.');
    return;
  }

  toggleBusy(true);
  try {
    const payloadFiles = [];
    for (const f of files) {
      payloadFiles.push({ name: f.name, csv_text: await f.text() });
    }
    appState.chartJob.files = payloadFiles;

    const queued = await postJson('/api/charts/jobs', { files: payloadFiles }, '차트 작업 생성');
    appState.chartJob.id = queued.job_id;
    appState.chartJob.status = queued.status;
    UI.retryChartsJobBtn.disabled = true;
    setChartsJobStatusText(`job=${queued.job_id} status=${queued.status}`);
    setStatus('차트 작업 큐 등록 완료');
    await pollChartJobOnce();
    startChartPolling();
  } catch (err) {
    showError(err.userMessage || '차트 작업 생성 실패', err.detail || '');
    setStatus('차트 작업 시작 실패');
  } finally {
    toggleBusy(false);
  }
}

async function retryChartsJob() {
  if (!appState.chartJob.files.length) {
    showError('재시도할 차트 작업 데이터가 없습니다.', 'chartJob.files is empty');
    return;
  }
  clearError();
  toggleBusy(true);
  try {
    const queued = await postJson('/api/charts/jobs', { files: appState.chartJob.files }, '차트 작업 재시도');
    appState.chartJob.id = queued.job_id;
    appState.chartJob.status = queued.status;
    UI.retryChartsJobBtn.disabled = true;
    setChartsJobStatusText(`job=${queued.job_id} status=${queued.status} (retry)`);
    setStatus('차트 작업 재시도 시작');
    await pollChartJobOnce();
    startChartPolling();
  } catch (err) {
    showError(err.userMessage || '차트 작업 재시도 실패', err.detail || '');
    setStatus('차트 작업 재시도 실패');
  } finally {
    toggleBusy(false);
  }
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
  const files = collectMultiFiles();
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

    appState.latestMultiResult = data;
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
      { label: '비동기 차트 생성 시작', onClick: () => UI.startChartsJobBtn?.focus() },
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
  UI.startChartsJobBtn?.addEventListener('click', startChartsJob);
  UI.retryChartsJobBtn?.addEventListener('click', retryChartsJob);

  UI.renderDashboardBtn?.addEventListener('click', () => {
    clearError();
    try {
      const parsed = JSON.parse(UI.dashboardJson.value || '{}');
      appState.latestMultiResult = parsed;
      renderDashboard(parsed);
    } catch (err) {
      UI.dashboardInsights.textContent = USER_ERROR.invalidDashboardJson;
      showError(USER_ERROR.invalidDashboardJson, err instanceof Error ? err.message : String(err));
      setStatus('대시보드 렌더 실패');
    }
  });

  [UI.filterFile, UI.filterType].forEach((el) => {
    el?.addEventListener('change', renderInsightList);
  });
  UI.filterColumn?.addEventListener('input', renderInsightList);

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
  if (UI.filterFile) UI.filterFile.innerHTML = '<option value="전체">전체</option>';
  if (UI.filterType) UI.filterType.innerHTML = '<option value="all">전체</option>';
  if (UI.retryChartsJobBtn) UI.retryChartsJobBtn.disabled = true;
  setChartsJobStatusText('차트 작업 대기 중');
}

init();
