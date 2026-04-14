const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_CODEX_API_BASE_URL || '');
const APP_ENV_NAME = normalizeText(import.meta.env.VITE_APP_ENV_NAME || '');
const ORIGINAL_FETCH = window.fetch.bind(window);

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeApiBaseUrl(value) {
  const token = normalizeText(value);
  if (!token) return '';
  return token.endsWith('/') ? token.slice(0, -1) : token;
}

function rewriteApiUrl(input) {
  if (!API_BASE_URL || typeof input !== 'string' || !input) {
    return input;
  }
  if (input.startsWith('/api/')) {
    return `${API_BASE_URL}${input}`;
  }
  try {
    const parsed = new URL(input, window.location.origin);
    if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')) {
      return `${API_BASE_URL}${parsed.pathname}${parsed.search}${parsed.hash}`;
    }
  } catch (error) {
    void error;
  }
  return input;
}

window.fetch = (input, init) => {
  if (input instanceof Request) {
    const rewritten = rewriteApiUrl(input.url);
    if (rewritten !== input.url) {
      return ORIGINAL_FETCH(new Request(rewritten, input), init);
    }
    return ORIGINAL_FETCH(input, init);
  }
  if (input instanceof URL) {
    return ORIGINAL_FETCH(rewriteApiUrl(input.toString()), init);
  }
  return ORIGINAL_FETCH(rewriteApiUrl(input), init);
};

async function fetchRuntimeInfo() {
  const runtimeUrl = API_BASE_URL
    ? `${API_BASE_URL}/api/codex/runtime/info`
    : '/api/codex/runtime/info';
  const response = await ORIGINAL_FETCH(runtimeUrl, {
    method: 'GET',
    credentials: 'omit',
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`runtime info request failed (${response.status})`);
  }
  const payload = await response.json();
  if (!payload || typeof payload !== 'object') {
    throw new Error('runtime info payload is invalid');
  }
  return payload;
}

function stringifyOptions(options) {
  return JSON.stringify(Array.isArray(options) ? options : []);
}

function setElementText(id, text, fallback = '') {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = normalizeText(text) || fallback;
}

function setSelectOptionsData(selectId, options) {
  const element = document.getElementById(selectId);
  if (!element) return;
  element.setAttribute('data-options', stringifyOptions(options));
}

function setElementVisibility(id, visible) {
  const element = document.getElementById(id);
  if (!element) return;
  element.classList.toggle('is-hidden', !visible);
  element.setAttribute('aria-hidden', visible ? 'false' : 'true');
  if (
    element instanceof HTMLButtonElement
    || element instanceof HTMLInputElement
    || element instanceof HTMLSelectElement
    || element instanceof HTMLTextAreaElement
  ) {
    element.disabled = !visible;
  }
}

function applyFeatureFlags(runtime) {
  const flags = runtime?.feature_flags || {};
  const gitEnabled = flags.git_api_enabled !== false;
  const filesEnabled = flags.files_api_enabled !== false;

  setElementVisibility('codex-git-branch', gitEnabled);
  setElementVisibility('codex-git-commit', gitEnabled);
  setElementVisibility('codex-git-push', gitEnabled);
  setElementVisibility('codex-git-sync', gitEnabled);

  setElementVisibility('codex-file-browser-open', filesEnabled);
  setElementVisibility('codex-work-mode-toggle', filesEnabled);
}

function applyRuntimeInfo(runtime) {
  const workspaceName = normalizeText(runtime?.workspace_directory_name) || 'Workspace';
  const workspacePath = normalizeText(runtime?.workspace_directory_path);
  const serverName = normalizeText(runtime?.server_directory_name) || 'Codex Backend';
  const serverPath = normalizeText(runtime?.server_directory_path);
  const branchName = normalizeText(runtime?.current_branch_name);

  if (document.body) {
    document.body.dataset.workspacePath = workspacePath;
    document.body.dataset.serverPath = serverPath;
    if (APP_ENV_NAME) {
      document.body.dataset.appEnvName = APP_ENV_NAME;
    }
  }

  const titleSuffix = APP_ENV_NAME ? `${workspaceName} (${APP_ENV_NAME})` : workspaceName;
  document.title = `Codex Agent · ${titleSuffix}`;

  setElementText('codex-server-directory', serverName, 'Codex Backend');
  setElementText('codex-server-directory-path', serverPath, '-');
  setElementText('codex-git-branch', branchName, '-');
  setElementText('codex-weather-location', workspaceName, workspaceName);
  const branchElement = document.getElementById('codex-git-branch');
  if (branchElement) {
    const branchLabel = branchName || '-';
    branchElement.setAttribute('data-branch-full', branchLabel);
    branchElement.setAttribute('title', branchLabel);
  }

  const workspaceLabel = APP_ENV_NAME
    ? `${workspaceName} · ${APP_ENV_NAME}`
    : workspaceName;
  setElementText('codex-app-workspace-name', workspaceLabel, 'Workspace');

  const modelOptions = Array.isArray(runtime?.model_options) ? runtime.model_options : [];
  const reasoningOptions = Array.isArray(runtime?.reasoning_options) ? runtime.reasoning_options : [];

  setSelectOptionsData('codex-model-select', modelOptions);
  setSelectOptionsData('codex-plan-mode-model-select', modelOptions);
  setSelectOptionsData('codex-reasoning-select', reasoningOptions);
  setSelectOptionsData('codex-plan-mode-reasoning-select', reasoningOptions);
  applyFeatureFlags(runtime);

  window.__CODEX_RUNTIME_INFO__ = runtime;
}

function applyRuntimeFallback(message) {
  if (document.body) {
    document.body.dataset.workspacePath = document.body.dataset.workspacePath || '';
    document.body.dataset.serverPath = document.body.dataset.serverPath || '';
    if (APP_ENV_NAME) {
      document.body.dataset.appEnvName = APP_ENV_NAME;
    }
  }

  const workspaceLabel = APP_ENV_NAME ? `Workspace · ${APP_ENV_NAME}` : 'Workspace';
  setElementText('codex-app-workspace-name', workspaceLabel, 'Workspace');
  setElementText('codex-server-directory', 'Codex Backend', 'Codex Backend');
  setElementText('codex-server-directory-path', message || '-', '-');

  window.__CODEX_RUNTIME_INFO__ = null;
}

async function boot() {
  try {
    const runtime = await fetchRuntimeInfo();
    applyRuntimeInfo(runtime);
  } catch (error) {
    applyRuntimeFallback(normalizeText(error?.message) || 'runtime info unavailable');
  }

  await import('./legacy-app.js');
}

void boot();
