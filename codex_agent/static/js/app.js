const state = {
    sessions: [],
    activeSessionId: null,
    sessionStorage: null,
    loading: false,
    sessionStates: {},
    streams: {},
    remoteStreamSessions: new Set(),
    remoteAttachInFlightSessions: new Set(),
    remoteStreams: [],
    liveClockTimer: null,
    jobMonitorTimerId: null,
    responseTimerId: null,
    responseTimerSessionId: null,
    autoScrollEnabled: true,
    autoScrollPinnedSessionId: null,
    autoScrollThreshold: 48,
    statusMessage: 'Idle',
    statusIsError: false,
    pendingAttachments: [],
    settings: {
        model: null,
        modelCatalog: [],
        modelOptions: [],
        planModeModel: null,
        planModeReasoningEffort: null,
        planModeState: 'off',
        reasoningEffort: null,
        reasoningOptions: [],
        usage: null,
        usageHistory: null,
        loaded: false
    }
};

const terminalState = {
    sessions: [],
    activeSessionId: null,
    overlayOpen: false,
    runtimePromise: null,
    terminal: null,
    fitAddon: null,
    mountedSessionId: null,
    streamSource: null,
    streamSessionId: null,
    streamReconnectTimer: null,
    streamReconnectAttempt: 0,
    streamConnected: false,
    pollTimer: null,
    pollInFlight: false,
    inputSessionId: null,
    inputBuffer: '',
    inputInFlight: false,
    inputFlushTimer: null,
    resizeTimerId: null,
    resizeObserver: null,
    viewportRefreshFrameId: null,
    viewportRefreshTimerId: null,
    viewportRefreshNeedsFocus: false,
    viewportRefreshNeedsFit: false,
    launchContext: {
        root: 'workspace',
        path: ''
    },
    extraKeyModifiers: {
        ctrl: false,
        alt: false
    }
};

const SESSION_COLLAPSE_KEY = 'codexSessionsCollapsed';
const ACTIVE_STREAM_KEY = 'codexActiveStream';
const CONTROLS_COLLAPSE_KEY = 'codexControlsCollapsed';
const PHONE_MEDIA_QUERY = '(max-width: 599px)';
const FOLD_MEDIA_QUERY = '(min-width: 600px) and (max-width: 840px)';
const MOBILE_MEDIA_QUERY = '(max-width: 840px)';
const MOBILE_VIEWPORT_HEIGHT_VAR = '--mobile-viewport-height';
const MOBILE_PROMPT_LIFT_VAR = '--mobile-prompt-lift';
const MOBILE_SETTINGS_FOCUS_CLASS = 'is-settings-input-focused';
const MOBILE_KEYBOARD_OPEN_CLASS = 'is-mobile-keyboard-open';
const MOBILE_KEYBOARD_VIEWPORT_DELTA = 120;
const CHAT_FULLSCREEN_CLASS = 'is-chat-fullscreen';
const WORK_MODE_CLASS = 'is-work-mode';
const WORK_MODE_PREVIEW_FULLSCREEN_CLASS = 'is-work-mode-fold-preview-fullscreen';
const WORK_MODE_KEY = 'codexWorkModeEnabled';
const WORK_MODE_SPLIT_KEY = 'codexWorkModeSplit';
const WORK_MODE_DEFAULT_SPLIT = 0.58;
const WORK_MODE_MIN_CHAT_WIDTH_PX = 420;
const WORK_MODE_MIN_PREVIEW_WIDTH_PX = 320;
const WORK_MODE_FILE_SPLIT_KEY = 'codexWorkModeFileSplit';
const WORK_MODE_FILE_COLUMNS_KEY = 'codexWorkModeFileColumns';
const WORK_MODE_FILE_VIEW_STATE_KEY = 'codexWorkModeFileViewState';
const WORK_MODE_FILE_STATE_PERSIST_DEBOUNCE_MS = 140;
const FILE_BROWSER_SPLIT_KEY = 'codexFileBrowserSplit';
const FILE_BROWSER_COLUMNS_KEY = 'codexFileBrowserColumns';
const WORK_MODE_FILE_DEFAULT_SPLIT = 0.36;
const WORK_MODE_FILE_MIN_LIST_WIDTH_PX = 220;
const WORK_MODE_FILE_MIN_VIEWER_WIDTH_PX = 320;
const WORK_MODE_FILE_COLUMN_DEFAULTS = Object.freeze({
    name: 220,
    size: 92,
    modified: 146
});
const WORK_MODE_FILE_COLUMN_LEGACY_DEFAULTS = Object.freeze({
    name: 260,
    size: 92,
    modified: 146
});
const WORK_MODE_FILE_COLUMN_LIMITS = Object.freeze({
    name: Object.freeze({ min: 180, max: 520 }),
    size: Object.freeze({ min: 72, max: 220 }),
    modified: Object.freeze({ min: 110, max: 280 })
});
const THEME_KEY = 'codexTheme';
const THEME_MEDIA_QUERY = '(prefers-color-scheme: dark)';
const STREAM_POLL_BASE_MS = 800;
const STREAM_POLL_MAX_MS = 5000;
const REMOTE_STREAM_POLL_MS = 2500;
const STREAM_IDLE_WARNING_MS = 15000;
const MERMAID_VENDOR_SRC = '/static/vendor/mermaid-11.13.0.min.js';
const XLSX_VENDOR_SRC = '/static/vendor/xlsx-0.18.5.full.min.js';
const MESSAGE_COLLAPSE_LINES = 12;
const MESSAGE_COLLAPSE_CHARS = 1200;
const KST_TIME_ZONE = 'Asia/Seoul';
const WEATHER_COMPACT_KEY = 'codexWeatherCompact';
const WEATHER_LOCATION_FAILURE_TOAST_MS = 3800;
const TOAST_LAYER_ID = 'codex-toast-layer';
const HOVER_TOOLTIP_LAYER_ID = 'codex-hover-tooltip-layer';
const HOVER_TOOLTIP_OFFSET_PX = 8;
const HOVER_TOOLTIP_VIEWPORT_MARGIN_PX = 10;
const LIVE_WEATHER_PANEL_TITLE = 'Clock & Weather';
const DEFAULT_WEATHER_LOCATION_LABEL = '화성시 반월동';
const DEFAULT_WEATHER_POSITION = Object.freeze({
    latitude: 37.23018,
    longitude: 127.06497,
    label: DEFAULT_WEATHER_LOCATION_LABEL,
    isDefault: true
});
const CHAT_INPUT_DEFAULT_PLACEHOLDER = 'Type a prompt for Codex. (Shift+Enter for newline)';
const CHAT_ATTACHMENT_UPLOAD_TIMEOUT_MS = 120000;
const GIT_BRANCH_STATUS_CACHE_MS = 5000;
const GIT_BRANCH_TOAST_COOLDOWN_MS = 900;
const GIT_BRANCH_POLL_MS = 10000;
const GIT_STATUS_REQUEST_TIMEOUT_MS = 25000;
const GIT_HISTORY_REQUEST_TIMEOUT_MS = 90000;
const GIT_COMMIT_PREVIEW_REQUEST_TIMEOUT_MS = 90000;
const GIT_COMMIT_PREVIEW_CACHE_MS = 15000;
const GIT_STAGE_REQUEST_TIMEOUT_MS = 100000;
const GIT_COMMIT_REQUEST_TIMEOUT_MS = 620000;
const GIT_PUSH_REQUEST_TIMEOUT_MS = 380000;
const GIT_FETCH_ONLY_REQUEST_TIMEOUT_MS = 240000;
const GIT_FETCH_SYNC_REQUEST_TIMEOUT_MS = 900000;
const GIT_CANCEL_REQUEST_TIMEOUT_MS = 12000;
const GIT_SYNC_TARGET_WORKSPACE = 'workspace';
const GIT_SYNC_TARGET_CODEX_AGENT = 'codex_agent';
const MESSAGE_LOG_OVERLAY_MODE_PREVIEW = 'preview';
const MESSAGE_LOG_OVERLAY_MODE_DETAIL = 'detail';
const MESSAGE_LOG_OVERLAY_CLASS_PREVIEW = 'is-preview-mode';
const MESSAGE_LOG_OVERLAY_CLASS_DETAIL = 'is-detail-mode';
const FILE_BROWSER_ROOT_WORKSPACE = 'workspace';
const FILE_BROWSER_REQUEST_TIMEOUT_MS = 30000;
const FILE_BROWSER_READ_TIMEOUT_MS = 30000;
const FILE_BROWSER_MUTATION_TIMEOUT_MS = 45000;
const FILE_BROWSER_RAW_FILE_ENDPOINT = '/api/codex/files/raw';
const FILE_BROWSER_VIEWER_IFRAME_SCROLL_RESTORE_RETRY_MS = 70;
const FILE_BROWSER_VIEWER_IFRAME_SCROLL_RESTORE_MAX_RETRIES = 45;
const FILE_BROWSER_SPREADSHEET_MAX_SHEETS = 20;
const FILE_BROWSER_SPREADSHEET_MAX_ROWS = 200;
const FILE_BROWSER_SPREADSHEET_MAX_COLS = 50;
const FILE_BROWSER_SPREADSHEET_EXTENSIONS = new Set([
    '.xls',
    '.xlsb',
    '.xlsm',
    '.xlsx',
    '.xltm',
    '.xltx',
    '.ods'
]);
const FILE_BROWSER_MOBILE_VIEW_LIST = 'list';
const FILE_BROWSER_MOBILE_VIEW_VIEWER = 'viewer';
const FILE_PANEL_VARIANT_WORK_MODE = 'work-mode';
const FILE_PANEL_VARIANT_OVERLAY = 'overlay';
const FILE_PANEL_CHAT_CONTEXT_MAX_FILES = 6;
const FILE_PANEL_CHAT_CONTEXT_MAX_CHARS_PER_FILE = 4000;
const FILE_PANEL_CHAT_CONTEXT_MAX_TOTAL_CHARS = 18000;
const FILE_PANEL_EDIT_DISCARD_MESSAGE = '저장하지 않은 변경 사항이 있습니다. 변경 내용을 버릴까요?';
const TERMINAL_REQUEST_TIMEOUT_MS = 20000;
const TERMINAL_INPUT_TIMEOUT_MS = 12000;
const TERMINAL_CLOSE_TIMEOUT_MS = 20000;
const TERMINAL_POLL_MS = 600;
const TERMINAL_STREAM_RECONNECT_BASE_MS = 320;
const TERMINAL_STREAM_RECONNECT_MAX_MS = 4000;
const TERMINAL_RESIZE_DEBOUNCE_MS = 120;
const TERMINAL_DEFAULT_COLS = 120;
const TERMINAL_DEFAULT_ROWS = 32;
const TERMINAL_FONT_SIZE_PHONE = 12.5;
const TERMINAL_FONT_SIZE_COMPACT = 13;
const TERMINAL_FONT_SIZE_DESKTOP = 14;
const TERMINAL_FONT_FAMILY = 'ui-monospace, "SFMono-Regular", "Cascadia Mono", "JetBrains Mono", "IBM Plex Mono", "Liberation Mono", Menlo, Consolas, monospace';
const TERMINAL_EXTRA_KEYS = Object.freeze([
    Object.freeze({ id: 'escape', label: 'Esc', sequence: '\x1b' }),
    Object.freeze({ id: 'tab', label: 'Tab', sequence: '\t' }),
    Object.freeze({ id: 'ctrl', label: 'Ctrl', modifier: 'ctrl' }),
    Object.freeze({ id: 'alt', label: 'Alt', modifier: 'alt' }),
    Object.freeze({ id: 'slash', label: '/', text: '/' }),
    Object.freeze({ id: 'dash', label: '-', text: '-' }),
    Object.freeze({ id: 'pipe', label: '|', text: '|' }),
    Object.freeze({ id: 'home', label: 'Home', sequence: '\x1b[H' }),
    Object.freeze({ id: 'up', label: '↑', sequence: '\x1b[A' }),
    Object.freeze({ id: 'end', label: 'End', sequence: '\x1b[F' }),
    Object.freeze({ id: 'page-up', label: 'PgUp', sequence: '\x1b[5~' }),
    Object.freeze({ id: 'left', label: '←', sequence: '\x1b[D' }),
    Object.freeze({ id: 'down', label: '↓', sequence: '\x1b[B' }),
    Object.freeze({ id: 'right', label: '→', sequence: '\x1b[C' }),
    Object.freeze({ id: 'page-down', label: 'PgDn', sequence: '\x1b[6~' })
]);
const XTERM_VENDOR_SRC = '/static/vendor/xterm-5.5.0.js';
const XTERM_VENDOR_CSS_HREF = '/static/vendor/xterm-5.5.0.css';
const XTERM_FIT_VENDOR_SRC = '/static/vendor/xterm-addon-fit-0.10.0.js';
const WORK_MODE_MOBILE_VIEW_CHAT = 'chat';
const WORK_MODE_MOBILE_VIEW_LIST = 'list';
const WORK_MODE_MOBILE_VIEW_VIEWER = 'viewer';
const FILE_BROWSER_ROOT_LABELS = Object.freeze({
    [FILE_BROWSER_ROOT_WORKSPACE]: 'Workspace'
});
const ABSOLUTE_PATH_HINT_PREFIXES = Object.freeze([
    '/home/',
    '/Users/',
    '/opt/',
    '/var/',
    '/tmp/',
    '/srv/',
    '/mnt/',
    '/Volumes/'
]);
const SESSION_LIST_REQUEST_TIMEOUT_MS = 20000;
const SESSION_DETAIL_REQUEST_TIMEOUT_MS = 20000;
const SESSION_MUTATION_REQUEST_TIMEOUT_MS = 25000;
const USAGE_HISTORY_REQUEST_TIMEOUT_MS = 25000;
const USAGE_HISTORY_DEFAULT_HOURS = 24 * 14;
const SESSION_PENDING_STALE_MS = 120000;
const REFRESH_BUTTON_STALE_MS = 30000;
const HEADER_RESTART_POLICY_REQUEST_TIMEOUT_MS = 3500;
const GIT_SYNC_TARGET_ORDER = Object.freeze([
    GIT_SYNC_TARGET_WORKSPACE,
    GIT_SYNC_TARGET_CODEX_AGENT
]);
const GIT_SYNC_TARGET_LABELS = Object.freeze({
    [GIT_SYNC_TARGET_WORKSPACE]: '상위 디렉토리 Repo',
    [GIT_SYNC_TARGET_CODEX_AGENT]: 'codex_agent Repo'
});
const PLAN_MODE_STATE_OFF = 'off';
const PLAN_MODE_STATE_PLAN_ONLY = 'plan';
const PLAN_MODE_STATE_PLAN_AND_EXECUTE = 'plan_and_execute';
const PLAN_MODE_AUTO_EXECUTE_PROMPT = '계획대로 수정해줘';

let hasManualTheme = false;
let gitBranchStatusCache = {
    count: null,
    branch: '',
    aheadCount: null,
    behindCount: null,
    windowsInvalidFiles: [],
    windowsInvalidCount: 0,
    hasWindowsPathIssues: false,
    changedFiles: [],
    isStale: false,
    fetchedAt: 0
};
let gitBranchToastAt = 0;
let gitBranchStatusInFlight = false;
let gitBranchPollTimer = null;
let gitOverlaySelectedFiles = new Set();
let gitOverlaySelectionTouched = false;
let gitBranchOverlayCollapsedFolders = new Set();
let gitBranchOverlayPreviewKey = '';
let gitMutationInFlight = false;
let gitSyncOverlayRepoTarget = GIT_SYNC_TARGET_WORKSPACE;
let gitSyncHistoryCacheByTarget = {
    [GIT_SYNC_TARGET_WORKSPACE]: null,
    [GIT_SYNC_TARGET_CODEX_AGENT]: null
};
let gitSyncHistoryInFlightByTarget = {
    [GIT_SYNC_TARGET_WORKSPACE]: false,
    [GIT_SYNC_TARGET_CODEX_AGENT]: false
};
let gitSyncOverlayCollapsedFoldersByTarget = {
    [GIT_SYNC_TARGET_WORKSPACE]: new Set(),
    [GIT_SYNC_TARGET_CODEX_AGENT]: new Set()
};
let gitSyncOverlayPreviewKeyByTarget = {
    [GIT_SYNC_TARGET_WORKSPACE]: '',
    [GIT_SYNC_TARGET_CODEX_AGENT]: ''
};
const gitCommitPreviewCacheByKey = new Map();
const gitCommitPreviewInFlightByKey = new Map();
let fileBrowserRoot = FILE_BROWSER_ROOT_WORKSPACE;
let fileBrowserPath = '';
let fileBrowserSelectedPath = '';
let fileBrowserShowHiddenEntries = false;
let fileBrowserShowPycacheEntries = false;
let fileBrowserViewerFullscreen = false;
let fileBrowserMobileView = FILE_BROWSER_MOBILE_VIEW_LIST;
let fileBrowserCachedEntries = [];
let fileBrowserCachedTruncated = false;
let fileBrowserSelectedPaths = new Set();
let fileBrowserSelectionAnchorPath = '';
let fileBrowserBulkActionInFlight = false;
let fileBrowserSplitRatio = WORK_MODE_FILE_DEFAULT_SPLIT;
let fileBrowserResizePointerId = null;
let fileBrowserColumnResizeState = null;
let fileBrowserHorizontalSyncLock = false;
let fileBrowserColumnWidths = {
    name: WORK_MODE_FILE_COLUMN_DEFAULTS.name,
    size: WORK_MODE_FILE_COLUMN_DEFAULTS.size,
    modified: WORK_MODE_FILE_COLUMN_DEFAULTS.modified
};
let workModeSplitRatio = WORK_MODE_DEFAULT_SPLIT;
let workModeResizePointerId = null;
let workModeFileRoot = FILE_BROWSER_ROOT_WORKSPACE;
let workModeFilePath = '';
let workModeFileSelectedPath = '';
let workModeFileCachedEntries = [];
let workModeFileCachedTruncated = false;
let workModeFileSelectedPaths = new Set();
let workModeFileSelectionAnchorPath = '';
let workModeFileBulkActionInFlight = false;
let workModeFileViewerFullscreen = false;
let workModePreviewFullscreen = false;
let workModeFileSplitRatio = WORK_MODE_FILE_DEFAULT_SPLIT;
let workModeFileResizePointerId = null;
let workModeFileColumnResizeState = null;
let workModeFileHorizontalSyncLock = false;
let workModeMobileView = WORK_MODE_MOBILE_VIEW_CHAT;
let workModeMobileBrowseView = WORK_MODE_MOBILE_VIEW_LIST;
let workModeFileColumnWidths = {
    name: WORK_MODE_FILE_COLUMN_DEFAULTS.name,
    size: WORK_MODE_FILE_COLUMN_DEFAULTS.size,
    modified: WORK_MODE_FILE_COLUMN_DEFAULTS.modified
};
let workModeFileStatePersistTimer = null;
let pendingWorkModeFileScrollRestore = null;
let pendingWorkModeFileViewerScrollRestore = null;
let workModeHtmlPreviewState = {
    root: FILE_BROWSER_ROOT_WORKSPACE,
    path: '',
    previewUrl: '',
    suspended: false,
    viewerScroll: null
};
let fileBrowserEditState = {
    root: FILE_BROWSER_ROOT_WORKSPACE,
    path: '',
    editable: false,
    editing: false,
    dirty: false,
    saving: false,
    modifiedNs: '',
    previewResult: null,
    editBuffer: ''
};
let workModeFileEditState = {
    root: FILE_BROWSER_ROOT_WORKSPACE,
    path: '',
    editable: false,
    editing: false,
    dirty: false,
    saving: false,
    modifiedNs: '',
    previewResult: null,
    editBuffer: ''
};
let remoteStreamStatusCache = {
    streams: [],
    fetchedAt: 0
};
let remoteStreamPollTimer = null;
let remoteStreamStatusInFlight = false;
let sessionLoadLockStartedAt = 0;
let streamMonitorState = null;
let usageHistoryLastRequestedHours = USAGE_HISTORY_DEFAULT_HOURS;
let usageHistoryResizeRaf = 0;
let hoverTooltipInteractionsBound = false;
let hoverTooltipLayer = null;
let hoverTooltipAnchor = null;
let hoverTooltipRefreshRaf = null;
let liveWeatherCompactDatetime = '--';
let liveWeatherCompactCurrentTemp = '--';
let liveWeatherCompactWeatherText = '날씨 불러오는 중...';
let liveWeatherCompactHighTemp = '--';
let liveWeatherCompactLowTemp = '--';
let liveWeatherCompactHasWeather = false;
let mermaidRenderSerial = 0;
let mermaidLoadPromise = null;
let xlsxLoadPromise = null;
let lastAppliedMobileViewportHeight = null;
let lastAppliedMobilePromptLift = null;
let sessionsRenderFrameId = 0;

function runAfterAnimationFrame(callback) {
    if (typeof callback !== 'function') return 0;
    if (typeof window.requestAnimationFrame === 'function') {
        return window.requestAnimationFrame(() => {
            callback();
        });
    }
    return window.setTimeout(() => {
        callback();
    }, 16);
}

function createRafThrottledHandler(callback) {
    if (typeof callback !== 'function') {
        return () => {};
    }
    let frameId = 0;
    let queuedArgs = null;
    return (...args) => {
        queuedArgs = args;
        if (frameId) return;
        frameId = runAfterAnimationFrame(() => {
            frameId = 0;
            const latestArgs = queuedArgs;
            queuedArgs = null;
            callback(...(latestArgs || []));
        });
    };
}

function loadVendorScript(src) {
    const source = String(src || '').trim();
    if (!source) {
        return Promise.reject(new Error('스크립트 경로가 비어 있습니다.'));
    }
    if (typeof document === 'undefined' || !document.head) {
        return Promise.reject(new Error('문서를 사용할 수 없어 스크립트를 로드할 수 없습니다.'));
    }
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = source;
        script.async = true;
        script.defer = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`스크립트를 불러오지 못했습니다: ${source}`));
        document.head.appendChild(script);
    });
}

function ensureMermaidApiLoaded() {
    const mermaidApi = window.mermaid;
    if (
        mermaidApi
        && typeof mermaidApi.initialize === 'function'
        && typeof mermaidApi.render === 'function'
    ) {
        return Promise.resolve(mermaidApi);
    }
    if (!mermaidLoadPromise) {
        mermaidLoadPromise = loadVendorScript(MERMAID_VENDOR_SRC)
            .then(() => window.mermaid || null)
            .catch(error => {
                mermaidLoadPromise = null;
                throw error;
            });
    }
    return mermaidLoadPromise;
}

function ensureXlsxApiLoaded() {
    const xlsxApi = window.XLSX;
    if (xlsxApi && typeof xlsxApi.read === 'function') {
        return Promise.resolve(xlsxApi);
    }
    if (!xlsxLoadPromise) {
        xlsxLoadPromise = loadVendorScript(XLSX_VENDOR_SRC)
            .then(() => window.XLSX || null)
            .catch(error => {
                xlsxLoadPromise = null;
                throw error;
            });
    }
    return xlsxLoadPromise;
}

function scheduleSessionsRender() {
    if (sessionsRenderFrameId) return;
    sessionsRenderFrameId = runAfterAnimationFrame(() => {
        sessionsRenderFrameId = 0;
        renderSessions();
    });
}

function ensureSessionState(sessionId) {
    if (!sessionId) return null;
    if (!state.sessionStates[sessionId]) {
        state.sessionStates[sessionId] = {
            sending: false,
            pendingSend: null,
            streamId: null,
            queuedPrompts: [],
            queueFlushing: false,
            status: 'Idle',
            statusIsError: false,
            responseStartedAt: null,
            responseStatus: null
        };
    }
    return state.sessionStates[sessionId];
}

function getSessionState(sessionId) {
    if (!sessionId) return null;
    return state.sessionStates[sessionId] || null;
}

function getSessionStream(sessionId) {
    const sessionState = getSessionState(sessionId);
    if (!sessionState?.streamId) return null;
    return state.streams[sessionState.streamId] || null;
}

function isSessionStreaming(sessionId) {
    if (!sessionId) return false;
    if (getSessionStream(sessionId)) return true;
    return Boolean(state.remoteStreamSessions?.has(sessionId));
}

function isSessionBusy(sessionId) {
    const sessionState = getSessionState(sessionId);
    if (!sessionState) return false;
    const stream = getSessionStream(sessionId);
    const remoteStreaming = state.remoteStreamSessions?.has(sessionId);
    return Boolean(sessionState.sending || sessionState.pendingSend || stream || remoteStreaming);
}

function getQueuedPromptCount(sessionId) {
    const sessionState = getSessionState(sessionId);
    const queued = sessionState?.queuedPrompts;
    if (!Array.isArray(queued)) return 0;
    return queued.length;
}

function enqueuePrompt(sessionId, prompt, { planMode = false } = {}) {
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return 0;
    if (!Array.isArray(sessionState.queuedPrompts)) {
        sessionState.queuedPrompts = [];
    }
    sessionState.queuedPrompts.push({
        prompt: String(prompt || ''),
        planMode: Boolean(planMode),
        queuedAt: Date.now()
    });
    return sessionState.queuedPrompts.length;
}

async function flushQueuedPrompts(sessionId) {
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    if (sessionState.queueFlushing) return;
    if (isSessionBusy(sessionId)) return;
    if (!Array.isArray(sessionState.queuedPrompts) || sessionState.queuedPrompts.length === 0) return;
    sessionState.queueFlushing = true;
    try {
        while (!isSessionBusy(sessionId) && sessionState.queuedPrompts.length > 0) {
            const next = sessionState.queuedPrompts.shift();
            if (!next || typeof next.prompt !== 'string' || !next.prompt.trim()) {
                continue;
            }
            if (sessionId === state.activeSessionId) {
                syncActiveSessionControls();
            }
            await sendPrompt(next.prompt, {
                sessionId,
                planMode: Boolean(next.planMode)
            });
        }
    } finally {
        sessionState.queueFlushing = false;
        if (sessionId === state.activeSessionId) {
            syncActiveSessionControls();
        }
    }
}

function flushReadyQueuedPrompts(sessionIds = null) {
    const targets = new Set();
    if (Array.isArray(sessionIds) && sessionIds.length > 0) {
        sessionIds.forEach(sessionId => {
            if (sessionId) targets.add(String(sessionId));
        });
    } else {
        Object.keys(state.sessionStates || {}).forEach(sessionId => {
            if (sessionId) targets.add(String(sessionId));
        });
    }
    targets.forEach(sessionId => {
        if (!sessionId) return;
        if (getQueuedPromptCount(sessionId) <= 0) return;
        if (isSessionBusy(sessionId)) return;
        void flushQueuedPrompts(sessionId);
    });
}

function setSessionStatus(sessionId, message, isError = false) {
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    sessionState.status = message;
    sessionState.statusIsError = isError;
    updateResponseTimerForSession(sessionId, message, isError);
    if (sessionId === state.activeSessionId) {
        setStatus(message, isError);
    }
}

function formatElapsedTime(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
        return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function normalizeStartedAt(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return null;
    if (numeric < 1000000000000) {
        return Math.round(numeric * 1000);
    }
    return Math.round(numeric);
}

function getRemoteStreamState(sessionId) {
    if (!sessionId) return null;
    return state.remoteStreams.find(
        stream => (stream?.session_id || stream?.sessionId) === sessionId
    ) || null;
}

function getRemoteStreamStartedAt(sessionId) {
    const remoteStream = getRemoteStreamState(sessionId);
    return normalizeStartedAt(
        remoteStream?.started_at
        ?? remoteStream?.startedAt
        ?? remoteStream?.created_at
        ?? remoteStream?.createdAt
    );
}

function getKnownResponseStartedAt(sessionId) {
    if (!sessionId) return null;
    const sessionState = getSessionState(sessionId);
    return normalizeStartedAt(sessionState?.pendingSend?.startedAt)
        || normalizeStartedAt(getSessionStream(sessionId)?.startedAt)
        || getRemoteStreamStartedAt(sessionId);
}

function isResponseStatusMessage(message) {
    if (typeof message !== 'string') return false;
    return message.startsWith('Waiting for Codex') || message.startsWith('Receiving response');
}

function buildActiveStreamStatus(processRunning) {
    if (processRunning === true) {
        return 'Receiving response... (CLI running)';
    }
    if (processRunning === false) {
        return 'Receiving response... (CLI finalizing)';
    }
    return 'Receiving response...';
}

function buildStreamMonitorStatus(stream) {
    if (!stream) return 'Streaming...';
    if (stream.done) return 'Completed';

    const runtimeLabel = Number.isFinite(stream.runtimeMs) ? formatElapsedTime(stream.runtimeMs) : null;
    const idleLabel = Number.isFinite(stream.idleMs) ? formatElapsedTime(stream.idleMs) : null;

    if (stream.processRunning === true) {
        if (runtimeLabel && idleLabel) {
            return `Streaming · CLI running · ${runtimeLabel} elapsed · ${idleLabel} idle`;
        }
        if (runtimeLabel) {
            return `Streaming · CLI running · ${runtimeLabel} elapsed`;
        }
        return 'Streaming · CLI running';
    }

    if (stream.processRunning === false) {
        if (idleLabel) {
            return `Finalizing · CLI process exited · ${idleLabel} idle`;
        }
        return 'Finalizing · CLI process exited';
    }

    return 'Streaming...';
}

function buildStreamListMeta(stream) {
    const updated = formatStreamTimestamp(stream?.updated_at);
    const runtimeLabel = Number.isFinite(stream?.runtime_ms) ? formatElapsedTime(stream.runtime_ms) : null;
    const idleLabel = Number.isFinite(stream?.idle_ms) ? formatElapsedTime(stream.idle_ms) : null;
    let processLabel = 'Streaming';
    if (stream?.process_running === true) {
        processLabel = 'CLI running';
    } else if (stream?.process_running === false) {
        processLabel = 'CLI exited';
    }
    const parts = [processLabel];
    if (runtimeLabel) parts.push(`${runtimeLabel} elapsed`);
    if (idleLabel) parts.push(`${idleLabel} idle`);
    if (updated) {
        parts.push(`Updated ${updated}`);
    } else if (stream?.id) {
        parts.push(`Stream ${stream.id.slice(0, 6)}`);
    }
    return parts.join(' · ');
}

function updateStatusDisplay() {
    const status = document.getElementById('codex-chat-status');
    if (!status) return;
    const sessionId = state.activeSessionId;
    const sessionState = sessionId ? getSessionState(sessionId) : null;
    const baseMessage = state.statusMessage || 'Idle';
    if (sessionState?.responseStartedAt && sessionState.responseStatus) {
        const elapsed = Date.now() - sessionState.responseStartedAt;
        const timeLabel = formatElapsedTime(elapsed);
        status.textContent = `${sessionState.responseStatus} · ${timeLabel}`;
    } else {
        status.textContent = baseMessage;
    }
    status.classList.toggle('is-error', state.statusIsError);
}

function stopResponseTimer() {
    if (state.responseTimerId) {
        window.clearInterval(state.responseTimerId);
        state.responseTimerId = null;
    }
    state.responseTimerSessionId = null;
}

function syncResponseTimerForActiveSession() {
    const sessionId = state.activeSessionId;
    const sessionState = sessionId ? getSessionState(sessionId) : null;
    const shouldRun = Boolean(sessionState?.responseStartedAt && sessionState.responseStatus);
    if (!shouldRun) {
        stopResponseTimer();
        updateStatusDisplay();
        return;
    }
    if (state.responseTimerSessionId !== sessionId) {
        stopResponseTimer();
        state.responseTimerSessionId = sessionId;
    }
    if (!state.responseTimerId) {
        state.responseTimerId = window.setInterval(updateStatusDisplay, 1000);
    }
    updateStatusDisplay();
}

function updateResponseTimerForSession(sessionId, message, isError = false) {
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    const responseStatus = isResponseStatusMessage(message);
    if (!isError && responseStatus) {
        sessionState.responseStartedAt = getKnownResponseStartedAt(sessionId)
            || sessionState.responseStartedAt
            || Date.now();
        sessionState.responseStatus = message;
    } else {
        sessionState.responseStartedAt = null;
        sessionState.responseStatus = null;
    }
    if (sessionId === state.activeSessionId) {
        syncResponseTimerForActiveSession();
    }
}

function syncActiveSessionStatus() {
    const sessionId = state.activeSessionId;
    const sessionState = getSessionState(sessionId);
    if (!sessionState) {
        setStatus('Idle');
        syncResponseTimerForActiveSession();
        return;
    }
    setStatus(sessionState.status || 'Idle', Boolean(sessionState.statusIsError));
    syncResponseTimerForActiveSession();
}

function syncActiveSessionControls() {
    const input = document.getElementById('codex-chat-input');
    const sendBtn = document.getElementById('codex-chat-send');
    const sessionId = state.activeSessionId;
    const sessionState = sessionId ? getSessionState(sessionId) : null;
    const localBusy = sessionId
        ? Boolean(sessionState?.sending || sessionState?.pendingSend || getSessionStream(sessionId))
        : false;
    const remoteBusy = sessionId ? Boolean(state.remoteStreamSessions?.has(sessionId)) : false;
    const queueCount = sessionId ? getQueuedPromptCount(sessionId) : 0;
    const hasDraftPrompt = Boolean(input?.value?.trim());
    const showQueue = sessionId ? (localBusy && hasDraftPrompt) : false;
    const showStop = sessionId ? (localBusy && !hasDraftPrompt) : false;
    const lockInput = sessionId ? (remoteBusy && !localBusy) : false;
    if (input) {
        input.disabled = lockInput;
        input.readOnly = lockInput;
        input.setAttribute('aria-disabled', String(lockInput));
        input.placeholder = lockInput
            ? 'Another client is responding for this session...'
            : localBusy
                ? `Response in progress... queue ready${queueCount > 0 ? ` (${queueCount} queued)` : ''}`
            : CHAT_INPUT_DEFAULT_PLACEHOLDER;
    }
    if (sendBtn) {
        sendBtn.disabled = remoteBusy && !localBusy;
        sendBtn.dataset.mode = showQueue ? 'queue' : (showStop ? 'stop' : 'send');
        if (queueCount > 0) {
            sendBtn.dataset.queueCount = String(queueCount);
        } else {
            delete sendBtn.dataset.queueCount;
        }
        const label = showQueue ? 'Queue' : (showStop ? 'Stop' : 'Send');
        sendBtn.setAttribute('aria-label', label);
        sendBtn.setAttribute('title', label);
        const srLabel = sendBtn.querySelector('.sr-only');
        if (srLabel) {
            srLabel.textContent = label;
        }
    }
    const imageAttachBtn = document.getElementById('codex-chat-image-attach');
    if (imageAttachBtn && imageAttachBtn.getAttribute('aria-busy') !== 'true') {
        imageAttachBtn.disabled = remoteBusy && !localBusy;
    }
    renderRunningJobsMonitor();
}

function appendTextToChatInput(text) {
    const input = document.getElementById('codex-chat-input');
    const addition = String(text || '');
    if (!input || !addition.trim()) return false;
    const current = String(input.value || '');
    input.value = current.trim()
        ? `${current.replace(/\s+$/u, '')}\n\n${addition}`
        : addition;
    input.focus();
    const length = input.value.length;
    if (typeof input.setSelectionRange === 'function') {
        input.setSelectionRange(length, length);
    }
    syncActiveSessionControls();
    return true;
}

function normalizeChatAttachment(attachment) {
    if (!attachment || typeof attachment !== 'object') return null;
    const path = typeof attachment.path === 'string' ? attachment.path.trim() : '';
    if (!path) return null;
    return {
        id: typeof attachment.id === 'string' && attachment.id.trim()
            ? attachment.id.trim()
            : path,
        name: typeof attachment.name === 'string' && attachment.name.trim()
            ? attachment.name.trim()
            : (typeof attachment.original_name === 'string' ? attachment.original_name.trim() : 'image'),
        original_name: typeof attachment.original_name === 'string' ? attachment.original_name.trim() : '',
        path,
        relative_path: typeof attachment.relative_path === 'string' ? attachment.relative_path.trim() : '',
        mime_type: typeof attachment.mime_type === 'string' ? attachment.mime_type.trim() : '',
        size: Number.isFinite(Number(attachment.size)) ? Math.max(0, Math.round(Number(attachment.size))) : 0
    };
}

function getPendingAttachmentPayload() {
    return (Array.isArray(state.pendingAttachments) ? state.pendingAttachments : [])
        .map(normalizeChatAttachment)
        .filter(Boolean);
}

function renderPendingAttachments() {
    const container = document.getElementById('codex-chat-attachments');
    if (!container) return;
    const attachments = getPendingAttachmentPayload();
    container.innerHTML = '';
    container.classList.toggle('is-empty', attachments.length === 0);
    attachments.forEach(attachment => {
        const chip = document.createElement('span');
        chip.className = 'chat-attachment-chip';
        chip.title = attachment.relative_path || attachment.path;

        const label = document.createElement('span');
        label.className = 'chat-attachment-name';
        label.textContent = attachment.name || 'image';

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'chat-attachment-remove';
        remove.setAttribute('aria-label', `Remove ${attachment.name || 'image'}`);
        remove.setAttribute('title', 'Remove');
        remove.addEventListener('click', event => {
            event.preventDefault();
            state.pendingAttachments = getPendingAttachmentPayload()
                .filter(item => item.id !== attachment.id);
            renderPendingAttachments();
            syncActiveSessionControls();
        });

        chip.appendChild(label);
        chip.appendChild(remove);
        container.appendChild(chip);
    });
}

function clearPendingAttachments() {
    state.pendingAttachments = [];
    renderPendingAttachments();
    const input = document.getElementById('codex-chat-image-input');
    if (input) {
        input.value = '';
    }
    syncActiveSessionControls();
}

async function uploadChatAttachmentFiles(fileList) {
    const files = Array.from(fileList || []).filter(Boolean);
    if (files.length === 0) return [];
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    const result = await fetchJson('/api/codex/attachments', {
        method: 'POST',
        body: formData,
        timeoutMs: CHAT_ATTACHMENT_UPLOAD_TIMEOUT_MS
    });
    const uploaded = Array.isArray(result?.attachments)
        ? result.attachments.map(normalizeChatAttachment).filter(Boolean)
        : [];
    if (uploaded.length > 0) {
        const merged = getPendingAttachmentPayload();
        uploaded.forEach(attachment => {
            if (!merged.some(item => item.path === attachment.path)) {
                merged.push(attachment);
            }
        });
        state.pendingAttachments = merged;
        renderPendingAttachments();
        syncActiveSessionControls();
    }
    return uploaded;
}

function resolveRunningJobSessionTitle(sessionId) {
    const targetId = String(sessionId || '').trim();
    if (!targetId) return 'Session';
    const summary = state.sessions.find(session => session?.id === targetId);
    const title = String(summary?.title || '').trim();
    if (title) return title;
    if (targetId === state.activeSessionId) {
        const headerTitle = String(document.getElementById('codex-chat-title')?.textContent || '').trim();
        if (headerTitle && headerTitle !== 'Select a session') {
            return headerTitle;
        }
    }
    return `Session ${targetId.slice(0, 8)}`;
}

function resolveRemoteRuntimeMs(remoteStream, nowMs) {
    if (!remoteStream) return null;
    const runtimeMs = Number(remoteStream.runtime_ms ?? remoteStream.runtimeMs);
    if (Number.isFinite(runtimeMs) && runtimeMs >= 0) {
        return Math.max(0, Math.round(runtimeMs));
    }
    const startedAt = normalizeStartedAt(
        remoteStream.started_at
        ?? remoteStream.startedAt
        ?? remoteStream.created_at
        ?? remoteStream.createdAt
    );
    if (!startedAt) return null;
    return Math.max(0, nowMs - startedAt);
}

function collectRunningJobs() {
    const sessionIds = new Set();
    state.sessions.forEach(session => {
        if (session?.id) sessionIds.add(session.id);
    });
    Object.keys(state.sessionStates || {}).forEach(sessionId => {
        if (sessionId) sessionIds.add(sessionId);
    });
    Object.values(state.streams || {}).forEach(stream => {
        if (stream?.sessionId) sessionIds.add(stream.sessionId);
    });
    (state.remoteStreams || []).forEach(stream => {
        const sessionId = stream?.session_id || stream?.sessionId;
        if (sessionId) sessionIds.add(sessionId);
    });

    const nowMs = Date.now();
    const jobs = [];
    sessionIds.forEach(sessionId => {
        const sessionState = getSessionState(sessionId);
        const localStream = getSessionStream(sessionId);
        const remoteStream = getRemoteStreamState(sessionId);
        const hasRemoteStream = Boolean(state.remoteStreamSessions?.has(sessionId) || remoteStream);
        if (!localStream && !sessionState?.pendingSend && !hasRemoteStream) return;

        let phase = '';
        let elapsedMs = null;
        let order = 3;

        if (localStream) {
            phase = localStream.processRunning === false ? 'CLI finalizing' : 'CLI running';
            elapsedMs = Number.isFinite(localStream.runtimeMs)
                ? Math.max(0, Math.round(localStream.runtimeMs))
                : Math.max(0, nowMs - (normalizeStartedAt(localStream.startedAt) || nowMs));
            order = 0;
        } else if (sessionState?.pendingSend) {
            phase = 'Submitting';
            const pendingStartedAt = normalizeStartedAt(sessionState.pendingSend.startedAt);
            elapsedMs = pendingStartedAt ? Math.max(0, nowMs - pendingStartedAt) : null;
            order = 1;
        } else if (hasRemoteStream) {
            const processRunning = remoteStream?.process_running;
            if (processRunning === true) {
                phase = 'Remote CLI running';
            } else if (processRunning === false) {
                phase = 'Remote finalizing';
            } else {
                phase = 'Remote streaming';
            }
            elapsedMs = resolveRemoteRuntimeMs(remoteStream, nowMs);
            order = 2;
        }

        jobs.push({
            sessionId,
            title: resolveRunningJobSessionTitle(sessionId),
            phase,
            elapsedMs,
            order,
            active: sessionId === state.activeSessionId
        });
    });

    jobs.sort((left, right) => {
        const activeDiff = Number(right.active) - Number(left.active);
        if (activeDiff !== 0) return activeDiff;
        const orderDiff = (left.order || 0) - (right.order || 0);
        if (orderDiff !== 0) return orderDiff;
        const elapsedLeft = Number.isFinite(left.elapsedMs) ? left.elapsedMs : -1;
        const elapsedRight = Number.isFinite(right.elapsedMs) ? right.elapsedMs : -1;
        return elapsedRight - elapsedLeft;
    });
    return jobs;
}

function renderRunningJobsMonitor() {
    const monitor = document.getElementById('codex-chat-job-monitor');
    const summary = document.getElementById('codex-chat-job-monitor-summary');
    const list = document.getElementById('codex-chat-job-monitor-list');
    const runtimeStrip = monitor?.closest('.chat-runtime-strip');
    if (!monitor || !summary || !list) return;

    const jobs = collectRunningJobs();
    if (jobs.length === 0) {
        monitor.classList.add('is-idle');
        runtimeStrip?.classList.add('is-idle');
        summary.textContent = 'Job 없음';
        list.innerHTML = '';
        return;
    }

    monitor.classList.remove('is-idle');
    runtimeStrip?.classList.remove('is-idle');
    summary.textContent = jobs.length === 1
        ? 'Job 1개 실행 중'
        : `Job ${jobs.length}개 실행 중`;
    list.innerHTML = '';

    const maxVisible = isCompactLayout() ? 2 : 3;
    jobs.slice(0, maxVisible).forEach(job => {
        const item = document.createElement('li');
        item.className = 'chat-job-monitor-item';
        if (job.active) {
            item.classList.add('is-active');
        }
        const elapsedText = Number.isFinite(job.elapsedMs) ? formatElapsedTime(job.elapsedMs) : '';
        item.textContent = elapsedText
            ? `${job.title} · ${job.phase} · ${elapsedText}`
            : `${job.title} · ${job.phase}`;
        list.appendChild(item);
    });

    if (jobs.length > maxVisible) {
        const moreItem = document.createElement('li');
        moreItem.className = 'chat-job-monitor-item is-more';
        moreItem.textContent = `외 ${jobs.length - maxVisible}개`;
        list.appendChild(moreItem);
    }
}

function startRunningJobsMonitorTicker() {
    renderRunningJobsMonitor();
    if (state.jobMonitorTimerId) {
        window.clearInterval(state.jobMonitorTimerId);
    }
    state.jobMonitorTimerId = window.setInterval(renderRunningJobsMonitor, 1000);
}

function appendMessageToDOMIfActive(sessionId, message, roleOverride = null) {
    if (sessionId !== state.activeSessionId) return null;
    return appendMessageToDOM(message, roleOverride);
}

function getMessageEntryFromWrapper(wrapper) {
    if (!wrapper) return null;
    const bubble = wrapper.querySelector('.message-bubble');
    const meta = wrapper.querySelector('.message-meta');
    const footer = wrapper.querySelector('.message-footer');
    if (!bubble || !meta || !footer) return null;
    return { wrapper, bubble, meta, footer };
}

function findMessageEntryById(messageId) {
    const targetId = typeof messageId === 'string' ? messageId.trim() : '';
    if (!targetId) return null;
    const container = document.getElementById('codex-chat-messages');
    if (!container) return null;
    const wrappers = container.querySelectorAll('.message');
    for (const wrapper of wrappers) {
        if (String(wrapper?.dataset?.messageId || '').trim() !== targetId) {
            continue;
        }
        const entry = getMessageEntryFromWrapper(wrapper);
        if (entry) {
            return entry;
        }
    }
    return null;
}

function detachSessionStreamEntry(sessionId) {
    const stream = getSessionStream(sessionId);
    if (!stream) return;
    if (stream.entry?.wrapper) {
        setMessageStreaming(stream.entry.wrapper, false);
    }
    stream.entry = null;
}

function attachSessionStreamEntry(sessionId) {
    const stream = getSessionStream(sessionId);
    if (!stream) return;
    if (stream.entry?.wrapper?.isConnected) return;
    let assistantEntry = findMessageEntryById(stream.messageId);
    if (!assistantEntry) {
        assistantEntry = appendMessageToDOM({
            id: stream.messageId || '',
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString()
        }, 'assistant');
    }
    if (!assistantEntry) return;
    stream.entry = assistantEntry;
    setMessageStreaming(assistantEntry.wrapper, true);
    if (stream.tokenUsage) {
        setMessageTokenUsage(
            assistantEntry.footer,
            { role: 'assistant', token_usage: stream.tokenUsage, content: stream.output || '' }
        );
    }
    updateStreamEntry(stream);
}

function createStreamState({
    id,
    sessionId,
    entry = null,
    output = '',
    error = '',
    tokenUsage = null,
    outputOffset = 0,
    errorOffset = 0,
    eventOffset = 0,
    startedAt = null,
    messageId = ''
}) {
    if (!id || !sessionId) return null;
    const normalizedStartedAt = normalizeStartedAt(startedAt) || Date.now();
    const stream = {
        id,
        sessionId,
        messageId: typeof messageId === 'string' ? messageId.trim() : '',
        outputOffset,
        errorOffset,
        eventOffset,
        output,
        error,
        tokenUsage,
        entry,
        startedAt: normalizedStartedAt,
        processRunning: null,
        processPid: null,
        runtimeMs: null,
        idleMs: null,
        timer: null,
        polling: false,
        failureCount: 0,
        pollDelay: STREAM_POLL_BASE_MS
    };
    state.streams[id] = stream;
    const sessionState = ensureSessionState(sessionId);
    if (sessionState) {
        sessionState.streamId = id;
        sessionState.sending = true;
        sessionState.responseStartedAt = normalizedStartedAt;
    }
    return stream;
}

function clearStreamState(streamId) {
    const stream = state.streams[streamId];
    if (!stream) return;
    if (stream.timer) {
        clearTimeout(stream.timer);
        stream.timer = null;
    }
    if (stream.entry?.wrapper) {
        setMessageStreaming(stream.entry.wrapper, false);
    }
    const sessionState = getSessionState(stream.sessionId);
    if (sessionState?.streamId === streamId) {
        sessionState.streamId = null;
    }
    delete state.streams[streamId];
}

function readOptionsFromData(element) {
    if (!element) return [];
    const raw = element.getAttribute('data-options');
    if (!raw) return [];
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
        // Ignore invalid JSON so we can fall back to API-loaded options.
        void error;
        return [];
    }
}

function normalizeOptionList(options) {
    if (!Array.isArray(options)) return [];
    const normalized = [];
    const seen = new Set();
    options.forEach(item => {
        const token = typeof item === 'string' ? item.trim() : '';
        if (!token || seen.has(token)) return;
        normalized.push(token);
        seen.add(token);
    });
    return normalized;
}

function normalizeModelCatalog(catalog) {
    if (!Array.isArray(catalog)) return [];
    const normalized = [];
    const seen = new Set();
    catalog.forEach(entry => {
        const slug = typeof entry?.slug === 'string' ? entry.slug.trim() : '';
        if (!slug || seen.has(slug)) return;
        const reasoningOptions = normalizeOptionList(entry?.reasoning_options);
        let defaultReasoningEffort = typeof entry?.default_reasoning_effort === 'string'
            ? entry.default_reasoning_effort.trim()
            : '';
        if (defaultReasoningEffort && !reasoningOptions.includes(defaultReasoningEffort)) {
            reasoningOptions.unshift(defaultReasoningEffort);
        }
        if (!defaultReasoningEffort && reasoningOptions.length > 0) {
            defaultReasoningEffort = reasoningOptions[0];
        }
        normalized.push({
            slug,
            defaultReasoningEffort: defaultReasoningEffort || null,
            reasoningOptions
        });
        seen.add(slug);
    });
    return normalized;
}

function collectCatalogModelOptions(catalog) {
    return normalizeOptionList(
        Array.isArray(catalog)
            ? catalog.map(entry => entry?.slug)
            : []
    );
}

function collectCatalogReasoningOptions(catalog) {
    return normalizeOptionList(
        Array.isArray(catalog)
            ? catalog.flatMap(entry => Array.isArray(entry?.reasoningOptions) ? entry.reasoningOptions : [])
            : []
    );
}

function getModelCatalogEntry(model) {
    const normalizedModel = typeof model === 'string' ? model.trim() : '';
    if (!normalizedModel) return null;
    return Array.isArray(state.settings.modelCatalog)
        ? state.settings.modelCatalog.find(entry => entry.slug === normalizedModel) || null
        : null;
}

function getReasoningProfile(model, reasoning, fallbackOptions = null) {
    const entry = getModelCatalogEntry(model);
    const reasoningOptions = entry?.reasoningOptions?.length
        ? entry.reasoningOptions
        : normalizeOptionList(fallbackOptions || state.settings.reasoningOptions);
    const explicitReasoning = typeof reasoning === 'string' ? reasoning.trim() : '';
    const defaultReasoning = entry?.defaultReasoningEffort || '';
    const isExplicitSupported = Boolean(explicitReasoning)
        && (reasoningOptions.length === 0 || reasoningOptions.includes(explicitReasoning));
    const effectiveReasoning = isExplicitSupported
        ? explicitReasoning
        : (defaultReasoning || explicitReasoning || '');
    return {
        defaultReasoning,
        effectiveReasoning,
        explicitReasoning,
        isExplicit: isExplicitSupported || (!defaultReasoning && Boolean(explicitReasoning)),
        reasoningOptions
    };
}

function buildReasoningPlaceholder(defaultReasoning, fallbackText) {
    return defaultReasoning ? `${fallbackText} (${defaultReasoning})` : fallbackText;
}

function formatReasoningStatus(model, reasoning) {
    const profile = getReasoningProfile(model, reasoning);
    if (!profile.effectiveReasoning) {
        return 'default';
    }
    return profile.isExplicit
        ? profile.effectiveReasoning
        : `${profile.effectiveReasoning} (default)`;
}

function primeSettingsOptionsFromDom(modelSelect, reasoningSelect, planModeModelSelect, planModeReasoningSelect) {
    const modelOptions = readOptionsFromData(modelSelect);
    const planModeModelOptions = readOptionsFromData(planModeModelSelect);
    const reasoningOptions = readOptionsFromData(reasoningSelect);
    const planModeReasoningOptions = readOptionsFromData(planModeReasoningSelect);
    if (modelOptions.length > 0) {
        state.settings.modelOptions = modelOptions;
    } else if (planModeModelOptions.length > 0) {
        state.settings.modelOptions = planModeModelOptions;
    }
    if (reasoningOptions.length > 0) {
        state.settings.reasoningOptions = reasoningOptions;
    } else if (planModeReasoningOptions.length > 0) {
        state.settings.reasoningOptions = planModeReasoningOptions;
    }
    if (
        modelOptions.length > 0
        || planModeModelOptions.length > 0
        || reasoningOptions.length > 0
        || planModeReasoningOptions.length > 0
    ) {
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updatePlanModeModelControls(state.settings.planModeModel, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        updatePlanModeReasoningControls(state.settings.planModeReasoningEffort, state.settings.reasoningOptions);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('codex-chat-form');
    const input = document.getElementById('codex-chat-input');
    const imageAttachBtn = document.getElementById('codex-chat-image-attach');
    const imageInput = document.getElementById('codex-chat-image-input');
    const newSessionBtn = document.getElementById('codex-chat-new-session');
    const newSessionInlineBtn = document.getElementById('codex-chat-new-session-inline');
    const chatSessionPrevBtn = document.getElementById('codex-chat-session-prev');
    const chatSessionNextBtn = document.getElementById('codex-chat-session-next');
    const refreshBtn = document.getElementById('codex-chat-refresh');
    const chatFullscreenBtn = document.getElementById('codex-chat-fullscreen');
    const chatTitleTrigger = document.getElementById('codex-chat-title');
    const messages = document.getElementById('codex-chat-messages');
    const scrollToLatestBtn = document.getElementById('codex-chat-scroll-bottom');
    const streamMonitorCloseBtn = document.getElementById('codex-stream-monitor-close');
    const streamMonitorToggle = document.getElementById('codex-stream-monitor-toggle');
    const streamMonitor = document.getElementById('codex-stream-monitor');
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    const compactMedia = window.matchMedia(MOBILE_MEDIA_QUERY);
    const phoneMedia = window.matchMedia(PHONE_MEDIA_QUERY);
    const themeToggle = document.getElementById('codex-theme-toggle');
    const themeMedia = window.matchMedia(THEME_MEDIA_QUERY);
    const modelSelect = document.getElementById('codex-model-select');
    const modelInput = document.getElementById('codex-model-input');
    const modelApply = document.getElementById('codex-model-apply');
    const planModeModelSelect = document.getElementById('codex-plan-mode-model-select');
    const planModeModelInput = document.getElementById('codex-plan-mode-model-input');
    const planModeReasoningSelect = document.getElementById('codex-plan-mode-reasoning-select');
    const planModeReasoningInput = document.getElementById('codex-plan-mode-reasoning-input');
    const planModeToggle = document.getElementById('codex-plan-mode-toggle');
    const reasoningSelect = document.getElementById('codex-reasoning-select');
    const reasoningInput = document.getElementById('codex-reasoning-input');
    const controlsToggle = document.getElementById('codex-controls-toggle');
    const controls = document.getElementById('codex-controls');
    const usageHistoryOpen = document.getElementById('codex-usage-history-open');
    const usageRefreshBtn = document.getElementById('codex-usage-refresh');
    const gitBranch = document.getElementById('codex-git-branch');
    const gitCommitBtn = document.getElementById('codex-git-commit');
    const gitPushBtn = document.getElementById('codex-git-push');
    const gitSyncBtn = document.getElementById('codex-git-sync');
    const fileBrowserBtn = document.getElementById('codex-file-browser-open');
    const workModeToggleBtn = document.getElementById('codex-work-mode-toggle');
    const workModeDivider = document.getElementById('codex-work-mode-divider');
    const workModeFileRefreshBtn = document.getElementById('codex-work-mode-file-refresh');
    const workModeFileUpBtn = document.getElementById('codex-work-mode-file-up');
    const workModeFileBackBtn = document.getElementById('codex-work-mode-file-back');
    const workModeChatBackBtn = document.getElementById('codex-work-mode-chat-back');
    const workModeTerminalOpenBtn = document.getElementById('codex-work-mode-terminal-open');
    const workModeFileOpenNewBtn = document.getElementById('codex-work-mode-file-open-new');
    const workModeMobileBrowserBtn = document.getElementById('codex-work-mode-mobile-browser');
    const workModeFileFullscreenBtn = document.getElementById('codex-work-mode-file-fullscreen');
    const workModeFileNewFileBtn = document.getElementById('codex-work-mode-file-new-file');
    const workModeFileDeleteDirectoryBtn = document.getElementById('codex-work-mode-file-delete-directory');
    const workModeFileAddContextBtn = document.getElementById('codex-work-mode-file-add-context');
    const workModeFileMoveBtn = document.getElementById('codex-work-mode-file-move');
    const workModeFileSelectAllBtn = document.getElementById('codex-work-mode-file-select-all');
    const workModeFileClearSelectionBtn = document.getElementById('codex-work-mode-file-clear-selection');
    const workModeFileDownloadBtn = document.getElementById('codex-work-mode-file-download');
    const workModeFileDeleteBtn = document.getElementById('codex-work-mode-file-delete');
    const workModeFileEditBtn = document.getElementById('codex-work-mode-file-edit');
    const workModeFileSaveBtn = document.getElementById('codex-work-mode-file-save');
    const workModeFileDivider = document.getElementById('codex-work-mode-file-divider');
    const workModeFileGridScroll = document.getElementById('codex-work-mode-file-grid-scroll');
    const workModeFileHScroll = document.getElementById('codex-work-mode-file-hscroll');
    const workModeFileViewerContent = document.getElementById('codex-work-mode-file-viewer-content');
    const workModeFileColumnResizers = Array.from(
        document.querySelectorAll('#codex-work-mode-file-columns [data-resize-col]')
    );
    const branchOverlayCommitBtn = document.getElementById('codex-branch-overlay-commit');
    const branchOverlayPushBtn = document.getElementById('codex-branch-overlay-push');
    const branchOverlayStageAllBtn = document.getElementById('codex-branch-overlay-stage-all');
    const branchOverlayStageNoneBtn = document.getElementById('codex-branch-overlay-stage-none');
    const branchOverlayCommitMessageInput = document.getElementById('codex-branch-overlay-commit-message');
    const syncOverlayFetchBtn = document.getElementById('codex-sync-overlay-fetch');
    const syncOverlaySyncBtn = document.getElementById('codex-sync-overlay-sync');
    const syncOverlayCommitBtn = document.getElementById('codex-sync-overlay-commit');
    const syncOverlayPushBtn = document.getElementById('codex-sync-overlay-push');
    const syncOverlayRefreshBtn = document.getElementById('codex-sync-overlay-refresh');
    const messageLogOverlay = document.getElementById('codex-message-log-overlay');
    const messageLogOverlayClose = document.getElementById('codex-message-log-overlay-close');
    const messageLogOverlayCloseFooter = document.getElementById('codex-message-log-overlay-close-footer');
    const mobileSessionOverlay = document.getElementById('codex-mobile-session-overlay');
    const mobileSessionOverlayClose = document.getElementById('codex-mobile-session-overlay-close');
    const mobileSessionOverlayCloseFooter = document.getElementById('codex-mobile-session-overlay-close-footer');
    const usageHistoryOverlay = document.getElementById('codex-usage-history-overlay');
    const usageHistoryOverlayClose = document.getElementById('codex-usage-history-overlay-close');
    const usageHistoryOverlayCloseFooter = document.getElementById('codex-usage-history-overlay-close-footer');
    const fileBrowserOverlay = document.getElementById('codex-file-browser-overlay');
    const fileBrowserOverlayClose = document.getElementById('codex-file-browser-overlay-close');
    const fileBrowserOverlayCloseFooter = document.getElementById('codex-file-browser-overlay-close-footer');
    const fileBrowserRefreshBtn = document.getElementById('codex-file-browser-refresh');
    const fileBrowserBackBtn = document.getElementById('codex-file-browser-back');
    const fileBrowserTerminalOpenBtn = document.getElementById('codex-file-browser-terminal-open');
    const fileBrowserUpBtn = document.getElementById('codex-file-browser-up');
    const fileBrowserFullscreenBtn = document.getElementById('codex-file-browser-fullscreen');
    const fileBrowserNewFileBtn = document.getElementById('codex-file-browser-new-file');
    const fileBrowserDeleteDirectoryBtn = document.getElementById('codex-file-browser-delete-directory');
    const fileBrowserAddContextBtn = document.getElementById('codex-file-browser-add-context');
    const fileBrowserMoveBtn = document.getElementById('codex-file-browser-move');
    const fileBrowserSelectAllBtn = document.getElementById('codex-file-browser-select-all');
    const fileBrowserClearSelectionBtn = document.getElementById('codex-file-browser-clear-selection');
    const fileBrowserDownloadBtn = document.getElementById('codex-file-browser-download');
    const fileBrowserDeleteBtn = document.getElementById('codex-file-browser-delete');
    const fileBrowserEditBtn = document.getElementById('codex-file-browser-edit');
    const fileBrowserSaveBtn = document.getElementById('codex-file-browser-save');
    const fileBrowserDivider = document.getElementById('codex-file-browser-divider');
    const fileBrowserGridScroll = document.getElementById('codex-file-browser-grid-scroll');
    const fileBrowserHScroll = document.getElementById('codex-file-browser-hscroll');
    const fileBrowserColumnResizers = Array.from(
        document.querySelectorAll('#codex-file-browser-columns [data-resize-col]')
    );
    const fileBrowserShowHiddenToggle = document.getElementById('codex-file-browser-show-hidden');
    const fileBrowserShowPycacheToggle = document.getElementById('codex-file-browser-show-pycache');
    const terminalOverlay = document.getElementById('codex-terminal-overlay');
    const terminalOverlayClose = document.getElementById('codex-terminal-overlay-close');
    const terminalOverlayNewTabBtn = document.getElementById('codex-terminal-overlay-new-tab');
    const terminalOverlayCloseTabBtn = document.getElementById('codex-terminal-overlay-close-tab');
    const terminalOverlayCloseFooter = document.getElementById('codex-terminal-overlay-close-footer');
    const headerDetailsTrigger = document.getElementById('codex-header-details-trigger');
    const syncOverlayTargetButtons = Array.from(
        document.querySelectorAll('#codex-sync-overlay .sync-overlay-target[data-repo-target]')
    );

    // Reset git highlights until fresh git status arrives.
    updateGitCommitButtonState({ count: 0, changedFiles: [] });
    updateGitPushButtonState({ aheadCount: 0 });
    initializeHoverTooltipInteractions();
    initializeHeaderActionTooltips({
        themeToggle,
        gitBranch,
        gitCommitBtn,
        gitPushBtn,
        gitSyncBtn,
        fileBrowserBtn,
        workModeToggleBtn,
        refreshBtn
    });
    syncFileBrowserOpenButtonState(false);

    if (form) {
        form.addEventListener('submit', handleSubmit);
    }

    if (input) {
        input.addEventListener('keydown', event => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
            }
        });
        input.addEventListener('input', () => {
            syncActiveSessionControls();
        });
    }

    if (imageAttachBtn && imageInput) {
        imageAttachBtn.addEventListener('click', event => {
            event.preventDefault();
            imageInput.click();
        });
        imageInput.addEventListener('change', async () => {
            const selectedFiles = Array.from(imageInput.files || []);
            if (selectedFiles.length === 0) return;
            imageAttachBtn.disabled = true;
            imageAttachBtn.setAttribute('aria-busy', 'true');
            try {
                const uploaded = await uploadChatAttachmentFiles(selectedFiles);
                if (uploaded.length > 0) {
                    showToast(`이미지 ${uploaded.length}개를 첨부했습니다.`, {
                        tone: 'success',
                        durationMs: 1800
                    });
                }
            } catch (error) {
                showToast(normalizeError(error, '이미지 첨부에 실패했습니다.'), {
                    tone: 'error',
                    durationMs: 4200
                });
            } finally {
                imageInput.value = '';
                imageAttachBtn.disabled = false;
                imageAttachBtn.removeAttribute('aria-busy');
                syncActiveSessionControls();
            }
        });
    }
    renderPendingAttachments();

    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', async () => {
            await createSession(true);
        });
    }

    if (newSessionInlineBtn) {
        newSessionInlineBtn.addEventListener('click', async () => {
            await createSession(true);
        });
    }

    if (chatSessionPrevBtn) {
        chatSessionPrevBtn.addEventListener('click', async () => {
            await moveToAdjacentSession(-1);
        });
    }

    if (chatSessionNextBtn) {
        chatSessionNextBtn.addEventListener('click', async () => {
            await moveToAdjacentSession(1);
        });
    }

    if (chatTitleTrigger) {
        chatTitleTrigger.addEventListener('click', event => {
            const canOpenOverlay = isPhoneLayout() || isWorkModeEnabled();
            if (!canOpenOverlay) return;
            event.preventDefault();
            if (isMobileSessionOverlayOpen()) {
                closeMobileSessionOverlay();
                return;
            }
            openMobileSessionOverlay();
        });
    }

    if (headerDetailsTrigger) {
        headerDetailsTrigger.addEventListener('click', event => {
            event.preventDefault();
            void showHeaderDetailsToast();
        });
    }

    if (gitCommitBtn) {
        gitCommitBtn.addEventListener('click', event => {
            event.preventDefault();
            void handleGitQuickCommit(gitCommitBtn);
        });
    }

    if (gitPushBtn) {
        gitPushBtn.addEventListener('click', () => {
            void handleGitPush(gitPushBtn);
        });
    }
    if (gitSyncBtn) {
        gitSyncBtn.addEventListener('click', event => {
            event.preventDefault();
            openGitSyncOverlay();
        });
    }
    if (fileBrowserBtn) {
        fileBrowserBtn.addEventListener('click', event => {
            event.preventDefault();
            if (isFileBrowserOverlayOpen()) {
                closeFileBrowserOverlay();
                return;
            }
            openFileBrowserOverlay();
        });
    }
    if (workModeToggleBtn) {
        workModeToggleBtn.addEventListener('click', event => {
            event.preventDefault();
            const enabled = isWorkModeEnabled();
            setWorkModeEnabled(!enabled, { persist: true, notifyOnMobile: true });
        });
    }
    if (workModeDivider) {
        workModeDivider.addEventListener('pointerdown', startWorkModeResize);
        workModeDivider.addEventListener('dblclick', event => {
            event.preventDefault();
            if (!isWorkModeEnabled()) return;
            workModeSplitRatio = WORK_MODE_DEFAULT_SPLIT;
            applyWorkModeSplitRatio(workModeSplitRatio, { persist: true });
        });
    }
    if (workModeFileRefreshBtn) {
        workModeFileRefreshBtn.addEventListener('click', async () => {
            const scrollSnapshot = captureWorkModeFileScrollSnapshot();
            const viewerScrollSnapshot = captureWorkModeFileViewerScrollSnapshot();
            const listed = await refreshWorkModeFileDirectory({
                root: workModeFileRoot,
                path: workModeFilePath,
                force: true,
                restoreScrollSnapshot: scrollSnapshot
            });
            if (!listed) return;
            await refreshWorkModeFilePreviewSelection({
                restoreViewerScrollSnapshot: viewerScrollSnapshot
            });
        });
    }
    if (workModeFileNewFileBtn) {
        workModeFileNewFileBtn.addEventListener('click', () => {
            void createFileInFilePanel(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileDeleteDirectoryBtn) {
        workModeFileDeleteDirectoryBtn.addEventListener('click', () => {
            void deleteCurrentDirectoryFromFilePanel(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileAddContextBtn) {
        workModeFileAddContextBtn.addEventListener('click', () => {
            void addSelectedFilesToChatContext(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileMoveBtn) {
        workModeFileMoveBtn.addEventListener('click', () => {
            void moveSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileSelectAllBtn) {
        workModeFileSelectAllBtn.addEventListener('click', () => {
            toggleFilePanelVisibleFileSelection(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileClearSelectionBtn) {
        workModeFileClearSelectionBtn.addEventListener('click', () => {
            clearFilePanelSelection(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileDownloadBtn) {
        workModeFileDownloadBtn.addEventListener('click', () => {
            void downloadSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileDeleteBtn) {
        workModeFileDeleteBtn.addEventListener('click', () => {
            void deleteSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileEditBtn) {
        workModeFileEditBtn.addEventListener('click', () => {
            void toggleFilePanelEditMode(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileSaveBtn) {
        workModeFileSaveBtn.addEventListener('click', () => {
            void saveFilePanelEdits(FILE_PANEL_VARIANT_WORK_MODE);
        });
    }
    if (workModeFileUpBtn) {
        workModeFileUpBtn.addEventListener('click', () => {
            if (!workModeFilePath) return;
            if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_WORK_MODE)) return;
            workModeFileSelectedPath = '';
            clearFilePanelSelection(FILE_PANEL_VARIANT_WORK_MODE);
            if (isMobileLayout()) {
                setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_LIST);
            } else if (isFoldLayout()) {
                setWorkModeBrowseView(WORK_MODE_MOBILE_VIEW_LIST);
            }
            void refreshWorkModeFileDirectory({
                root: workModeFileRoot,
                path: getFileBrowserParentPath(workModeFilePath),
                force: true
            }).then(result => {
                if (!result) return;
                clearWorkModeFileViewer('파일을 선택하세요.');
            });
        });
    }
    if (workModeFileBackBtn) {
        workModeFileBackBtn.addEventListener('click', event => {
            event.preventDefault();
            if (isMobileLayout()) {
                setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_LIST);
                return;
            }
            if (isFoldLayout()) {
                setWorkModeBrowseView(WORK_MODE_MOBILE_VIEW_LIST);
            }
        });
    }
    if (workModeTerminalOpenBtn) {
        workModeTerminalOpenBtn.addEventListener('click', event => {
            event.preventDefault();
            void openTerminalOverlayFromContext({
                root: workModeFileRoot,
                path: workModeFilePath
            }).catch(error => {
                showToast(normalizeError(error, 'Terminal을 열지 못했습니다.'), {
                    tone: 'error',
                    durationMs: 4200
                });
            });
        });
    }
    if (workModeChatBackBtn) {
        workModeChatBackBtn.addEventListener('click', event => {
            event.preventDefault();
            setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_CHAT);
        });
    }
    if (workModeFileOpenNewBtn) {
        workModeFileOpenNewBtn.addEventListener('click', event => {
            event.preventDefault();
            openWorkModePreviewInNewWindow();
        });
        syncHoverTooltipFromLabel(workModeFileOpenNewBtn);
    }
    if (workModeTerminalOpenBtn) {
        syncHoverTooltipFromLabel(workModeTerminalOpenBtn, '현재 폴더 Terminal 오버레이 열기');
    }
    if (workModeMobileBrowserBtn) {
        workModeMobileBrowserBtn.addEventListener('click', event => {
            event.preventDefault();
            if (!isWorkModeEnabled() || !isMobileLayout()) return;
            const hasSelection = Boolean(normalizeFileBrowserRelativePath(workModeFileSelectedPath));
            const targetView = hasSelection
                ? normalizeWorkModeMobileBrowseView(workModeMobileBrowseView)
                : WORK_MODE_MOBILE_VIEW_LIST;
            setWorkModeMobileView(targetView);
            void ensureWorkModeFilePanelContent();
        });
    }
    if (workModeFileFullscreenBtn) {
        workModeFileFullscreenBtn.addEventListener('click', event => {
            event.preventDefault();
            if (isFoldLayout()) {
                setWorkModePreviewFullscreen(!workModePreviewFullscreen);
                return;
            }
            setWorkModeFileViewerFullscreen(!workModeFileViewerFullscreen);
        });
    }
    if (workModeFileDivider) {
        workModeFileDivider.addEventListener('pointerdown', startWorkModeFileResize);
        workModeFileDivider.addEventListener('dblclick', event => {
            event.preventDefault();
            if (!isWorkModeEnabled()) return;
            workModeFileSplitRatio = WORK_MODE_FILE_DEFAULT_SPLIT;
            applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: true });
        });
    }
    if (workModeFileGridScroll && workModeFileHScroll) {
        workModeFileGridScroll.addEventListener('scroll', handleWorkModeFileGridScroll, { passive: true });
        workModeFileHScroll.addEventListener('scroll', handleWorkModeFileHScroll, { passive: true });
    }
    if (workModeFileViewerContent) {
        workModeFileViewerContent.addEventListener('scroll', handleWorkModeFileViewerScroll, { passive: true });
    }
    workModeFileColumnResizers.forEach(resizer => {
        resizer.addEventListener('pointerdown', event => {
            startWorkModeFileColumnResize(event, resizer.dataset?.resizeCol || '');
        });
    });
    if (branchOverlayCommitBtn) {
        branchOverlayCommitBtn.addEventListener('click', () => {
            void handleGitCommit(branchOverlayCommitBtn);
        });
    }
    if (branchOverlayPushBtn) {
        branchOverlayPushBtn.addEventListener('click', () => {
            void handleGitPush(branchOverlayPushBtn);
        });
    }
    if (branchOverlayStageAllBtn) {
        branchOverlayStageAllBtn.addEventListener('click', () => {
            setGitOverlaySelectionState(true);
        });
    }
    if (branchOverlayStageNoneBtn) {
        branchOverlayStageNoneBtn.addEventListener('click', () => {
            setGitOverlaySelectionState(false);
        });
    }
    if (branchOverlayCommitMessageInput) {
        branchOverlayCommitMessageInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                if (branchOverlayCommitBtn) {
                    void handleGitCommit(branchOverlayCommitBtn);
                }
            }
        });
        branchOverlayCommitMessageInput.addEventListener('input', () => {
            if (!isGitBranchOverlayOpen()) return;
            updateGitBranchOverlayCommitPreview(gitBranchStatusCache);
        });
    }

    if (gitBranch) {
        gitBranch.addEventListener('click', event => {
            event.preventDefault();
            openGitBranchOverlay();
        });
        gitBranch.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openGitBranchOverlay();
            }
        });
        startGitBranchPolling();
    }

    const branchOverlay = document.getElementById('codex-branch-overlay');
    const branchOverlayClose = document.getElementById('codex-branch-overlay-close');
    const branchOverlayCloseFooter = document.getElementById('codex-branch-overlay-close-footer');
    const branchOverlayRefresh = document.getElementById('codex-branch-overlay-refresh');
    if (branchOverlay) {
        branchOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeGitBranchOverlay();
            }
        });
    }
    if (branchOverlayClose) {
        branchOverlayClose.addEventListener('click', closeGitBranchOverlay);
    }
    if (branchOverlayCloseFooter) {
        branchOverlayCloseFooter.addEventListener('click', closeGitBranchOverlay);
    }
    if (branchOverlayRefresh) {
        branchOverlayRefresh.addEventListener('click', () => {
            void refreshGitBranchStatus({ force: true, updateOverlay: true });
        });
    }
    const syncOverlay = document.getElementById('codex-sync-overlay');
    const syncOverlayClose = document.getElementById('codex-sync-overlay-close');
    const syncOverlayCloseFooter = document.getElementById('codex-sync-overlay-close-footer');
    if (syncOverlay) {
        syncOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeGitSyncOverlay();
            }
        });
    }
    if (syncOverlayClose) {
        syncOverlayClose.addEventListener('click', closeGitSyncOverlay);
    }
    if (syncOverlayCloseFooter) {
        syncOverlayCloseFooter.addEventListener('click', closeGitSyncOverlay);
    }
    if (usageHistoryOpen) {
        usageHistoryOpen.addEventListener('click', () => {
            void openUsageHistoryOverlay();
        });
    }
    if (usageRefreshBtn) {
        usageRefreshBtn.addEventListener('click', async () => {
            usageRefreshBtn.classList.add('is-spinning');
            usageRefreshBtn.disabled = true;
            await refreshUsageSummary({ silent: false, showSuccessToast: true });
            usageRefreshBtn.classList.remove('is-spinning');
            usageRefreshBtn.disabled = false;
        });
    }
    if (usageHistoryOverlay) {
        usageHistoryOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeUsageHistoryOverlay();
            }
        });
    }
    if (usageHistoryOverlayClose) {
        usageHistoryOverlayClose.addEventListener('click', closeUsageHistoryOverlay);
    }
    if (usageHistoryOverlayCloseFooter) {
        usageHistoryOverlayCloseFooter.addEventListener('click', closeUsageHistoryOverlay);
    }
    if (messageLogOverlay) {
        messageLogOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeMessageLogOverlay();
            }
        });
    }
    if (messageLogOverlayClose) {
        messageLogOverlayClose.addEventListener('click', closeMessageLogOverlay);
    }
    if (messageLogOverlayCloseFooter) {
        messageLogOverlayCloseFooter.addEventListener('click', closeMessageLogOverlay);
    }
    if (mobileSessionOverlay) {
        mobileSessionOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeMobileSessionOverlay();
            }
        });
    }
    if (mobileSessionOverlayClose) {
        mobileSessionOverlayClose.addEventListener('click', closeMobileSessionOverlay);
    }
    if (mobileSessionOverlayCloseFooter) {
        mobileSessionOverlayCloseFooter.addEventListener('click', closeMobileSessionOverlay);
    }
    if (terminalOverlay) {
        terminalOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeTerminalOverlay();
            }
        });
    }
    if (terminalOverlayClose) {
        terminalOverlayClose.addEventListener('click', closeTerminalOverlay);
    }
    if (terminalOverlayCloseFooter) {
        terminalOverlayCloseFooter.addEventListener('click', closeTerminalOverlay);
    }
    if (terminalOverlayNewTabBtn) {
        terminalOverlayNewTabBtn.addEventListener('click', event => {
            event.preventDefault();
            void openNewTerminalTab().catch(error => {
                showToast(normalizeError(error, '새 Terminal 탭을 열지 못했습니다.'), {
                    tone: 'error',
                    durationMs: 4200
                });
            });
        });
    }
    if (terminalOverlayCloseTabBtn) {
        terminalOverlayCloseTabBtn.addEventListener('click', event => {
            event.preventDefault();
            void closeTerminalTab().catch(error => {
                showToast(normalizeError(error, 'Terminal 종료에 실패했습니다.'), {
                    tone: 'error',
                    durationMs: 4200
                });
            });
        });
    }
    if (fileBrowserOverlay) {
        fileBrowserOverlay.addEventListener('click', event => {
            const target = event.target;
            if (target && target.dataset?.action === 'close') {
                closeFileBrowserOverlay();
            }
        });
    }
    if (fileBrowserOverlayClose) {
        fileBrowserOverlayClose.addEventListener('click', closeFileBrowserOverlay);
    }
    if (fileBrowserOverlayCloseFooter) {
        fileBrowserOverlayCloseFooter.addEventListener('click', closeFileBrowserOverlay);
    }
    if (fileBrowserRefreshBtn) {
        fileBrowserRefreshBtn.addEventListener('click', async () => {
            const listed = await refreshFileBrowserDirectory({ force: true });
            if (!listed) return;
            await refreshFileBrowserPreviewSelection();
        });
    }
    if (fileBrowserNewFileBtn) {
        fileBrowserNewFileBtn.addEventListener('click', () => {
            void createFileInFilePanel(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserDeleteDirectoryBtn) {
        fileBrowserDeleteDirectoryBtn.addEventListener('click', () => {
            void deleteCurrentDirectoryFromFilePanel(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserAddContextBtn) {
        fileBrowserAddContextBtn.addEventListener('click', () => {
            void addSelectedFilesToChatContext(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserMoveBtn) {
        fileBrowserMoveBtn.addEventListener('click', () => {
            void moveSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserSelectAllBtn) {
        fileBrowserSelectAllBtn.addEventListener('click', () => {
            toggleFilePanelVisibleFileSelection(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserClearSelectionBtn) {
        fileBrowserClearSelectionBtn.addEventListener('click', () => {
            clearFilePanelSelection(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserDownloadBtn) {
        fileBrowserDownloadBtn.addEventListener('click', () => {
            void downloadSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserDeleteBtn) {
        fileBrowserDeleteBtn.addEventListener('click', () => {
            void deleteSelectedFilesFromFilePanel(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserEditBtn) {
        fileBrowserEditBtn.addEventListener('click', () => {
            void toggleFilePanelEditMode(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserSaveBtn) {
        fileBrowserSaveBtn.addEventListener('click', () => {
            void saveFilePanelEdits(FILE_PANEL_VARIANT_OVERLAY);
        });
    }
    if (fileBrowserBackBtn) {
        fileBrowserBackBtn.addEventListener('click', () => {
            setFileBrowserMobileView(FILE_BROWSER_MOBILE_VIEW_LIST);
        });
    }
    if (fileBrowserTerminalOpenBtn) {
        fileBrowserTerminalOpenBtn.addEventListener('click', event => {
            event.preventDefault();
            void openTerminalOverlayFromContext({
                root: fileBrowserRoot,
                path: fileBrowserPath
            }).catch(error => {
                showToast(normalizeError(error, 'Terminal을 열지 못했습니다.'), {
                    tone: 'error',
                    durationMs: 4200
                });
            });
        });
    }
    if (fileBrowserUpBtn) {
        fileBrowserUpBtn.addEventListener('click', () => {
            if (!fileBrowserPath) return;
            if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) return;
            const parentPath = getFileBrowserParentPath(fileBrowserPath);
            fileBrowserSelectedPath = '';
            clearFilePanelSelection(FILE_PANEL_VARIANT_OVERLAY);
            void refreshFileBrowserDirectory({
                root: fileBrowserRoot,
                path: parentPath,
                force: true
            }).then(result => {
                if (!result) return;
                clearFileBrowserViewer();
            });
        });
    }
    if (fileBrowserDivider) {
        fileBrowserDivider.addEventListener('pointerdown', startFileBrowserResize);
        fileBrowserDivider.addEventListener('dblclick', event => {
            event.preventDefault();
            if (!isFileBrowserOverlayOpen()) return;
            fileBrowserSplitRatio = WORK_MODE_FILE_DEFAULT_SPLIT;
            applyFileBrowserSplitRatio(fileBrowserSplitRatio, { persist: true });
        });
    }
    if (fileBrowserGridScroll && fileBrowserHScroll) {
        fileBrowserGridScroll.addEventListener('scroll', handleFileBrowserGridScroll, { passive: true });
        fileBrowserHScroll.addEventListener('scroll', handleFileBrowserHScroll, { passive: true });
    }
    fileBrowserColumnResizers.forEach(resizer => {
        resizer.addEventListener('pointerdown', event => {
            startFileBrowserColumnResize(event, resizer.dataset?.resizeCol || '');
        });
    });
    fileBrowserSplitRatio = readFileBrowserSplitPreference();
    fileBrowserColumnWidths = readFileBrowserColumnsPreference();
    updateFileBrowserFilterToggleState();
    setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
    if (fileBrowserShowHiddenToggle) {
        fileBrowserShowHiddenToggle.addEventListener('change', () => {
            fileBrowserShowHiddenEntries = Boolean(fileBrowserShowHiddenToggle.checked);
            rerenderFileBrowserDirectoryFromCache();
        });
    }
    if (fileBrowserShowPycacheToggle) {
        fileBrowserShowPycacheToggle.addEventListener('change', () => {
            fileBrowserShowPycacheEntries = Boolean(fileBrowserShowPycacheToggle.checked);
            rerenderFileBrowserDirectoryFromCache();
        });
    }
    if (fileBrowserFullscreenBtn) {
        fileBrowserFullscreenBtn.addEventListener('click', () => {
            setFileBrowserViewerFullscreen(!fileBrowserViewerFullscreen);
        });
    }
    if (fileBrowserTerminalOpenBtn) {
        syncHoverTooltipFromLabel(fileBrowserTerminalOpenBtn, '현재 폴더 Terminal 오버레이 열기');
    }
    document.querySelectorAll('.file-browser-root-target[data-root-target]').forEach(button => {
        button.addEventListener('click', () => {
            const nextRoot = normalizeFileBrowserRoot(button.dataset?.rootTarget);
            if (!nextRoot || nextRoot === fileBrowserRoot) return;
            if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) return;
            fileBrowserRoot = nextRoot;
            fileBrowserPath = '';
            fileBrowserSelectedPath = '';
            clearFilePanelSelection(FILE_PANEL_VARIANT_OVERLAY);
            updateFileBrowserRootButtons();
            void refreshFileBrowserDirectory({ root: nextRoot, path: '', force: true }).then(result => {
                if (!result) return;
                clearFileBrowserViewer();
            });
        });
    });
    if (syncOverlayRefreshBtn) {
        syncOverlayRefreshBtn.addEventListener('click', () => {
            void refreshGitSyncOverlayHistory({ force: true });
        });
    }
    if (syncOverlayFetchBtn) {
        syncOverlayFetchBtn.addEventListener('click', () => {
            void handleGitSync(syncOverlayFetchBtn);
        });
    }
    if (syncOverlaySyncBtn) {
        syncOverlaySyncBtn.addEventListener('click', () => {
            void handleGitSync(syncOverlaySyncBtn, { applyAfterFetch: true });
        });
    }
    if (syncOverlayCommitBtn) {
        syncOverlayCommitBtn.addEventListener('click', () => {
            void handleGitQuickCommit(syncOverlayCommitBtn, {
                repoTarget: normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)
            });
        });
    }
    if (syncOverlayPushBtn) {
        syncOverlayPushBtn.addEventListener('click', () => {
            void handleGitPush(syncOverlayPushBtn, {
                repoTarget: normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)
            });
        });
    }
    syncOverlayTargetButtons.forEach(button => {
        button.addEventListener('click', () => {
            const repoTarget = typeof button.dataset?.repoTarget === 'string'
                ? button.dataset.repoTarget.trim()
                : '';
            if (!repoTarget) return;
            if (repoTarget === gitSyncOverlayRepoTarget) return;
            setGitSyncOverlayRepoTarget(repoTarget);
            void refreshGitSyncOverlayHistory({ force: true });
        });
    });
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_WORK_MODE);
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_OVERLAY);
    syncTerminalOverlayState();
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        if (isTerminalOverlayOpen()) {
            closeTerminalOverlay();
            return;
        }
        if (isMobileSessionOverlayOpen()) {
            closeMobileSessionOverlay();
            return;
        }
        if (isUsageHistoryOverlayOpen()) {
            closeUsageHistoryOverlay();
            return;
        }
        if (isFileBrowserOverlayOpen()) {
            closeFileBrowserOverlay();
            return;
        }
        if (isMessageLogOverlayOpen()) {
            closeMessageLogOverlay();
            return;
        }
        if (isGitSyncOverlayOpen()) {
            closeGitSyncOverlay();
            return;
        }
        if (isGitBranchOverlayOpen()) {
            closeGitBranchOverlay();
        }
    });

    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            if (refreshBtn.classList.contains('is-loading')) {
                const startedAt = Number(refreshBtn.dataset.loadingStartedAt);
                const isStale = Number.isFinite(startedAt) && Date.now() - startedAt >= REFRESH_BUTTON_STALE_MS;
                if (!isStale) return;
                refreshBtn.classList.remove('is-loading');
                delete refreshBtn.dataset.loadingStartedAt;
                const staleRecovered = recoverClientUiState({
                    clearSessionLoadingLock: true,
                    source: 'stale-refresh-button'
                });
                if (staleRecovered.length > 0) {
                    showToast('잠긴 UI 상태를 복구하고 다시 동기화를 시작합니다.', {
                        tone: 'success',
                        durationMs: 2600
                    });
                }
            }
            refreshBtn.classList.add('is-loading');
            refreshBtn.dataset.loadingStartedAt = String(Date.now());
            const recovered = recoverClientUiState({
                clearSessionLoadingLock: true,
                source: 'manual-refresh'
            });
            if (recovered.length > 0) {
                showToast('로컬 잠금 상태를 정리한 뒤 새로고침합니다.', {
                    tone: 'success',
                    durationMs: 2200
                });
            }
            try {
                await Promise.all([
                    loadSessions({ preserveActive: true }),
                    refreshRemoteStreams({ force: true }),
                    loadSettings({ silent: true }),
                    refreshUsageSummary({ silent: true }),
                    loadLiveWeatherData({ silent: true })
                ]);
            } finally {
                refreshBtn.classList.remove('is-loading');
                delete refreshBtn.dataset.loadingStartedAt;
            }
        });
    }

    if (chatFullscreenBtn) {
        chatFullscreenBtn.addEventListener('click', () => {
            const app = document.querySelector('.app');
            const isEnabled = app?.classList.contains(CHAT_FULLSCREEN_CLASS);
            const nextEnabled = !isEnabled;
            setChatFullscreen(nextEnabled);
        });
        const app = document.querySelector('.app');
        updateChatFullscreenButton(chatFullscreenBtn, app?.classList.contains(CHAT_FULLSCREEN_CLASS));
    }
    updateChatSessionNavigationButtons();

    if (streamMonitorCloseBtn) {
        streamMonitorCloseBtn.addEventListener('click', () => {
            stopStreamMonitor(true);
        });
    }

    if (streamMonitorToggle) {
        streamMonitorToggle.addEventListener('click', () => {
            const isCollapsed = streamMonitor?.classList.contains('is-collapsed');
            setStreamMonitorCollapsed(!isCollapsed);
        });
    }

    if (sessionsToggle && sessionsPanel) {
        sessionsToggle.addEventListener('click', () => {
            const collapsed = sessionsPanel.classList.contains('is-collapsed');
            setSessionsCollapsed(!collapsed);
        });
    }

    if (controlsToggle && controls) {
        controlsToggle.addEventListener('click', () => {
            const collapsed = controls.classList.contains('is-collapsed');
            setControlsCollapsed(!collapsed);
            if (collapsed && !state.settings.loaded) {
                void loadSettings({ silent: true });
            }
        });
    }

    primeSettingsOptionsFromDom(modelSelect, reasoningSelect, planModeModelSelect, planModeReasoningSelect);

    syncSessionsLayout(compactMedia.matches);
    syncControlsLayout();
    setFileBrowserMobileView(fileBrowserMobileView);
    setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
    initializeWorkMode(phoneMedia.matches);
    setWorkModeFileViewerFullscreen(false);
    if (isWorkModeEnabled()) {
        applyWorkModeSplitRatio(workModeSplitRatio, { persist: false });
    }
    const handleCompactLayoutChange = event => {
        const isCompact = Boolean(event?.matches);
        syncSessionsLayout(isCompact);
        syncLiveWeatherLayout(isCompact);
        setFileBrowserMobileView(fileBrowserMobileView);
        setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
        handleWorkModeMediaChange(isPhoneLayout());
        syncTerminalExtraKeysState();
    };
    if (typeof compactMedia.addEventListener === 'function') {
        compactMedia.addEventListener('change', handleCompactLayoutChange);
    } else if (typeof compactMedia.addListener === 'function') {
        compactMedia.addListener(handleCompactLayoutChange);
    }
    const handlePhoneLayoutChange = event => {
        const isPhone = Boolean(event?.matches);
        if (!isPhone && isMobileSessionOverlayOpen()) {
            closeMobileSessionOverlay();
        }
        setFileBrowserMobileView(fileBrowserMobileView);
        setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
        handleWorkModeMediaChange(isPhone);
        syncTerminalExtraKeysState();
    };
    if (typeof phoneMedia.addEventListener === 'function') {
        phoneMedia.addEventListener('change', handlePhoneLayoutChange);
    } else if (typeof phoneMedia.addListener === 'function') {
        phoneMedia.addListener(handlePhoneLayoutChange);
    }
    const handleWindowLayoutResize = createRafThrottledHandler(() => {
        if (isWorkModeEnabled()) {
            applyWorkModeSplitRatio(workModeSplitRatio, { persist: false });
            applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: false });
        }
        if (isTerminalOverlayOpen()) {
            scheduleTerminalViewportRefresh({ fit: true });
        }
        if (isFileBrowserOverlayOpen()) {
            applyFileBrowserSplitRatio(fileBrowserSplitRatio, { persist: false });
            syncFileBrowserHorizontalScrollMetrics();
        }
        syncWorkModeFileHorizontalScrollMetrics();
        if (isUsageHistoryOverlayOpen()) {
            scheduleUsageHistoryOverlayRerender();
        }
        if (isTerminalOverlayOpen()) {
            syncTerminalExtraKeysState();
        }
    });
    window.addEventListener('resize', handleWindowLayoutResize);
    window.addEventListener('pagehide', flushPersistWorkModeFileViewState);
    window.addEventListener('beforeunload', flushPersistWorkModeFileViewState);

    setupMobileViewportBehavior(compactMedia, input);
    setupMobileSettingsInputBehavior(
        compactMedia,
        [
            modelInput,
            planModeModelInput,
            planModeReasoningInput,
            reasoningInput,
            modelSelect,
            planModeModelSelect,
            planModeReasoningSelect,
            reasoningSelect
        ],
    );

    if (messages) {
        messages.addEventListener('scroll', () => {
            handleMessageScroll(messages);
        });
        handleMessageScroll(messages);
    }

    if (scrollToLatestBtn) {
        scrollToLatestBtn.addEventListener('click', () => {
            setAutoScrollEnabled(true);
            scrollToBottom(true);
        });
    }

    if (modelSelect) {
        modelSelect.addEventListener('change', () => {
            const selectedModel = modelSelect.value || '';
            if (modelInput) {
                modelInput.value = selectedModel;
            }
            updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions, selectedModel);
        });
    }

    if (modelInput) {
        modelInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void updateSettings();
            }
        });
    }

    if (modelApply) {
        modelApply.addEventListener('click', () => {
            void updateSettings();
        });
    }

    if (planModeModelSelect) {
        planModeModelSelect.addEventListener('change', () => {
            const selectedModel = planModeModelSelect.value || '';
            if (planModeModelInput) {
                planModeModelInput.value = selectedModel;
            }
            updatePlanModeReasoningControls(
                state.settings.planModeReasoningEffort,
                state.settings.reasoningOptions,
                selectedModel || state.settings.model
            );
        });
    }

    if (planModeModelInput) {
        planModeModelInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void updateSettings();
            }
        });
    }

    if (reasoningSelect) {
        reasoningSelect.addEventListener('change', () => {
            if (reasoningInput) {
                reasoningInput.value = reasoningSelect.value || '';
            }
        });
    }

    if (reasoningInput) {
        reasoningInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void updateSettings();
            }
        });
    }

    if (planModeReasoningSelect) {
        planModeReasoningSelect.addEventListener('change', () => {
            if (planModeReasoningInput) {
                planModeReasoningInput.value = planModeReasoningSelect.value || '';
            }
        });
    }

    if (planModeReasoningInput) {
        planModeReasoningInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void updateSettings();
            }
        });
    }

    if (planModeToggle) {
        planModeToggle.addEventListener('click', () => {
            setPlanModeToggleState(getNextPlanModeState(getPlanModeState()));
        });
    }
    setPlanModeToggleState(state.settings.planModeState);

    syncActiveSessionControls();
    syncActiveSessionStatus();
    startRunningJobsMonitorTicker();
    initializeTheme(themeToggle, themeMedia);
    initializeLiveWeatherPanel(compactMedia);
    if (streamMonitor) {
        setStreamMonitorCollapsed(streamMonitor.classList.contains('is-collapsed'));
    }
    void initializeApp();
});

async function initializeApp() {
    if (!state.settings.loaded) {
        void loadSettings({ silent: true });
    }
    const pendingStreams = getPersistedStreams();
    const targetSessionId = pendingStreams.length > 0 ? pendingStreams[0].sessionId : null;
    await loadSessions({ preserveActive: true, selectSessionId: targetSessionId });
    if (pendingStreams.length > 0) {
        await resumeStreamsFromStorage(pendingStreams);
    }
    startRemoteStreamPolling();
}

function initializeLiveWeatherPanel(mobileMedia) {
    const panel = document.getElementById('codex-live-weather-panel');
    const toggle = document.getElementById('codex-live-weather-toggle');
    if (!panel || !toggle) return;

    initializeHoverTooltipInteractions();
    syncLiveWeatherLayout(Boolean(mobileMedia?.matches));
    const serverDirectory = document.getElementById('codex-server-directory');
    const serverDirectoryPath = document.getElementById('codex-server-directory-path');
    setHoverTooltip(serverDirectory, serverDirectory?.textContent || '');
    setHoverTooltip(serverDirectoryPath, serverDirectoryPath?.textContent || '');
    updateLiveDatetime();
    if (state.liveClockTimer) {
        window.clearInterval(state.liveClockTimer);
    }
    state.liveClockTimer = window.setInterval(updateLiveDatetime, 1000);
    toggle.addEventListener('click', () => {
        const isCompact = panel.classList.contains('is-compact');
        setLiveWeatherCompact(!isCompact);
    });
    void loadLiveWeatherData();
}

function readLiveWeatherCompactPreference(defaultCompact) {
    let compact = Boolean(defaultCompact);
    try {
        const stored = localStorage.getItem(WEATHER_COMPACT_KEY);
        if (stored !== null) {
            compact = stored === '1';
        }
    } catch (error) {
        void error;
    }
    return compact;
}

function setLiveWeatherCompact(compact, { persist = true } = {}) {
    const panel = document.getElementById('codex-live-weather-panel');
    const toggle = document.getElementById('codex-live-weather-toggle');
    if (!panel || !toggle) return;
    const isCompact = Boolean(compact);
    const toggleLabel = isCompact ? 'Expand weather panel' : 'Collapse weather panel';
    panel.classList.toggle('is-compact', isCompact);
    toggle.setAttribute('aria-expanded', String(!isCompact));
    toggle.classList.toggle('is-collapsed', isCompact);
    toggle.setAttribute('aria-label', toggleLabel);
    syncHoverTooltipFromLabel(toggle, toggleLabel);
    updateLiveWeatherPanelTitle();
    syncSidebarStackLayout();
    if (persist) {
        try {
            localStorage.setItem(WEATHER_COMPACT_KEY, isCompact ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function updateLiveWeatherCompactSummary({
    datetime,
    currentTemp,
    weatherText,
    highTemp,
    lowTemp,
    hasWeather
} = {}) {
    if (typeof datetime === 'string' && datetime.trim()) {
        liveWeatherCompactDatetime = datetime.trim();
    }
    if (typeof currentTemp === 'string' && currentTemp.trim()) {
        liveWeatherCompactCurrentTemp = currentTemp.trim();
    }
    if (typeof weatherText === 'string' && weatherText.trim()) {
        liveWeatherCompactWeatherText = weatherText.trim();
    }
    if (typeof highTemp === 'string' && highTemp.trim()) {
        liveWeatherCompactHighTemp = highTemp.trim();
    }
    if (typeof lowTemp === 'string' && lowTemp.trim()) {
        liveWeatherCompactLowTemp = lowTemp.trim();
    }
    if (typeof hasWeather === 'boolean') {
        liveWeatherCompactHasWeather = hasWeather;
    }
    updateLiveWeatherPanelTitle();
}

function updateLiveWeatherPanelTitle() {
    const panel = document.getElementById('codex-live-weather-panel');
    const title = document.getElementById('codex-live-weather-title');
    if (!panel || !title) return;
    const isCompact = panel.classList.contains('is-compact');
    if (!isCompact) {
        title.textContent = LIVE_WEATHER_PANEL_TITLE;
        setHoverTooltip(title, LIVE_WEATHER_PANEL_TITLE);
        return;
    }
    const datetimeText = liveWeatherCompactDatetime || '--';
    const line1 = document.createElement('span');
    line1.className = 'live-weather-compact-line live-weather-compact-line-primary';
    const dateSpan = document.createElement('span');
    dateSpan.className = 'live-weather-compact-date';
    dateSpan.textContent = datetimeText;
    line1.appendChild(dateSpan);

    const line2 = document.createElement('span');
    line2.className = 'live-weather-compact-line live-weather-compact-line-secondary';

    if (!liveWeatherCompactHasWeather) {
        const pendingText = liveWeatherCompactWeatherText || '날씨 불러오는 중...';
        const compactTitle = `${datetimeText} · ${pendingText}`;
        line2.textContent = pendingText;
        title.replaceChildren(line1, line2);
        setHoverTooltip(title, compactTitle);
        return;
    }

    const currentTemp = liveWeatherCompactCurrentTemp || '--';
    const weatherText = liveWeatherCompactWeatherText || '알 수 없음';
    const highTemp = liveWeatherCompactHighTemp || '--';
    const lowTemp = liveWeatherCompactLowTemp || '--';

    const currentSpan = document.createElement('span');
    currentSpan.className = 'live-weather-compact-current-temp';
    currentSpan.textContent = currentTemp;
    line2.appendChild(currentSpan);
    line2.appendChild(document.createTextNode(' '));
    const weatherSpan = document.createElement('span');
    weatherSpan.className = 'live-weather-compact-weather';
    weatherSpan.textContent = weatherText;
    line2.appendChild(weatherSpan);
    line2.appendChild(document.createTextNode(' · '));
    const highSpan = document.createElement('span');
    highSpan.className = 'live-weather-compact-high';
    highSpan.textContent = `↑${highTemp}`;
    line2.appendChild(highSpan);
    line2.appendChild(document.createTextNode(' '));
    const lowSpan = document.createElement('span');
    lowSpan.className = 'live-weather-compact-low';
    lowSpan.textContent = `↓${lowTemp}`;
    line2.appendChild(lowSpan);

    title.replaceChildren(line1, line2);

    const compactTitle = `${datetimeText} · ${currentTemp} ${weatherText} · 최고 ${highTemp} / 최저 ${lowTemp}`;
    setHoverTooltip(title, compactTitle);
}

function syncLiveWeatherLayout(isMobile) {
    void isMobile;
    const compact = readLiveWeatherCompactPreference(true);
    setLiveWeatherCompact(compact, { persist: false });
}

const KST_FIXED_HOLIDAYS = Object.freeze([
    [1, 1],
    [3, 1],
    [5, 5],
    [6, 6],
    [8, 15],
    [10, 3],
    [10, 9],
    [12, 25]
]);

const kstHolidayCache = new Map();

function toDateKey(year, month, day) {
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return '';
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function getWeekdayIndexFromDateKey(dateKey) {
    if (!dateKey) return null;
    const parts = dateKey.split('-').map(value => Number(value));
    if (parts.length !== 3 || parts.some(value => !Number.isFinite(value))) return null;
    const [year, month, day] = parts;
    const date = new Date(Date.UTC(year, month - 1, day));
    if (Number.isNaN(date.getTime())) return null;
    return date.getUTCDay();
}

function addDaysToDateKey(dateKey, days) {
    const parts = dateKey.split('-').map(value => Number(value));
    if (parts.length !== 3 || parts.some(value => !Number.isFinite(value))) return '';
    const [year, month, day] = parts;
    const date = new Date(Date.UTC(year, month - 1, day));
    date.setUTCDate(date.getUTCDate() + days);
    return toDateKey(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

function getFixedDomesticHolidays(year) {
    if (kstHolidayCache.has(year)) return kstHolidayCache.get(year);
    const holidays = new Set();
    KST_FIXED_HOLIDAYS.forEach(([month, day]) => {
        const baseKey = toDateKey(year, month, day);
        if (!baseKey) return;
        holidays.add(baseKey);
        const weekdayIndex = getWeekdayIndexFromDateKey(baseKey);
        let observedKey = baseKey;
        if (weekdayIndex === 6) {
            observedKey = addDaysToDateKey(baseKey, 2);
        } else if (weekdayIndex === 0) {
            observedKey = addDaysToDateKey(baseKey, 1);
        }
        if (observedKey && observedKey.startsWith(`${year}-`)) {
            holidays.add(observedKey);
        }
    });
    kstHolidayCache.set(year, holidays);
    return holidays;
}

function isFixedDomesticHoliday(dateKey) {
    if (!dateKey) return false;
    const year = Number(dateKey.split('-', 1)[0]);
    if (!Number.isFinite(year)) return false;
    return getFixedDomesticHolidays(year).has(dateKey);
}

function getKstNowParts(date = new Date()) {
    const formatter = new Intl.DateTimeFormat('ko-KR', {
        timeZone: KST_TIME_ZONE,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    const parts = formatter.formatToParts(date);
    const lookup = {};
    parts.forEach(part => {
        if (part.type !== 'literal') {
            lookup[part.type] = part.value;
        }
    });
    if (!lookup.year || !lookup.month || !lookup.day) return null;
    return {
        year: lookup.year,
        month: lookup.month,
        day: lookup.day,
        weekday: lookup.weekday || '',
        hour: lookup.hour || '00',
        minute: lookup.minute || '00',
        second: lookup.second || '00',
        dateKey: toDateKey(Number(lookup.year), Number(lookup.month), Number(lookup.day))
    };
}

function updateLiveDatetime() {
    const datetime = document.getElementById('codex-live-datetime');
    if (!datetime) return;
    const parts = getKstNowParts();
    if (!parts) {
        const fallback = formatKstNow();
        datetime.textContent = fallback;
        setHoverTooltip(datetime, fallback);
        updateLiveWeatherCompactSummary({ datetime: fallback });
        return;
    }
    const datePart = `${parts.year}. ${parts.month}. ${parts.day}.`;
    const timePart = `${parts.hour}:${parts.minute}:${parts.second}`;
    const weekday = parts.weekday || '';
    const weekdayIndex = parts.dateKey ? getWeekdayIndexFromDateKey(parts.dateKey) : null;
    const isSunday = weekdayIndex === 0;
    const isHoliday = parts.dateKey ? isFixedDomesticHoliday(parts.dateKey) : false;
    const datetimeText = `${datePart} (${weekday}) ${timePart}`;
    if (isSunday || isHoliday) {
        datetime.innerHTML = `${datePart} (<span class="holiday-weekday">${weekday}</span>) ${timePart}`;
    } else {
        datetime.textContent = datetimeText;
    }
    setHoverTooltip(datetime, datetimeText);
    const compactDatetime = `${parts.month}.${parts.day}${weekday ? `(${weekday})` : ''} ${parts.hour}:${parts.minute}`;
    updateLiveWeatherCompactSummary({ datetime: compactDatetime });
}

function formatKstNow() {
    const parts = getKstNowParts();
    if (!parts) return '--';
    const datePart = `${parts.year}. ${parts.month}. ${parts.day}.`;
    const timePart = `${parts.hour}:${parts.minute}:${parts.second}`;
    const weekday = parts.weekday || '';
    return `${datePart} (${weekday}) ${timePart}`;
}

function isNaturallyFocusableElement(element) {
    if (!(element instanceof HTMLElement)) return false;
    if (element.hasAttribute('disabled')) return false;
    const tag = element.tagName.toLowerCase();
    if (['button', 'input', 'select', 'textarea'].includes(tag)) return true;
    if (tag === 'a' && element.hasAttribute('href')) return true;
    const editable = element.getAttribute('contenteditable');
    return editable === '' || editable === 'true';
}

function clampToRange(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return Math.min(Math.max(value, min), max);
}

function getHoverTooltipText(element) {
    if (!element) return '';
    const value = element.getAttribute('data-tooltip');
    return value ? value.trim() : '';
}

function ensureHoverTooltipLayer() {
    if (hoverTooltipLayer && document.body.contains(hoverTooltipLayer)) {
        return hoverTooltipLayer;
    }
    hoverTooltipLayer = document.getElementById(HOVER_TOOLTIP_LAYER_ID);
    if (!hoverTooltipLayer) {
        const layer = document.createElement('div');
        layer.id = HOVER_TOOLTIP_LAYER_ID;
        layer.className = 'hover-tooltip-layer';
        layer.setAttribute('aria-hidden', 'true');
        document.body.appendChild(layer);
        hoverTooltipLayer = layer;
    }
    document.body.classList.add('has-tooltip-layer');
    return hoverTooltipLayer;
}

function hideHoverTooltipLayer({ clearAnchor = true } = {}) {
    if (hoverTooltipRefreshRaf) {
        window.cancelAnimationFrame(hoverTooltipRefreshRaf);
        hoverTooltipRefreshRaf = null;
    }
    const layer = ensureHoverTooltipLayer();
    if (layer) {
        layer.classList.remove('is-visible');
        layer.setAttribute('aria-hidden', 'true');
    }
    if (clearAnchor) {
        hoverTooltipAnchor = null;
    }
}

function renderHoverTooltipLayer(anchor) {
    if (!anchor || !(anchor instanceof Element) || !document.body.contains(anchor)) {
        hideHoverTooltipLayer();
        return;
    }
    const text = getHoverTooltipText(anchor);
    if (!text) {
        hideHoverTooltipLayer();
        return;
    }

    const layer = ensureHoverTooltipLayer();
    if (!layer) return;
    layer.textContent = text;
    layer.setAttribute('aria-hidden', 'false');

    const anchorRect = anchor.getBoundingClientRect();
    const viewportWidth = Math.max(window.innerWidth || 0, document.documentElement.clientWidth || 0);
    const viewportHeight = Math.max(window.innerHeight || 0, document.documentElement.clientHeight || 0);
    const margin = HOVER_TOOLTIP_VIEWPORT_MARGIN_PX;
    const offset = HOVER_TOOLTIP_OFFSET_PX;

    layer.style.left = `${margin}px`;
    layer.style.top = `${margin}px`;
    const layerRect = layer.getBoundingClientRect();
    const width = layerRect.width;
    const height = layerRect.height;

    const maxLeft = Math.max(margin, viewportWidth - width - margin);
    const maxTop = Math.max(margin, viewportHeight - height - margin);
    let left = anchorRect.left + ((anchorRect.width - width) / 2);
    left = clampToRange(left, margin, maxLeft);

    let top = anchorRect.bottom + offset;
    if (top + height > (viewportHeight - margin)) {
        top = anchorRect.top - height - offset;
    }
    top = clampToRange(top, margin, maxTop);

    layer.style.left = `${Math.round(left)}px`;
    layer.style.top = `${Math.round(top)}px`;
    layer.classList.add('is-visible');
}

function scheduleHoverTooltipRender(anchor = null) {
    if (anchor) {
        hoverTooltipAnchor = anchor;
    }
    if (!hoverTooltipAnchor) {
        hideHoverTooltipLayer();
        return;
    }
    if (hoverTooltipRefreshRaf) return;
    hoverTooltipRefreshRaf = window.requestAnimationFrame(() => {
        hoverTooltipRefreshRaf = null;
        renderHoverTooltipLayer(hoverTooltipAnchor);
    });
}

function setHoverTooltip(element, text, { focusable = true } = {}) {
    if (!element) return;
    const resolved = text == null ? '' : String(text);
    if (resolved.trim()) {
        element.classList.add('hover-tooltip');
        element.setAttribute('data-tooltip', resolved);
        element.setAttribute('title', resolved);
        if (hoverTooltipAnchor === element) {
            scheduleHoverTooltipRender(element);
        }
        if (
            focusable
            && !element.hasAttribute('tabindex')
            && !isNaturallyFocusableElement(element)
        ) {
            element.setAttribute('tabindex', '0');
            element.setAttribute('data-tooltip-tabindex', '1');
        } else if (!focusable && element.getAttribute('data-tooltip-tabindex') === '1') {
            element.removeAttribute('tabindex');
            element.removeAttribute('data-tooltip-tabindex');
        }
    } else {
        element.classList.remove('hover-tooltip');
        element.classList.remove('is-open');
        element.removeAttribute('data-tooltip');
        element.removeAttribute('title');
        if (hoverTooltipAnchor === element) {
            hideHoverTooltipLayer();
        }
        if (element.getAttribute('data-tooltip-tabindex') === '1') {
            element.removeAttribute('tabindex');
            element.removeAttribute('data-tooltip-tabindex');
        }
    }
}

function resolveTooltipText(element, fallbackText = '') {
    const fallback = fallbackText == null ? '' : String(fallbackText).trim();
    if (fallback) return fallback;
    if (!element) return '';
    const title = element.getAttribute('title');
    if (title && title.trim()) return title.trim();
    const ariaLabel = element.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
    return '';
}

function syncHoverTooltipFromLabel(element, fallbackText = '', options = {}) {
    if (!element) return;
    setHoverTooltip(element, resolveTooltipText(element, fallbackText), options);
}

function closeOpenHoverTooltips(exceptElement = null) {
    let hasPinnedTooltip = false;
    document.querySelectorAll('.hover-tooltip.is-open').forEach(element => {
        if (exceptElement && element === exceptElement) {
            hasPinnedTooltip = true;
            return;
        }
        element.classList.remove('is-open');
    });
    if (hasPinnedTooltip && exceptElement) {
        scheduleHoverTooltipRender(exceptElement);
        return;
    }
    hideHoverTooltipLayer();
}

function initializeHoverTooltipInteractions() {
    if (hoverTooltipInteractionsBound) return;
    hoverTooltipInteractionsBound = true;
    ensureHoverTooltipLayer();

    document.addEventListener('pointerover', event => {
        if (event.pointerType === 'touch') return;
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || !getHoverTooltipText(target)) return;
        if (
            hoverTooltipAnchor
            && hoverTooltipAnchor !== target
            && hoverTooltipAnchor.classList.contains('is-open')
        ) {
            return;
        }
        scheduleHoverTooltipRender(target);
    });

    document.addEventListener('pointerout', event => {
        if (event.pointerType === 'touch') return;
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || hoverTooltipAnchor !== target) return;
        if (target.classList.contains('is-open') || document.activeElement === target) return;
        const related = event.relatedTarget;
        if (related instanceof Node && target.contains(related)) return;
        hideHoverTooltipLayer();
    });

    document.addEventListener('focusin', event => {
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || !getHoverTooltipText(target)) return;
        scheduleHoverTooltipRender(target);
    });

    document.addEventListener('focusout', event => {
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || hoverTooltipAnchor !== target || target.classList.contains('is-open')) return;
        window.requestAnimationFrame(() => {
            if (document.activeElement === target) return;
            hideHoverTooltipLayer();
        });
    });

    document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || !target.getAttribute('data-tooltip')) {
            closeOpenHoverTooltips();
            return;
        }
        const willOpen = !target.classList.contains('is-open');
        closeOpenHoverTooltips(target);
        target.classList.toggle('is-open', willOpen);
        if (willOpen) {
            scheduleHoverTooltipRender(target);
        } else if (hoverTooltipAnchor === target) {
            hideHoverTooltipLayer();
        }
    });

    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        closeOpenHoverTooltips();
    });

    window.addEventListener('resize', () => {
        if (!hoverTooltipAnchor) return;
        scheduleHoverTooltipRender();
    });

    window.addEventListener('scroll', () => {
        if (!hoverTooltipAnchor) return;
        scheduleHoverTooltipRender();
    }, true);
}

function setTextWithTooltip(element, text) {
    if (!element) return;
    const resolved = text == null ? '' : String(text);
    element.textContent = resolved;
    setHoverTooltip(element, resolved);
}

function syncWeatherCurrentRowTooltip(currentElement = null) {
    const valueElement = currentElement || document.getElementById('codex-weather-current');
    if (!valueElement) return;
    const row = valueElement.closest('.live-weather-current');
    if (!row) return;
    const rowTooltip = valueElement.getAttribute('data-tooltip') || valueElement.textContent || '';
    setHoverTooltip(row, rowTooltip);
}

function getThemeToggleTooltipText(isDarkThemeEnabled) {
    return isDarkThemeEnabled ? 'Switch to light mode' : 'Switch to dark mode';
}

function updateThemeSwitchTooltip(themeToggle = null) {
    const toggle = themeToggle || document.getElementById('codex-theme-toggle');
    if (!toggle) return;
    const tooltip = getThemeToggleTooltipText(Boolean(toggle.checked));
    toggle.setAttribute('aria-label', tooltip);
    toggle.setAttribute('title', tooltip);
    const switchControl = document.querySelector('.theme-switch');
    if (switchControl) {
        setHoverTooltip(switchControl, tooltip, { focusable: false });
    }
}

function initializeHeaderActionTooltips({
    themeToggle,
    gitBranch,
    gitCommitBtn,
    gitPushBtn,
    gitSyncBtn,
    fileBrowserBtn,
    workModeToggleBtn,
    refreshBtn
} = {}) {
    syncHoverTooltipFromLabel(gitBranch);
    [gitCommitBtn, gitPushBtn, gitSyncBtn, fileBrowserBtn, workModeToggleBtn, refreshBtn].forEach(button => {
        syncHoverTooltipFromLabel(button);
    });
    updateThemeSwitchTooltip(themeToggle);
}

function normalizeGitChangedFilesCount(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    return Math.max(0, Math.round(numeric));
}

function normalizeGitDivergenceCount(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    return Math.max(0, Math.round(numeric));
}

function normalizeGitWindowsInvalidFiles(value) {
    if (!Array.isArray(value)) return [];
    const normalized = [];
    const seenPaths = new Set();
    value.forEach(item => {
        if (!item || typeof item !== 'object') return;
        const rawPath = typeof item.path === 'string' ? item.path.trim() : '';
        const path = rawPath.replace(/^\.\//, '');
        if (!path || seenPaths.has(path)) return;
        seenPaths.add(path);
        const reasons = Array.isArray(item.reasons)
            ? item.reasons.map(reason => String(reason || '').trim()).filter(Boolean)
            : [];
        normalized.push({ path, reasons });
    });
    normalized.sort((left, right) => compareGitPathValues(left.path, right.path));
    return normalized;
}

function normalizeGitWindowsInvalidCount(value, fallback = 0) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
        return Math.max(0, Math.round(numeric));
    }
    const fallbackNumeric = Number(fallback);
    if (Number.isFinite(fallbackNumeric)) {
        return Math.max(0, Math.round(fallbackNumeric));
    }
    return 0;
}

function normalizeGitWindowsPathIssueState(value, invalidCount = 0) {
    return Boolean(value) || normalizeGitWindowsInvalidCount(invalidCount) > 0;
}

function formatGitWindowsPathIssueSummary(invalidCount = 0) {
    const count = normalizeGitWindowsInvalidCount(invalidCount);
    return `Windows 비호환 파일명 ${count}개`;
}

function buildGitWindowsPathIssueToastMessage(invalidFiles, invalidCount = 0) {
    const normalizedFiles = normalizeGitWindowsInvalidFiles(invalidFiles);
    const count = normalizeGitWindowsInvalidCount(
        invalidCount,
        normalizedFiles.length
    );
    if (!normalizedFiles.length) {
        return `${formatGitWindowsPathIssueSummary(count)}가 포함되어 커밋할 수 없습니다. 파일명을 수정해주세요.`;
    }
    const preview = normalizedFiles.slice(0, 3).map(file => file.path).join(', ');
    const suffix = normalizedFiles.length > 3 ? ', ...' : '';
    return `${formatGitWindowsPathIssueSummary(count)}가 포함되어 커밋할 수 없습니다: ${preview}${suffix}`;
}

async function loadLiveWeatherData({ silent = false } = {}) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;

    if (!silent) {
        setTextWithTooltip(locationElement, DEFAULT_WEATHER_LOCATION_LABEL);
        setTextWithTooltip(currentElement, '날씨 불러오는 중...');
        setTextWithTooltip(todayElement, '불러오는 중...');
        setTextWithTooltip(tomorrowElement, '불러오는 중...');
        syncWeatherCurrentRowTooltip(currentElement);
    }

    try {
        const position = getDefaultWeatherPosition();
        const weather = await fetchWeatherForecast(position.latitude, position.longitude);

        renderWeatherSummary({
            locationName: position.label || DEFAULT_WEATHER_LOCATION_LABEL,
            weather
        });
    } catch (error) {
        renderWeatherError(DEFAULT_WEATHER_LOCATION_LABEL, normalizeError(error, '날씨 정보를 불러오지 못했습니다.'));
    }
}

function getDefaultWeatherPosition() {
    return {
        latitude: DEFAULT_WEATHER_POSITION.latitude,
        longitude: DEFAULT_WEATHER_POSITION.longitude,
        label: DEFAULT_WEATHER_POSITION.label,
        isDefault: true
    };
}

function showToast(message, { tone = 'error', durationMs = WEATHER_LOCATION_FAILURE_TOAST_MS } = {}) {
    const text = String(message || '').trim();
    if (!text) return;
    const layer = ensureToastLayer();
    if (!layer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${tone}`;
    toast.textContent = text;
    layer.appendChild(toast);

    window.requestAnimationFrame(() => {
        toast.classList.add('is-visible');
    });

    const visibleMs = Number.isFinite(Number(durationMs))
        ? Math.max(1200, Number(durationMs))
        : WEATHER_LOCATION_FAILURE_TOAST_MS;
    window.setTimeout(() => {
        toast.classList.remove('is-visible');
        window.setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 180);
    }, visibleMs);
}

async function fetchCodexRestartPolicy() {
    try {
        const result = await fetchJson('/api/codex/runtime/restart-policy', {
            cache: 'no-store',
            timeoutMs: HEADER_RESTART_POLICY_REQUEST_TIMEOUT_MS
        });
        return result && typeof result === 'object' ? result : {};
    } catch (error) {
        return {
            known: false,
            use_reloader: null,
            error: normalizeError(error, 'use_reloader 설정을 확인하지 못했습니다.')
        };
    }
}

function getRecognizedViewportWidth() {
    const innerWidth = Number(window.innerWidth);
    if (Number.isFinite(innerWidth) && innerWidth > 0) {
        return Math.round(innerWidth);
    }
    const clientWidth = Number(document.documentElement?.clientWidth);
    if (Number.isFinite(clientWidth) && clientWidth > 0) {
        return Math.round(clientWidth);
    }
    return null;
}

async function showHeaderDetailsToast() {
    const descriptionElement = document.getElementById('codex-header-description');
    const storageElement = document.getElementById('codex-session-storage');
    const descriptionText = String(descriptionElement?.textContent || 'Manage Codex Agent sessions.').trim();
    const storageText = String(storageElement?.textContent || '').trim();
    const restartPolicy = await fetchCodexRestartPolicy();
    const useReloader = restartPolicy?.use_reloader;
    const restartText = typeof useReloader === 'boolean'
        ? `코드 변경 감지 재시작(use_reloader): ${useReloader ? 'true' : 'false'}`
        : '코드 변경 감지 재시작(use_reloader): 확인 불가';
    const parts = [];
    if (descriptionText) {
        parts.push(descriptionText);
    }
    if (storageText) {
        parts.push(storageText);
    }
    parts.push(restartText);
    const recognizedWidth = getRecognizedViewportWidth();
    parts.push(
        recognizedWidth !== null
            ? `현재 인식 너비: ${recognizedWidth}px`
            : '현재 인식 너비: 확인 불가'
    );
    const message = parts.length > 0 ? parts.join(' · ') : '세부 정보가 없습니다.';
    showToast(message, { tone: 'default', durationMs: 4600 });
}

function ensureToastLayer() {
    const existing = document.getElementById(TOAST_LAYER_ID);
    if (existing) return existing;
    if (!document.body) return null;

    const layer = document.createElement('div');
    layer.id = TOAST_LAYER_ID;
    layer.className = 'toast-layer';
    layer.setAttribute('aria-live', 'polite');
    layer.setAttribute('aria-atomic', 'true');
    document.body.appendChild(layer);
    return layer;
}

async function fetchWeatherForecast(latitude, longitude) {
    const url = new URL('https://api.open-meteo.com/v1/forecast');
    url.searchParams.set('latitude', String(latitude));
    url.searchParams.set('longitude', String(longitude));
    url.searchParams.set('timezone', KST_TIME_ZONE);
    url.searchParams.set('forecast_days', '2');
    url.searchParams.set(
        'current',
        [
            'temperature_2m',
            'apparent_temperature',
            'relative_humidity_2m',
            'wind_speed_10m',
            'weather_code',
            'is_day'
        ].join(',')
    );
    url.searchParams.set(
        'daily',
        [
            'weather_code',
            'temperature_2m_max',
            'temperature_2m_min',
            'precipitation_probability_max',
            'sunrise',
            'sunset'
        ].join(',')
    );

    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`날씨 정보를 불러오지 못했습니다. (${response.status})`);
    }
    return response.json();
}

function renderWeatherSummary({ locationName, weather }) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;

    const current = weather?.current || {};
    const currentTemp = formatTemperatureValue(current.temperature_2m);
    const feelsLike = formatTemperatureValue(current.apparent_temperature);
    const humidity = formatPercentValue(current.relative_humidity_2m);
    const wind = Number.isFinite(Number(current.wind_speed_10m))
        ? `${Math.round(Number(current.wind_speed_10m))}km/h`
        : '--';
    const weatherText = formatWeatherCode(current.weather_code, current.is_day === 1);
    const todayHighRaw = Array.isArray(weather?.daily?.temperature_2m_max)
        ? weather.daily.temperature_2m_max[0]
        : null;
    const todayLowRaw = Array.isArray(weather?.daily?.temperature_2m_min)
        ? weather.daily.temperature_2m_min[0]
        : null;
    const todayHigh = formatTemperatureValue(todayHighRaw);
    const todayLow = formatTemperatureValue(todayLowRaw);

    setTextWithTooltip(locationElement, locationName || '알 수 없는 위치');
    setTextWithTooltip(
        currentElement,
        `현재 ${currentTemp} · ${weatherText} · 체감 ${feelsLike} · 습도 ${humidity} · 바람 ${wind}`
    );
    syncWeatherCurrentRowTooltip(currentElement);
    setTextWithTooltip(todayElement, renderDailyForecast(weather?.daily, 0));
    setTextWithTooltip(tomorrowElement, renderDailyForecast(weather?.daily, 1));
    updateLiveWeatherCompactSummary({
        currentTemp,
        weatherText,
        highTemp: todayHigh,
        lowTemp: todayLow,
        hasWeather: true
    });
}

function renderWeatherError(locationText, detailText) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;
    setTextWithTooltip(locationElement, locationText);
    setTextWithTooltip(currentElement, detailText);
    syncWeatherCurrentRowTooltip(currentElement);
    setTextWithTooltip(todayElement, '--');
    setTextWithTooltip(tomorrowElement, '--');
    updateLiveWeatherCompactSummary({
        currentTemp: '--',
        weatherText: '날씨 확인 불가',
        highTemp: '--',
        lowTemp: '--',
        hasWeather: false
    });
}

function renderDailyForecast(daily, index) {
    if (!daily || !Number.isFinite(index)) return '--';
    const weatherCode = Array.isArray(daily.weather_code) ? daily.weather_code[index] : null;
    const maxTemp = Array.isArray(daily.temperature_2m_max) ? daily.temperature_2m_max[index] : null;
    const minTemp = Array.isArray(daily.temperature_2m_min) ? daily.temperature_2m_min[index] : null;
    const rainChance = Array.isArray(daily.precipitation_probability_max)
        ? daily.precipitation_probability_max[index]
        : null;
    const sunrise = Array.isArray(daily.sunrise) ? daily.sunrise[index] : null;
    const sunset = Array.isArray(daily.sunset) ? daily.sunset[index] : null;

    const weatherText = formatWeatherCode(weatherCode, true);
    const highLow = `최고 ${formatTemperatureValue(maxTemp)} / 최저 ${formatTemperatureValue(minTemp)}`;
    const rainText = `강수확률 ${formatPercentValue(rainChance)}`;
    const sunriseText = `일출 ${formatKstHourMinute(sunrise)}`;
    const sunsetText = `일몰 ${formatKstHourMinute(sunset)}`;
    return `${weatherText} · ${highLow} · ${rainText} · ${sunriseText} · ${sunsetText}`;
}

function formatWeatherCode(code, isDay) {
    const normalized = Number(code);
    if (!Number.isFinite(normalized)) return '알 수 없음';
    if (normalized === 0) return isDay ? '맑음' : '맑은 밤';
    if ([1, 2, 3].includes(normalized)) return '흐림';
    if ([45, 48].includes(normalized)) return '안개';
    if ([51, 53, 55, 56, 57].includes(normalized)) return '이슬비';
    if ([61, 63, 65, 66, 67, 80, 81, 82].includes(normalized)) return '비';
    if ([71, 73, 75, 77, 85, 86].includes(normalized)) return '눈';
    if ([95, 96, 99].includes(normalized)) return '뇌우';
    return '혼합';
}

function formatTemperatureValue(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return `${Math.round(numeric)}°C`;
}

function formatPercentValue(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    return `${Math.max(0, Math.min(100, Math.round(numeric)))}%`;
}

function formatKstHourMinute(value) {
    if (!value) return '--';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return new Intl.DateTimeFormat('ko-KR', {
        timeZone: KST_TIME_ZONE,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    }).format(date);
}

function updateSessionsToggleButton(toggle, collapsed) {
    if (!toggle) return;
    const isCollapsed = Boolean(collapsed);
    toggle.classList.toggle('is-collapsed', isCollapsed);
    toggle.setAttribute('aria-label', isCollapsed ? 'Expand sessions panel' : 'Collapse sessions panel');
    toggle.setAttribute('title', isCollapsed ? 'Expand sessions panel' : 'Collapse sessions panel');
}

function syncSidebarStackLayout() {
    const stack = document.querySelector('.sidebar-stack');
    if (!stack) return;
    const weatherPanel = document.getElementById('codex-live-weather-panel');
    const sessionsPanel = document.querySelector('.sessions');
    const weatherCompact = Boolean(weatherPanel?.classList.contains('is-compact'));
    const sessionsCollapsed = Boolean(sessionsPanel?.classList.contains('is-collapsed'));
    stack.classList.toggle('is-weather-compact', weatherCompact);
    stack.classList.toggle('is-sessions-collapsed', sessionsCollapsed);
}

function setSessionsCollapsed(collapsed, { persist = true } = {}) {
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    if (!sessionsPanel || !sessionsToggle) return;
    sessionsPanel.classList.toggle('is-collapsed', collapsed);
    sessionsToggle.setAttribute('aria-expanded', String(!collapsed));
    updateSessionsToggleButton(sessionsToggle, collapsed);
    syncSidebarStackLayout();
    updateSessionsHeaderSummary();
    if (persist) {
        try {
            localStorage.setItem(SESSION_COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function updateChatFullscreenButton(button, enabled) {
    if (!button) return;
    const isEnabled = Boolean(enabled);
    button.classList.toggle('is-active', isEnabled);
    button.setAttribute('aria-pressed', String(isEnabled));
    const label = isEnabled ? 'Exit fullscreen chat' : 'Expand chat to fullscreen';
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
}

function getActiveSessionIndex() {
    if (!Array.isArray(state.sessions) || state.sessions.length === 0) return -1;
    if (!state.activeSessionId) return -1;
    return state.sessions.findIndex(session => session?.id === state.activeSessionId);
}

function getAdjacentSessionId(step) {
    const direction = Math.sign(Number(step));
    if (!Number.isFinite(direction) || direction === 0) return null;
    const activeIndex = getActiveSessionIndex();
    if (activeIndex < 0) return null;
    const targetIndex = activeIndex + direction;
    if (targetIndex < 0 || targetIndex >= state.sessions.length) return null;
    const target = state.sessions[targetIndex];
    return target?.id || null;
}

async function moveToAdjacentSession(step) {
    const targetId = getAdjacentSessionId(step);
    if (!targetId || targetId === state.activeSessionId) return;
    await loadSession(targetId);
}

function updateChatSessionNavigationButtons() {
    const prevButton = document.getElementById('codex-chat-session-prev');
    const nextButton = document.getElementById('codex-chat-session-next');
    if (!prevButton && !nextButton) return;

    const activeIndex = getActiveSessionIndex();
    const hasSessions = Array.isArray(state.sessions) && state.sessions.length > 0;
    const hasActive = hasSessions && activeIndex >= 0;

    if (prevButton) {
        prevButton.disabled = !(hasActive && activeIndex > 0);
    }
    if (nextButton) {
        nextButton.disabled = !(hasActive && activeIndex < state.sessions.length - 1);
    }
}

function setChatFullscreen(enabled) {
    const app = document.querySelector('.app');
    const button = document.getElementById('codex-chat-fullscreen');
    if (!app || !button) return;
    const isEnabled = Boolean(enabled);
    app.classList.toggle(CHAT_FULLSCREEN_CLASS, isEnabled);
    updateChatFullscreenButton(button, isEnabled);
}

function getWorkModeElements() {
    return {
        app: document.querySelector('.app'),
        layout: document.querySelector('.layout'),
        toggle: document.getElementById('codex-work-mode-toggle'),
        divider: document.getElementById('codex-work-mode-divider'),
        mobileBrowserBtn: document.getElementById('codex-work-mode-mobile-browser'),
        preview: document.getElementById('codex-work-mode-preview')
    };
}

function getFilePanelElementsByPrefix({
    scopeElement,
    rootElement = scopeElement,
    prefix = '',
    pathElement = null,
    listPanelSelector = '.file-browser-list-panel',
    viewerPanelSelector = '.file-browser-viewer-panel'
} = {}) {
    const scope = scopeElement instanceof Element ? scopeElement : null;
    if (!scope) return null;
    const root = rootElement instanceof Element ? rootElement : scope;
    const normalizedPrefix = String(prefix || '').trim();
    if (!normalizedPrefix) return null;
    const scopedQuery = selector => root.querySelector(selector);
    const byId = suffix => scopedQuery(`#${normalizedPrefix}-${suffix}`);
    const columns = byId('columns');
    return {
        root,
        layout: byId('layout'),
        selectionBar: byId('selection-bar'),
        selectionSummary: byId('selection-summary'),
        selectionActions: byId('selection-actions'),
        newFileBtn: byId('new-file'),
        deleteDirectoryBtn: byId('delete-directory'),
        addContextBtn: byId('add-context'),
        moveBtn: byId('move'),
        selectAllBtn: byId('select-all'),
        clearSelectionBtn: byId('clear-selection'),
        downloadBtn: byId('download'),
        deleteBtn: byId('delete'),
        gridScroll: byId('grid-scroll'),
        hScroll: byId('hscroll'),
        hScrollTrack: byId('hscroll-track'),
        table: byId('table'),
        columns,
        divider: byId('divider'),
        path: pathElement instanceof Element ? pathElement : document.getElementById(`${normalizedPrefix}-path`),
        meta: byId('meta'),
        loading: byId('loading'),
        empty: byId('empty'),
        list: byId('list'),
        listPanel: root.querySelector(listPanelSelector),
        viewerPanel: root.querySelector(viewerPanelSelector),
        viewerHeader: byId('viewer-header'),
        viewerMeta: byId('viewer-meta'),
        viewerActions: byId('viewer-actions'),
        viewerContent: byId('viewer-content'),
        editBtn: byId('edit'),
        saveBtn: byId('save'),
        colResizers: columns ? Array.from(columns.querySelectorAll('[data-resize-col]')) : []
    };
}

function getWorkModeFileElements() {
    const preview = document.getElementById('codex-work-mode-preview');
    if (!preview) return null;
    const panel = getFilePanelElementsByPrefix({
        scopeElement: preview,
        rootElement: preview,
        prefix: 'codex-work-mode-file',
        pathElement: document.getElementById('codex-work-mode-file-path'),
        listPanelSelector: '.work-mode-file-list-panel'
    });
    if (!panel) return null;
    return {
        ...panel,
        preview,
        refreshBtn: document.getElementById('codex-work-mode-file-refresh'),
        upBtn: document.getElementById('codex-work-mode-file-up'),
        backBtn: document.getElementById('codex-work-mode-file-back'),
        chatBtn: document.getElementById('codex-work-mode-chat-back'),
        openNewBtn: document.getElementById('codex-work-mode-file-open-new'),
        fullscreenBtn: document.getElementById('codex-work-mode-file-fullscreen')
    };
}

function normalizeWorkModeFileScrollSnapshot(value, { includeContext = false } = {}) {
    if (!value || typeof value !== 'object') return null;
    const rawTop = Number(value.top);
    const rawLeft = Number(value.left);
    const normalized = {
        top: Number.isFinite(rawTop) ? Math.max(0, Math.round(rawTop)) : 0,
        left: Number.isFinite(rawLeft) ? Math.max(0, Math.round(rawLeft)) : 0
    };
    if (!includeContext) {
        return normalized;
    }
    return {
        ...normalized,
        root: normalizeFileBrowserRoot(value.root),
        path: normalizeFileBrowserRelativePath(value.path)
    };
}

function captureWorkModeFileScrollSnapshot({ includeContext = false } = {}) {
    const elements = getWorkModeFileElements();
    if (!elements?.gridScroll) return null;
    const rawTop = Number(elements.gridScroll.scrollTop || 0);
    const rawGridLeft = Number(elements.gridScroll.scrollLeft || 0);
    const rawRailLeft = Number(elements.hScroll?.scrollLeft || 0);
    const snapshot = {
        top: Number.isFinite(rawTop) ? Math.max(0, Math.round(rawTop)) : 0,
        left: Number.isFinite(rawGridLeft) || Number.isFinite(rawRailLeft)
            ? Math.max(0, Math.round(Math.max(rawGridLeft, rawRailLeft)))
            : 0
    };
    if (!includeContext) {
        return snapshot;
    }
    return {
        ...snapshot,
        root: normalizeFileBrowserRoot(workModeFileRoot),
        path: normalizeFileBrowserRelativePath(workModeFilePath)
    };
}

function applyWorkModeFileScrollSnapshot(snapshot) {
    const normalized = normalizeWorkModeFileScrollSnapshot(snapshot);
    if (!normalized) return false;
    const elements = getWorkModeFileElements();
    if (!elements?.gridScroll) return false;
    const nextTop = normalized.top;
    const nextLeft = normalized.left;
    if (Math.round(elements.gridScroll.scrollTop || 0) !== nextTop) {
        elements.gridScroll.scrollTop = nextTop;
    }
    if (workModeFileHorizontalSyncLock) {
        return true;
    }
    workModeFileHorizontalSyncLock = true;
    try {
        if (Math.round(elements.gridScroll.scrollLeft || 0) !== nextLeft) {
            elements.gridScroll.scrollLeft = nextLeft;
        }
        if (elements.hScroll && Math.round(elements.hScroll.scrollLeft || 0) !== nextLeft) {
            elements.hScroll.scrollLeft = nextLeft;
        }
    } finally {
        workModeFileHorizontalSyncLock = false;
    }
    return true;
}

function normalizeWorkModeFileViewerScrollSnapshot(value, { includeContext = false } = {}) {
    if (!value || typeof value !== 'object') return null;
    const rawTop = Number(value.top);
    const rawLeft = Number(value.left);
    const rawIframeTop = Number(value.iframeTop);
    const rawIframeLeft = Number(value.iframeLeft);
    const normalized = {
        top: Number.isFinite(rawTop) ? Math.max(0, Math.round(rawTop)) : 0,
        left: Number.isFinite(rawLeft) ? Math.max(0, Math.round(rawLeft)) : 0
    };
    if (Number.isFinite(rawIframeTop) || Number.isFinite(rawIframeLeft)) {
        normalized.iframeTop = Number.isFinite(rawIframeTop) ? Math.max(0, Math.round(rawIframeTop)) : 0;
        normalized.iframeLeft = Number.isFinite(rawIframeLeft) ? Math.max(0, Math.round(rawIframeLeft)) : 0;
    }
    if (!includeContext) {
        return normalized;
    }
    return {
        ...normalized,
        root: normalizeFileBrowserRoot(value.root),
        path: normalizeFileBrowserRelativePath(value.path),
        selectedPath: normalizeFileBrowserRelativePath(value.selectedPath)
    };
}

function readFileBrowserIframeScrollSnapshot(iframe) {
    if (!(iframe instanceof HTMLIFrameElement)) return null;
    try {
        const frameWindow = iframe.contentWindow;
        const frameDocument = iframe.contentDocument;
        if (!frameWindow || !frameDocument || frameDocument.readyState !== 'complete') {
            return null;
        }
        const scrollingElement = frameDocument.scrollingElement
            || frameDocument.documentElement
            || frameDocument.body;
        const windowTop = Number(frameWindow.scrollY);
        const windowLeft = Number(frameWindow.scrollX);
        const pageTop = Number(frameWindow.pageYOffset);
        const pageLeft = Number(frameWindow.pageXOffset);
        const elementTop = Number(scrollingElement?.scrollTop);
        const elementLeft = Number(scrollingElement?.scrollLeft);
        const rawTop = Number.isFinite(windowTop)
            ? windowTop
            : (Number.isFinite(pageTop) ? pageTop : elementTop);
        const rawLeft = Number.isFinite(windowLeft)
            ? windowLeft
            : (Number.isFinite(pageLeft) ? pageLeft : elementLeft);
        return {
            top: Number.isFinite(rawTop) ? Math.max(0, Math.round(rawTop)) : 0,
            left: Number.isFinite(rawLeft) ? Math.max(0, Math.round(rawLeft)) : 0
        };
    } catch (error) {
        return null;
    }
}

function writeFileBrowserIframeScrollSnapshot(iframe, top, left) {
    if (!(iframe instanceof HTMLIFrameElement)) return false;
    try {
        const frameWindow = iframe.contentWindow;
        const frameDocument = iframe.contentDocument;
        if (!frameWindow || !frameDocument || frameDocument.readyState !== 'complete') {
            return false;
        }
        const nextTop = Number.isFinite(Number(top)) ? Math.max(0, Math.round(Number(top))) : 0;
        const nextLeft = Number.isFinite(Number(left)) ? Math.max(0, Math.round(Number(left))) : 0;
        const scrollingElement = frameDocument.scrollingElement
            || frameDocument.documentElement
            || frameDocument.body;
        if (scrollingElement) {
            if (Math.round(scrollingElement.scrollTop || 0) !== nextTop) {
                scrollingElement.scrollTop = nextTop;
            }
            if (Math.round(scrollingElement.scrollLeft || 0) !== nextLeft) {
                scrollingElement.scrollLeft = nextLeft;
            }
        }
        if (typeof frameWindow.scrollTo === 'function') {
            frameWindow.scrollTo(nextLeft, nextTop);
        }
        return true;
    } catch (error) {
        return false;
    }
}

function captureFileBrowserViewerScrollSnapshot(container) {
    if (!(container instanceof HTMLElement)) return null;
    const snapshot = {
        top: Math.max(0, Math.round(Number(container.scrollTop || 0))),
        left: Math.max(0, Math.round(Number(container.scrollLeft || 0)))
    };
    const iframe = container.querySelector('.file-browser-html-preview');
    const iframeSnapshot = readFileBrowserIframeScrollSnapshot(iframe);
    if (iframeSnapshot) {
        snapshot.iframeTop = iframeSnapshot.top;
        snapshot.iframeLeft = iframeSnapshot.left;
    }
    return snapshot;
}

function applyFileBrowserViewerScrollSnapshot(container, snapshot, { renderToken = '' } = {}) {
    if (!(container instanceof HTMLElement)) return false;
    const normalized = normalizeWorkModeFileViewerScrollSnapshot(snapshot);
    if (!normalized) return false;
    const expectedRenderToken = String(renderToken || container.dataset?.renderToken || '');
    const matchesRenderToken = () => !expectedRenderToken || container.dataset?.renderToken === expectedRenderToken;

    if (!matchesRenderToken()) return false;
    if (Math.round(container.scrollTop || 0) !== normalized.top) {
        container.scrollTop = normalized.top;
    }
    if (Math.round(container.scrollLeft || 0) !== normalized.left) {
        container.scrollLeft = normalized.left;
    }

    const hasIframeSnapshot = Object.prototype.hasOwnProperty.call(normalized, 'iframeTop')
        || Object.prototype.hasOwnProperty.call(normalized, 'iframeLeft');
    if (!hasIframeSnapshot) {
        return true;
    }

    const applyIframeSnapshot = () => {
        if (!matchesRenderToken()) return true;
        const iframe = container.querySelector('.file-browser-html-preview');
        if (!(iframe instanceof HTMLIFrameElement)) return false;
        return writeFileBrowserIframeScrollSnapshot(iframe, normalized.iframeTop, normalized.iframeLeft);
    };

    if (applyIframeSnapshot()) {
        return true;
    }

    let retries = 0;
    const scheduleRetry = () => {
        if (!matchesRenderToken()) return;
        if (applyIframeSnapshot()) return;
        retries += 1;
        if (retries >= FILE_BROWSER_VIEWER_IFRAME_SCROLL_RESTORE_MAX_RETRIES) {
            return;
        }
        window.setTimeout(scheduleRetry, FILE_BROWSER_VIEWER_IFRAME_SCROLL_RESTORE_RETRY_MS);
    };

    const iframe = container.querySelector('.file-browser-html-preview');
    if (iframe instanceof HTMLIFrameElement) {
        iframe.addEventListener('load', () => {
            window.setTimeout(scheduleRetry, 0);
        }, { once: true });
    }
    window.setTimeout(scheduleRetry, 0);
    return true;
}

function captureWorkModeFileViewerScrollSnapshot({ includeContext = false } = {}) {
    const elements = getWorkModeFileElements();
    const snapshot = captureFileBrowserViewerScrollSnapshot(elements?.viewerContent);
    if (!snapshot) return null;
    if (!includeContext) {
        return snapshot;
    }
    return {
        ...snapshot,
        root: normalizeFileBrowserRoot(workModeFileRoot),
        path: normalizeFileBrowserRelativePath(workModeFilePath),
        selectedPath: normalizeFileBrowserRelativePath(workModeFileSelectedPath)
    };
}

function resolveWorkModeFileViewerScrollSnapshotForPersist() {
    const liveSnapshot = captureWorkModeFileViewerScrollSnapshot({ includeContext: true });
    if (!workModeHtmlPreviewState?.suspended) {
        return liveSnapshot;
    }
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    const selectedRoot = normalizeFileBrowserRoot(workModeFileRoot);
    const previewPath = normalizeFileBrowserRelativePath(workModeHtmlPreviewState?.path);
    const previewRoot = normalizeFileBrowserRoot(workModeHtmlPreviewState?.root || selectedRoot);
    if (!selectedPath || selectedPath !== previewPath || selectedRoot !== previewRoot) {
        return liveSnapshot;
    }
    const suspendedSnapshot = normalizeWorkModeFileViewerScrollSnapshot(
        workModeHtmlPreviewState?.viewerScroll,
        { includeContext: true }
    );
    return suspendedSnapshot || liveSnapshot;
}

function applyWorkModeFileViewerScrollSnapshot(snapshot, { renderToken = '' } = {}) {
    const normalized = normalizeWorkModeFileViewerScrollSnapshot(snapshot);
    if (!normalized) return false;
    const elements = getWorkModeFileElements();
    return applyFileBrowserViewerScrollSnapshot(elements?.viewerContent, normalized, { renderToken });
}

function readWorkModeFileViewState() {
    try {
        const raw = window.sessionStorage?.getItem(WORK_MODE_FILE_VIEW_STATE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        const scroll = normalizeWorkModeFileScrollSnapshot(parsed?.scroll, { includeContext: true });
        const viewerScroll = normalizeWorkModeFileViewerScrollSnapshot(parsed?.viewerScroll, { includeContext: true });
        return {
            root: normalizeFileBrowserRoot(parsed?.root),
            path: normalizeFileBrowserRelativePath(parsed?.path),
            selectedPath: normalizeFileBrowserRelativePath(parsed?.selectedPath),
            mobileView: normalizeWorkModeMobileView(parsed?.mobileView),
            mobileBrowseView: normalizeWorkModeMobileBrowseView(parsed?.mobileBrowseView || parsed?.mobileView),
            viewerFullscreen: Boolean(parsed?.viewerFullscreen),
            scroll,
            viewerScroll
        };
    } catch (error) {
        return null;
    }
}

function persistWorkModeFileViewState() {
    try {
        const payload = {
            root: normalizeFileBrowserRoot(workModeFileRoot),
            path: normalizeFileBrowserRelativePath(workModeFilePath),
            selectedPath: normalizeFileBrowserRelativePath(workModeFileSelectedPath),
            mobileView: normalizeWorkModeMobileView(workModeMobileView),
            mobileBrowseView: normalizeWorkModeMobileBrowseView(workModeMobileBrowseView),
            viewerFullscreen: Boolean(workModeFileViewerFullscreen),
            scroll: captureWorkModeFileScrollSnapshot({ includeContext: true }),
            viewerScroll: resolveWorkModeFileViewerScrollSnapshotForPersist(),
            savedAt: Date.now()
        };
        window.sessionStorage?.setItem(WORK_MODE_FILE_VIEW_STATE_KEY, JSON.stringify(payload));
    } catch (error) {
        void error;
    }
}

function schedulePersistWorkModeFileViewState(delayMs = WORK_MODE_FILE_STATE_PERSIST_DEBOUNCE_MS) {
    const numericDelay = Number(delayMs);
    const waitMs = Number.isFinite(numericDelay) ? Math.max(0, Math.round(numericDelay)) : 0;
    if (workModeFileStatePersistTimer !== null) {
        window.clearTimeout(workModeFileStatePersistTimer);
        workModeFileStatePersistTimer = null;
    }
    workModeFileStatePersistTimer = window.setTimeout(() => {
        workModeFileStatePersistTimer = null;
        persistWorkModeFileViewState();
    }, waitMs);
}

function flushPersistWorkModeFileViewState() {
    if (workModeFileStatePersistTimer !== null) {
        window.clearTimeout(workModeFileStatePersistTimer);
        workModeFileStatePersistTimer = null;
    }
    persistWorkModeFileViewState();
}

function initializeWorkModeFileViewState(isMobile = false) {
    const saved = readWorkModeFileViewState();
    if (!saved) return;
    workModeFileRoot = normalizeFileBrowserRoot(saved.root || workModeFileRoot);
    workModeFilePath = normalizeFileBrowserRelativePath(saved.path || '');
    workModeFileSelectedPath = normalizeFileBrowserRelativePath(saved.selectedPath || '');
    workModeMobileBrowseView = normalizeWorkModeMobileBrowseView(saved.mobileBrowseView || saved.mobileView);
    workModeMobileView = isMobile
        ? WORK_MODE_MOBILE_VIEW_CHAT
        : normalizeWorkModeMobileView(saved.mobileView);
    workModeFileViewerFullscreen = Boolean(saved.viewerFullscreen);
    pendingWorkModeFileScrollRestore = normalizeWorkModeFileScrollSnapshot(saved.scroll, { includeContext: true });
    pendingWorkModeFileViewerScrollRestore = normalizeWorkModeFileViewerScrollSnapshot(
        saved.viewerScroll,
        { includeContext: true }
    );
}

function consumePendingWorkModeFileScrollRestore(root = workModeFileRoot, path = workModeFilePath) {
    const pending = normalizeWorkModeFileScrollSnapshot(pendingWorkModeFileScrollRestore, { includeContext: true });
    if (!pending) return null;
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    if (pending.root !== normalizedRoot || pending.path !== normalizedPath) {
        pendingWorkModeFileScrollRestore = null;
        return null;
    }
    pendingWorkModeFileScrollRestore = null;
    return normalizeWorkModeFileScrollSnapshot(pending);
}

function consumePendingWorkModeFileViewerScrollRestore(
    root = workModeFileRoot,
    path = workModeFilePath,
    selectedPath = workModeFileSelectedPath
) {
    const pending = normalizeWorkModeFileViewerScrollSnapshot(
        pendingWorkModeFileViewerScrollRestore,
        { includeContext: true }
    );
    if (!pending) return null;
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    const normalizedSelectedPath = normalizeFileBrowserRelativePath(selectedPath);
    if (
        pending.root !== normalizedRoot
        || pending.path !== normalizedPath
        || pending.selectedPath !== normalizedSelectedPath
    ) {
        pendingWorkModeFileViewerScrollRestore = null;
        return null;
    }
    pendingWorkModeFileViewerScrollRestore = null;
    return normalizeWorkModeFileViewerScrollSnapshot(pending);
}

function normalizeWorkModeMobileView(value) {
    if (value === WORK_MODE_MOBILE_VIEW_LIST || value === WORK_MODE_MOBILE_VIEW_VIEWER) {
        return value;
    }
    return WORK_MODE_MOBILE_VIEW_CHAT;
}

function normalizeWorkModeMobileBrowseView(value) {
    return value === WORK_MODE_MOBILE_VIEW_VIEWER
        ? WORK_MODE_MOBILE_VIEW_VIEWER
        : WORK_MODE_MOBILE_VIEW_LIST;
}

function setWorkModeBrowseView(view = WORK_MODE_MOBILE_VIEW_LIST) {
    workModeMobileBrowseView = normalizeWorkModeMobileBrowseView(view);
    setWorkModeMobileView(workModeMobileView);
}

function syncWorkModeFileFullscreenButtonState() {
    const elements = getWorkModeFileElements();
    if (!elements?.fullscreenBtn) return;
    const button = elements.fullscreenBtn;
    const enabled = isWorkModeEnabled();
    const mobile = isMobileLayout();
    const fold = isFoldLayout();
    const visible = enabled && !mobile;
    const foldFullscreenEnabled = Boolean(
        workModePreviewFullscreen
        && enabled
        && fold
    );
    const viewerFullscreenEnabled = Boolean(
        workModeFileViewerFullscreen
        && enabled
        && !mobile
        && !fold
    );
    const active = foldFullscreenEnabled || viewerFullscreenEnabled;
    const nextLabel = fold
        ? (foldFullscreenEnabled ? 'File Preview 축소' : 'File Preview 전체화면')
        : (viewerFullscreenEnabled ? '파일 목록 보기' : '파일 내용 전체화면');

    button.classList.toggle('is-hidden', !visible);
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    button.setAttribute('aria-label', nextLabel);
    button.setAttribute('title', nextLabel);
    syncHoverTooltipFromLabel(button, nextLabel);
}

function setWorkModeMobileView(view = WORK_MODE_MOBILE_VIEW_CHAT) {
    const previousView = normalizeWorkModeMobileView(workModeMobileView);
    const nextView = normalizeWorkModeMobileView(view);
    workModeMobileView = nextView;
    const elements = getWorkModeElements();
    const fileElements = getWorkModeFileElements();
    const mobile = isMobileLayout();
    const fold = isFoldLayout();
    const enabled = isWorkModeEnabled();
    const applyMobileView = mobile && enabled;
    const applyFoldBrowseView = fold && enabled;
    const foldBrowseView = normalizeWorkModeMobileBrowseView(workModeMobileBrowseView);

    if (
        applyMobileView
        && previousView === WORK_MODE_MOBILE_VIEW_VIEWER
        && nextView !== WORK_MODE_MOBILE_VIEW_VIEWER
    ) {
        const viewerSnapshot = captureWorkModeFileViewerScrollSnapshot({ includeContext: true });
        if (viewerSnapshot) {
            const normalizedViewerSnapshot = syncWorkModeHtmlPreviewViewerScrollSnapshot(viewerSnapshot) || viewerSnapshot;
            pendingWorkModeFileViewerScrollRestore = normalizedViewerSnapshot;
        }
        suspendWorkModeHtmlPreviewForMobileTransition(fileElements, { viewerSnapshot });
    }

    if (applyMobileView && nextView !== WORK_MODE_MOBILE_VIEW_CHAT) {
        workModeMobileBrowseView = normalizeWorkModeMobileBrowseView(nextView);
    }

    if (elements?.app) {
        elements.app.classList.toggle(
            'is-work-mode-mobile-chat',
            applyMobileView && nextView === WORK_MODE_MOBILE_VIEW_CHAT
        );
        elements.app.classList.toggle(
            'is-work-mode-mobile-list',
            applyMobileView && nextView === WORK_MODE_MOBILE_VIEW_LIST
        );
        elements.app.classList.toggle(
            'is-work-mode-mobile-viewer',
            applyMobileView && nextView === WORK_MODE_MOBILE_VIEW_VIEWER
        );
        elements.app.classList.toggle(
            'is-work-mode-fold-list',
            applyFoldBrowseView && foldBrowseView === WORK_MODE_MOBILE_VIEW_LIST
        );
        elements.app.classList.toggle(
            'is-work-mode-fold-viewer',
            applyFoldBrowseView && foldBrowseView === WORK_MODE_MOBILE_VIEW_VIEWER
        );
    }

    const showMobileBrowserButton = applyMobileView && nextView === WORK_MODE_MOBILE_VIEW_CHAT;
    if (elements?.mobileBrowserBtn) {
        elements.mobileBrowserBtn.classList.toggle('is-hidden', !showMobileBrowserButton);
        elements.mobileBrowserBtn.disabled = !showMobileBrowserButton;
        const switchSlot = elements.mobileBrowserBtn.closest('.chat-work-mode-switch-slot');
        if (switchSlot) {
            switchSlot.classList.toggle('is-hidden', !showMobileBrowserButton);
        }
    }

    const showChatButton = applyMobileView && nextView !== WORK_MODE_MOBILE_VIEW_CHAT;
    const showBackButton = (
        applyMobileView && nextView === WORK_MODE_MOBILE_VIEW_VIEWER
    ) || (
        applyFoldBrowseView && foldBrowseView === WORK_MODE_MOBILE_VIEW_VIEWER
    );

    if (fileElements?.chatBtn) {
        fileElements.chatBtn.classList.toggle('is-hidden', !showChatButton);
        fileElements.chatBtn.disabled = !showChatButton;
        const switchSlot = fileElements.chatBtn.closest('.work-mode-preview-switch-slot');
        if (switchSlot) {
            switchSlot.classList.toggle('is-hidden', !showChatButton);
        }
    }
    if (fileElements?.backBtn) {
        fileElements.backBtn.classList.toggle('is-hidden', !showBackButton);
        fileElements.backBtn.disabled = !showBackButton;
    }
    syncWorkModeFileFullscreenButtonState();
    syncWorkModeHtmlPreviewOpenButton();
    syncWorkModeFileHorizontalScrollMetrics();
    schedulePersistWorkModeFileViewState();
}

function setWorkModeFileViewerFullscreen(isFullscreen) {
    const elements = getWorkModeFileElements();
    workModeFileViewerFullscreen = Boolean(isFullscreen);
    const fullscreenEnabled = Boolean(
        workModeFileViewerFullscreen
        && isWorkModeEnabled()
        && !isMobileLayout()
        && !isFoldLayout()
    );
    if (fullscreenEnabled) {
        stopWorkModeFileResize();
        stopWorkModeFileColumnResize();
    }

    if (elements?.preview) {
        elements.preview.classList.toggle('is-viewer-fullscreen', fullscreenEnabled);
    }
    if (elements?.divider) {
        elements.divider.classList.toggle('is-disabled', fullscreenEnabled);
    }
    if (Array.isArray(elements?.colResizers)) {
        const disableColumnResize = fullscreenEnabled || !isWorkModeEnabled() || isMobileLayout() || isFoldLayout();
        elements.colResizers.forEach(handle => {
            handle.disabled = disableColumnResize;
        });
    }
    syncWorkModeFileFullscreenButtonState();
    if (!fullscreenEnabled && isWorkModeEnabled()) {
        applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: false });
    }
    syncWorkModeFileHorizontalScrollMetrics();
    schedulePersistWorkModeFileViewState();
}

function setWorkModePreviewFullscreen(isFullscreen) {
    const elements = getWorkModeElements();
    workModePreviewFullscreen = Boolean(isFullscreen);
    const fullscreenEnabled = Boolean(
        workModePreviewFullscreen
        && isWorkModeEnabled()
        && isFoldLayout()
    );
    if (fullscreenEnabled) {
        stopWorkModeResize();
        stopWorkModeFileResize();
        stopWorkModeFileColumnResize();
    }
    if (elements?.app) {
        elements.app.classList.toggle(WORK_MODE_PREVIEW_FULLSCREEN_CLASS, fullscreenEnabled);
    }
    syncWorkModeFileFullscreenButtonState();
    schedulePersistWorkModeFileViewState();
}

function normalizeWorkModeFileSplitRatio(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return WORK_MODE_FILE_DEFAULT_SPLIT;
    return Math.min(0.72, Math.max(0.2, numeric));
}

function readWorkModeFileSplitPreference() {
    try {
        return normalizeWorkModeFileSplitRatio(localStorage.getItem(WORK_MODE_FILE_SPLIT_KEY));
    } catch (error) {
        return WORK_MODE_FILE_DEFAULT_SPLIT;
    }
}

function persistWorkModeFileSplitPreference(ratio) {
    try {
        localStorage.setItem(WORK_MODE_FILE_SPLIT_KEY, String(normalizeWorkModeFileSplitRatio(ratio)));
    } catch (error) {
        void error;
    }
}

function clampWorkModeFileListWidth(listWidthPx, totalWidthPx) {
    const total = Number(totalWidthPx);
    if (!Number.isFinite(total) || total <= 0) return WORK_MODE_FILE_MIN_LIST_WIDTH_PX;
    const min = Math.min(WORK_MODE_FILE_MIN_LIST_WIDTH_PX, Math.max(170, total - WORK_MODE_FILE_MIN_VIEWER_WIDTH_PX));
    const max = Math.max(min, total - WORK_MODE_FILE_MIN_VIEWER_WIDTH_PX);
    return Math.min(max, Math.max(min, Number(listWidthPx)));
}

function normalizeFilePanelVariant(value) {
    if (value === FILE_PANEL_VARIANT_OVERLAY) return FILE_PANEL_VARIANT_OVERLAY;
    return FILE_PANEL_VARIANT_WORK_MODE;
}

function getFilePanelVariantConfig(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    if (normalizedVariant === FILE_PANEL_VARIANT_OVERLAY) {
        return {
            getElements: getFileBrowserElements,
            getSurfaceElement: elements => elements?.overlay,
            getSplitRatio: () => fileBrowserSplitRatio,
            setSplitRatio: value => {
                fileBrowserSplitRatio = normalizeWorkModeFileSplitRatio(value);
            },
            persistSplit: persistFileBrowserSplitPreference,
            getColumnWidths: () => fileBrowserColumnWidths,
            setColumnWidths: next => {
                fileBrowserColumnWidths = next;
            },
            persistColumns: persistFileBrowserColumnsPreference,
            getHorizontalSyncLock: () => fileBrowserHorizontalSyncLock,
            setHorizontalSyncLock: isLocked => {
                fileBrowserHorizontalSyncLock = Boolean(isLocked);
            },
            canSyncHorizontal: () => !isMobileLayout() && isFileBrowserOverlayOpen()
        };
    }
    return {
        getElements: getWorkModeFileElements,
        getSurfaceElement: elements => elements?.preview,
        getSplitRatio: () => workModeFileSplitRatio,
        setSplitRatio: value => {
            workModeFileSplitRatio = normalizeWorkModeFileSplitRatio(value);
        },
        persistSplit: persistWorkModeFileSplitPreference,
        getColumnWidths: () => workModeFileColumnWidths,
        setColumnWidths: next => {
            workModeFileColumnWidths = next;
        },
        persistColumns: persistWorkModeFileColumnsPreference,
        getHorizontalSyncLock: () => workModeFileHorizontalSyncLock,
        setHorizontalSyncLock: isLocked => {
            workModeFileHorizontalSyncLock = Boolean(isLocked);
        },
        canSyncHorizontal: () => isWorkModeEnabled() && !isMobileLayout()
    };
}

function getFilePanelEditState(variant) {
    return normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
        ? fileBrowserEditState
        : workModeFileEditState;
}

function updateFilePanelActionButtonLabel(button, label) {
    if (!(button instanceof HTMLButtonElement)) return;
    const normalizedLabel = String(label || '').trim();
    button.setAttribute('aria-label', normalizedLabel);
    button.setAttribute('title', normalizedLabel);
}

function setFilePanelViewerMetaText(elements, text, { truncated = false } = {}) {
    if (!elements?.viewerMeta) return;
    elements.viewerMeta.textContent = String(text || '');
    if (truncated) {
        const note = document.createElement('span');
        note.className = 'file-browser-truncated-note';
        note.textContent = '미리보기 용량 제한으로 일부만 표시됩니다.';
        elements.viewerMeta.appendChild(note);
    }
}

function resetFilePanelEditState(variant, { root = null } = {}) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const state = getFilePanelEditState(normalizedVariant);
    const fallbackRoot = normalizedVariant === FILE_PANEL_VARIANT_OVERLAY ? fileBrowserRoot : workModeFileRoot;
    state.root = normalizeFileBrowserRoot(root || fallbackRoot);
    state.path = '';
    state.editable = false;
    state.editing = false;
    state.dirty = false;
    state.saving = false;
    state.modifiedNs = '';
    state.previewResult = null;
    state.editBuffer = '';
    syncFilePanelViewerActionState(normalizedVariant);
}

function hydrateFilePanelEditStateFromResult(variant, result, { root = null } = {}) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const state = getFilePanelEditState(normalizedVariant);
    state.root = normalizeFileBrowserRoot(root || result?.root || getFilePanelCurrentRoot(normalizedVariant));
    state.path = normalizeFileBrowserRelativePath(result?.path || '');
    state.editable = Boolean(result?.editable);
    state.editing = false;
    state.dirty = false;
    state.saving = false;
    state.modifiedNs = String(result?.modified_ns || '').trim();
    state.previewResult = result && typeof result === 'object' ? { ...result } : null;
    state.editBuffer = typeof result?.content === 'string' ? result.content : '';
    syncFilePanelViewerActionState(normalizedVariant);
}

function discardFilePanelEditChanges(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const state = getFilePanelEditState(normalizedVariant);
    state.editing = false;
    state.dirty = false;
    state.saving = false;
    state.editBuffer = typeof state.previewResult?.content === 'string' ? state.previewResult.content : '';
    syncFilePanelViewerActionState(normalizedVariant);
}

function confirmDiscardFilePanelEditChanges(variant, message = FILE_PANEL_EDIT_DISCARD_MESSAGE) {
    const state = getFilePanelEditState(variant);
    if (!state.editing || !state.dirty) return true;
    const confirmed = window.confirm(message);
    if (!confirmed) return false;
    discardFilePanelEditChanges(variant);
    return true;
}

function syncFilePanelViewerActionState(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const config = getFilePanelVariantConfig(normalizedVariant);
    const elements = config.getElements();
    if (!elements) return;

    const state = getFilePanelEditState(normalizedVariant);
    const hasPreview = Boolean(state.path);
    const isBusy = isFilePanelLoading(elements) || isFilePanelBulkActionInFlight(normalizedVariant) || state.saving;
    const canEdit = hasPreview && Boolean(state.editable);
    if (elements.viewerPanel) {
        elements.viewerPanel.classList.toggle('is-editing', Boolean(state.editing));
    }
    if (elements.editBtn) {
        elements.editBtn.classList.toggle('is-hidden', !hasPreview);
        elements.editBtn.classList.toggle('is-active', Boolean(state.editing));
        elements.editBtn.disabled = !canEdit || isBusy;
        elements.editBtn.setAttribute('aria-pressed', state.editing ? 'true' : 'false');
        updateFilePanelActionButtonLabel(
            elements.editBtn,
            state.editing ? '파일 수정 모드 종료' : '파일 수정 모드 열기'
        );
    }
    if (elements.saveBtn) {
        const showSave = hasPreview && state.editing;
        elements.saveBtn.classList.toggle('is-hidden', !showSave);
        elements.saveBtn.classList.toggle('is-ready', Boolean(state.dirty) && !state.saving);
        elements.saveBtn.classList.toggle('is-loading', Boolean(state.saving));
        elements.saveBtn.disabled = !showSave || !state.dirty || isBusy;
        elements.saveBtn.setAttribute('aria-busy', state.saving ? 'true' : 'false');
        updateFilePanelActionButtonLabel(
            elements.saveBtn,
            state.saving ? '파일 저장 중...' : '파일 저장'
        );
    }
}

function applyFilePanelSplitRatio(variant, ratio, { persist = false } = {}) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    const surface = config.getSurfaceElement(elements);
    if (!surface || !elements?.layout) return;
    const dividerWidth = Math.max(1, Math.round(elements.divider?.getBoundingClientRect().width || 10));
    const totalWidth = Math.max(0, elements.layout.clientWidth - dividerWidth);
    if (totalWidth <= 0) return;

    const nextRatio = normalizeWorkModeFileSplitRatio(ratio);
    const desiredWidth = totalWidth * nextRatio;
    const listWidth = clampWorkModeFileListWidth(desiredWidth, totalWidth);
    config.setSplitRatio(totalWidth > 0 ? (listWidth / totalWidth) : WORK_MODE_FILE_DEFAULT_SPLIT);
    surface.style.setProperty('--work-mode-file-list-width', `${Math.round(listWidth)}px`);
    syncFilePanelHorizontalScrollMetricsCore(variant);
    if (persist) {
        config.persistSplit(config.getSplitRatio());
    }
}

function updateFilePanelSplitFromPointer(variant, clientX, { persist = false } = {}) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    if (!elements?.layout) return;
    const layoutRect = elements.layout.getBoundingClientRect();
    const dividerWidth = Math.max(1, Math.round(elements.divider?.getBoundingClientRect().width || 10));
    const totalWidth = Math.max(0, layoutRect.width - dividerWidth);
    if (totalWidth <= 0) return;
    const rawWidth = Number(clientX) - layoutRect.left;
    const listWidth = clampWorkModeFileListWidth(rawWidth, totalWidth);
    const ratio = listWidth / totalWidth;
    applyFilePanelSplitRatio(variant, ratio, { persist: false });
    if (persist) {
        config.persistSplit(config.getSplitRatio());
    }
}

function syncFilePanelHorizontalScrollMetricsCore(variant) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    if (!elements?.gridScroll || !elements?.hScroll || !elements?.hScrollTrack || !elements?.table) return;
    if (!config.canSyncHorizontal()) return;

    const viewportWidth = Math.max(0, Math.round(elements.gridScroll.clientWidth));
    const contentWidth = Math.max(
        Math.round(elements.table.scrollWidth || 0),
        Math.round(elements.columns?.scrollWidth || 0),
        Math.round(elements.list?.scrollWidth || 0)
    );
    const effectiveWidth = Math.max(viewportWidth, contentWidth);
    elements.hScrollTrack.style.width = `${effectiveWidth}px`;

    const maxScroll = Math.max(0, contentWidth - viewportWidth);
    const gridScrollLeft = Math.max(0, Math.min(maxScroll, Math.round(elements.gridScroll.scrollLeft || 0)));
    const railScrollLeft = Math.max(0, Math.min(maxScroll, Math.round(elements.hScroll.scrollLeft || 0)));
    const nextScrollLeft = Math.max(gridScrollLeft, railScrollLeft);

    if (config.getHorizontalSyncLock()) return;
    config.setHorizontalSyncLock(true);
    try {
        if (Math.round(elements.gridScroll.scrollLeft || 0) !== nextScrollLeft) {
            elements.gridScroll.scrollLeft = nextScrollLeft;
        }
        if (Math.round(elements.hScroll.scrollLeft || 0) !== nextScrollLeft) {
            elements.hScroll.scrollLeft = nextScrollLeft;
        }
    } finally {
        config.setHorizontalSyncLock(false);
    }
}

function syncFilePanelHorizontalScrollFromGrid(variant) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    if (!elements?.gridScroll || !elements?.hScroll) return;
    if (config.getHorizontalSyncLock()) return;
    config.setHorizontalSyncLock(true);
    try {
        elements.hScroll.scrollLeft = elements.gridScroll.scrollLeft;
    } finally {
        config.setHorizontalSyncLock(false);
    }
}

function syncFilePanelHorizontalScrollFromRail(variant) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    if (!elements?.gridScroll || !elements?.hScroll) return;
    if (config.getHorizontalSyncLock()) return;
    config.setHorizontalSyncLock(true);
    try {
        elements.gridScroll.scrollLeft = elements.hScroll.scrollLeft;
    } finally {
        config.setHorizontalSyncLock(false);
    }
}

function applyFilePanelColumnWidthsCore(variant, { persist = false } = {}) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    const surface = config.getSurfaceElement(elements);
    if (!surface) return;
    const currentWidths = config.getColumnWidths();
    const nameWidth = normalizeWorkModeFileColumnWidth('name', currentWidths?.name);
    const sizeWidth = normalizeWorkModeFileColumnWidth('size', currentWidths?.size);
    const modifiedWidth = normalizeWorkModeFileColumnWidth('modified', currentWidths?.modified);
    const nextWidths = {
        name: nameWidth,
        size: sizeWidth,
        modified: modifiedWidth
    };
    config.setColumnWidths(nextWidths);
    surface.style.setProperty('--work-mode-file-col-name-width', `${nameWidth}px`);
    surface.style.setProperty('--work-mode-file-col-size-width', `${sizeWidth}px`);
    surface.style.setProperty('--work-mode-file-col-modified-width', `${modifiedWidth}px`);
    syncFilePanelHorizontalScrollMetricsCore(variant);
    if (persist) {
        config.persistColumns();
    }
}

function applyWorkModeFileSplitRatio(ratio = workModeFileSplitRatio, { persist = false } = {}) {
    applyFilePanelSplitRatio(FILE_PANEL_VARIANT_WORK_MODE, ratio, { persist });
}

function updateWorkModeFileSplitFromPointer(clientX, { persist = false } = {}) {
    updateFilePanelSplitFromPointer(FILE_PANEL_VARIANT_WORK_MODE, clientX, { persist });
}

function syncWorkModeFileHorizontalScrollMetrics() {
    syncFilePanelHorizontalScrollMetricsCore(FILE_PANEL_VARIANT_WORK_MODE);
}

function handleWorkModeFileGridScroll() {
    syncFilePanelHorizontalScrollFromGrid(FILE_PANEL_VARIANT_WORK_MODE);
    schedulePersistWorkModeFileViewState();
}

function handleWorkModeFileHScroll() {
    syncFilePanelHorizontalScrollFromRail(FILE_PANEL_VARIANT_WORK_MODE);
    schedulePersistWorkModeFileViewState();
}

function handleWorkModeFileViewerScroll() {
    schedulePersistWorkModeFileViewState();
}

function normalizeWorkModeFileColumnName(column) {
    const normalized = String(column || '').trim().toLowerCase();
    if (normalized === 'name' || normalized === 'size' || normalized === 'modified') {
        return normalized;
    }
    return '';
}

function normalizeWorkModeFileColumnWidth(column, width) {
    const key = normalizeWorkModeFileColumnName(column);
    if (!key) return null;
    const limits = WORK_MODE_FILE_COLUMN_LIMITS[key];
    const numeric = Number(width);
    if (!Number.isFinite(numeric)) return WORK_MODE_FILE_COLUMN_DEFAULTS[key];
    return Math.min(limits.max, Math.max(limits.min, Math.round(numeric)));
}

function hasLegacyDefaultFileColumnWidths(value) {
    if (!value || typeof value !== 'object') return false;
    return Number(value.name) === WORK_MODE_FILE_COLUMN_LEGACY_DEFAULTS.name
        && Number(value.size) === WORK_MODE_FILE_COLUMN_LEGACY_DEFAULTS.size
        && Number(value.modified) === WORK_MODE_FILE_COLUMN_LEGACY_DEFAULTS.modified;
}

function readWorkModeFileColumnsPreference() {
    const fallback = {
        name: WORK_MODE_FILE_COLUMN_DEFAULTS.name,
        size: WORK_MODE_FILE_COLUMN_DEFAULTS.size,
        modified: WORK_MODE_FILE_COLUMN_DEFAULTS.modified
    };
    try {
        const raw = localStorage.getItem(WORK_MODE_FILE_COLUMNS_KEY);
        if (!raw) return fallback;
        const parsed = JSON.parse(raw);
        if (hasLegacyDefaultFileColumnWidths(parsed)) {
            return fallback;
        }
        return {
            name: normalizeWorkModeFileColumnWidth('name', parsed?.name),
            size: normalizeWorkModeFileColumnWidth('size', parsed?.size),
            modified: normalizeWorkModeFileColumnWidth('modified', parsed?.modified)
        };
    } catch (error) {
        return fallback;
    }
}

function persistWorkModeFileColumnsPreference() {
    try {
        localStorage.setItem(WORK_MODE_FILE_COLUMNS_KEY, JSON.stringify(workModeFileColumnWidths));
    } catch (error) {
        void error;
    }
}

function applyWorkModeFileColumnWidths({ persist = false } = {}) {
    applyFilePanelColumnWidthsCore(FILE_PANEL_VARIANT_WORK_MODE, { persist });
}

function isWorkModeEnabled() {
    const app = document.querySelector('.app');
    return Boolean(app?.classList.contains(WORK_MODE_CLASS));
}

function normalizeWorkModeSplitRatio(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return WORK_MODE_DEFAULT_SPLIT;
    return Math.min(0.82, Math.max(0.3, numeric));
}

function updateWorkModeToggleButton(button, enabled, { disabled = false } = {}) {
    if (!button) return;
    const isEnabled = Boolean(enabled);
    const isDisabled = Boolean(disabled);
    button.classList.toggle('is-active', isEnabled);
    button.setAttribute('aria-pressed', String(isEnabled));
    button.disabled = isDisabled;
    const label = isEnabled ? 'Disable work mode' : 'Enable work mode';
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    syncHoverTooltipFromLabel(button, label);
}

function readWorkModePreference() {
    try {
        return localStorage.getItem(WORK_MODE_KEY) === '1';
    } catch (error) {
        return false;
    }
}

function persistWorkModePreference(enabled) {
    try {
        localStorage.setItem(WORK_MODE_KEY, enabled ? '1' : '0');
    } catch (error) {
        void error;
    }
}

function readWorkModeSplitPreference() {
    try {
        return normalizeWorkModeSplitRatio(localStorage.getItem(WORK_MODE_SPLIT_KEY));
    } catch (error) {
        return WORK_MODE_DEFAULT_SPLIT;
    }
}

function persistWorkModeSplitPreference(ratio) {
    try {
        localStorage.setItem(WORK_MODE_SPLIT_KEY, String(normalizeWorkModeSplitRatio(ratio)));
    } catch (error) {
        void error;
    }
}

function clampWorkModeChatWidth(chatWidthPx, contentWidthPx) {
    const total = Number(contentWidthPx);
    if (!Number.isFinite(total) || total <= 0) return WORK_MODE_MIN_CHAT_WIDTH_PX;
    const min = Math.min(WORK_MODE_MIN_CHAT_WIDTH_PX, Math.max(240, total - WORK_MODE_MIN_PREVIEW_WIDTH_PX));
    const max = Math.max(min, total - WORK_MODE_MIN_PREVIEW_WIDTH_PX);
    return Math.min(max, Math.max(min, Number(chatWidthPx)));
}

function applyWorkModeSplitRatio(ratio = workModeSplitRatio, { persist = false } = {}) {
    const elements = getWorkModeElements();
    if (!elements.app || !elements.layout) return;
    const dividerWidth = Math.max(1, Math.round(elements.divider?.getBoundingClientRect().width || 10));
    const totalWidth = Math.max(0, elements.layout.clientWidth - dividerWidth);
    if (totalWidth <= 0) return;

    const nextRatio = normalizeWorkModeSplitRatio(ratio);
    const desiredWidth = totalWidth * nextRatio;
    const chatWidth = clampWorkModeChatWidth(desiredWidth, totalWidth);
    workModeSplitRatio = totalWidth > 0 ? (chatWidth / totalWidth) : WORK_MODE_DEFAULT_SPLIT;
    elements.app.style.setProperty('--work-mode-chat-width', `${Math.round(chatWidth)}px`);
    if (persist) {
        persistWorkModeSplitPreference(workModeSplitRatio);
    }
}

function setWorkModeEnabled(enabled, { persist = true, notifyOnMobile = true } = {}) {
    const elements = getWorkModeElements();
    if (!elements.app) return false;
    void notifyOnMobile;
    const wantsEnabled = Boolean(enabled);
    const mobile = isMobileLayout();
    const wasEnabled = elements.app.classList.contains(WORK_MODE_CLASS);

    if (wantsEnabled) {
        if (elements.app.classList.contains(CHAT_FULLSCREEN_CLASS)) {
            setChatFullscreen(false);
        }
        if (isFileBrowserOverlayOpen()) {
            closeFileBrowserOverlay();
        }
    } else {
        if (workModeResizePointerId !== null) {
            stopWorkModeResize();
        }
        stopWorkModeFileResize();
        stopWorkModeFileColumnResize();
    }

    elements.app.classList.toggle(WORK_MODE_CLASS, wantsEnabled);
    if (!wantsEnabled && !isPhoneLayout() && isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    if (elements.preview) {
        elements.preview.setAttribute('aria-hidden', wantsEnabled ? 'false' : 'true');
    }
    if (elements.divider) {
        elements.divider.setAttribute('aria-hidden', wantsEnabled ? 'false' : 'true');
    }
    updateWorkModeToggleButton(elements.toggle, wantsEnabled, { disabled: false });

    if (wantsEnabled) {
        applyWorkModeSplitRatio(workModeSplitRatio, { persist: false });
        applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: false });
        applyWorkModeFileColumnWidths({ persist: false });
        setWorkModeFileViewerFullscreen(workModeFileViewerFullscreen);
        if (mobile && !wasEnabled) {
            workModeMobileView = WORK_MODE_MOBILE_VIEW_CHAT;
        }
        setWorkModeMobileView(workModeMobileView);
        setWorkModePreviewFullscreen(workModePreviewFullscreen);
        requestAnimationFrame(() => {
            syncWorkModeFileHorizontalScrollMetrics();
        });
        void ensureWorkModeFilePanelContent();
    } else {
        setWorkModeFileViewerFullscreen(false);
        setWorkModePreviewFullscreen(false);
        setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_CHAT);
    }

    if (persist) {
        persistWorkModePreference(wantsEnabled);
    }
    return wantsEnabled;
}

function initializeWorkMode(isMobile) {
    workModeSplitRatio = readWorkModeSplitPreference();
    workModeFileSplitRatio = readWorkModeFileSplitPreference();
    workModeFileColumnWidths = readWorkModeFileColumnsPreference();
    initializeWorkModeFileViewState(isMobile);
    setWorkModeFilePathLabel(workModeFileRoot, workModeFilePath);
    const preferred = readWorkModePreference();
    setWorkModeEnabled(preferred, { persist: false, notifyOnMobile: false });
    const initialMobileView = isMobile
        ? WORK_MODE_MOBILE_VIEW_CHAT
        : normalizeWorkModeMobileView(workModeMobileView) === WORK_MODE_MOBILE_VIEW_CHAT
            ? WORK_MODE_MOBILE_VIEW_LIST
            : normalizeWorkModeMobileView(workModeMobileView);
    setWorkModeMobileView(initialMobileView);
    applyWorkModeSplitRatio(workModeSplitRatio, { persist: false });
    applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: false });
    applyWorkModeFileColumnWidths({ persist: false });
    requestAnimationFrame(() => {
        syncWorkModeFileHorizontalScrollMetrics();
    });
}

function handleWorkModeMediaChange(isMobile) {
    const elements = getWorkModeElements();
    if (!isMobile && isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    if ((isMobile || isFoldLayout()) && isWorkModeEnabled()) {
        setWorkModeFileViewerFullscreen(false);
    }
    updateWorkModeToggleButton(elements.toggle, isWorkModeEnabled(), { disabled: false });
    if (readWorkModePreference() && !isWorkModeEnabled()) {
        setWorkModeEnabled(true, { persist: false, notifyOnMobile: false });
    }
    setWorkModeMobileView(workModeMobileView);
    applyWorkModeFileSplitRatio(workModeFileSplitRatio, { persist: false });
    applyWorkModeFileColumnWidths({ persist: false });
    setWorkModeFileViewerFullscreen(workModeFileViewerFullscreen);
    setWorkModePreviewFullscreen(workModePreviewFullscreen);
    applyWorkModeSplitRatio(workModeSplitRatio, { persist: false });
    requestAnimationFrame(() => {
        syncWorkModeFileHorizontalScrollMetrics();
    });
}

function updateWorkModeSplitFromPointer(clientX, { persist = false } = {}) {
    const elements = getWorkModeElements();
    if (!elements.layout) return;
    const layoutRect = elements.layout.getBoundingClientRect();
    const dividerWidth = Math.max(1, Math.round(elements.divider?.getBoundingClientRect().width || 10));
    const totalWidth = Math.max(0, layoutRect.width - dividerWidth);
    if (totalWidth <= 0) return;
    const rawWidth = Number(clientX) - layoutRect.left;
    const chatWidth = clampWorkModeChatWidth(rawWidth, totalWidth);
    const ratio = chatWidth / totalWidth;
    applyWorkModeSplitRatio(ratio, { persist: false });
    if (persist) {
        persistWorkModeSplitPreference(workModeSplitRatio);
    }
}

function syncWorkModeResizeBodyClass() {
    const active = workModeResizePointerId !== null
        || workModeFileResizePointerId !== null
        || Boolean(workModeFileColumnResizeState)
        || fileBrowserResizePointerId !== null
        || Boolean(fileBrowserColumnResizeState);
    document.body.classList.toggle('is-work-mode-resizing', active);
}

function stopWorkModeResize() {
    if (workModeResizePointerId === null) return;
    workModeResizePointerId = null;
    syncWorkModeResizeBodyClass();
    window.removeEventListener('pointermove', handleWorkModeResizePointerMove);
    window.removeEventListener('pointerup', handleWorkModeResizePointerUp);
    window.removeEventListener('pointercancel', handleWorkModeResizePointerUp);
}

function handleWorkModeResizePointerMove(event) {
    if (workModeResizePointerId === null || event.pointerId !== workModeResizePointerId) return;
    if (!isWorkModeEnabled()) return;
    event.preventDefault();
    updateWorkModeSplitFromPointer(event.clientX, { persist: false });
}

function handleWorkModeResizePointerUp(event) {
    if (workModeResizePointerId === null || event.pointerId !== workModeResizePointerId) return;
    event.preventDefault();
    updateWorkModeSplitFromPointer(event.clientX, { persist: true });
    stopWorkModeResize();
}

function startWorkModeResize(event) {
    if (!event || event.button !== 0) return;
    if (!isWorkModeEnabled() || isMobileLayout()) return;
    event.preventDefault();
    workModeResizePointerId = event.pointerId;
    syncWorkModeResizeBodyClass();
    window.addEventListener('pointermove', handleWorkModeResizePointerMove);
    window.addEventListener('pointerup', handleWorkModeResizePointerUp);
    window.addEventListener('pointercancel', handleWorkModeResizePointerUp);
}

function stopWorkModeFileResize() {
    if (workModeFileResizePointerId === null) return;
    workModeFileResizePointerId = null;
    syncWorkModeResizeBodyClass();
    window.removeEventListener('pointermove', handleWorkModeFileResizePointerMove);
    window.removeEventListener('pointerup', handleWorkModeFileResizePointerUp);
    window.removeEventListener('pointercancel', handleWorkModeFileResizePointerUp);
}

function handleWorkModeFileResizePointerMove(event) {
    if (workModeFileResizePointerId === null || event.pointerId !== workModeFileResizePointerId) return;
    if (!isWorkModeEnabled() || workModeFileViewerFullscreen) return;
    event.preventDefault();
    updateWorkModeFileSplitFromPointer(event.clientX, { persist: false });
}

function handleWorkModeFileResizePointerUp(event) {
    if (workModeFileResizePointerId === null || event.pointerId !== workModeFileResizePointerId) return;
    event.preventDefault();
    updateWorkModeFileSplitFromPointer(event.clientX, { persist: true });
    stopWorkModeFileResize();
}

function startWorkModeFileResize(event) {
    if (!event || event.button !== 0) return;
    if (!isWorkModeEnabled() || isMobileLayout() || isFoldLayout() || workModeFileViewerFullscreen) return;
    const elements = getWorkModeFileElements();
    if (elements?.divider?.classList.contains('is-disabled')) return;
    event.preventDefault();
    workModeFileResizePointerId = event.pointerId;
    syncWorkModeResizeBodyClass();
    window.addEventListener('pointermove', handleWorkModeFileResizePointerMove);
    window.addEventListener('pointerup', handleWorkModeFileResizePointerUp);
    window.addEventListener('pointercancel', handleWorkModeFileResizePointerUp);
}

function stopWorkModeFileColumnResize() {
    if (!workModeFileColumnResizeState) return;
    workModeFileColumnResizeState = null;
    syncWorkModeResizeBodyClass();
    window.removeEventListener('pointermove', handleWorkModeFileColumnResizePointerMove);
    window.removeEventListener('pointerup', handleWorkModeFileColumnResizePointerUp);
    window.removeEventListener('pointercancel', handleWorkModeFileColumnResizePointerUp);
}

function handleWorkModeFileColumnResizePointerMove(event) {
    const state = workModeFileColumnResizeState;
    if (!state || event.pointerId !== state.pointerId) return;
    event.preventDefault();
    const delta = Number(event.clientX) - state.startX;
    const width = state.startWidth + delta;
    const normalized = normalizeWorkModeFileColumnWidth(state.column, width);
    if (!normalized) return;
    workModeFileColumnWidths[state.column] = normalized;
    applyWorkModeFileColumnWidths({ persist: false });
}

function handleWorkModeFileColumnResizePointerUp(event) {
    const state = workModeFileColumnResizeState;
    if (!state || event.pointerId !== state.pointerId) return;
    event.preventDefault();
    applyWorkModeFileColumnWidths({ persist: true });
    stopWorkModeFileColumnResize();
}

function startWorkModeFileColumnResize(event, column) {
    const targetColumn = normalizeWorkModeFileColumnName(column);
    if (!targetColumn || !event || event.button !== 0) return;
    if (!isWorkModeEnabled() || isMobileLayout() || isFoldLayout() || workModeFileViewerFullscreen) return;
    event.preventDefault();
    workModeFileColumnResizeState = {
        pointerId: event.pointerId,
        column: targetColumn,
        startX: Number(event.clientX),
        startWidth: normalizeWorkModeFileColumnWidth(targetColumn, workModeFileColumnWidths[targetColumn])
    };
    syncWorkModeResizeBodyClass();
    window.addEventListener('pointermove', handleWorkModeFileColumnResizePointerMove);
    window.addEventListener('pointerup', handleWorkModeFileColumnResizePointerUp);
    window.addEventListener('pointercancel', handleWorkModeFileColumnResizePointerUp);
}

function syncSessionsLayout(isCompact) {
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    if (!sessionsPanel || !sessionsToggle) return;
    if (!isCompact) {
        setSessionsCollapsed(false, { persist: false });
        return;
    }
    if (isFoldLayout()) {
        setSessionsCollapsed(false, { persist: false });
        return;
    }
    let collapsed = true;
    try {
        const stored = localStorage.getItem(SESSION_COLLAPSE_KEY);
        if (stored !== null) {
            collapsed = stored === '1';
        }
    } catch (error) {
        void error;
    }
    setSessionsCollapsed(collapsed, { persist: false });
}

function isPhoneLayout() {
    return window.matchMedia(PHONE_MEDIA_QUERY).matches;
}

function isFoldLayout() {
    return window.matchMedia(FOLD_MEDIA_QUERY).matches;
}

function isCompactLayout() {
    return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

function isMobileLayout() {
    return isPhoneLayout();
}

function mediaQueryMatches(query) {
    if (!query || typeof window.matchMedia !== 'function') return false;
    try {
        return window.matchMedia(query).matches;
    } catch (error) {
        void error;
    }
    return false;
}

function isLikelyVirtualKeyboardEnvironment() {
    const userAgentData = navigator.userAgentData;
    if (userAgentData && typeof userAgentData.mobile === 'boolean' && userAgentData.mobile) {
        return true;
    }
    const userAgent = String(navigator.userAgent || '');
    if (/\b(Android|iPhone|iPad|iPod|Mobile)\b/i.test(userAgent)) {
        return true;
    }
    const hasFinePointer = mediaQueryMatches('(any-pointer: fine)');
    const hasCoarsePointer = mediaQueryMatches('(any-pointer: coarse)');
    if (hasCoarsePointer && !hasFinePointer) {
        return true;
    }
    const touchPoints = Number(navigator.maxTouchPoints || 0);
    return touchPoints > 0 && !hasFinePointer;
}

function isEditableElement(element) {
    if (!element || typeof element.tagName !== 'string') return false;
    const tag = element.tagName.toLowerCase();
    if (tag === 'textarea' || tag === 'select') return true;
    if (tag !== 'input') return false;
    const type = (element.getAttribute('type') || 'text').toLowerCase();
    return !['button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit'].includes(type);
}

function isMobileKeyboardOpen(isMobile = isCompactLayout()) {
    if (!isMobile) return false;
    const activeElement = document.activeElement;
    const hasEditableFocus = isEditableElement(activeElement);
    if (!hasEditableFocus) return false;
    const visualHeight = Number(window.visualViewport?.height);
    const layoutHeight = Number(window.innerHeight);
    if (Number.isFinite(visualHeight) && Number.isFinite(layoutHeight) && visualHeight > 0 && layoutHeight > 0) {
        const viewportDelta = layoutHeight - visualHeight;
        if (viewportDelta > MOBILE_KEYBOARD_VIEWPORT_DELTA) {
            return true;
        }
    }
    return hasEditableFocus && isLikelyVirtualKeyboardEnvironment();
}

function setMobileKeyboardOpen(open) {
    const app = document.querySelector('.app');
    const root = document.documentElement;
    const body = document.body;
    const isOpen = Boolean(open);
    if (app) {
        app.classList.toggle(MOBILE_KEYBOARD_OPEN_CLASS, isOpen);
    }
    if (root) {
        root.classList.toggle(MOBILE_KEYBOARD_OPEN_CLASS, isOpen);
    }
    if (body) {
        body.classList.toggle(MOBILE_KEYBOARD_OPEN_CLASS, isOpen);
    }
}

function syncMobileKeyboardState(isMobile = isCompactLayout()) {
    const isKeyboardOpen = isMobileKeyboardOpen(isMobile);
    setMobileKeyboardOpen(isKeyboardOpen);
    applyMobilePromptLift({ isMobile, keyboardOpen: isKeyboardOpen });
    if (isTerminalOverlayOpen()) {
        syncTerminalExtraKeysState();
        if (isKeyboardOpen) {
            scheduleTerminalViewportRefresh();
        }
    }
    return isKeyboardOpen;
}

function applyMobileViewportHeight() {
    const root = document.documentElement;
    if (!root) return;
    const visualHeight = Number(window.visualViewport?.height);
    const fallbackHeight = Number(window.innerHeight);
    const nextHeight = Number.isFinite(visualHeight) && visualHeight > 0
        ? visualHeight
        : fallbackHeight;
    if (!Number.isFinite(nextHeight) || nextHeight <= 0) return;
    const clamped = Math.max(320, Math.round(nextHeight));
    if (lastAppliedMobileViewportHeight === clamped) {
        return;
    }
    lastAppliedMobileViewportHeight = clamped;
    root.style.setProperty(MOBILE_VIEWPORT_HEIGHT_VAR, `${clamped}px`);
}

function applyMobilePromptLift({ isMobile = isCompactLayout(), keyboardOpen = false } = {}) {
    const root = document.documentElement;
    if (!root) return;

    let nextLift = 0;
    if (isMobile && keyboardOpen) {
        const form = document.getElementById('codex-chat-form');
        const runtimeStrip = document.querySelector('.chat-runtime-strip');
        const viewport = window.visualViewport;
        const visualBottom = Number(viewport?.height) + Number(viewport?.offsetTop);
        const fallbackBottom = Number(window.innerHeight);
        const viewportBottom = Number.isFinite(visualBottom) && visualBottom > 0
            ? visualBottom
            : fallbackBottom;
        if (Number.isFinite(viewportBottom) && viewportBottom > 0) {
            const formBottom = Number(form?.getBoundingClientRect?.().bottom);
            const runtimeStripBottom = Number(runtimeStrip?.getBoundingClientRect?.().bottom);
            const promptBottom = Math.max(
                Number.isFinite(formBottom) ? formBottom : 0,
                Number.isFinite(runtimeStripBottom) ? runtimeStripBottom : 0
            );
            if (promptBottom > 0) {
                nextLift = Math.max(0, Math.ceil(promptBottom + 8 - viewportBottom));
            }
        }
    }

    if (lastAppliedMobilePromptLift === nextLift) {
        return;
    }
    lastAppliedMobilePromptLift = nextLift;
    root.style.setProperty(MOBILE_PROMPT_LIFT_VAR, `${nextLift}px`);
}

function normalizeMobileDocumentScroll(isMobile = isCompactLayout()) {
    if (!isMobile) return;
    if (window.scrollX !== 0 || window.scrollY !== 0) {
        window.scrollTo(0, 0);
    }
    if (document.documentElement.scrollTop !== 0) {
        document.documentElement.scrollTop = 0;
    }
    if (document.body.scrollTop !== 0) {
        document.body.scrollTop = 0;
    }
}

function setupMobileViewportBehavior(mobileMedia, input) {
    const syncViewportState = ({ normalizeScroll = false } = {}) => {
        applyMobileViewportHeight();
        const isMobile = mobileMedia.matches;
        syncMobileKeyboardState(isMobile);
        if (normalizeScroll) {
            normalizeMobileDocumentScroll(isMobile);
        }
    };
    syncViewportState({ normalizeScroll: true });

    const handleViewportChange = createRafThrottledHandler(() => {
        syncViewportState();
    });

    const handleLayoutModeChange = event => {
        syncViewportState({ normalizeScroll: Boolean(event?.matches) });
    };

    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', handleLayoutModeChange);
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(handleLayoutModeChange);
    }

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', handleViewportChange, { passive: true });
        window.visualViewport.addEventListener('scroll', handleViewportChange, { passive: true });
    }
    window.addEventListener('resize', handleViewportChange);

    if (!input) return;
    input.addEventListener('focus', () => {
        if (!mobileMedia.matches) return;
        syncViewportState({ normalizeScroll: true });
        window.setTimeout(() => {
            syncViewportState({ normalizeScroll: true });
        }, 80);
    });
    input.addEventListener('blur', () => {
        if (!mobileMedia.matches) return;
        window.setTimeout(() => {
            syncViewportState({ normalizeScroll: true });
        }, 120);
    });
    input.addEventListener('input', handleViewportChange);
}

function setupMobileSettingsInputBehavior(mobileMedia, inputs) {
    const fields = Array.isArray(inputs) ? inputs.filter(Boolean) : [];
    if (!fields.length) return;
    const getFocusedField = () => fields.find(field => field === document.activeElement) || null;
    const hasFocusedField = () => Boolean(getFocusedField());

    const keepFieldVisible = (field, behavior = 'auto') => {
        if (!field) return;
        const controlsBody = document.getElementById('codex-controls-body');
        if (controlsBody && controlsBody.contains(field)) {
            const bodyRect = controlsBody.getBoundingClientRect();
            const fieldRect = field.getBoundingClientRect();
            const topMargin = 12;
            const bottomMargin = 28;
            if (fieldRect.top < bodyRect.top + topMargin) {
                controlsBody.scrollBy({
                    top: fieldRect.top - (bodyRect.top + topMargin),
                    behavior
                });
            } else if (fieldRect.bottom > bodyRect.bottom - bottomMargin) {
                controlsBody.scrollBy({
                    top: fieldRect.bottom - (bodyRect.bottom - bottomMargin),
                    behavior
                });
            }
            return;
        }
        field.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior });
    };

    const keepFocusedFieldVisible = (behavior = 'auto') => {
        if (!mobileMedia.matches) return;
        const focusedField = getFocusedField();
        if (!focusedField) return;
        applyMobileViewportHeight();
        keepFieldVisible(focusedField, behavior);
    };

    let focusVisibilityScheduled = false;
    let focusVisibilityTimeoutId = null;
    const scheduleFocusedFieldVisibility = () => {
        if (!mobileMedia.matches) return;
        if (focusVisibilityTimeoutId) {
            window.clearTimeout(focusVisibilityTimeoutId);
        }
        focusVisibilityTimeoutId = window.setTimeout(() => {
            focusVisibilityTimeoutId = null;
            keepFocusedFieldVisible('auto');
        }, 140);
        if (focusVisibilityScheduled) return;
        focusVisibilityScheduled = true;
        runAfterAnimationFrame(() => {
            focusVisibilityScheduled = false;
            keepFocusedFieldVisible('auto');
        });
    };

    const applyMobileFocusState = focused => {
        const chat = document.querySelector('.chat');
        if (!chat) return;
        chat.classList.toggle(MOBILE_SETTINGS_FOCUS_CLASS, Boolean(focused));
    };

    const clearFocusStateIfNeeded = () => {
        if (!mobileMedia.matches || hasFocusedField()) return;
        applyMobileFocusState(false);
        syncMobileKeyboardState(true);
    };

    const handleLayoutModeChange = event => {
        if (event.matches) return;
        applyMobileFocusState(false);
        setMobileKeyboardOpen(false);
        applyMobilePromptLift({ isMobile: false, keyboardOpen: false });
    };

    const handleMobileViewportChange = createRafThrottledHandler(() => {
        if (!mobileMedia.matches) {
            setMobileKeyboardOpen(false);
            applyMobilePromptLift({ isMobile: false, keyboardOpen: false });
            return;
        }
        syncMobileKeyboardState(true);
        scheduleFocusedFieldVisibility();
    });

    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', handleLayoutModeChange);
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(handleLayoutModeChange);
    }
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', handleMobileViewportChange, { passive: true });
        window.visualViewport.addEventListener('scroll', handleMobileViewportChange, { passive: true });
    }
    window.addEventListener('resize', handleMobileViewportChange);

    fields.forEach(field => {
        field.addEventListener('focus', () => {
            if (!mobileMedia.matches) return;
            applyMobileFocusState(true);
            syncMobileKeyboardState(true);
            keepFieldVisible(field, 'auto');
            scheduleFocusedFieldVisibility();
        });

        field.addEventListener('blur', () => {
            if (!mobileMedia.matches) return;
            window.setTimeout(() => {
                applyMobileViewportHeight();
                clearFocusStateIfNeeded();
                keepFocusedFieldVisible('auto');
            }, 160);
        });
    });
}

function setControlsCollapsed(collapsed, { persist = true } = {}) {
    const controls = document.getElementById('codex-controls');
    const toggle = document.getElementById('codex-controls-toggle');
    if (!controls || !toggle) return;
    controls.classList.toggle('is-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    if (persist) {
        try {
            localStorage.setItem(CONTROLS_COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function syncControlsLayout() {
    setControlsCollapsed(true, { persist: false });
}

function initializeTheme(themeToggle, themeMedia) {
    const storedTheme = getStoredTheme();
    if (storedTheme) {
        hasManualTheme = true;
        applyTheme(storedTheme, { persist: false });
    } else {
        applyTheme(themeMedia?.matches ? 'dark' : 'light', { persist: false });
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', () => {
            const nextTheme = themeToggle.checked ? 'dark' : 'light';
            hasManualTheme = true;
            applyTheme(nextTheme);
        });
    }

    if (themeMedia) {
        const handler = event => {
            if (hasManualTheme) return;
            applyTheme(event.matches ? 'dark' : 'light', { persist: false });
        };
        if (typeof themeMedia.addEventListener === 'function') {
            themeMedia.addEventListener('change', handler);
        } else if (typeof themeMedia.addListener === 'function') {
            themeMedia.addListener(handler);
        }
    }
}

function applyTheme(theme, { persist = true } = {}) {
    const root = document.documentElement;
    if (!root) return;
    const normalized = theme === 'dark' ? 'dark' : 'light';
    root.dataset.theme = normalized;
    const toggle = document.getElementById('codex-theme-toggle');
    if (toggle) {
        toggle.checked = normalized === 'dark';
        updateThemeSwitchTooltip(toggle);
    }
    if (persist) {
        try {
            localStorage.setItem(THEME_KEY, normalized);
        } catch (error) {
            void error;
        }
    }
    syncTerminalTheme();
    scheduleTerminalFit();
    requestAnimationFrame(() => {
        void hydrateMermaidDiagrams(document.body);
    });
}

function getStoredTheme() {
    try {
        const stored = localStorage.getItem(THEME_KEY);
        if (stored === 'dark' || stored === 'light') return stored;
        return null;
    } catch (error) {
        return null;
    }
}

function getPersistedStreams() {
    try {
        const raw = localStorage.getItem(ACTIVE_STREAM_KEY);
        if (!raw) return [];
        const data = JSON.parse(raw);
        if (Array.isArray(data)) {
            return data.filter(item => item?.id && item?.sessionId);
        }
        if (data?.id && data?.sessionId) {
            return [data];
        }
        return [];
    } catch (error) {
        return [];
    }
}

function persistActiveStream(stream) {
    if (!stream?.id || !stream?.sessionId) return;
    const startedAt = normalizeStartedAt(stream.startedAt) || Date.now();
    const messageId = typeof stream?.messageId === 'string' ? stream.messageId.trim() : '';
    try {
        const existing = getPersistedStreams().filter(item => item.id !== stream.id);
        existing.push({
            id: stream.id,
            sessionId: stream.sessionId,
            startedAt,
            messageId
        });
        localStorage.setItem(ACTIVE_STREAM_KEY, JSON.stringify(existing));
    } catch (error) {
        void error;
    }
}

function clearPersistedStream(streamId = null) {
    try {
        if (!streamId) {
            localStorage.removeItem(ACTIVE_STREAM_KEY);
            return;
        }
        const existing = getPersistedStreams().filter(item => item.id !== streamId);
        if (existing.length === 0) {
            localStorage.removeItem(ACTIVE_STREAM_KEY);
        } else {
            localStorage.setItem(ACTIVE_STREAM_KEY, JSON.stringify(existing));
        }
    } catch (error) {
        void error;
    }
}

function setsEqual(a, b) {
    if (a === b) return true;
    if (!a || !b) return false;
    if (a.size !== b.size) return false;
    for (const value of a) {
        if (!b.has(value)) return false;
    }
    return true;
}

function getSessionTitleById(sessionId) {
    if (!sessionId) return 'Unknown session';
    const session = state.sessions.find(item => item.id === sessionId);
    if (session) {
        return session.title || 'New session';
    }
    return `Session ${sessionId.slice(0, 6)}`;
}

function formatStreamTimestamp(value) {
    if (!value) return '';
    const ms = value < 1000000000000 ? value * 1000 : value;
    return formatTimestamp(ms);
}

function getStreamMonitorElements() {
    const container = document.getElementById('codex-stream-monitor');
    if (!container) return null;
    return {
        container,
        list: document.getElementById('codex-stream-monitor-list'),
        empty: document.getElementById('codex-stream-monitor-empty'),
        output: document.getElementById('codex-stream-monitor-output'),
        outputTitle: document.getElementById('codex-stream-monitor-title'),
        outputStatus: document.getElementById('codex-stream-monitor-status'),
        outputContent: document.getElementById('codex-stream-monitor-content')
    };
}

function setStreamMonitorCollapsed(collapsed) {
    const monitor = document.getElementById('codex-stream-monitor');
    if (!monitor) return;
    monitor.classList.toggle('is-collapsed', Boolean(collapsed));
    const toggle = document.getElementById('codex-stream-monitor-toggle');
    if (toggle) {
        toggle.setAttribute('aria-expanded', String(!collapsed));
    }
}

function renderStreamMonitorOutput() {
    const elements = getStreamMonitorElements();
    if (!elements) return;
    if (!streamMonitorState) {
        if (elements.output) {
            elements.output.classList.add('is-hidden');
        }
        if (elements.outputContent) {
            elements.outputContent.textContent = '';
        }
        return;
    }
    if (elements.output) {
        elements.output.classList.remove('is-hidden');
    }
    if (elements.outputTitle) {
        const title = getSessionTitleById(streamMonitorState.sessionId);
        elements.outputTitle.textContent = `Monitoring: ${title}`;
    }
    if (elements.outputStatus) {
        elements.outputStatus.textContent = buildStreamMonitorStatus(streamMonitorState);
    }
    if (elements.outputContent) {
        const combined = streamMonitorState.output + (streamMonitorState.error ? `\n${streamMonitorState.error}` : '');
        elements.outputContent.textContent = combined || 'Waiting for output...';
        if (!streamMonitorState.done) {
            elements.outputContent.scrollTop = elements.outputContent.scrollHeight;
        }
    }
}

function renderStreamMonitorList(streams) {
    const elements = getStreamMonitorElements();
    if (!elements) return;
    const list = elements.list;
    if (!list) return;
    list.innerHTML = '';
    const hasStreams = Array.isArray(streams) && streams.length > 0;
    if (elements.empty) {
        elements.empty.classList.toggle('is-hidden', hasStreams);
    }
    list.classList.toggle('is-hidden', !hasStreams);
    if (!hasStreams) {
        return;
    }
    streams.forEach(stream => {
        const item = document.createElement('li');
        item.className = 'stream-monitor-item';
        const isWatching = streamMonitorState?.id === stream.id;
        if (isWatching) {
            item.classList.add('is-watching');
        }

        const info = document.createElement('div');
        info.className = 'stream-monitor-info';

        const title = document.createElement('div');
        title.className = 'stream-monitor-session';
        title.textContent = getSessionTitleById(stream.session_id || stream.sessionId);

        const meta = document.createElement('div');
        meta.className = 'stream-monitor-meta';
        meta.textContent = buildStreamListMeta(stream);

        info.appendChild(title);
        info.appendChild(meta);

        const watchBtn = document.createElement('button');
        watchBtn.type = 'button';
        watchBtn.className = 'stream-monitor-watch';
        watchBtn.textContent = isWatching ? 'Watching' : 'Monitor';
        watchBtn.disabled = isWatching;
        watchBtn.addEventListener('click', () => {
            startStreamMonitor(stream);
        });

        item.appendChild(info);
        item.appendChild(watchBtn);
        list.appendChild(item);
    });
}

function updateRemoteStreamSessions(streams) {
    const nextSet = new Set(
        (Array.isArray(streams) ? streams : [])
            .map(stream => stream?.session_id || stream?.sessionId)
            .filter(Boolean)
    );
    const changed = !setsEqual(state.remoteStreamSessions, nextSet);
    state.remoteStreamSessions = nextSet;
    state.remoteStreams = Array.isArray(streams) ? streams : [];
    if (changed) {
        scheduleSessionsRender();
        syncActiveSessionControls();
        syncRemoteActiveSessionStatus();
    }
    flushReadyQueuedPrompts();
}

function syncRemoteActiveSessionStatus() {
    const sessionId = state.activeSessionId;
    if (!sessionId) return;
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    const hasRemote = state.remoteStreamSessions?.has(sessionId);
    const hasLocal = Boolean(sessionState.sending || sessionState.pendingSend || getSessionStream(sessionId));
    if (hasRemote && !hasLocal) {
        const remoteState = getRemoteStreamState(sessionId);
        const remoteRunning = typeof remoteState?.process_running === 'boolean'
            ? remoteState.process_running
            : null;
        const remoteStartedAt = getRemoteStreamStartedAt(sessionId);
        let nextStatus = 'Receiving response (remote)...';
        if (remoteRunning === true) {
            nextStatus = 'Receiving response (remote, CLI running)...';
        } else if (remoteRunning === false) {
            nextStatus = 'Receiving response (remote, CLI finalizing)...';
        }
        if (sessionState.status !== nextStatus || sessionState.responseStartedAt !== remoteStartedAt) {
            setSessionStatus(sessionId, nextStatus);
        }
        return;
    }
    if (!hasRemote && typeof sessionState.status === 'string' && sessionState.status.startsWith('Receiving response (remote')) {
        setSessionStatus(sessionId, 'Idle');
    }
}

async function maybeAttachRemoteStreamToActiveSession(streams = state.remoteStreams) {
    const sessionId = state.activeSessionId;
    if (!sessionId) return false;
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState || getSessionStream(sessionId) || sessionState.pendingSend) {
        return false;
    }
    const remoteStream = (Array.isArray(streams) ? streams : []).find(
        item => (item?.session_id || item?.sessionId) === sessionId && item?.id
    );
    const remoteStreamId = remoteStream?.id;
    if (!remoteStreamId) return false;
    if (state.remoteAttachInFlightSessions.has(sessionId)) {
        return false;
    }

    state.remoteAttachInFlightSessions.add(sessionId);
    try {
        return await connectToExistingStream(
            sessionId,
            remoteStreamId,
            remoteStream?.started_at ?? remoteStream?.created_at
        );
    } finally {
        state.remoteAttachInFlightSessions.delete(sessionId);
    }
}

async function fetchRemoteStreams(force = false) {
    const now = Date.now();
    if (!force && remoteStreamStatusCache.fetchedAt && now - remoteStreamStatusCache.fetchedAt < REMOTE_STREAM_POLL_MS - 250) {
        return remoteStreamStatusCache;
    }
    if (remoteStreamStatusInFlight) {
        return remoteStreamStatusCache;
    }
    remoteStreamStatusInFlight = true;
    try {
        const result = await fetchJson('/api/codex/streams');
        const streams = Array.isArray(result?.streams) ? result.streams : [];
        remoteStreamStatusCache = {
            streams,
            fetchedAt: Date.now()
        };
        return remoteStreamStatusCache;
    } catch (error) {
        return remoteStreamStatusCache;
    } finally {
        remoteStreamStatusInFlight = false;
    }
}

async function refreshRemoteStreams({ force = false } = {}) {
    const result = await fetchRemoteStreams(force);
    const streams = Array.isArray(result?.streams) ? result.streams : [];
    renderStreamMonitorList(streams);
    updateRemoteStreamSessions(streams);
    syncRemoteActiveSessionStatus();
    void maybeAttachRemoteStreamToActiveSession(streams);
    if (!streamMonitorState && streams.length > 0) {
        const activeMatch = state.activeSessionId
            ? streams.find(item => (item?.session_id || item?.sessionId) === state.activeSessionId)
            : null;
        const candidate = activeMatch || (streams.length === 1 ? streams[0] : null);
        if (candidate) {
            startStreamMonitor(candidate);
        }
    }
}

function startRemoteStreamPolling() {
    if (remoteStreamPollTimer) return;
    remoteStreamPollTimer = window.setInterval(() => {
        void refreshRemoteStreams();
    }, REMOTE_STREAM_POLL_MS);
    void refreshRemoteStreams({ force: true });
}

function stopStreamMonitor(clearOutput = true) {
    if (!streamMonitorState) return;
    if (streamMonitorState.timer) {
        clearTimeout(streamMonitorState.timer);
        streamMonitorState.timer = null;
    }
    streamMonitorState.polling = false;
    if (clearOutput) {
        streamMonitorState = null;
    }
    renderStreamMonitorOutput();
    renderStreamMonitorList(state.remoteStreams);
}

function startStreamMonitor(stream) {
    if (!stream?.id) return;
    stopStreamMonitor(false);
    streamMonitorState = {
        id: stream.id,
        sessionId: stream.session_id || stream.sessionId,
        outputOffset: 0,
        errorOffset: 0,
        eventOffset: 0,
        output: '',
        error: '',
        done: false,
        processRunning: typeof stream?.process_running === 'boolean' ? stream.process_running : null,
        processPid: Number.isFinite(stream?.process_pid) ? stream.process_pid : null,
        runtimeMs: Number.isFinite(stream?.runtime_ms) ? stream.runtime_ms : null,
        idleMs: Number.isFinite(stream?.idle_ms) ? stream.idle_ms : null,
        timer: null,
        polling: false
    };
    renderStreamMonitorOutput();
    renderStreamMonitorList(state.remoteStreams);
    scheduleStreamMonitorPoll(0);
}

function scheduleStreamMonitorPoll(delay) {
    if (!streamMonitorState) return;
    if (streamMonitorState.timer) {
        clearTimeout(streamMonitorState.timer);
    }
    streamMonitorState.timer = setTimeout(() => {
        void pollStreamMonitor();
    }, delay);
}

async function pollStreamMonitor() {
    if (!streamMonitorState || streamMonitorState.polling) return;
    const current = streamMonitorState;
    current.polling = true;
    try {
        const result = await fetchJson(
            `/api/codex/streams/${current.id}?offset=${current.outputOffset}&error_offset=${current.errorOffset}&event_offset=${current.eventOffset || 0}`
        );
        if (!streamMonitorState || streamMonitorState.id !== current.id) return;
        if (typeof result?.process_running === 'boolean') {
            current.processRunning = result.process_running;
        }
        current.processPid = Number.isFinite(result?.process_pid) ? result.process_pid : null;
        if (Number.isFinite(result?.runtime_ms)) {
            current.runtimeMs = result.runtime_ms;
        }
        if (Number.isFinite(result?.idle_ms)) {
            current.idleMs = result.idle_ms;
        }
        if (result?.token_usage && typeof result.token_usage === 'object') {
            current.tokenUsage = result.token_usage;
            setMessageTokenUsage(
                current.entry?.footer,
                { role: 'assistant', token_usage: current.tokenUsage, content: current.output || '' }
            );
        }
        if (result?.output) {
            current.output += result.output;
            current.outputOffset = Number.isFinite(result.output_length)
                ? result.output_length
                : current.output.length;
        }
        if (result?.error) {
            current.error += result.error;
            current.errorOffset = Number.isFinite(result.error_length)
                ? result.error_length
                : current.error.length;
        }
        if (Number.isFinite(result?.event_length)) {
            current.eventOffset = result.event_length;
        }
        renderStreamMonitorOutput();
        if (result?.done) {
            current.done = true;
            renderStreamMonitorOutput();
            return;
        }
        scheduleStreamMonitorPoll(STREAM_POLL_BASE_MS);
    } catch (error) {
        if (isStreamNotFoundError(error)) {
            if (streamMonitorState) {
                streamMonitorState.done = true;
                streamMonitorState.processRunning = false;
            }
            renderStreamMonitorOutput();
            return;
        }
        scheduleStreamMonitorPoll(REMOTE_STREAM_POLL_MS);
    } finally {
        if (streamMonitorState) {
            streamMonitorState.polling = false;
        }
    }
}

async function loadSessions({ preserveActive = true, selectSessionId = null, reloadActive = true } = {}) {
    if (state.loading) {
        const isStaleLock = sessionLoadLockStartedAt > 0
            && Date.now() - sessionLoadLockStartedAt >= REFRESH_BUTTON_STALE_MS;
        if (!isStaleLock) {
            return;
        }
        state.loading = false;
        sessionLoadLockStartedAt = 0;
        console.warn('[codex-ui] recovered stale session loading lock before reloading sessions');
    }
    state.loading = true;
    sessionLoadLockStartedAt = Date.now();
    setStatus('Loading sessions...');
    try {
        const result = await fetchJson('/api/codex/sessions', {
            timeoutMs: SESSION_LIST_REQUEST_TIMEOUT_MS
        });
        state.sessions = Array.isArray(result?.sessions) ? result.sessions : [];
        state.sessionStorage = result?.session_storage || null;
        updateSessionStorageSummary(state.sessionStorage);
        renderSessions();

        let activeId = selectSessionId || (preserveActive ? state.activeSessionId : null);
        if (!activeId && state.sessions.length > 0) {
            activeId = state.sessions[0].id;
        }
        state.activeSessionId = activeId || null;
        if (state.activeSessionId) {
            ensureSessionState(state.activeSessionId);
        }

        if (activeId) {
            if (reloadActive) {
                await loadSession(activeId);
            } else {
                const summary = state.sessions.find(session => session.id === activeId) || null;
                updateHeader(summary);
            }
        } else {
            renderMessages([]);
            updateHeader(null);
        }
        updateChatSessionNavigationButtons();
        syncActiveSessionControls();
        syncActiveSessionStatus();
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to load sessions.'), true);
    } finally {
        state.loading = false;
        sessionLoadLockStartedAt = 0;
    }
}

async function loadSettings({ silent = true } = {}) {
    const refreshBtn = document.getElementById('codex-controls-refresh');
    if (refreshBtn) refreshBtn.classList.add('is-loading');
    try {
        const result = await fetchJson('/api/codex/settings');
        const modelCatalog = normalizeModelCatalog(result?.model_catalog);
        const catalogModelOptions = collectCatalogModelOptions(modelCatalog);
        const catalogReasoningOptions = collectCatalogReasoningOptions(modelCatalog);
        const modelOptions = catalogModelOptions.length > 0
            ? catalogModelOptions
            : normalizeOptionList(result?.model_options);
        const reasoningOptions = normalizeOptionList(result?.reasoning_options);
        state.settings = {
            model: result?.settings?.model || null,
            modelCatalog,
            modelOptions,
            planModeModel: result?.settings?.plan_mode_model || null,
            planModeReasoningEffort: result?.settings?.plan_mode_reasoning_effort || null,
            planModeState: normalizePlanModeState(state.settings?.planModeState),
            reasoningEffort: result?.settings?.reasoning_effort || null,
            reasoningOptions: reasoningOptions.length > 0 ? reasoningOptions : catalogReasoningOptions,
            usage: result?.usage || null,
            usageHistory: state.settings?.usageHistory || null,
            loaded: true
        };
        if (result?.session_storage) {
            state.sessionStorage = result.session_storage;
            updateSessionStorageSummary(state.sessionStorage);
        }
        updateUsageSummary(state.settings.usage);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updatePlanModeModelControls(state.settings.planModeModel, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        updatePlanModeReasoningControls(state.settings.planModeReasoningEffort, state.settings.reasoningOptions);
        setSettingsStatus(state.settings.model, state.settings.reasoningEffort);
    } catch (error) {
        updateUsageSummary(null);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updatePlanModeModelControls(state.settings.planModeModel, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        updatePlanModeReasoningControls(state.settings.planModeReasoningEffort, state.settings.reasoningOptions);
        setSettingsStatus(null, null, normalizeError(error, 'Failed to load settings.'));
        if (!silent) {
            setStatus(normalizeError(error, 'Failed to load settings.'), true);
        }
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('is-loading');
    }
}

async function refreshUsageSummary({ silent = true, showSuccessToast = false } = {}) {
    try {
        const result = await fetchJson('/api/codex/usage', { cache: 'no-store' });
        const usage = result?.usage ?? null;
        const usageHistory = result?.usage_history ?? null;
        state.settings.usage = usage;
        state.settings.usageHistory = usageHistory;
        if (result?.session_storage) {
            state.sessionStorage = result.session_storage;
            updateSessionStorageSummary(state.sessionStorage);
        }
        updateUsageSummary(usage);
        if (showSuccessToast) {
            showToast('사용량을 갱신했습니다.', { tone: 'default', durationMs: 3000 });
        }
    } catch (error) {
        const message = normalizeError(error, '사용량 갱신에 실패했습니다.');
        setStatus(message, true);
    }
}

function updateUsageSummary(usage) {
    const element = document.getElementById('codex-usage-summary');
    if (!element) return;
    const historyButton = document.getElementById('codex-usage-history-open');
    if (historyButton) {
        const hasHistory = Array.isArray(state.settings?.usageHistory?.items)
            && state.settings.usageHistory.items.length > 1;
        historyButton.classList.toggle('is-ready', hasHistory);
    }
    const accountName = typeof usage?.account_name === 'string' ? usage.account_name.trim() : '';
    const tokenUsage = usage?.token_usage || null;
    const hasTokenUsage = Boolean(tokenUsage && (tokenUsage.today || tokenUsage.all_time));
    element.innerHTML = '';
    if (accountName) {
        element.appendChild(buildUsageAccount(accountName));
    }
    const hasUsage = Boolean(usage && (usage.five_hour || usage.weekly));
    if (hasTokenUsage) {
        const tokenEntries = [
            buildTokenUsageEntry(tokenUsage?.today, 'Today'),
            buildTokenUsageEntry(tokenUsage?.all_time, 'All')
        ].filter(Boolean);
        tokenEntries.forEach(entry => {
            element.appendChild(entry);
        });
    }
    if (!hasUsage && !hasTokenUsage) {
        const fallbackText = state.settings.loaded ? 'Usage unavailable' : 'Refresh to load';
        if (!accountName) {
            element.textContent = fallbackText;
            return;
        }
        const fallback = document.createElement('div');
        fallback.className = 'usage-empty';
        fallback.textContent = fallbackText;
        element.appendChild(fallback);
        return;
    }
    const entries = [
        buildUsageEntry(usage?.five_hour, '5h'),
        buildUsageEntry(usage?.weekly, 'Weekly')
    ].filter(Boolean);
    entries.forEach(entry => {
        element.appendChild(entry);
    });
}

function updateModelControls(model, options) {
    const select = document.getElementById('codex-model-select');
    const input = document.getElementById('codex-model-input');
    const field = select ? select.closest('.model-field') : null;
    const normalizedOptions = normalizeOptionList(options);
    const hasOptions = normalizedOptions.length > 0;
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select model';
            select.appendChild(placeholder);
            normalizedOptions.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (model) {
                select.value = normalizedOptions.includes(model) ? model : '';
            } else {
                select.value = '';
            }
        } else {
            select.classList.add('is-hidden');
        }
    }
    if (input) {
        input.value = model || '';
        input.placeholder = model ? model : 'Default model';
        input.disabled = hasOptions;
        input.classList.toggle('is-hidden', hasOptions);
    }
    if (field) {
        field.classList.toggle('is-select-only', hasOptions);
    }
    setSettingsStatus(model, state.settings.reasoningEffort);
}

function updatePlanModeModelControls(planModeModel, options) {
    const select = document.getElementById('codex-plan-mode-model-select');
    const input = document.getElementById('codex-plan-mode-model-input');
    const field = select ? select.closest('.model-field') : null;
    const normalizedOptions = normalizeOptionList(options);
    const hasOptions = normalizedOptions.length > 0;
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Use default';
            select.appendChild(placeholder);
            normalizedOptions.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (planModeModel) {
                select.value = normalizedOptions.includes(planModeModel) ? planModeModel : '';
            } else {
                select.value = '';
            }
        } else {
            select.classList.add('is-hidden');
        }
    }
    if (input) {
        input.value = planModeModel || '';
        input.placeholder = planModeModel ? planModeModel : 'Use default model';
        input.disabled = hasOptions;
        input.classList.toggle('is-hidden', hasOptions);
    }
    if (field) {
        field.classList.toggle('is-select-only', hasOptions);
    }
    setSettingsStatus(state.settings.model, state.settings.reasoningEffort);
}

function updateReasoningControls(reasoning, options, model = state.settings.model) {
    const select = document.getElementById('codex-reasoning-select');
    const input = document.getElementById('codex-reasoning-input');
    const field = select ? select.closest('.model-field') : null;
    const profile = getReasoningProfile(model, reasoning, options);
    const hasOptions = profile.reasoningOptions.length > 0;
    const placeholderText = buildReasoningPlaceholder(profile.defaultReasoning, 'Use model default');
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = placeholderText;
            select.appendChild(placeholder);
            profile.reasoningOptions.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (profile.explicitReasoning) {
                select.value = profile.reasoningOptions.includes(profile.explicitReasoning)
                    ? profile.explicitReasoning
                    : '';
            } else {
                select.value = '';
            }
        } else {
            select.classList.add('is-hidden');
        }
    }
    if (input) {
        input.value = reasoning || '';
        input.placeholder = reasoning ? reasoning : placeholderText;
        input.disabled = hasOptions;
        input.classList.toggle('is-hidden', hasOptions);
    }
    if (field) {
        field.classList.toggle('is-select-only', hasOptions);
    }
}

function updatePlanModeReasoningControls(
    reasoning,
    options,
    model = state.settings.planModeModel || state.settings.model
) {
    const select = document.getElementById('codex-plan-mode-reasoning-select');
    const input = document.getElementById('codex-plan-mode-reasoning-input');
    const field = select ? select.closest('.model-field') : null;
    const profile = getReasoningProfile(model, reasoning, options);
    const hasOptions = profile.reasoningOptions.length > 0;
    const placeholderText = buildReasoningPlaceholder(profile.defaultReasoning, 'Use model default');
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = placeholderText;
            select.appendChild(placeholder);
            profile.reasoningOptions.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (profile.explicitReasoning) {
                select.value = profile.reasoningOptions.includes(profile.explicitReasoning)
                    ? profile.explicitReasoning
                    : '';
            } else {
                select.value = '';
            }
        } else {
            select.classList.add('is-hidden');
        }
    }
    if (input) {
        input.value = reasoning || '';
        input.placeholder = reasoning ? reasoning : placeholderText;
        input.disabled = hasOptions;
        input.classList.toggle('is-hidden', hasOptions);
    }
    if (field) {
        field.classList.toggle('is-select-only', hasOptions);
    }
}

function setSettingsStatus(model, reasoning, overrideText = null) {
    const status = document.getElementById('codex-model-status');
    const summary = document.getElementById('codex-controls-summary');
    if (!status) return;
    if (overrideText) {
        status.textContent = overrideText;
        if (summary) {
            summary.textContent = overrideText;
            summary.title = overrideText;
        }
        return;
    }
    if (!state.settings.loaded && !model && !reasoning && !state.settings.planModeReasoningEffort) {
        status.textContent = 'Refresh to load';
        if (summary) {
            summary.textContent = 'Refresh to load';
            summary.title = 'Refresh to load';
        }
        return;
    }
    const modelText = model ? model : 'default';
    const planModeModelText = state.settings.planModeModel ? state.settings.planModeModel : 'default';
    const reasoningText = formatReasoningStatus(model, reasoning);
    const planModeReasoningText = formatReasoningStatus(
        state.settings.planModeModel || model,
        state.settings.planModeReasoningEffort
    );
    const fullText = `Model: ${modelText} · Plan model: ${planModeModelText} · Reasoning: ${reasoningText} · Plan reasoning: ${planModeReasoningText}`;
    const compactToken = value => {
        if (value === 'default') return 'def';
        return value.replace(' (default)', '*');
    };
    const compactSummaryParts = [
        `Model:${compactToken(modelText)}`,
        `R:${compactToken(reasoningText)}`
    ];
    if (planModeModelText !== modelText || state.settings.planModeModel) {
        compactSummaryParts.push(`Plan:${compactToken(planModeModelText)}`);
    }
    if (planModeReasoningText !== reasoningText || state.settings.planModeReasoningEffort) {
        compactSummaryParts.push(`PR:${compactToken(planModeReasoningText)}`);
    }
    const compactSummary = compactSummaryParts.join(' · ');

    status.textContent = fullText;
    if (summary) {
        summary.textContent = compactSummary;
        summary.title = fullText;
    }
}

async function updateSettings() {
    const input = document.getElementById('codex-model-input');
    const status = document.getElementById('codex-model-status');
    const refreshBtn = document.getElementById('codex-controls-refresh');
    const modelSelect = document.getElementById('codex-model-select');
    const planModeModelInput = document.getElementById('codex-plan-mode-model-input');
    const planModeModelSelect = document.getElementById('codex-plan-mode-model-select');
    const planModeReasoningInput = document.getElementById('codex-plan-mode-reasoning-input');
    const planModeReasoningSelect = document.getElementById('codex-plan-mode-reasoning-select');
    const reasoningInput = document.getElementById('codex-reasoning-input');
    const reasoningSelect = document.getElementById('codex-reasoning-select');
    const model = modelSelect && !modelSelect.classList.contains('is-hidden')
        ? modelSelect.value.trim()
        : (input ? input.value.trim() : '');
    const plan_mode_model = planModeModelSelect && !planModeModelSelect.classList.contains('is-hidden')
        ? planModeModelSelect.value.trim()
        : (planModeModelInput ? planModeModelInput.value.trim() : '');
    const reasoning_effort = reasoningSelect && !reasoningSelect.classList.contains('is-hidden')
        ? reasoningSelect.value.trim()
        : (reasoningInput ? reasoningInput.value.trim() : '');
    const plan_mode_reasoning_effort = planModeReasoningSelect && !planModeReasoningSelect.classList.contains('is-hidden')
        ? planModeReasoningSelect.value.trim()
        : (planModeReasoningInput ? planModeReasoningInput.value.trim() : '');
    if (status) status.textContent = 'Saving...';
    if (refreshBtn) refreshBtn.classList.add('is-loading');
    try {
        const result = await fetchJson('/api/codex/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model, plan_mode_model, reasoning_effort, plan_mode_reasoning_effort })
        });
        const modelCatalog = normalizeModelCatalog(result?.model_catalog);
        const catalogModelOptions = collectCatalogModelOptions(modelCatalog);
        const catalogReasoningOptions = collectCatalogReasoningOptions(modelCatalog);
        state.settings.model = result?.settings?.model || null;
        state.settings.modelCatalog = modelCatalog.length > 0 ? modelCatalog : state.settings.modelCatalog;
        state.settings.planModeModel = result?.settings?.plan_mode_model || null;
        state.settings.reasoningEffort = result?.settings?.reasoning_effort || null;
        state.settings.planModeReasoningEffort = result?.settings?.plan_mode_reasoning_effort || null;
        state.settings.modelOptions = catalogModelOptions.length > 0
            ? catalogModelOptions
            : (Array.isArray(result?.model_options)
                ? normalizeOptionList(result.model_options)
                : state.settings.modelOptions);
        state.settings.reasoningOptions = Array.isArray(result?.reasoning_options)
            ? normalizeOptionList(result.reasoning_options)
            : (catalogReasoningOptions.length > 0
                ? catalogReasoningOptions
                : state.settings.reasoningOptions);
        state.settings.usage = result?.usage || state.settings.usage;
        state.settings.loaded = true;
        updateUsageSummary(state.settings.usage);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updatePlanModeModelControls(state.settings.planModeModel, state.settings.modelOptions);
        updateReasoningControls(
            state.settings.reasoningEffort,
            state.settings.reasoningOptions,
            state.settings.model
        );
        updatePlanModeReasoningControls(
            state.settings.planModeReasoningEffort,
            state.settings.reasoningOptions,
            state.settings.planModeModel || state.settings.model
        );
        setSettingsStatus(state.settings.model, state.settings.reasoningEffort);
        if (status) status.textContent = 'Saved';
    } catch (error) {
        if (status) status.textContent = normalizeError(error, 'Failed to update settings.');
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('is-loading');
    }
}

function createFetchTimeoutController(timeoutMs, baseSignal = null) {
    const normalized = Number(timeoutMs);
    if (!Number.isFinite(normalized) || normalized <= 0) {
        return {
            signal: baseSignal || undefined,
            didTimeout: () => false,
            clear: () => {}
        };
    }
    const controller = new AbortController();
    let timeoutId = null;
    let timedOut = false;

    const clear = () => {
        if (timeoutId !== null) {
            clearTimeout(timeoutId);
            timeoutId = null;
        }
    };

    const abortWithTimeout = () => {
        timedOut = true;
        controller.abort(new DOMException('Request timed out', 'TimeoutError'));
    };

    if (baseSignal) {
        if (baseSignal.aborted) {
            controller.abort(baseSignal.reason);
        } else {
            baseSignal.addEventListener('abort', () => {
                controller.abort(baseSignal.reason);
            }, { once: true });
        }
    }

    timeoutId = window.setTimeout(abortWithTimeout, normalized);

    return {
        signal: controller.signal,
        didTimeout: () => timedOut,
        clear
    };
}

async function fetchJson(url, options = {}) {
    const requestOptions = options && typeof options === 'object'
        ? { ...options }
        : {};
    const timeoutMs = requestOptions.timeoutMs;
    delete requestOptions.timeoutMs;
    const timeoutController = createFetchTimeoutController(timeoutMs, requestOptions.signal);
    if (timeoutController.signal) {
        requestOptions.signal = timeoutController.signal;
    }
    let response;
    try {
        response = await fetch(url, requestOptions);
    } catch (error) {
        if (timeoutController.didTimeout()) {
            const seconds = Math.max(1, Math.round(Number(timeoutMs) / 1000));
            const timeoutError = new Error(`요청 시간이 초과되었습니다. (${seconds}초)`);
            timeoutError.isTimeout = true;
            timeoutError.timeoutMs = Number(timeoutMs);
            timeoutError.cause = error;
            throw timeoutError;
        }
        throw error;
    } finally {
        timeoutController.clear();
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        const data = await response.json();
        if (!response.ok) {
            const error = new Error(data?.error || `Request failed (${response.status})`);
            error.status = response.status;
            error.payload = data;
            throw error;
        }
        return data;
    }
    const text = await response.text();
    if (!response.ok) {
        const error = new Error(`Request failed (${response.status})`);
        error.status = response.status;
        error.payload = text;
        throw error;
    }
    throw new Error(text || 'Unexpected response format.');
}

async function fetchArrayBuffer(url, options = {}) {
    const requestOptions = options && typeof options === 'object'
        ? { ...options }
        : {};
    const timeoutMs = requestOptions.timeoutMs;
    delete requestOptions.timeoutMs;
    const timeoutController = createFetchTimeoutController(timeoutMs, requestOptions.signal);
    if (timeoutController.signal) {
        requestOptions.signal = timeoutController.signal;
    }
    let response;
    try {
        response = await fetch(url, requestOptions);
    } catch (error) {
        if (timeoutController.didTimeout()) {
            const seconds = Math.max(1, Math.round(Number(timeoutMs) / 1000));
            const timeoutError = new Error(`요청 시간이 초과되었습니다. (${seconds}초)`);
            timeoutError.isTimeout = true;
            timeoutError.timeoutMs = Number(timeoutMs);
            timeoutError.cause = error;
            throw timeoutError;
        }
        throw error;
    } finally {
        timeoutController.clear();
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok) {
        if (contentType.includes('application/json')) {
            const data = await response.json();
            const error = new Error(data?.error || `Request failed (${response.status})`);
            error.status = response.status;
            error.payload = data;
            throw error;
        }
        const text = await response.text();
        const error = new Error(text || `Request failed (${response.status})`);
        error.status = response.status;
        error.payload = text;
        throw error;
    }

    return {
        contentType,
        buffer: await response.arrayBuffer()
    };
}

async function fetchBlob(url, options = {}) {
    const requestOptions = options && typeof options === 'object'
        ? { ...options }
        : {};
    const timeoutMs = requestOptions.timeoutMs;
    delete requestOptions.timeoutMs;
    const timeoutController = createFetchTimeoutController(timeoutMs, requestOptions.signal);
    if (timeoutController.signal) {
        requestOptions.signal = timeoutController.signal;
    }
    let response;
    try {
        response = await fetch(url, requestOptions);
    } catch (error) {
        if (timeoutController.didTimeout()) {
            const seconds = Math.max(1, Math.round(Number(timeoutMs) / 1000));
            const timeoutError = new Error(`요청 시간이 초과되었습니다. (${seconds}초)`);
            timeoutError.isTimeout = true;
            timeoutError.timeoutMs = Number(timeoutMs);
            timeoutError.cause = error;
            throw timeoutError;
        }
        throw error;
    } finally {
        timeoutController.clear();
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok) {
        if (contentType.includes('application/json')) {
            const data = await response.json();
            const error = new Error(data?.error || `Request failed (${response.status})`);
            error.status = response.status;
            error.payload = data;
            throw error;
        }
        const text = await response.text();
        const error = new Error(text || `Request failed (${response.status})`);
        error.status = response.status;
        error.payload = text;
        throw error;
    }

    return {
        contentType,
        contentDisposition: response.headers.get('content-disposition') || '',
        blob: await response.blob()
    };
}

function extractFilenameFromContentDisposition(value = '') {
    const source = String(value || '').trim();
    if (!source) return '';
    const encodedMatch = source.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
    if (encodedMatch?.[1]) {
        try {
            return decodeURIComponent(encodedMatch[1]);
        } catch (error) {
            void error;
        }
    }
    const quotedMatch = source.match(/filename\s*=\s*"([^"]+)"/i);
    if (quotedMatch?.[1]) {
        return quotedMatch[1];
    }
    const plainMatch = source.match(/filename\s*=\s*([^;]+)/i);
    return plainMatch?.[1] ? plainMatch[1].trim() : '';
}

function saveBlobAsFile(blob, filename = 'download.bin') {
    if (!(blob instanceof Blob)) return false;
    const downloadName = String(filename || 'download.bin').trim() || 'download.bin';
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = downloadName;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => {
        URL.revokeObjectURL(objectUrl);
    }, 0);
    return true;
}

function getTerminalOverlayElements() {
    const overlay = document.getElementById('codex-terminal-overlay');
    if (!overlay) return null;
    return {
        overlay,
        card: overlay.querySelector('.terminal-overlay-card'),
        body: overlay.querySelector('.terminal-overlay-body'),
        subtitle: document.getElementById('codex-terminal-overlay-subtitle'),
        tabs: document.getElementById('codex-terminal-overlay-tabs'),
        path: document.getElementById('codex-terminal-overlay-path'),
        status: document.getElementById('codex-terminal-overlay-status'),
        empty: document.getElementById('codex-terminal-overlay-empty'),
        shell: document.getElementById('codex-terminal-overlay-shell'),
        extraKeys: document.getElementById('codex-terminal-overlay-extra-keys'),
        newTabBtn: document.getElementById('codex-terminal-overlay-new-tab'),
        closeTabBtn: document.getElementById('codex-terminal-overlay-close-tab')
    };
}

function isTerminalOverlayOpen() {
    const overlay = document.getElementById('codex-terminal-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function normalizeTerminalLaunchContext(value) {
    const source = value && typeof value === 'object' ? value : {};
    return {
        root: normalizeFileBrowserRoot(source.root),
        path: normalizeFileBrowserRelativePath(source.path)
    };
}

function getTerminalLaunchContext() {
    return normalizeTerminalLaunchContext(terminalState.launchContext);
}

function setTerminalLaunchContext(context = null) {
    terminalState.launchContext = normalizeTerminalLaunchContext(
        context || resolveDefaultTerminalLaunchContext()
    );
    syncTerminalOverlayState();
    return terminalState.launchContext;
}

function buildTerminalLaunchContextDisplayPath(context = null) {
    const normalized = normalizeTerminalLaunchContext(context || terminalState.launchContext);
    return formatFileBrowserDisplayPath(normalized.root, normalized.path);
}

function clearTerminalExtraKeyModifiers() {
    terminalState.extraKeyModifiers.ctrl = false;
    terminalState.extraKeyModifiers.alt = false;
    syncTerminalExtraKeysState();
}

function toggleTerminalExtraKeyModifier(modifierName = '') {
    const key = modifierName === 'alt' ? 'alt' : (modifierName === 'ctrl' ? 'ctrl' : '');
    if (!key) return false;
    terminalState.extraKeyModifiers[key] = !terminalState.extraKeyModifiers[key];
    syncTerminalExtraKeysState();
    return terminalState.extraKeyModifiers[key];
}

function resolveCtrlModifiedTerminalData(data = '') {
    const source = typeof data === 'string' ? data : '';
    if (!source) return '';
    if (source.length !== 1) return source;
    const codePoint = source.charCodeAt(0);
    if (codePoint >= 97 && codePoint <= 122) {
        return String.fromCharCode(codePoint - 96);
    }
    if (codePoint >= 65 && codePoint <= 90) {
        return String.fromCharCode(codePoint - 64);
    }
    if (source === ' ') return '\x00';
    if (source === '@') return '\x00';
    if (source === '[') return '\x1b';
    if (source === '\\') return '\x1c';
    if (source === ']') return '\x1d';
    if (source === '^') return '\x1e';
    if (source === '_') return '\x1f';
    if (source === '?') return '\x7f';
    return source;
}

function applyTerminalExtraKeyModifiers(data = '') {
    let output = typeof data === 'string' ? data : '';
    const useCtrl = Boolean(terminalState.extraKeyModifiers.ctrl);
    const useAlt = Boolean(terminalState.extraKeyModifiers.alt);
    if (!output) return output;
    if (useCtrl) {
        output = resolveCtrlModifiedTerminalData(output);
    }
    if (useAlt) {
        output = `\x1b${output}`;
    }
    if (useCtrl || useAlt) {
        clearTerminalExtraKeyModifiers();
    }
    return output;
}

function focusActiveTerminalInstance() {
    if (!terminalState.terminal) return;
    try {
        terminalState.terminal.focus();
    } catch (error) {
        void error;
    }
}

function cancelTerminalViewportRefresh() {
    if (terminalState.viewportRefreshFrameId !== null) {
        window.cancelAnimationFrame(terminalState.viewportRefreshFrameId);
        terminalState.viewportRefreshFrameId = null;
    }
    if (terminalState.viewportRefreshTimerId !== null) {
        window.clearTimeout(terminalState.viewportRefreshTimerId);
        terminalState.viewportRefreshTimerId = null;
    }
    terminalState.viewportRefreshNeedsFocus = false;
    terminalState.viewportRefreshNeedsFit = false;
}

function getTerminalVisibleRowMetrics() {
    const terminal = terminalState.terminal;
    const elements = getTerminalOverlayElements();
    if (!terminal || !elements?.shell) return null;

    const shellRect = elements.shell.getBoundingClientRect();
    if (!Number.isFinite(shellRect.top) || !Number.isFinite(shellRect.bottom)) {
        return null;
    }

    const viewport = window.visualViewport;
    const visualBottom = Number(viewport?.height) + Number(viewport?.offsetTop);
    const layoutBottom = Number(window.innerHeight);
    let visibleBottom = Number.isFinite(visualBottom) && visualBottom > 0
        ? visualBottom
        : layoutBottom;

    const extraKeys = elements.extraKeys;
    if (
        extraKeys instanceof HTMLElement
        && extraKeys.classList.contains('is-mobile-visible')
        && !extraKeys.classList.contains('is-hidden')
    ) {
        const extraKeysRect = extraKeys.getBoundingClientRect();
        if (Number.isFinite(extraKeysRect.top) && extraKeysRect.top > shellRect.top) {
            visibleBottom = Math.min(visibleBottom, extraKeysRect.top - 8);
        }
    }

    const rowsLayer = elements.shell.querySelector('.xterm-rows');
    const rowsRect = rowsLayer instanceof Element ? rowsLayer.getBoundingClientRect() : shellRect;
    const rowAreaTop = Math.max(shellRect.top, Number.isFinite(rowsRect.top) ? rowsRect.top : shellRect.top);
    const rowAreaBottom = Math.min(
        Number.isFinite(rowsRect.bottom) ? rowsRect.bottom : shellRect.bottom,
        visibleBottom,
        shellRect.bottom
    );
    const totalRowsHeight = Number.isFinite(rowsRect.height) && rowsRect.height > 0
        ? rowsRect.height
        : Math.max(1, shellRect.height);
    const rowHeight = totalRowsHeight / Math.max(1, terminal.rows);
    if (!Number.isFinite(rowHeight) || rowHeight <= 0) {
        return null;
    }

    const visibleHeight = Math.max(0, rowAreaBottom - rowAreaTop);
    const visibleRows = Math.min(
        Math.max(1, terminal.rows),
        Math.max(1, Math.floor(visibleHeight / rowHeight))
    );
    return { visibleRows };
}

function ensureTerminalCursorVisible({ focus = false } = {}) {
    const terminal = terminalState.terminal;
    if (!terminal || !isTerminalOverlayOpen()) {
        terminalState.viewportRefreshNeedsFocus = false;
        return;
    }

    const buffer = terminal.buffer?.active;
    const metrics = getTerminalVisibleRowMetrics();
    if (
        buffer
        && metrics
        && Number.isFinite(buffer.baseY)
        && Number.isFinite(buffer.cursorY)
        && Number.isFinite(buffer.viewportY)
        && metrics.visibleRows > 0
    ) {
        const cursorLine = Math.max(0, Math.round(buffer.baseY + buffer.cursorY));
        const currentViewportY = Math.max(0, Math.round(buffer.viewportY));
        const reducedViewport = metrics.visibleRows < terminal.rows || isMobileKeyboardOpen();
        const bottomMarginRows = reducedViewport
            ? Math.min(2, Math.max(1, Math.floor(metrics.visibleRows / 6)))
            : 0;
        const bottomSafeRows = Math.max(1, metrics.visibleRows - bottomMarginRows);
        const maxVisibleLine = currentViewportY + bottomSafeRows - 1;
        let nextViewportY = currentViewportY;

        if (cursorLine > maxVisibleLine) {
            nextViewportY = Math.max(0, cursorLine - bottomSafeRows + 1);
        } else if (cursorLine < currentViewportY) {
            nextViewportY = cursorLine;
        }

        if (nextViewportY !== currentViewportY && typeof terminal.scrollToLine === 'function') {
            try {
                terminal.scrollToLine(nextViewportY);
            } catch (error) {
                void error;
            }
        }
    }

    if (focus || terminalState.viewportRefreshNeedsFocus) {
        terminalState.viewportRefreshNeedsFocus = false;
        focusActiveTerminalInstance();
    }
}

function scheduleTerminalViewportRefresh({ focus = false, fit = false } = {}) {
    if (!terminalState.terminal || !isTerminalOverlayOpen()) return;
    if (focus) {
        terminalState.viewportRefreshNeedsFocus = true;
    }
    if (fit) {
        terminalState.viewportRefreshNeedsFit = true;
    }
    if (terminalState.viewportRefreshFrameId !== null) {
        return;
    }
    terminalState.viewportRefreshFrameId = requestAnimationFrame(() => {
        terminalState.viewportRefreshFrameId = null;
        if (!terminalState.terminal || !isTerminalOverlayOpen()) {
            terminalState.viewportRefreshNeedsFocus = false;
            return;
        }
        const needsFit = Boolean(terminalState.viewportRefreshNeedsFit);
        terminalState.viewportRefreshNeedsFit = false;
        if (needsFit) {
            scheduleTerminalFit();
        }
        if (terminalState.viewportRefreshTimerId !== null) {
            window.clearTimeout(terminalState.viewportRefreshTimerId);
        }
        terminalState.viewportRefreshTimerId = window.setTimeout(() => {
            terminalState.viewportRefreshTimerId = null;
            if (!terminalState.terminal || !isTerminalOverlayOpen()) {
                terminalState.viewportRefreshNeedsFocus = false;
                return;
            }
            ensureTerminalCursorVisible({ focus: terminalState.viewportRefreshNeedsFocus });
        }, needsFit ? 72 : 24);
    });
}

function queueTerminalDataForActiveSession(rawData, { focus = false } = {}) {
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    if (!activeSession?.id) return false;
    const data = applyTerminalExtraKeyModifiers(rawData);
    if (!data) return false;
    queueTerminalInput(activeSession.id, data);
    if (focus) {
        requestAnimationFrame(() => {
            focusActiveTerminalInstance();
        });
    }
    return true;
}

function renderTerminalExtraKeys() {
    const elements = getTerminalOverlayElements();
    const container = elements?.extraKeys;
    if (!(container instanceof Element)) return;
    if (container.dataset.rendered === 'true') {
        syncTerminalExtraKeysState();
        return;
    }
    container.innerHTML = '';
    TERMINAL_EXTRA_KEYS.forEach(key => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'terminal-overlay-extra-key';
        button.textContent = key.label;
        button.dataset.keyId = key.id;
        if (key.modifier) {
            button.dataset.terminalModifier = key.modifier;
        }
        button.addEventListener('pointerdown', event => {
            event.preventDefault();
        });
        button.addEventListener('click', event => {
            event.preventDefault();
            if (key.modifier) {
                toggleTerminalExtraKeyModifier(key.modifier);
                focusActiveTerminalInstance();
                return;
            }
            queueTerminalDataForActiveSession(key.sequence || key.text || '', { focus: true });
        });
        container.appendChild(button);
    });
    container.dataset.rendered = 'true';
    syncTerminalExtraKeysState();
}

function shouldShowTerminalExtraKeys() {
    const hasCoarsePointer = mediaQueryMatches('(pointer: coarse)') || mediaQueryMatches('(any-pointer: coarse)');
    const hasFinePointer = mediaQueryMatches('(pointer: fine)') || mediaQueryMatches('(any-pointer: fine)');
    if (isLikelyVirtualKeyboardEnvironment()) {
        return true;
    }
    if (hasCoarsePointer && isCompactLayout()) {
        return true;
    }
    return hasCoarsePointer && !hasFinePointer;
}

function getTerminalExtraKeysViewportBottomInset() {
    const viewport = window.visualViewport;
    const visualHeight = Number(viewport?.height);
    const visualTop = Number(viewport?.offsetTop);
    const layoutHeight = Number(window.innerHeight);
    const visualBottom = visualHeight + visualTop;
    if (
        Number.isFinite(visualBottom)
        && visualBottom > 0
        && Number.isFinite(layoutHeight)
        && layoutHeight > 0
    ) {
        return Math.max(0, Math.round(layoutHeight - visualBottom));
    }
    return 0;
}

function syncTerminalExtraKeysOverlayMetrics({ visible = false } = {}) {
    const elements = getTerminalOverlayElements();
    const container = elements?.extraKeys;
    if (!(container instanceof HTMLElement)) return false;
    if (!(elements?.body instanceof HTMLElement)) return false;
    let layoutChanged = false;
    if (!visible) {
        if (elements.body.style.getPropertyValue('--terminal-overlay-extra-keys-reserved-space') !== '0px') {
            elements.body.style.setProperty('--terminal-overlay-extra-keys-reserved-space', '0px');
            layoutChanged = true;
        }
        if (container.style.getPropertyValue('--terminal-extra-keys-left')) {
            container.style.removeProperty('--terminal-extra-keys-left');
            layoutChanged = true;
        }
        if (container.style.getPropertyValue('--terminal-extra-keys-width')) {
            container.style.removeProperty('--terminal-extra-keys-width');
            layoutChanged = true;
        }
        if (container.style.getPropertyValue('--terminal-extra-keys-bottom')) {
            container.style.removeProperty('--terminal-extra-keys-bottom');
            layoutChanged = true;
        }
        return layoutChanged;
    }

    const cardRect = elements.card instanceof Element ? elements.card.getBoundingClientRect() : null;
    const horizontalInset = isCompactLayout() ? 12 : 16;
    const fallbackWidth = Math.max(220, Math.round(window.innerWidth - (horizontalInset * 2)));
    const nextLeft = cardRect
        ? Math.max(8, Math.round(cardRect.left + horizontalInset))
        : horizontalInset;
    const nextWidth = cardRect
        ? Math.max(220, Math.round(cardRect.width - (horizontalInset * 2)))
        : fallbackWidth;
    const nextBottom = Math.max(8, getTerminalExtraKeysViewportBottomInset() + 8);
    const nextLeftValue = `${nextLeft}px`;
    const nextWidthValue = `${nextWidth}px`;
    const nextBottomValue = `${nextBottom}px`;
    if (container.style.getPropertyValue('--terminal-extra-keys-left') !== nextLeftValue) {
        container.style.setProperty('--terminal-extra-keys-left', nextLeftValue);
        layoutChanged = true;
    }
    if (container.style.getPropertyValue('--terminal-extra-keys-width') !== nextWidthValue) {
        container.style.setProperty('--terminal-extra-keys-width', nextWidthValue);
        layoutChanged = true;
    }
    if (container.style.getPropertyValue('--terminal-extra-keys-bottom') !== nextBottomValue) {
        container.style.setProperty('--terminal-extra-keys-bottom', nextBottomValue);
        layoutChanged = true;
    }

    const reservedSpace = Math.max(0, Math.ceil(container.getBoundingClientRect().height) + 12);
    const reservedSpaceValue = `${reservedSpace}px`;
    if (elements.body.style.getPropertyValue('--terminal-overlay-extra-keys-reserved-space') !== reservedSpaceValue) {
        elements.body.style.setProperty('--terminal-overlay-extra-keys-reserved-space', reservedSpaceValue);
        layoutChanged = true;
    }
    return layoutChanged;
}

function syncTerminalExtraKeysState() {
    const elements = getTerminalOverlayElements();
    const container = elements?.extraKeys;
    if (!(container instanceof Element)) return;
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    const shouldShow = shouldShowTerminalExtraKeys();
    const isVisible = shouldShow && isTerminalOverlayOpen();
    const wasVisible = container.classList.contains('is-mobile-visible');
    const hasActiveSession = Boolean(activeSession?.id);
    container.classList.toggle('is-hidden', !isVisible);
    container.classList.toggle('is-mobile-visible', isVisible);
    container.classList.toggle('is-disabled', isVisible && !hasActiveSession);
    container.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
    container.querySelectorAll('[data-terminal-modifier]').forEach(button => {
        const modifierName = button.getAttribute('data-terminal-modifier') || '';
        button.classList.toggle('is-active', Boolean(terminalState.extraKeyModifiers[modifierName]));
    });
    container.querySelectorAll('.terminal-overlay-extra-key').forEach(button => {
        button.disabled = !hasActiveSession;
    });
    const layoutChanged = syncTerminalExtraKeysOverlayMetrics({ visible: isVisible });
    if (wasVisible !== isVisible || layoutChanged) {
        scheduleTerminalViewportRefresh({ fit: true });
    }
}

function normalizeTerminalSessionSummary(value) {
    if (!value || typeof value !== 'object') return null;
    const id = typeof value.id === 'string' ? value.id.trim() : '';
    if (!id) return null;
    const outputBaseOffset = Number.isFinite(value.output_base_offset)
        ? Math.max(0, Math.round(value.output_base_offset))
        : 0;
    const outputLength = Number.isFinite(value.output_length)
        ? Math.max(outputBaseOffset, Math.round(value.output_length))
        : outputBaseOffset;
    return {
        id,
        root: normalizeFileBrowserRoot(value.root),
        rootPath: typeof value.root_path === 'string' ? value.root_path : '',
        path: normalizeFileBrowserRelativePath(value.path),
        cwd: typeof value.cwd === 'string' ? value.cwd : '',
        displayPath: typeof value.display_path === 'string' ? value.display_path : '$workspace',
        title: typeof value.title === 'string' && value.title.trim() ? value.title.trim() : 'Terminal',
        shell: typeof value.shell === 'string' ? value.shell.trim() : '',
        cols: Number.isFinite(value.cols) ? Math.max(1, Math.round(value.cols)) : TERMINAL_DEFAULT_COLS,
        rows: Number.isFinite(value.rows) ? Math.max(1, Math.round(value.rows)) : TERMINAL_DEFAULT_ROWS,
        processRunning: Boolean(value.process_running),
        exitCode: Number.isFinite(value.exit_code) ? Math.round(value.exit_code) : null,
        createdAt: typeof value.created_at === 'string' ? value.created_at : '',
        updatedAt: typeof value.updated_at === 'string' ? value.updated_at : '',
        lastOutputAt: typeof value.last_output_at === 'string' ? value.last_output_at : '',
        outputBaseOffset,
        outputLength
    };
}

function parseTerminalTimestampMs(value) {
    const parsed = Date.parse(typeof value === 'string' ? value : '');
    return Number.isFinite(parsed) ? parsed : 0;
}

function mergeTerminalSessionSummary(existing, incoming) {
    if (!existing) return incoming;
    const existingUpdatedMs = parseTerminalTimestampMs(existing.updatedAt);
    const incomingUpdatedMs = parseTerminalTimestampMs(incoming.updatedAt);
    const preferIncomingState = incomingUpdatedMs >= existingUpdatedMs;
    const merged = preferIncomingState
        ? { ...existing, ...incoming }
        : { ...incoming, ...existing };
    merged.outputBaseOffset = Math.max(existing.outputBaseOffset, incoming.outputBaseOffset);
    merged.outputLength = Math.max(existing.outputLength, incoming.outputLength, merged.outputBaseOffset);
    if (parseTerminalTimestampMs(incoming.lastOutputAt) < parseTerminalTimestampMs(existing.lastOutputAt)) {
        merged.lastOutputAt = existing.lastOutputAt;
    }
    if (!preferIncomingState && existing.processRunning === false) {
        merged.processRunning = false;
        merged.exitCode = existing.exitCode;
    }
    return merged;
}

function getTerminalSessionById(sessionId) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return null;
    return terminalState.sessions.find(session => session.id === targetId) || null;
}

function setTerminalSessions(sessions, { preserveActive = true, preferSessionId = '' } = {}) {
    const previousActiveId = preserveActive
        ? (typeof terminalState.activeSessionId === 'string' ? terminalState.activeSessionId.trim() : '')
        : '';
    const preferredId = typeof preferSessionId === 'string' ? preferSessionId.trim() : '';
    const normalizedSessions = Array.isArray(sessions)
        ? sessions
            .map(normalizeTerminalSessionSummary)
            .filter(Boolean)
        : [];

    terminalState.sessions = normalizedSessions;
    let nextActiveId = '';
    if (preferredId && normalizedSessions.some(session => session.id === preferredId)) {
        nextActiveId = preferredId;
    } else if (previousActiveId && normalizedSessions.some(session => session.id === previousActiveId)) {
        nextActiveId = previousActiveId;
    } else if (normalizedSessions.length > 0) {
        nextActiveId = normalizedSessions[normalizedSessions.length - 1].id;
    }
    terminalState.activeSessionId = nextActiveId || null;
    if (!nextActiveId) {
        terminalState.mountedSessionId = null;
    }
}

function upsertTerminalSession(summary) {
    const normalized = normalizeTerminalSessionSummary(summary);
    if (!normalized) return null;
    const nextSessions = terminalState.sessions.slice();
    const index = nextSessions.findIndex(session => session.id === normalized.id);
    if (index >= 0) {
        nextSessions[index] = mergeTerminalSessionSummary(nextSessions[index], normalized);
    } else {
        nextSessions.push(normalized);
    }
    setTerminalSessions(nextSessions, {
        preserveActive: true,
        preferSessionId: normalized.id
    });
    return getTerminalSessionById(normalized.id);
}

function removeTerminalSessionFromState(sessionId) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return;
    const remaining = terminalState.sessions.filter(session => session.id !== targetId);
    setTerminalSessions(remaining, {
        preserveActive: terminalState.activeSessionId !== targetId
    });
    if (terminalState.mountedSessionId === targetId) {
        terminalState.mountedSessionId = null;
    }
}

function buildTerminalSessionStatusText(session) {
    if (!session) {
        return '열린 Terminal 세션이 없습니다.';
    }
    const statusParts = [];
    statusParts.push(session.processRunning ? '실행 중' : `종료됨 (${session.exitCode ?? '-'})`);
    if (session.processRunning && session.id === terminalState.activeSessionId) {
        if (terminalState.streamReconnectTimer !== null) {
            statusParts.push('실시간 재연결 중');
        } else if (terminalState.streamSource && terminalState.streamSessionId === session.id) {
            statusParts.push(terminalState.streamConnected ? '실시간 연결' : '실시간 연결 중');
        } else if (typeof window.EventSource !== 'function') {
            statusParts.push('폴링 연결');
        }
    }
    if (session.shell) {
        statusParts.push(session.shell);
    }
    if (Number.isFinite(session.cols) && Number.isFinite(session.rows)) {
        statusParts.push(`${session.cols}x${session.rows}`);
    }
    return statusParts.join(' · ');
}

function syncTerminalOverlayState() {
    const elements = getTerminalOverlayElements();
    if (!elements) return;
    renderTerminalExtraKeys();
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    if (!activeSession) {
        terminalState.extraKeyModifiers.ctrl = false;
        terminalState.extraKeyModifiers.alt = false;
    }
    const hasSessions = terminalState.sessions.length > 0;
    const launchContext = getTerminalLaunchContext();
    const launchDisplayPath = buildTerminalLaunchContextDisplayPath(launchContext);
    if (elements.subtitle) {
        elements.subtitle.textContent = `현재 폴더 기준 CLI 세션 · ${launchDisplayPath}`;
        setHoverTooltip(elements.subtitle, launchDisplayPath, { focusable: false });
    }
    if (elements.tabs) {
        elements.tabs.innerHTML = '';
        terminalState.sessions.forEach(session => {
            const isActive = activeSession?.id === session.id;
            const item = document.createElement('div');
            item.className = `terminal-overlay-tab${isActive ? ' is-active' : ''}`;

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'terminal-overlay-tab-button';
            button.setAttribute('role', 'tab');
            button.setAttribute('aria-selected', isActive ? 'true' : 'false');
            button.tabIndex = isActive ? 0 : -1;
            button.addEventListener('click', () => {
                void setActiveTerminalSession(session.id, {
                    attach: true,
                    forceReset: terminalState.mountedSessionId !== session.id
                });
            });

            const textWrap = document.createElement('span');
            textWrap.className = 'terminal-overlay-tab-text';
            const title = document.createElement('span');
            title.className = 'terminal-overlay-tab-title';
            title.textContent = session.title;
            const subtitle = document.createElement('span');
            subtitle.className = 'terminal-overlay-tab-subtitle';
            subtitle.textContent = session.displayPath;
            textWrap.appendChild(title);
            textWrap.appendChild(subtitle);
            button.appendChild(textWrap);
            item.appendChild(button);

            const closeButton = document.createElement('button');
            closeButton.type = 'button';
            closeButton.className = 'terminal-overlay-tab-close';
            closeButton.setAttribute('aria-label', `${session.title} Terminal 종료`);
            closeButton.setAttribute('title', `${session.title} Terminal 종료`);
            closeButton.addEventListener('click', event => {
                event.stopPropagation();
                void closeTerminalTab(session.id);
            });
            item.appendChild(closeButton);

            elements.tabs.appendChild(item);
        });
    }

    if (elements.path) {
        const nextPath = activeSession?.displayPath || launchDisplayPath;
        elements.path.textContent = nextPath;
        setHoverTooltip(elements.path, activeSession?.cwd || nextPath);
    }
    if (elements.status) {
        elements.status.textContent = buildTerminalSessionStatusText(activeSession);
    }
    if (elements.newTabBtn) {
        const createLabel = `현재 폴더 기준 새 Terminal 탭 생성 (${launchDisplayPath})`;
        elements.newTabBtn.disabled = false;
        elements.newTabBtn.setAttribute('aria-label', createLabel);
        elements.newTabBtn.setAttribute('title', createLabel);
        syncHoverTooltipFromLabel(elements.newTabBtn);
    }
    if (elements.closeTabBtn) {
        elements.closeTabBtn.disabled = !activeSession;
    }
    if (elements.empty) {
        elements.empty.textContent = `열린 Terminal 탭이 없습니다. + 버튼으로 ${launchDisplayPath} 세션을 생성하세요.`;
        elements.empty.classList.toggle('is-hidden', hasSessions);
    }
    if (elements.shell) {
        elements.shell.classList.toggle('is-hidden', !hasSessions);
    }
    syncTerminalExtraKeysState();
}

function loadExternalStylesheet(href, id) {
    const head = document.head || document.getElementsByTagName('head')[0];
    if (!head) {
        return Promise.reject(new Error('stylesheet mount point not found'));
    }
    if (id) {
        const existing = document.getElementById(id);
        if (existing) return Promise.resolve(existing);
    }
    return new Promise((resolve, reject) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        if (id) {
            link.id = id;
        }
        link.addEventListener('load', () => resolve(link), { once: true });
        link.addEventListener('error', () => reject(new Error(`Failed to load stylesheet: ${href}`)), { once: true });
        head.appendChild(link);
    });
}

function loadExternalScript(src, { id = '', readyCheck = null } = {}) {
    if (typeof readyCheck === 'function' && readyCheck()) {
        return Promise.resolve();
    }
    if (id) {
        const existing = document.getElementById(id);
        if (existing) {
            return new Promise((resolve, reject) => {
                const onLoad = () => resolve();
                const onError = () => reject(new Error(`Failed to load script: ${src}`));
                existing.addEventListener('load', onLoad, { once: true });
                existing.addEventListener('error', onError, { once: true });
                if (existing.dataset.loaded === 'true') {
                    resolve();
                }
            });
        }
    }
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        if (id) {
            script.id = id;
        }
        script.addEventListener('load', () => {
            script.dataset.loaded = 'true';
            resolve();
        }, { once: true });
        script.addEventListener('error', () => reject(new Error(`Failed to load script: ${src}`)), { once: true });
        document.head.appendChild(script);
    });
}

async function ensureTerminalRuntimeLoaded() {
    if (terminalState.runtimePromise) {
        return terminalState.runtimePromise;
    }
    terminalState.runtimePromise = (async () => {
        await loadExternalStylesheet(XTERM_VENDOR_CSS_HREF, 'codex-xterm-style');
        await loadExternalScript(XTERM_VENDOR_SRC, {
            id: 'codex-xterm-script',
            readyCheck: () => typeof window.Terminal === 'function'
        });
        await loadExternalScript(XTERM_FIT_VENDOR_SRC, {
            id: 'codex-xterm-fit-script',
            readyCheck: () => Boolean(window.FitAddon?.FitAddon || window.FitAddon)
        });
        const FitAddonClass = window.FitAddon?.FitAddon || window.FitAddon;
        if (typeof window.Terminal !== 'function' || typeof FitAddonClass !== 'function') {
            throw new Error('xterm runtime unavailable');
        }
        return {
            Terminal: window.Terminal,
            FitAddon: FitAddonClass
        };
    })().catch(error => {
        terminalState.runtimePromise = null;
        throw error;
    });
    return terminalState.runtimePromise;
}

function buildTerminalTheme() {
    const styles = getComputedStyle(document.documentElement);
    const background = styles.getPropertyValue('--code-bg').trim() || '#111111';
    const foreground = styles.getPropertyValue('--text-primary').trim() || '#f0f0f0';
    const cursor = styles.getPropertyValue('--accent').trim() || foreground;
    return {
        background,
        foreground,
        cursor,
        cursorAccent: background,
        selectionBackground: 'rgba(127, 143, 163, 0.24)'
    };
}

function syncTerminalTheme() {
    if (!terminalState.terminal) return;
    terminalState.terminal.options.theme = buildTerminalTheme();
}

function getTerminalFontSize() {
    if (isPhoneLayout()) return TERMINAL_FONT_SIZE_PHONE;
    if (isFoldLayout()) return TERMINAL_FONT_SIZE_COMPACT;
    return TERMINAL_FONT_SIZE_DESKTOP;
}

function clearQueuedTerminalInput() {
    if (terminalState.inputFlushTimer !== null) {
        window.clearTimeout(terminalState.inputFlushTimer);
        terminalState.inputFlushTimer = null;
    }
    terminalState.inputSessionId = null;
    terminalState.inputBuffer = '';
    terminalState.inputInFlight = false;
}

function isTerminalSessionClosedError(error) {
    const errorCode = error?.payload?.error_code;
    return errorCode === 'session_not_running' || errorCode === 'session_closed';
}

async function syncTerminalSessionAfterInputFailure(sessionId) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return;
    try {
        const response = await readTerminalApiSession(targetId);
        const updatedSession = upsertTerminalSession(response);
        if (terminalState.activeSessionId === targetId && updatedSession) {
            writeTerminalOutput(response?.output || '', { reset: true });
            terminalState.mountedSessionId = updatedSession.id;
            syncTerminalOverlayState();
            if (response?.process_running) {
                connectTerminalEventStream(updatedSession.id, updatedSession.outputLength);
            } else {
                closeTerminalEventStream({
                    clearSession: true,
                    resetReconnect: true
                });
                stopTerminalPolling();
            }
        }
    } catch (error) {
        void error;
    }
}

function queueTerminalInput(sessionId, data) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    const chunk = typeof data === 'string' ? data : '';
    if (!targetId || !chunk) return;
    if (terminalState.inputSessionId && terminalState.inputSessionId !== targetId && terminalState.inputBuffer) {
        clearQueuedTerminalInput();
    }
    terminalState.inputSessionId = targetId;
    terminalState.inputBuffer += chunk;
    if (terminalState.inputFlushTimer !== null) {
        return;
    }
    terminalState.inputFlushTimer = window.setTimeout(() => {
        terminalState.inputFlushTimer = null;
        void flushQueuedTerminalInput();
    }, 10);
}

async function flushQueuedTerminalInput() {
    if (terminalState.inputInFlight) return;
    const sessionId = typeof terminalState.inputSessionId === 'string' ? terminalState.inputSessionId.trim() : '';
    const payload = terminalState.inputBuffer;
    if (!sessionId || !payload) return;
    terminalState.inputBuffer = '';
    terminalState.inputInFlight = true;
    try {
        const summary = await writeTerminalApiInput(sessionId, payload);
        upsertTerminalSession(summary);
        if (terminalState.activeSessionId === sessionId) {
            syncTerminalOverlayState();
        }
    } catch (error) {
        if (isTerminalSessionClosedError(error)) {
            await syncTerminalSessionAfterInputFailure(sessionId);
        } else {
            showToast(normalizeError(error, '터미널 입력 전송에 실패했습니다.'), {
                tone: 'error',
                durationMs: 3600
            });
        }
    } finally {
        terminalState.inputInFlight = false;
        if (terminalState.inputBuffer) {
            void flushQueuedTerminalInput();
        }
    }
}

function queueTerminalResize(sessionId, cols, rows) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return;
    if (terminalState.resizeTimerId !== null) {
        window.clearTimeout(terminalState.resizeTimerId);
    }
    terminalState.resizeTimerId = window.setTimeout(() => {
        terminalState.resizeTimerId = null;
        const activeSession = getTerminalSessionById(targetId);
        if (!activeSession) return;
        void resizeTerminalApiSession(targetId, cols, rows).then(summary => {
            upsertTerminalSession(summary);
            if (terminalState.activeSessionId === targetId) {
                syncTerminalOverlayState();
            }
        }).catch(() => {
            void 0;
        });
    }, TERMINAL_RESIZE_DEBOUNCE_MS);
}

async function ensureTerminalInstance() {
    const elements = getTerminalOverlayElements();
    if (!elements?.shell) {
        throw new Error('terminal overlay shell not found');
    }
    if (terminalState.terminal && terminalState.fitAddon) {
        syncTerminalTheme();
        return terminalState.terminal;
    }
    elements.shell.classList.add('is-loading');
    let runtime;
    try {
        runtime = await ensureTerminalRuntimeLoaded();
    } catch (error) {
        elements.shell.classList.remove('is-loading');
        throw error;
    }
    const terminal = new runtime.Terminal({
        cursorBlink: true,
        convertEol: false,
        allowTransparency: true,
        scrollback: 6000,
        fontSize: getTerminalFontSize(),
        fontFamily: TERMINAL_FONT_FAMILY,
        lineHeight: 1.16,
        fontWeight: '500',
        theme: buildTerminalTheme()
    });
    const fitAddon = new runtime.FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(elements.shell);
    const focusTerminal = () => {
        try {
            terminal.focus();
        } catch (error) {
            void error;
        }
    };
    elements.shell.addEventListener('mousedown', focusTerminal);
    elements.shell.addEventListener('touchstart', focusTerminal, { passive: true });
    terminal.onData(data => {
        queueTerminalDataForActiveSession(data);
    });
    terminal.onCursorMove(() => {
        if (!isMobileKeyboardOpen()) return;
        scheduleTerminalViewportRefresh();
    });
    terminal.onResize(size => {
        const activeSession = getTerminalSessionById(terminalState.activeSessionId);
        if (!activeSession) return;
        queueTerminalResize(activeSession.id, size.cols, size.rows);
    });
    terminalState.terminal = terminal;
    terminalState.fitAddon = fitAddon;
    elements.shell.classList.remove('is-loading');

    if (typeof ResizeObserver === 'function' && !terminalState.resizeObserver) {
        terminalState.resizeObserver = new ResizeObserver(() => {
            if (!isTerminalOverlayOpen()) return;
            scheduleTerminalViewportRefresh({ fit: true });
        });
        terminalState.resizeObserver.observe(elements.shell);
    }
    syncTerminalTheme();
    scheduleTerminalViewportRefresh({ fit: true });
    return terminal;
}

function scheduleTerminalFit() {
    if (!terminalState.fitAddon || !isTerminalOverlayOpen()) return;
    requestAnimationFrame(() => {
        if (!terminalState.fitAddon || !isTerminalOverlayOpen()) return;
        if (terminalState.terminal) {
            terminalState.terminal.options.fontSize = getTerminalFontSize();
            terminalState.terminal.options.fontFamily = TERMINAL_FONT_FAMILY;
        }
        try {
            terminalState.fitAddon.fit();
        } catch (error) {
            void error;
        }
    });
}

function getTerminalViewportSize() {
    const terminal = terminalState.terminal;
    const cols = terminal && Number.isFinite(terminal.cols) && terminal.cols > 0
        ? Math.max(1, Math.round(terminal.cols))
        : TERMINAL_DEFAULT_COLS;
    const rows = terminal && Number.isFinite(terminal.rows) && terminal.rows > 0
        ? Math.max(1, Math.round(terminal.rows))
        : TERMINAL_DEFAULT_ROWS;
    return { cols, rows };
}

async function fetchTerminalSessionsList() {
    return fetchJson('/api/codex/terminals', {
        cache: 'no-store',
        timeoutMs: TERMINAL_REQUEST_TIMEOUT_MS
    });
}

async function createTerminalApiSession(root, path, cols, rows) {
    return fetchJson('/api/codex/terminals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: TERMINAL_REQUEST_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path),
            cols,
            rows
        })
    });
}

async function readTerminalApiSession(sessionId, offset = null) {
    const query = offset === null || offset === undefined
        ? ''
        : `?offset=${encodeURIComponent(String(offset))}`;
    return fetchJson(`/api/codex/terminals/${encodeURIComponent(sessionId)}${query}`, {
        cache: 'no-store',
        timeoutMs: TERMINAL_REQUEST_TIMEOUT_MS
    });
}

async function writeTerminalApiInput(sessionId, data) {
    return fetchJson(`/api/codex/terminals/${encodeURIComponent(sessionId)}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: TERMINAL_INPUT_TIMEOUT_MS,
        body: JSON.stringify({
            data: typeof data === 'string' ? data : ''
        })
    });
}

async function resizeTerminalApiSession(sessionId, cols, rows) {
    return fetchJson(`/api/codex/terminals/${encodeURIComponent(sessionId)}/resize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: TERMINAL_REQUEST_TIMEOUT_MS,
        body: JSON.stringify({ cols, rows })
    });
}

async function closeTerminalApiSession(sessionId) {
    return fetchJson(`/api/codex/terminals/${encodeURIComponent(sessionId)}/close`, {
        method: 'POST',
        timeoutMs: TERMINAL_CLOSE_TIMEOUT_MS
    });
}

function findTerminalSessionByContext(root, path) {
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    return terminalState.sessions.find(session => (
        session.root === normalizedRoot
        && session.path === normalizedPath
    )) || null;
}

function closeTerminalEventStream({ clearSession = true, resetReconnect = true } = {}) {
    if (terminalState.streamSource) {
        terminalState.streamSource.onopen = null;
        terminalState.streamSource.onmessage = null;
        terminalState.streamSource.onerror = null;
        terminalState.streamSource.close();
        terminalState.streamSource = null;
    }
    terminalState.streamConnected = false;
    if (terminalState.streamReconnectTimer !== null) {
        window.clearTimeout(terminalState.streamReconnectTimer);
        terminalState.streamReconnectTimer = null;
    }
    if (resetReconnect) {
        terminalState.streamReconnectAttempt = 0;
    }
    if (clearSession) {
        terminalState.streamSessionId = null;
    }
}

function handleTerminalStreamSnapshot(sessionId, rawData) {
    let payload = null;
    try {
        payload = JSON.parse(typeof rawData === 'string' ? rawData : '{}');
    } catch (error) {
        void error;
        return;
    }
    const updatedSession = upsertTerminalSession(payload);
    if (!updatedSession || updatedSession.id !== sessionId) return;
    if (terminalState.activeSessionId !== updatedSession.id) return;
    writeTerminalOutput(payload?.output || '', {
        reset: terminalState.mountedSessionId !== updatedSession.id || Boolean(payload?.reset)
    });
    terminalState.mountedSessionId = updatedSession.id;
    syncTerminalOverlayState();
}

function handleTerminalStreamEnd(sessionId, rawData) {
    let payload = null;
    try {
        payload = JSON.parse(typeof rawData === 'string' ? rawData : '{}');
    } catch (error) {
        void error;
    }
    if (payload?.error_code === 'session_not_found' || payload?.closed) {
        removeTerminalSessionFromState(sessionId);
    } else if (payload && typeof payload === 'object') {
        upsertTerminalSession(payload);
    }
    closeTerminalEventStream({
        clearSession: true,
        resetReconnect: true
    });
    syncTerminalOverlayState();
}

function scheduleTerminalStreamReconnect(sessionId) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return;
    if (!isTerminalOverlayOpen() || terminalState.activeSessionId !== targetId) return;
    if (terminalState.streamReconnectTimer !== null) return;
    const activeSession = getTerminalSessionById(targetId);
    if (!activeSession?.processRunning) return;
    const delay = Math.min(
        TERMINAL_STREAM_RECONNECT_MAX_MS,
        TERMINAL_STREAM_RECONNECT_BASE_MS * (2 ** Math.min(terminalState.streamReconnectAttempt, 4))
    );
    terminalState.streamReconnectAttempt += 1;
    terminalState.streamReconnectTimer = window.setTimeout(() => {
        terminalState.streamReconnectTimer = null;
        const currentSession = getTerminalSessionById(targetId);
        if (!currentSession?.processRunning || !isTerminalOverlayOpen() || terminalState.activeSessionId !== targetId) {
            syncTerminalOverlayState();
            return;
        }
        connectTerminalEventStream(targetId, currentSession.outputLength);
    }, delay);
    syncTerminalOverlayState();
}

function connectTerminalEventStream(sessionId, offset = null) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId || !isTerminalOverlayOpen()) {
        closeTerminalEventStream();
        return false;
    }
    if (typeof window.EventSource !== 'function') {
        scheduleTerminalPoll(Math.min(TERMINAL_POLL_MS, 240));
        syncTerminalOverlayState();
        return false;
    }
    stopTerminalPolling();
    closeTerminalEventStream({
        clearSession: false,
        resetReconnect: false
    });
    terminalState.streamSessionId = targetId;
    terminalState.streamConnected = false;
    const activeSession = getTerminalSessionById(targetId);
    const startOffset = Number.isFinite(offset)
        ? Math.max(0, Math.round(offset))
        : Math.max(0, Math.round(activeSession?.outputLength || 0));
    const streamUrl = `/api/codex/terminals/${encodeURIComponent(targetId)}/events?offset=${encodeURIComponent(String(startOffset))}`;
    const source = new EventSource(streamUrl);
    terminalState.streamSource = source;
    source.onopen = () => {
        if (terminalState.streamSource !== source) return;
        terminalState.streamConnected = true;
        terminalState.streamReconnectAttempt = 0;
        syncTerminalOverlayState();
    };
    source.onmessage = event => {
        if (terminalState.streamSource !== source) return;
        terminalState.streamConnected = true;
        handleTerminalStreamSnapshot(targetId, event.data);
    };
    source.addEventListener('ping', () => {
        if (terminalState.streamSource !== source) return;
        terminalState.streamConnected = true;
        syncTerminalOverlayState();
    });
    source.addEventListener('end', event => {
        if (terminalState.streamSource !== source) return;
        handleTerminalStreamEnd(targetId, event.data);
    });
    source.onerror = () => {
        if (terminalState.streamSource !== source) return;
        source.close();
        terminalState.streamSource = null;
        terminalState.streamConnected = false;
        syncTerminalOverlayState();
        scheduleTerminalStreamReconnect(targetId);
    };
    syncTerminalOverlayState();
    return true;
}

async function loadTerminalSessions({ preserveActive = true, preferSessionId = '', attachActive = false } = {}) {
    const payload = await fetchTerminalSessionsList();
    const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
    const previousActiveId = terminalState.activeSessionId;
    setTerminalSessions(sessions, { preserveActive, preferSessionId });
    syncTerminalOverlayState();
    const nextActiveId = terminalState.activeSessionId;
    if (attachActive && nextActiveId) {
        const forceReset = previousActiveId !== nextActiveId || terminalState.mountedSessionId !== nextActiveId;
        await attachActiveTerminalSession({ forceReset });
    }
    return terminalState.sessions;
}

function openTerminalOverlay() {
    const elements = getTerminalOverlayElements();
    if (!elements) return;
    if (!terminalState.launchContext) {
        terminalState.launchContext = normalizeTerminalLaunchContext(resolveDefaultTerminalLaunchContext());
    }
    terminalState.overlayOpen = true;
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    syncTerminalOverlayState();
    requestAnimationFrame(() => {
        syncTerminalExtraKeysState();
        scheduleTerminalViewportRefresh({ fit: true });
    });
}

function closeTerminalOverlay() {
    const elements = getTerminalOverlayElements();
    if (!elements) return;
    terminalState.overlayOpen = false;
    stopTerminalPolling();
    closeTerminalEventStream({
        clearSession: true,
        resetReconnect: true
    });
    clearQueuedTerminalInput();
    cancelTerminalViewportRefresh();
    clearTerminalExtraKeyModifiers();
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    if (
        !isGitBranchOverlayOpen()
        && !isGitSyncOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isUsageHistoryOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
    syncTerminalExtraKeysState();
}

function stopTerminalPolling() {
    if (terminalState.pollTimer !== null) {
        window.clearTimeout(terminalState.pollTimer);
        terminalState.pollTimer = null;
    }
    terminalState.pollInFlight = false;
}

function scheduleTerminalPoll(delayMs = TERMINAL_POLL_MS) {
    if (!isTerminalOverlayOpen()) return;
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    if (!activeSession) return;
    if (terminalState.pollTimer !== null) {
        window.clearTimeout(terminalState.pollTimer);
    }
    terminalState.pollTimer = window.setTimeout(() => {
        terminalState.pollTimer = null;
        void pollActiveTerminalSession();
    }, Math.max(0, Math.round(Number(delayMs) || 0)));
}

function writeTerminalOutput(output, { reset = false } = {}) {
    const terminal = terminalState.terminal;
    if (!terminal) return;
    if (reset) {
        terminal.reset();
        syncTerminalTheme();
    }
    if (typeof output === 'string' && output) {
        terminal.write(output);
    }
}

async function attachActiveTerminalSession({ forceReset = false } = {}) {
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    if (!activeSession) {
        closeTerminalEventStream({
            clearSession: true,
            resetReconnect: true
        });
        stopTerminalPolling();
        syncTerminalOverlayState();
        return false;
    }
    closeTerminalEventStream({
        clearSession: true,
        resetReconnect: true
    });
    stopTerminalPolling();
    await ensureTerminalInstance();
    const needsReset = Boolean(forceReset || terminalState.mountedSessionId !== activeSession.id);
    const offset = needsReset ? null : activeSession.outputLength;
    const response = await readTerminalApiSession(activeSession.id, offset);
    if (terminalState.activeSessionId !== activeSession.id) {
        return false;
    }
    const updatedSession = upsertTerminalSession(response) || activeSession;
    writeTerminalOutput(response?.output || '', {
        reset: needsReset || Boolean(response?.reset)
    });
    terminalState.mountedSessionId = updatedSession.id;
    syncTerminalOverlayState();
    scheduleTerminalViewportRefresh({ focus: true, fit: true });
    if (response?.process_running) {
        connectTerminalEventStream(updatedSession.id, updatedSession.outputLength);
    } else {
        closeTerminalEventStream({
            clearSession: true,
            resetReconnect: true
        });
    }
    return true;
}

async function pollActiveTerminalSession() {
    if (terminalState.pollInFlight || !isTerminalOverlayOpen()) return;
    const activeSession = getTerminalSessionById(terminalState.activeSessionId);
    if (!activeSession) return;
    terminalState.pollInFlight = true;
    try {
        const response = await readTerminalApiSession(
            activeSession.id,
            terminalState.mountedSessionId === activeSession.id ? activeSession.outputLength : null
        );
        if (terminalState.activeSessionId !== activeSession.id) {
            return;
        }
        const updatedSession = upsertTerminalSession(response) || activeSession;
        writeTerminalOutput(response?.output || '', {
            reset: terminalState.mountedSessionId !== updatedSession.id || Boolean(response?.reset)
        });
        terminalState.mountedSessionId = updatedSession.id;
        syncTerminalOverlayState();
        if (response?.process_running || response?.output) {
            scheduleTerminalPoll();
        } else {
            stopTerminalPolling();
        }
    } catch (error) {
        const elements = getTerminalOverlayElements();
        if (elements?.status) {
            elements.status.textContent = `연결 재시도 중 · ${normalizeError(error, 'Terminal 상태를 불러오지 못했습니다.')}`;
        }
        scheduleTerminalPoll(TERMINAL_POLL_MS * 2);
    } finally {
        terminalState.pollInFlight = false;
    }
}

async function setActiveTerminalSession(sessionId, { attach = true, forceReset = false } = {}) {
    const targetId = typeof sessionId === 'string' ? sessionId.trim() : '';
    if (!targetId) return false;
    if (!getTerminalSessionById(targetId)) return false;
    if (terminalState.activeSessionId !== targetId) {
        clearQueuedTerminalInput();
    }
    terminalState.activeSessionId = targetId;
    syncTerminalOverlayState();
    if (attach && isTerminalOverlayOpen()) {
        await attachActiveTerminalSession({ forceReset });
    }
    return true;
}

function resolveDefaultTerminalLaunchContext() {
    const activeTerminalSession = getTerminalSessionById(terminalState.activeSessionId);
    if (activeTerminalSession) {
        return {
            root: activeTerminalSession.root,
            path: activeTerminalSession.path
        };
    }
    if (isFileBrowserOverlayOpen()) {
        return {
            root: fileBrowserRoot,
            path: fileBrowserPath
        };
    }
    if (isWorkModeEnabled()) {
        return {
            root: workModeFileRoot,
            path: workModeFilePath
        };
    }
    return {
        root: FILE_BROWSER_ROOT_WORKSPACE,
        path: ''
    };
}

async function openNewTerminalTab(context = null) {
    const requestedContext = normalizeTerminalLaunchContext(
        context
        || terminalState.launchContext
        || resolveDefaultTerminalLaunchContext()
    );
    const root = normalizeFileBrowserRoot(requestedContext?.root);
    const path = normalizeFileBrowserRelativePath(requestedContext?.path);
    setTerminalLaunchContext(requestedContext);
    openTerminalOverlay();
    syncTerminalOverlayState();
    const elements = getTerminalOverlayElements();
    if (elements?.status) {
        elements.status.textContent = '새 Terminal 세션을 여는 중...';
    }
    try {
        await ensureTerminalInstance();
        if (terminalState.fitAddon) {
            try {
                terminalState.fitAddon.fit();
            } catch (error) {
                void error;
            }
        }
        const viewport = getTerminalViewportSize();
        const response = await createTerminalApiSession(root, path, viewport.cols, viewport.rows);
        const createdSession = upsertTerminalSession(response);
        syncTerminalOverlayState();
        if (!createdSession) {
            throw new Error('Terminal session creation failed.');
        }
        await setActiveTerminalSession(createdSession.id, {
            attach: true,
            forceReset: true
        });
        showToast(`Terminal 탭을 열었습니다: ${createdSession.displayPath}`, {
            tone: 'success',
            durationMs: 2400
        });
        return createdSession;
    } catch (error) {
        if (elements?.status) {
            elements.status.textContent = `Terminal 열기 실패 · ${normalizeError(error, 'Terminal 초기화에 실패했습니다.')}`;
        }
        throw error;
    }
}

async function openTerminalOverlayFromContext(context = null) {
    const requestedContext = normalizeTerminalLaunchContext(
        context || resolveDefaultTerminalLaunchContext()
    );
    setTerminalLaunchContext(requestedContext);
    openTerminalOverlay();
    await loadTerminalSessions({
        preserveActive: true,
        attachActive: false
    }).catch(() => []);
    const matchingSession = findTerminalSessionByContext(requestedContext?.root, requestedContext?.path);
    if (matchingSession) {
        await setActiveTerminalSession(matchingSession.id, {
            attach: true,
            forceReset: terminalState.mountedSessionId !== matchingSession.id
        });
        return matchingSession;
    }
    if (terminalState.activeSessionId) {
        const activeSession = getTerminalSessionById(terminalState.activeSessionId);
        if (activeSession) {
            await setActiveTerminalSession(activeSession.id, {
                attach: true,
                forceReset: terminalState.mountedSessionId !== activeSession.id
            });
            return activeSession;
        }
    }
    syncTerminalOverlayState();
    return null;
}

async function closeTerminalTab(sessionId = '') {
    const targetId = typeof sessionId === 'string' && sessionId.trim()
        ? sessionId.trim()
        : (typeof terminalState.activeSessionId === 'string' ? terminalState.activeSessionId.trim() : '');
    const targetSession = getTerminalSessionById(targetId);
    if (!targetSession) return false;
    const confirmMessage = targetSession.processRunning
        ? `현재 Terminal을 종료할까요?\n실행 중인 프로세스도 함께 종료됩니다.\n\n${targetSession.displayPath}`
        : `현재 Terminal 탭을 닫을까요?\n\n${targetSession.displayPath}`;
    if (!window.confirm(confirmMessage)) {
        return false;
    }
    stopTerminalPolling();
    closeTerminalEventStream({
        clearSession: true,
        resetReconnect: true
    });
    clearQueuedTerminalInput();
    await closeTerminalApiSession(targetId);
    removeTerminalSessionFromState(targetId);
    syncTerminalOverlayState();
    if (!terminalState.sessions.length) {
        if (terminalState.terminal) {
            terminalState.terminal.reset();
            syncTerminalTheme();
        }
        showToast('Terminal 탭을 종료했습니다.', {
            tone: 'default',
            durationMs: 2200
        });
        return true;
    }
    const nextActiveSession = getTerminalSessionById(terminalState.activeSessionId) || terminalState.sessions[0];
    if (nextActiveSession) {
        await setActiveTerminalSession(nextActiveSession.id, {
            attach: true,
            forceReset: terminalState.mountedSessionId !== nextActiveSession.id
        });
    }
    showToast('Terminal 탭을 종료했습니다.', {
        tone: 'default',
        durationMs: 2200
    });
    return true;
}

function getGitErrorPayload(error) {
    if (!error || typeof error !== 'object') return null;
    const payload = error.payload;
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
    return payload;
}

function isRequestTimeoutError(error) {
    if (error && typeof error === 'object' && error.isTimeout === true) {
        return true;
    }
    const message = normalizeError(error, '').toLowerCase();
    return message.includes('요청 시간이 초과');
}

function normalizeGitActionError(error, fallback) {
    const payload = getGitErrorPayload(error);
    const base = normalizeError(error, fallback);
    if (!payload || payload.error_code !== 'git_mutation_in_flight') {
        return base;
    }
    if (base.includes('초 경과')) {
        return base;
    }
    const activeAction = typeof payload.active_action === 'string' ? payload.active_action.trim() : '';
    const elapsed = Number.isFinite(payload.active_elapsed_seconds)
        ? Math.max(0, payload.active_elapsed_seconds)
        : null;
    if (activeAction && elapsed != null) {
        return `${base} (서버: ${activeAction} ${elapsed}초 경과)`;
    }
    if (activeAction) {
        return `${base} (서버: ${activeAction} 실행 중)`;
    }
    if (elapsed != null) {
        return `${base} (서버: git 작업 ${elapsed}초 경과)`;
    }
    return base;
}

async function requestGitCancel(repoTarget) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    try {
        const result = await fetchJson('/api/codex/git/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_CANCEL_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                repo_target: target
            })
        });
        return { ok: true, result };
    } catch (error) {
        return { ok: false, error };
    }
}

function buildGitCancelNotice(outcome) {
    if (!outcome) return '';
    if (outcome.ok) {
        const data = outcome.result;
        if (!data || typeof data !== 'object') {
            return '서버 취소 요청을 전송했습니다.';
        }
        if (data.cancel_requested) {
            const actionName = typeof data.cancelled_action === 'string' && data.cancelled_action.trim()
                ? data.cancelled_action.trim()
                : 'git';
            const elapsed = Number.isFinite(data.active_elapsed_seconds)
                ? Math.max(0, data.active_elapsed_seconds)
                : null;
            return elapsed != null
                ? `서버 취소 요청 완료 (${actionName}, ${elapsed}초 경과)`
                : `서버 취소 요청 완료 (${actionName})`;
        }
        return '서버에서 취소할 실행 중 작업이 없습니다.';
    }
    const cancelError = normalizeError(outcome.error, '서버 취소 요청에 실패했습니다.');
    return `서버 취소 요청 실패: ${cancelError}`;
}

async function requestGitCancelAfterTimeout(error, repoTarget) {
    if (!isRequestTimeoutError(error)) {
        return '';
    }
    const outcome = await requestGitCancel(repoTarget);
    return buildGitCancelNotice(outcome);
}

function setGitButtonBusy(button, busy, busyLabel) {
    if (!button) return;
    const isIconOnly = button.classList.contains('icon-only');
    if (!button.dataset.label) {
        button.dataset.label = button.textContent.trim();
    }
    if (!button.dataset.defaultAriaLabel) {
        button.dataset.defaultAriaLabel = button.getAttribute('aria-label') || '';
    }
    if (!button.dataset.defaultTitle) {
        button.dataset.defaultTitle = button.getAttribute('title') || '';
    }
    if (busy) {
        button.classList.add('is-loading');
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        if (busyLabel) {
            button.setAttribute('aria-label', busyLabel);
            button.setAttribute('title', busyLabel);
            if (!isIconOnly) {
                button.textContent = busyLabel;
            }
        }
        syncHoverTooltipFromLabel(button, busyLabel || '');
        return;
    }
    button.classList.remove('is-loading');
    button.disabled = false;
    button.setAttribute('aria-busy', 'false');
    if (button.dataset.defaultAriaLabel) {
        button.setAttribute('aria-label', button.dataset.defaultAriaLabel);
    }
    if (button.dataset.defaultTitle) {
        button.setAttribute('title', button.dataset.defaultTitle);
    }
    if (!isIconOnly) {
        button.textContent = button.dataset.label || button.textContent;
    }
    syncHoverTooltipFromLabel(button);
}

function isRecoverableActionButtonBusy(button) {
    if (!button) return false;
    return button.disabled
        || button.classList.contains('is-loading')
        || button.getAttribute('aria-busy') === 'true';
}

function getRecoverableGitActionButtons() {
    const selectors = [
        '#codex-git-commit',
        '#codex-git-push',
        '#codex-git-sync',
        '#codex-file-browser-open',
        '#codex-branch-overlay-commit',
        '#codex-branch-overlay-push',
        '#codex-sync-overlay-fetch',
        '#codex-sync-overlay-sync',
        '#codex-sync-overlay-commit',
        '#codex-sync-overlay-push',
        '#codex-sync-overlay-refresh'
    ];
    const seen = new Set();
    const buttons = [];
    selectors.forEach(selector => {
        const button = document.querySelector(selector);
        if (!button || seen.has(button)) return;
        seen.add(button);
        buttons.push(button);
    });
    return buttons;
}

function recoverGitActionButtons() {
    let recoveredCount = 0;
    getRecoverableGitActionButtons().forEach(button => {
        if (!isRecoverableActionButtonBusy(button)) return;
        setGitButtonBusy(button, false);
        recoveredCount += 1;
    });
    recoverGitPushButtonsIfIdle();
    return recoveredCount;
}

function isTransientBusySessionStatus(message) {
    if (typeof message !== 'string') return false;
    return message.startsWith('Waiting for Codex')
        || message.startsWith('Receiving response')
        || message.startsWith('Reconnecting to Codex')
        || message.startsWith('Connection lost. Retrying')
        || message.startsWith('Stream completed. Reloading')
        || message.startsWith('Stopping');
}

function recoverStaleSessionBusyStates(now = Date.now()) {
    let recoveredCount = 0;
    Object.entries(state.sessionStates).forEach(([sessionId, sessionState]) => {
        if (!sessionState || typeof sessionState !== 'object') return;
        let changed = false;

        if (sessionState.streamId && !state.streams[sessionState.streamId]) {
            sessionState.streamId = null;
            changed = true;
        }

        const pendingSend = sessionState.pendingSend;
        const pendingStartedAt = Number(pendingSend?.startedAt);
        const pendingAgeMs = Number.isFinite(pendingStartedAt) ? now - pendingStartedAt : null;
        if (pendingSend && pendingAgeMs != null && pendingAgeMs >= SESSION_PENDING_STALE_MS) {
            try {
                pendingSend.controller?.abort();
            } catch (error) {
                void error;
            }
            sessionState.pendingSend = null;
            changed = true;
        }

        const hasLocalStream = Boolean(getSessionStream(sessionId));
        const hasRemoteStream = Boolean(state.remoteStreamSessions?.has(sessionId));
        const hasPendingSend = Boolean(sessionState.pendingSend);
        if (sessionState.sending && !hasLocalStream && !hasRemoteStream && !hasPendingSend) {
            sessionState.sending = false;
            changed = true;
        }

        if (!hasLocalStream && !hasRemoteStream && !hasPendingSend && isTransientBusySessionStatus(sessionState.status)) {
            sessionState.status = 'Idle';
            sessionState.statusIsError = false;
            sessionState.responseStartedAt = null;
            sessionState.responseStatus = null;
            changed = true;
        }

        if (changed) {
            recoveredCount += 1;
        }
    });
    return recoveredCount;
}

function recoverClientUiState({ clearSessionLoadingLock = false, source = 'manual' } = {}) {
    const recovered = [];
    if (clearSessionLoadingLock && state.loading) {
        const isStaleLoadLock = sessionLoadLockStartedAt > 0
            && Date.now() - sessionLoadLockStartedAt >= REFRESH_BUTTON_STALE_MS;
        if (isStaleLoadLock) {
            state.loading = false;
            sessionLoadLockStartedAt = 0;
            recovered.push('session loading lock');
        }
    }
    if (gitMutationInFlight) {
        gitMutationInFlight = false;
        recovered.push('git mutation lock');
    }

    const recoveredButtons = recoverGitActionButtons();
    if (recoveredButtons > 0) {
        recovered.push(`git action buttons (${recoveredButtons})`);
    }

    const recoveredSessions = recoverStaleSessionBusyStates();
    if (recoveredSessions > 0) {
        recovered.push(`session busy states (${recoveredSessions})`);
        renderSessions();
    }

    syncActiveSessionControls();
    syncActiveSessionStatus();

    if (recovered.length > 0) {
        console.info(`[codex-ui] recovered stale state (${source}): ${recovered.join(', ')}`);
    }
    return recovered;
}

function summarizeGitOutput(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const firstLine = text.split(/\r?\n/)[0].trim();
    if (!firstLine) return '';
    if (firstLine.length > 120) {
        return `${firstLine.slice(0, 117)}...`;
    }
    return firstLine;
}

function getGitBranchFullName(element) {
    if (!element) return '';
    const dataName = element.dataset?.branchFull;
    if (dataName && dataName.trim()) return dataName.trim();
    return element.textContent ? element.textContent.trim() : '';
}

function getGitChangedFilesCountFromStatus(status) {
    if (!status || typeof status !== 'object') return 0;
    const normalizedCount = normalizeGitChangedFilesCount(status.count);
    if (Number.isFinite(normalizedCount)) {
        return normalizedCount;
    }
    return normalizeGitChangedFiles(status.changedFiles).length;
}

function updateGitCommitButtonState(status) {
    const hasChanges = getGitChangedFilesCountFromStatus(status) > 0;
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        status?.windowsInvalidCount,
        normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles).length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        status?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    const canCommit = hasChanges && !hasWindowsPathIssues;
    document.querySelectorAll('.git-action-commit').forEach(button => {
        if (button.id === 'codex-sync-overlay-commit') return;
        button.classList.toggle('is-ready', canCommit);
    });
}

function getGitAheadCountFromStatus(status) {
    if (!status || typeof status !== 'object') return null;
    return normalizeGitDivergenceCount(status.aheadCount);
}

function updateGitPushButtonState(status) {
    const aheadCount = getGitAheadCountFromStatus(status);
    const hasPendingPush = Number.isFinite(aheadCount) && aheadCount > 0;
    document.querySelectorAll('.git-action-push').forEach(button => {
        if (button.id === 'codex-sync-overlay-push') return;
        button.classList.toggle('is-ready', hasPendingPush);
    });
}

function applyGitBranchStatusToElement(element, status) {
    if (!element || !status) return;
    const branchName = typeof status.branch === 'string' ? status.branch.trim() : '';
    if (!branchName) return;
    if (element.textContent.trim() !== branchName) {
        element.textContent = branchName;
    }
    element.dataset.branchFull = branchName;
    syncHoverTooltipFromLabel(element, branchName);
}

function getGitBranchOverlayElements() {
    const overlay = document.getElementById('codex-branch-overlay');
    if (!overlay) return null;
    return {
        overlay,
        subtitle: document.getElementById('codex-branch-overlay-subtitle'),
        meta: document.getElementById('codex-branch-overlay-meta'),
        latestCommit: document.getElementById('codex-branch-overlay-last-commit'),
        selection: document.getElementById('codex-branch-overlay-selection'),
        stageAllBtn: document.getElementById('codex-branch-overlay-stage-all'),
        stageNoneBtn: document.getElementById('codex-branch-overlay-stage-none'),
        commitMessage: document.getElementById('codex-branch-overlay-commit-message'),
        commitBtn: document.getElementById('codex-branch-overlay-commit'),
        pushBtn: document.getElementById('codex-branch-overlay-push'),
        loading: document.getElementById('codex-branch-overlay-loading'),
        empty: document.getElementById('codex-branch-overlay-empty'),
        list: document.getElementById('codex-branch-overlay-list')
    };
}

function setGitBranchOverlayLoading(isLoading) {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    if (elements.loading) {
        elements.loading.classList.toggle('is-hidden', !isLoading);
    }
    if (elements.list) {
        elements.list.classList.toggle('is-hidden', isLoading);
    }
    if (elements.empty) {
        elements.empty.classList.add('is-hidden');
    }
    if (elements.latestCommit) {
        elements.latestCommit.textContent = isLoading
            ? '커밋 예정 메시지: 계산 중...'
            : elements.latestCommit.textContent;
    }
    if (elements.commitBtn) {
        elements.commitBtn.disabled = Boolean(isLoading);
    }
    if (elements.stageAllBtn) {
        elements.stageAllBtn.disabled = Boolean(isLoading);
    }
    if (elements.stageNoneBtn) {
        elements.stageNoneBtn.disabled = Boolean(isLoading);
    }
    if (elements.selection) {
        elements.selection.textContent = isLoading ? '선택 -' : elements.selection.textContent;
    }
}

function normalizeGitChangedFiles(files) {
    if (!Array.isArray(files)) return [];
    const normalized = [];
    const seenPaths = new Set();
    files.forEach(file => {
        if (!file) return;
        const rawPath = typeof file === 'string'
            ? file.trim()
            : (typeof file.path === 'string' ? file.path.trim() : '');
        if (!rawPath) return;
        const path = rawPath.replace(/\\/g, '/').replace(/^\.\//, '');
        if (!path || seenPaths.has(path)) return;
        seenPaths.add(path);
        const rawStatus = typeof file === 'string'
            ? ''
            : (typeof file.status === 'string' ? file.status.trim() : '');
        normalized.push({
            path,
            status: rawStatus.toUpperCase()
        });
    });
    return normalized;
}

function compareGitPathValues(left, right) {
    return String(left || '').localeCompare(String(right || ''), undefined, {
        numeric: true,
        sensitivity: 'base'
    });
}

function createGitChangedFolderNode(name = '', fullPath = '') {
    return {
        name,
        fullPath,
        folderMap: new Map(),
        childFolders: [],
        childFiles: [],
        fileCount: 0,
        folderCount: 0,
        filePaths: [],
        statusCounts: {}
    };
}

function buildGitChangedFileTree(files) {
    const root = createGitChangedFolderNode('', '');
    const normalizedFiles = normalizeGitChangedFiles(files);
    normalizedFiles.forEach(file => {
        const segments = file.path.split('/').filter(Boolean);
        if (!segments.length) return;
        const fileName = segments[segments.length - 1];
        if (!fileName) return;
        let cursor = root;
        let folderPath = '';
        segments.slice(0, -1).forEach(segment => {
            folderPath = folderPath ? `${folderPath}/${segment}` : segment;
            let folderNode = cursor.folderMap.get(segment);
            if (!folderNode) {
                folderNode = createGitChangedFolderNode(segment, folderPath);
                cursor.folderMap.set(segment, folderNode);
            }
            cursor = folderNode;
        });
        cursor.childFiles.push({
            name: fileName,
            path: file.path,
            status: file.status
        });
    });

    const finalizeFolder = folder => {
        const childFolders = Array.from(folder.folderMap.values())
            .sort((a, b) => compareGitPathValues(a.name, b.name))
            .map(child => finalizeFolder(child));
        const childFiles = folder.childFiles
            .slice()
            .sort((a, b) => compareGitPathValues(a.path, b.path));

        const statusCounts = {};
        const filePaths = [];
        childFiles.forEach(file => {
            filePaths.push(file.path);
            if (!file.status) return;
            statusCounts[file.status] = (statusCounts[file.status] || 0) + 1;
        });
        childFolders.forEach(childFolder => {
            filePaths.push(...childFolder.filePaths);
            Object.entries(childFolder.statusCounts || {}).forEach(([status, count]) => {
                if (!status || !Number.isFinite(count)) return;
                statusCounts[status] = (statusCounts[status] || 0) + count;
            });
        });

        return {
            name: folder.name,
            fullPath: folder.fullPath,
            childFolders,
            childFiles,
            fileCount: filePaths.length,
            folderCount: childFolders.length + childFolders.reduce((sum, child) => sum + child.folderCount, 0),
            filePaths,
            statusCounts
        };
    };

    return finalizeFolder(root);
}

function flattenGitChangedFileTree(tree, collapsedFolders = new Set()) {
    const rows = [];
    const collapsedSet = collapsedFolders instanceof Set ? collapsedFolders : new Set();
    const walkFolder = (folder, depth) => {
        rows.push({
            type: 'folder',
            depth,
            folder
        });
        if (collapsedSet.has(folder.fullPath)) {
            return;
        }
        folder.childFolders.forEach(childFolder => {
            walkFolder(childFolder, depth + 1);
        });
        folder.childFiles.forEach(file => {
            rows.push({
                type: 'file',
                depth: depth + 1,
                file
            });
        });
    };
    const safeTree = tree && typeof tree === 'object'
        ? tree
        : createGitChangedFolderNode('', '');
    safeTree.childFolders.forEach(folder => {
        walkFolder(folder, 0);
    });
    safeTree.childFiles.forEach(file => {
        rows.push({
            type: 'file',
            depth: 0,
            file
        });
    });
    return rows;
}

function getGitFolderSelectionState(folder, selectedFiles) {
    const allPaths = Array.isArray(folder?.filePaths) ? folder.filePaths : [];
    const total = allPaths.length;
    if (total <= 0) {
        return {
            total,
            selected: 0,
            checked: false,
            indeterminate: false
        };
    }
    let selected = 0;
    allPaths.forEach(path => {
        if (selectedFiles.has(path)) {
            selected += 1;
        }
    });
    return {
        total,
        selected,
        checked: selected === total,
        indeterminate: selected > 0 && selected < total
    };
}

function getGitFolderStatusEntries(statusCounts) {
    const statusOrder = ['M', 'A', 'D', 'U', 'R', 'C', 'T'];
    const entries = Object.entries(statusCounts || {}).filter(([status, count]) => {
        return Boolean(status) && Number.isFinite(count) && count > 0;
    });
    entries.sort((left, right) => {
        const leftIndex = statusOrder.indexOf(String(left[0] || '').toUpperCase());
        const rightIndex = statusOrder.indexOf(String(right[0] || '').toUpperCase());
        if (leftIndex !== rightIndex) {
            if (leftIndex === -1) return 1;
            if (rightIndex === -1) return -1;
            return leftIndex - rightIndex;
        }
        return compareGitPathValues(left[0], right[0]);
    });
    return entries;
}

function createGitStatusBadgeNode(status, text = '') {
    const badge = document.createElement('span');
    badge.className = `branch-overlay-status ${getGitStatusBadgeClass(status)}`.trim();
    badge.textContent = text || String(status || '').toUpperCase();
    return badge;
}

function renderGitChangedFileTreeList(options = {}) {
    const listElement = options.listElement;
    if (!listElement) {
        return {
            fileCount: 0,
            folderCount: 0
        };
    }
    const collapsedFolders = options.collapsedFolders instanceof Set ? options.collapsedFolders : new Set();
    const selectable = Boolean(options.selectable);
    const selectedFiles = options.selectedFiles instanceof Set ? options.selectedFiles : new Set();
    const onFileSelectionChange = typeof options.onFileSelectionChange === 'function'
        ? options.onFileSelectionChange
        : null;
    const onFolderSelectionChange = typeof options.onFolderSelectionChange === 'function'
        ? options.onFolderSelectionChange
        : null;
    const onFolderCollapseToggle = typeof options.onFolderCollapseToggle === 'function'
        ? options.onFolderCollapseToggle
        : null;

    const tree = buildGitChangedFileTree(options.files);
    const rows = flattenGitChangedFileTree(tree, collapsedFolders);
    listElement.innerHTML = '';

    rows.forEach(row => {
        const item = document.createElement('li');
        item.className = 'git-file-tree-item';
        const rowNode = document.createElement('div');
        rowNode.className = `git-file-tree-row is-${row.type}`;
        rowNode.style.setProperty('--git-tree-depth', String(Math.max(0, Number(row.depth) || 0)));

        if (row.type === 'folder') {
            const folder = row.folder;
            const folderPath = String(folder?.fullPath || '');
            const isCollapsed = collapsedFolders.has(folderPath);
            const toggle = document.createElement('button');
            toggle.type = 'button';
            toggle.className = 'git-file-tree-toggle';
            toggle.textContent = isCollapsed ? '>' : 'v';
            toggle.setAttribute('aria-label', isCollapsed ? '폴더 펼치기' : '폴더 접기');
            toggle.addEventListener('click', event => {
                event.preventDefault();
                if (onFolderCollapseToggle) {
                    onFolderCollapseToggle(folderPath, !isCollapsed);
                }
            });
            rowNode.appendChild(toggle);

            if (selectable) {
                const selection = getGitFolderSelectionState(folder, selectedFiles);
                const folderCheck = document.createElement('input');
                folderCheck.type = 'checkbox';
                folderCheck.className = 'branch-overlay-folder-check';
                folderCheck.checked = selection.checked;
                folderCheck.indeterminate = selection.indeterminate;
                folderCheck.disabled = selection.total <= 0;
                folderCheck.addEventListener('change', () => {
                    if (onFolderSelectionChange) {
                        onFolderSelectionChange(folder, folderCheck.checked);
                    }
                });
                rowNode.appendChild(folderCheck);
            }

            const name = document.createElement('span');
            name.className = 'git-file-tree-folder-name';
            name.textContent = folder?.name || folderPath || '(root)';
            if (folderPath) {
                name.title = folderPath;
            }
            rowNode.appendChild(name);

            const meta = document.createElement('span');
            meta.className = 'git-file-tree-folder-meta';
            meta.textContent = `${Number(folder?.fileCount) || 0} files`;
            rowNode.appendChild(meta);

            const statusWrap = document.createElement('span');
            statusWrap.className = 'git-file-tree-folder-statuses';
            getGitFolderStatusEntries(folder?.statusCounts).forEach(([status, count]) => {
                statusWrap.appendChild(createGitStatusBadgeNode(status, `${status}${count}`));
            });
            if (statusWrap.childElementCount > 0) {
                rowNode.appendChild(statusWrap);
            }
        } else {
            const togglePlaceholder = document.createElement('span');
            togglePlaceholder.className = 'git-file-tree-toggle-placeholder';
            rowNode.appendChild(togglePlaceholder);

            const file = row.file;
            if (selectable) {
                const check = document.createElement('input');
                check.type = 'checkbox';
                check.className = 'branch-overlay-file-check';
                check.value = file.path;
                check.checked = selectedFiles.has(file.path);
                check.addEventListener('change', () => {
                    if (onFileSelectionChange) {
                        onFileSelectionChange(file.path, check.checked);
                    }
                });
                rowNode.appendChild(check);
            }
            if (file?.status) {
                rowNode.appendChild(createGitStatusBadgeNode(file.status));
            }
            const textWrap = document.createElement('span');
            textWrap.className = 'git-file-tree-file-text';

            const fileName = document.createElement('span');
            fileName.className = 'git-file-tree-file-name';
            fileName.textContent = file?.name || file?.path || '(unknown)';
            textWrap.appendChild(fileName);

            rowNode.appendChild(textWrap);
        }

        item.appendChild(rowNode);
        listElement.appendChild(item);
    });

    return {
        fileCount: Number(tree.fileCount) || 0,
        folderCount: Number(tree.folderCount) || 0
    };
}

function getGitStatusBadgeClass(status) {
    switch ((status || '').toUpperCase()) {
        case 'M':
            return 'is-modified';
        case 'A':
            return 'is-added';
        case 'D':
            return 'is-deleted';
        case 'U':
            return 'is-untracked';
        case 'R':
            return 'is-renamed';
        case 'C':
            return 'is-copied';
        case 'T':
            return 'is-typechange';
        default:
            return '';
    }
}

function syncGitOverlaySelection(files) {
    const normalizedFiles = Array.isArray(files) ? files : [];
    const validPaths = new Set(normalizedFiles.map(file => file.path));
    if (!gitOverlaySelectionTouched) {
        gitOverlaySelectedFiles = new Set(normalizedFiles.map(file => file.path));
        return;
    }
    const next = new Set();
    validPaths.forEach(path => {
        if (gitOverlaySelectedFiles.has(path)) {
            next.add(path);
        }
    });
    gitOverlaySelectedFiles = next;
}

function updateGitOverlaySelectionSummary(totalCount = 0, options = {}) {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    const selectedCount = gitOverlaySelectedFiles.size;
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        options?.windowsInvalidCount,
        normalizeGitWindowsInvalidFiles(options?.windowsInvalidFiles).length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        options?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    const windowsIssueText = hasWindowsPathIssues
        ? ` · 오류: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`
        : '';
    if (elements.selection) {
        elements.selection.textContent = `선택 ${selectedCount}개 / 전체 ${totalCount}개${windowsIssueText}`;
    }
    if (elements.commitBtn) {
        const isBusy = elements.commitBtn.classList.contains('is-loading')
            || elements.commitBtn.getAttribute('aria-busy') === 'true';
        const isDisabled = totalCount === 0 || selectedCount === 0 || hasWindowsPathIssues;
        elements.commitBtn.disabled = isBusy ? true : isDisabled;
        const label = hasWindowsPathIssues
            ? `Commit 불가: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`
            : 'Commit staged files';
        elements.commitBtn.dataset.label = label;
        syncHoverTooltipFromLabel(elements.commitBtn, label);
    }
    if (elements.stageAllBtn) {
        elements.stageAllBtn.disabled = totalCount === 0;
    }
    if (elements.stageNoneBtn) {
        elements.stageNoneBtn.disabled = totalCount === 0;
    }
}

function normalizeGitCommitPreviewPaths(paths) {
    if (!Array.isArray(paths)) return [];
    const normalized = [];
    const seen = new Set();
    paths.forEach(path => {
        const text = String(path || '').trim().replace(/\\/g, '/').replace(/^\.\//, '');
        if (!text || text.startsWith('/') || text.startsWith('../') || text.includes('/..')) {
            return;
        }
        if (seen.has(text)) return;
        seen.add(text);
        normalized.push(text);
    });
    normalized.sort(compareGitPathValues);
    return normalized;
}

function buildGitCommitPreviewCacheKey(repoTarget, paths) {
    const target = normalizeGitSyncRepoTarget(repoTarget || GIT_SYNC_TARGET_WORKSPACE);
    const normalizedPaths = normalizeGitCommitPreviewPaths(paths);
    if (!normalizedPaths.length) {
        return {
            key: '',
            target,
            paths: []
        };
    }
    return {
        key: `${target}::${normalizedPaths.join('\n')}`,
        target,
        paths: normalizedPaths
    };
}

function getGitCommitPreviewCacheEntry(cacheKey, { allowStale = false } = {}) {
    if (!cacheKey) return null;
    const cached = gitCommitPreviewCacheByKey.get(cacheKey);
    if (!cached || typeof cached !== 'object') return null;
    if (allowStale) return cached;
    const fetchedAt = Number(cached.fetchedAt);
    if (!Number.isFinite(fetchedAt)) return null;
    const age = Date.now() - fetchedAt;
    if (age < 0 || age > GIT_COMMIT_PREVIEW_CACHE_MS) return null;
    return cached;
}

function buildGitCommitPreviewFallbackSubject(pathCount = 0) {
    const count = Number.isFinite(Number(pathCount)) ? Math.max(0, Number(pathCount)) : 0;
    if (count <= 0) return '변경사항 반영';
    return `변경사항 ${count}건 반영`;
}

function normalizeGitCommitPreviewResult(result, fallbackCount = 0) {
    const subjectRaw = typeof result?.commit_message_subject === 'string'
        ? result.commit_message_subject
        : (typeof result?.commit_message === 'string' ? result.commit_message : '');
    const subject = subjectRaw.trim();
    const body = typeof result?.commit_message_body === 'string' ? result.commit_message_body.trim() : '';
    const comment = typeof result?.commit_comment === 'string' ? result.commit_comment.trim() : '';
    const analysisLines = Array.isArray(result?.commit_analysis_lines)
        ? result.commit_analysis_lines.map(line => String(line || '').trim()).filter(Boolean)
        : [];
    return {
        subject: subject || buildGitCommitPreviewFallbackSubject(fallbackCount),
        body,
        comment,
        analysisLines,
        error: ''
    };
}

function formatGitCommitPreviewLabel(previewEntry, fallbackCount = 0) {
    const subject = typeof previewEntry?.subject === 'string' ? previewEntry.subject.trim() : '';
    if (subject) {
        return `커밋 예정 메시지(자동): ${subject}`;
    }
    return `커밋 예정 메시지(자동): ${buildGitCommitPreviewFallbackSubject(fallbackCount)}`;
}

async function ensureGitCommitPreview(repoTarget, paths) {
    const request = buildGitCommitPreviewCacheKey(repoTarget, paths);
    if (!request.key) {
        return {
            key: '',
            entry: null
        };
    }
    const cached = getGitCommitPreviewCacheEntry(request.key);
    if (cached) {
        return {
            key: request.key,
            entry: cached
        };
    }
    const inFlight = gitCommitPreviewInFlightByKey.get(request.key);
    if (inFlight) {
        const pendingEntry = await inFlight;
        return {
            key: request.key,
            entry: pendingEntry
        };
    }

    let promise = null;
    promise = (async () => {
        try {
            const result = await fetchJson('/api/codex/git/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                timeoutMs: GIT_COMMIT_PREVIEW_REQUEST_TIMEOUT_MS,
                body: JSON.stringify({
                    repo_target: request.target,
                    files: request.paths
                })
            });
            const normalized = normalizeGitCommitPreviewResult(result, request.paths.length);
            const next = {
                ...normalized,
                fetchedAt: Date.now()
            };
            gitCommitPreviewCacheByKey.set(request.key, next);
            return next;
        } catch (error) {
            const fallbackSubject = buildGitCommitPreviewFallbackSubject(request.paths.length);
            const stale = getGitCommitPreviewCacheEntry(request.key, { allowStale: true });
            const next = {
                subject: stale?.subject || fallbackSubject,
                body: stale?.body || '',
                comment: stale?.comment || '',
                analysisLines: Array.isArray(stale?.analysisLines) ? stale.analysisLines : [],
                error: normalizeGitActionError(error, '커밋 예정 메시지 계산에 실패했습니다.'),
                fetchedAt: Date.now()
            };
            gitCommitPreviewCacheByKey.set(request.key, next);
            return next;
        } finally {
            if (gitCommitPreviewInFlightByKey.get(request.key) === promise) {
                gitCommitPreviewInFlightByKey.delete(request.key);
            }
        }
    })();
    gitCommitPreviewInFlightByKey.set(request.key, promise);

    const resolved = await promise;
    return {
        key: request.key,
        entry: resolved
    };
}

function getGitSelectedFilePathsInOrder(files) {
    const normalizedFiles = normalizeGitChangedFiles(files);
    const selectedPaths = [];
    const seen = new Set();
    normalizedFiles.forEach(file => {
        const path = typeof file?.path === 'string' ? file.path.trim() : '';
        if (!path || seen.has(path) || !gitOverlaySelectedFiles.has(path)) {
            return;
        }
        seen.add(path);
        selectedPaths.push(path);
    });
    gitOverlaySelectedFiles.forEach(path => {
        const text = String(path || '').trim();
        if (!text || seen.has(text)) return;
        seen.add(text);
        selectedPaths.push(text);
    });
    return selectedPaths;
}

function updateGitBranchOverlayCommitPreview(status) {
    const elements = getGitBranchOverlayElements();
    if (!elements?.latestCommit) return;
    const manualMessage = elements.commitMessage?.value?.trim() || '';
    if (manualMessage) {
        gitBranchOverlayPreviewKey = '';
        elements.latestCommit.textContent = `커밋 예정 메시지(수동): ${manualMessage}`;
        return;
    }
    const selectedPaths = getGitSelectedFilePathsInOrder(status?.changedFiles);
    if (!selectedPaths.length) {
        gitBranchOverlayPreviewKey = '';
        elements.latestCommit.textContent = '커밋 예정 메시지: 파일 선택 시 자동 생성됩니다.';
        return;
    }
    const request = buildGitCommitPreviewCacheKey(GIT_SYNC_TARGET_WORKSPACE, selectedPaths);
    gitBranchOverlayPreviewKey = request.key;
    const freshEntry = getGitCommitPreviewCacheEntry(request.key);
    if (freshEntry) {
        elements.latestCommit.textContent = formatGitCommitPreviewLabel(freshEntry, selectedPaths.length);
        return;
    }
    const staleEntry = getGitCommitPreviewCacheEntry(request.key, { allowStale: true });
    if (staleEntry) {
        elements.latestCommit.textContent = formatGitCommitPreviewLabel(staleEntry, selectedPaths.length);
    } else {
        elements.latestCommit.textContent = '커밋 예정 메시지: 계산 중...';
    }
    if (gitCommitPreviewInFlightByKey.has(request.key)) {
        return;
    }
    void ensureGitCommitPreview(GIT_SYNC_TARGET_WORKSPACE, selectedPaths).then(({ key, entry }) => {
        if (!entry) return;
        if (!isGitBranchOverlayOpen()) return;
        if (gitBranchOverlayPreviewKey !== key) return;
        const currentElements = getGitBranchOverlayElements();
        if (!currentElements?.latestCommit) return;
        currentElements.latestCommit.textContent = formatGitCommitPreviewLabel(entry, selectedPaths.length);
    });
}

function setGitOverlaySelectionState(selectAll) {
    const files = normalizeGitChangedFiles(gitBranchStatusCache.changedFiles);
    const selected = new Set();
    if (selectAll) {
        files.forEach(file => selected.add(file.path));
    }
    gitOverlaySelectedFiles = selected;
    gitOverlaySelectionTouched = true;
    if (isGitBranchOverlayOpen()) {
        renderGitBranchOverlay(gitBranchStatusCache);
        return;
    }
    updateGitOverlaySelectionSummary(files.length, {
        hasWindowsPathIssues: gitBranchStatusCache.hasWindowsPathIssues,
        windowsInvalidCount: gitBranchStatusCache.windowsInvalidCount,
        windowsInvalidFiles: gitBranchStatusCache.windowsInvalidFiles
    });
}

function renderGitBranchOverlay(status) {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    const branchElement = document.getElementById('codex-git-branch');
    const branchName = (status?.branch || getGitBranchFullName(branchElement) || '').trim();
    const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles);
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        status?.windowsInvalidCount,
        windowsInvalidFiles.length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        status?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    if (elements.subtitle) {
        elements.subtitle.textContent = branchName ? `브랜치: ${branchName}` : '브랜치 정보를 불러오는 중...';
    }
    const files = normalizeGitChangedFiles(status?.changedFiles);
    const count = Number.isFinite(status?.count) ? status.count : files.length;
    if (elements.meta) {
        const countText = Number.isFinite(count)
            ? `변경 파일 ${count}개`
            : '변경 파일 수를 불러올 수 없습니다.';
        const windowsIssueText = hasWindowsPathIssues
            ? ` · 오류: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`
            : '';
        elements.meta.textContent = `${countText}${windowsIssueText}`;
    }
    syncGitOverlaySelection(files);
    if (hasWindowsPathIssues) {
        gitBranchOverlayPreviewKey = '';
        if (elements.latestCommit) {
            elements.latestCommit.textContent = `커밋 차단: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`;
        }
    } else {
        updateGitBranchOverlayCommitPreview(status);
    }
    let renderedFileCount = files.length;
    if (elements.list) {
        const rendered = renderGitChangedFileTreeList({
            listElement: elements.list,
            files,
            collapsedFolders: gitBranchOverlayCollapsedFolders,
            selectable: true,
            selectedFiles: gitOverlaySelectedFiles,
            onFileSelectionChange: (path, checked) => {
                gitOverlaySelectionTouched = true;
                if (checked) {
                    gitOverlaySelectedFiles.add(path);
                } else {
                    gitOverlaySelectedFiles.delete(path);
                }
                renderGitBranchOverlay(gitBranchStatusCache);
            },
            onFolderSelectionChange: (folder, checked) => {
                gitOverlaySelectionTouched = true;
                const targetPaths = Array.isArray(folder?.filePaths) ? folder.filePaths : [];
                targetPaths.forEach(path => {
                    if (checked) {
                        gitOverlaySelectedFiles.add(path);
                    } else {
                        gitOverlaySelectedFiles.delete(path);
                    }
                });
                renderGitBranchOverlay(gitBranchStatusCache);
            },
            onFolderCollapseToggle: (folderPath, shouldCollapse) => {
                if (!folderPath) return;
                if (shouldCollapse) {
                    gitBranchOverlayCollapsedFolders.add(folderPath);
                } else {
                    gitBranchOverlayCollapsedFolders.delete(folderPath);
                }
                renderGitBranchOverlay(gitBranchStatusCache);
            }
        });
        renderedFileCount = rendered.fileCount;
        elements.list.classList.toggle('is-hidden', rendered.fileCount === 0);
    }
    if (elements.empty) {
        elements.empty.textContent = Number.isFinite(count)
            ? '변경 파일이 없습니다.'
            : '변경 파일 정보를 불러올 수 없습니다.';
        elements.empty.classList.toggle('is-hidden', renderedFileCount !== 0);
    }
    updateGitOverlaySelectionSummary(renderedFileCount, {
        hasWindowsPathIssues,
        windowsInvalidCount,
        windowsInvalidFiles
    });
    if (elements.loading) {
        elements.loading.classList.add('is-hidden');
    }
}

function isGitBranchOverlayOpen() {
    const overlay = document.getElementById('codex-branch-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function openGitBranchOverlay() {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    if (isGitSyncOverlayOpen()) {
        closeGitSyncOverlay();
    }
    if (isMessageLogOverlayOpen()) {
        closeMessageLogOverlay();
    }
    if (isFileBrowserOverlayOpen()) {
        closeFileBrowserOverlay();
    }
    if (isUsageHistoryOverlayOpen()) {
        closeUsageHistoryOverlay();
    }
    if (isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    gitOverlaySelectionTouched = false;
    gitOverlaySelectedFiles = new Set();
    gitBranchOverlayPreviewKey = '';
    if (elements.commitMessage) {
        elements.commitMessage.value = '';
    }
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    setGitBranchOverlayLoading(true);
    void refreshGitBranchStatus({ force: true, updateOverlay: true });
}

function closeGitBranchOverlay() {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    gitBranchOverlayPreviewKey = '';
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    if (
        !isGitSyncOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isUsageHistoryOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function normalizeGitSyncRepoTarget(value) {
    const target = String(value || '').trim();
    return GIT_SYNC_TARGET_ORDER.includes(target) ? target : GIT_SYNC_TARGET_WORKSPACE;
}

function getGitSyncRepoLabel(repoTarget) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    return GIT_SYNC_TARGET_LABELS[target] || target;
}

function getGitSyncOverlayCollapsedFolders(repoTarget = gitSyncOverlayRepoTarget) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    const current = gitSyncOverlayCollapsedFoldersByTarget[target];
    if (current instanceof Set) {
        return current;
    }
    const created = new Set();
    gitSyncOverlayCollapsedFoldersByTarget[target] = created;
    return created;
}

function createGitSyncHistoryCache(repoTarget = GIT_SYNC_TARGET_WORKSPACE) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    return {
        repoTarget: target,
        repoLabel: getGitSyncRepoLabel(target),
        repoRoot: '',
        repoMissing: false,
        currentBranch: '',
        currentBranchHistory: [],
        requestedMainBranch: 'main',
        mainBranch: 'main',
        mainBranchFallback: false,
        remoteName: 'origin',
        remoteMainRef: 'origin/(unknown)',
        remoteMainHistory: [],
        remoteMainHistoryError: '',
        windowsInvalidFiles: [],
        windowsInvalidCount: 0,
        hasWindowsPathIssues: false,
        changedCount: null,
        changedFiles: [],
        aheadCount: null,
        behindCount: null,
        fetchedAt: 0,
        isStale: false
    };
}

function getGitSyncHistoryCache(repoTarget = GIT_SYNC_TARGET_WORKSPACE) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    const cached = gitSyncHistoryCacheByTarget[target];
    if (cached && typeof cached === 'object') {
        return cached;
    }
    const initial = createGitSyncHistoryCache(target);
    gitSyncHistoryCacheByTarget[target] = initial;
    return initial;
}

function setGitSyncHistoryCache(repoTarget, partial = {}) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    const next = {
        ...createGitSyncHistoryCache(target),
        ...getGitSyncHistoryCache(target),
        ...(partial && typeof partial === 'object' ? partial : {}),
        repoTarget: target,
        repoLabel: getGitSyncRepoLabel(target)
    };
    gitSyncHistoryCacheByTarget[target] = next;
    return next;
}

function normalizeGitSyncBranchName(value, { allowDetached = false } = {}) {
    const branch = typeof value === 'string' ? value.trim() : '';
    if (!branch) return '';
    const lowered = branch.toLowerCase();
    if (!allowDetached && (lowered === 'head' || lowered.startsWith('detached@'))) {
        return '';
    }
    return branch;
}

function resolveGitSyncRequestBranch(repoTarget, preferredBranch = '') {
    const explicitBranch = normalizeGitSyncBranchName(preferredBranch);
    if (explicitBranch) {
        return explicitBranch;
    }
    const cache = getGitSyncHistoryCache(repoTarget);
    const cachedBranch = normalizeGitSyncBranchName(cache?.currentBranch);
    if (cachedBranch) {
        return cachedBranch;
    }
    if (normalizeGitSyncRepoTarget(repoTarget) === GIT_SYNC_TARGET_WORKSPACE) {
        const workspaceBranch = normalizeGitSyncBranchName(gitBranchStatusCache?.branch);
        if (workspaceBranch) {
            return workspaceBranch;
        }
    }
    return '';
}

function getGitSyncOverlayElements() {
    const overlay = document.getElementById('codex-sync-overlay');
    if (!overlay) return null;
    return {
        overlay,
        subtitle: document.getElementById('codex-sync-overlay-subtitle'),
        meta: document.getElementById('codex-sync-overlay-meta'),
        latestCommit: document.getElementById('codex-sync-overlay-last-commit'),
        targetButtons: Array.from(overlay.querySelectorAll('.sync-overlay-target[data-repo-target]')),
        fetchBtn: document.getElementById('codex-sync-overlay-fetch'),
        syncBtn: document.getElementById('codex-sync-overlay-sync'),
        commitBtn: document.getElementById('codex-sync-overlay-commit'),
        pushBtn: document.getElementById('codex-sync-overlay-push'),
        refreshBtn: document.getElementById('codex-sync-overlay-refresh'),
        loading: document.getElementById('codex-sync-overlay-loading'),
        filesEmpty: document.getElementById('codex-sync-overlay-files-empty'),
        filesList: document.getElementById('codex-sync-overlay-files-list'),
        empty: document.getElementById('codex-sync-overlay-empty'),
        list: document.getElementById('codex-sync-overlay-list')
    };
}

function updateGitSyncOverlayActionButtonState(status) {
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    const repoMissing = Boolean(status?.repoMissing);
    const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles);
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        status?.windowsInvalidCount,
        windowsInvalidFiles.length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        status?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    const normalizedChangedCount = normalizeGitChangedFilesCount(status?.changedCount);
    const changedCount = Number.isFinite(normalizedChangedCount)
        ? normalizedChangedCount
        : normalizeGitChangedFiles(status?.changedFiles).length;
    const aheadCount = normalizeGitDivergenceCount(status?.aheadCount);
    const behindCount = normalizeGitDivergenceCount(status?.behindCount);
    const hasChanges = !repoMissing && Number.isFinite(changedCount) && changedCount > 0;
    const canCommit = hasChanges && !hasWindowsPathIssues;
    const hasPendingPush = !repoMissing && Number.isFinite(aheadCount) && aheadCount > 0;
    const hasPendingSync = !repoMissing && Number.isFinite(behindCount) && behindCount > 0;

    if (elements.commitBtn) {
        elements.commitBtn.classList.toggle('is-ready', canCommit);
        const isBusy = elements.commitBtn.classList.contains('is-loading')
            || elements.commitBtn.getAttribute('aria-busy') === 'true';
        const isLoading = elements.loading && !elements.loading.classList.contains('is-hidden');
        if (!isBusy && !isLoading) {
            elements.commitBtn.disabled = !canCommit;
        }
        const label = hasWindowsPathIssues
            ? `Commit 불가: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`
            : 'Commit all changed files';
        elements.commitBtn.dataset.label = label;
        syncHoverTooltipFromLabel(elements.commitBtn, label);
    }
    if (elements.pushBtn) {
        elements.pushBtn.classList.toggle('is-ready', hasPendingPush);
    }
    if (elements.syncBtn) {
        elements.syncBtn.classList.toggle('is-ready', hasPendingSync);
    }
}

function syncGitSyncOverlayActionButtonsFromCache() {
    if (!isGitSyncOverlayOpen()) return;
    const target = normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget);
    const cached = getGitSyncHistoryCache(target);
    updateGitSyncOverlayActionButtonState(cached);
}

function setGitSyncOverlayLoading(isLoading) {
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    if (elements.loading) {
        elements.loading.classList.toggle('is-hidden', !isLoading);
    }
    if (elements.fetchBtn) {
        const fetchBusy = elements.fetchBtn.classList.contains('is-loading')
            || elements.fetchBtn.getAttribute('aria-busy') === 'true';
        elements.fetchBtn.disabled = Boolean(isLoading) || fetchBusy;
    }
    if (elements.syncBtn) {
        const syncBusy = elements.syncBtn.classList.contains('is-loading')
            || elements.syncBtn.getAttribute('aria-busy') === 'true';
        elements.syncBtn.disabled = Boolean(isLoading) || syncBusy;
    }
    [elements.commitBtn, elements.pushBtn].forEach(button => {
        if (!button) return;
        const actionBusy = button.classList.contains('is-loading')
            || button.getAttribute('aria-busy') === 'true';
        button.disabled = Boolean(isLoading) || actionBusy;
    });
    if (elements.refreshBtn) {
        elements.refreshBtn.disabled = Boolean(isLoading);
    }
    if (Array.isArray(elements.targetButtons)) {
        elements.targetButtons.forEach(button => {
            button.disabled = Boolean(isLoading);
        });
    }
    if (!isLoading) {
        updateGitSyncOverlayActionButtonState(getGitSyncHistoryCache(gitSyncOverlayRepoTarget));
    }
}

function setGitSyncOverlayRepoTarget(repoTarget) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    gitSyncOverlayRepoTarget = target;
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    const label = getGitSyncRepoLabel(target);
    if (elements.subtitle) {
        elements.subtitle.textContent = `${label} · 원격 이력`;
    }
    if (Array.isArray(elements.targetButtons)) {
        elements.targetButtons.forEach(button => {
            const buttonTarget = normalizeGitSyncRepoTarget(button.dataset?.repoTarget);
            const isActive = buttonTarget === target;
            button.classList.toggle('is-active', isActive);
            button.classList.toggle('secondary', isActive);
            button.classList.toggle('ghost', !isActive);
        });
    }
    if (elements.fetchBtn) {
        const fetchLabel = 'Fetch only';
        elements.fetchBtn.textContent = fetchLabel;
        elements.fetchBtn.dataset.label = fetchLabel;
        syncHoverTooltipFromLabel(elements.fetchBtn, fetchLabel);
    }
    if (elements.syncBtn) {
        const syncLabel = 'Fetch + fast-forward';
        elements.syncBtn.textContent = syncLabel;
        elements.syncBtn.dataset.label = syncLabel;
        syncHoverTooltipFromLabel(elements.syncBtn, syncLabel);
    }
    updateGitSyncOverlayActionButtonState(getGitSyncHistoryCache(target));
}

function normalizeGitHistoryEntries(value) {
    if (!Array.isArray(value)) return [];
    return value.map(entry => {
        if (!entry || typeof entry !== 'object') return null;
        const commitHash = typeof entry.commit_hash === 'string'
            ? entry.commit_hash.trim()
            : (typeof entry.commitHash === 'string' ? entry.commitHash.trim() : '');
        const shortHashRaw = typeof entry.short_hash === 'string'
            ? entry.short_hash.trim()
            : (typeof entry.shortHash === 'string' ? entry.shortHash.trim() : '');
        const shortHash = shortHashRaw || (commitHash ? commitHash.slice(0, 8) : '');
        const committedAt = typeof entry.committed_at === 'string'
            ? entry.committed_at.trim()
            : (typeof entry.committedAt === 'string' ? entry.committedAt.trim() : '');
        const author = typeof entry.author === 'string' ? entry.author.trim() : '';
        const subject = typeof entry.subject === 'string' ? entry.subject.trim() : '';
        const fullMessageRaw = typeof entry.full_message === 'string'
            ? entry.full_message
            : (typeof entry.fullMessage === 'string' ? entry.fullMessage : '');
        const fullMessage = fullMessageRaw.trim() || subject;
        if (!shortHash && !subject) return null;
        return { commitHash, shortHash, committedAt, author, subject, fullMessage };
    }).filter(Boolean);
}

function formatGitHistoryDetailToastText(entry) {
    const shortHash = typeof entry?.shortHash === 'string' ? entry.shortHash.trim() : '';
    const subject = typeof entry?.subject === 'string' ? entry.subject.trim() : '';
    const fullMessage = typeof entry?.fullMessage === 'string' ? entry.fullMessage.trim() : '';
    const detailSource = fullMessage || subject;
    if (!detailSource && !shortHash) {
        return '상세 커밋 메시지가 없습니다.';
    }
    const flattened = detailSource.replace(/\s+/g, ' ').trim();
    const normalizedDetail = flattened.length > 260 ? `${flattened.slice(0, 259)}…` : flattened;
    if (shortHash && normalizedDetail) {
        return `${shortHash} · ${normalizedDetail}`;
    }
    return normalizedDetail || shortHash;
}

function formatGitHistoryTimestamp(value) {
    const text = String(value || '').trim();
    if (!text) return '-';
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return text;
    return parsed.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
}

function renderGitSyncOverlay(history) {
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    const repoTarget = normalizeGitSyncRepoTarget(history?.repoTarget || gitSyncOverlayRepoTarget);
    setGitSyncOverlayRepoTarget(repoTarget);
    const repoLabel = getGitSyncRepoLabel(repoTarget);
    const repoRoot = typeof history?.repoRoot === 'string' ? history.repoRoot.trim() : '';
    const repoMissing = Boolean(history?.repoMissing) || !repoRoot;
    const currentBranch = typeof history?.currentBranch === 'string' ? history.currentBranch.trim() : '';
    const remoteMainRef = typeof history?.remoteMainRef === 'string' && history.remoteMainRef.trim()
        ? history.remoteMainRef.trim()
        : 'origin/(unknown)';
    const requestedMainBranch = typeof history?.requestedMainBranch === 'string'
        ? history.requestedMainBranch.trim()
        : 'main';
    const mainBranch = typeof history?.mainBranch === 'string' && history.mainBranch.trim()
        ? history.mainBranch.trim()
        : requestedMainBranch;
    const mainBranchFallback = Boolean(history?.mainBranchFallback);
    const remoteHistory = normalizeGitHistoryEntries(history?.remoteMainHistory).slice(0, 10);
    const remoteHistoryError = typeof history?.remoteMainHistoryError === 'string'
        ? history.remoteMainHistoryError.trim()
        : '';
    const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(history?.windowsInvalidFiles);
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        history?.windowsInvalidCount,
        windowsInvalidFiles.length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        history?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    const changedFiles = normalizeGitChangedFiles(history?.changedFiles);
    const normalizedChangedCount = normalizeGitChangedFilesCount(history?.changedCount);
    const changedCount = Number.isFinite(normalizedChangedCount)
        ? normalizedChangedCount
        : changedFiles.length;
    const aheadCount = Number.isFinite(history?.aheadCount) ? history.aheadCount : null;
    const behindCount = Number.isFinite(history?.behindCount) ? history.behindCount : null;
    const compareText = !repoMissing && aheadCount != null && behindCount != null
        ? `HEAD 대비 ahead ${aheadCount} / behind ${behindCount}`
        : 'HEAD 비교 정보 없음';
    if (elements.subtitle) {
        elements.subtitle.textContent = `${repoLabel} · ${remoteMainRef} 최근 이력`;
    }
    if (elements.fetchBtn) {
        const fetchLabel = 'Fetch only';
        elements.fetchBtn.textContent = fetchLabel;
        elements.fetchBtn.dataset.label = fetchLabel;
        syncHoverTooltipFromLabel(elements.fetchBtn, fetchLabel);
    }
    if (elements.meta) {
        const repoText = `${repoLabel} (${repoRoot || 'None'})`;
        const branchText = currentBranch ? `현재 브랜치: ${currentBranch}` : '현재 브랜치: None';
        const changedText = Number.isFinite(changedCount)
            ? `작업 트리 변경: ${changedCount}개`
            : '작업 트리 변경: 확인 불가';
        const windowsIssueText = hasWindowsPathIssues
            ? ` · 오류: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`
            : '';
        const fallbackText = mainBranchFallback && requestedMainBranch && mainBranch && requestedMainBranch !== mainBranch
            ? ` · 요청 ${requestedMainBranch} -> 사용 ${mainBranch}`
            : '';
        elements.meta.textContent = `${repoText} · ${branchText} · ${compareText} · ${changedText}${windowsIssueText}${fallbackText}`;
    }
    if (elements.latestCommit) {
        if (hasWindowsPathIssues) {
            gitSyncOverlayPreviewKeyByTarget[repoTarget] = '';
            elements.latestCommit.textContent = `커밋 차단: ${formatGitWindowsPathIssueSummary(windowsInvalidCount)}`;
        } else {
            const changedPaths = changedFiles.map(file => file.path);
            const previewRequest = buildGitCommitPreviewCacheKey(repoTarget, changedPaths);
            gitSyncOverlayPreviewKeyByTarget[repoTarget] = previewRequest.key;
            if (!changedPaths.length || !previewRequest.key) {
                elements.latestCommit.textContent = '커밋 예정 메시지: 커밋 대상 파일이 없습니다.';
            } else {
                const freshPreview = getGitCommitPreviewCacheEntry(previewRequest.key);
                if (freshPreview) {
                    elements.latestCommit.textContent = formatGitCommitPreviewLabel(freshPreview, changedPaths.length);
                } else {
                    const stalePreview = getGitCommitPreviewCacheEntry(previewRequest.key, { allowStale: true });
                    if (stalePreview) {
                        elements.latestCommit.textContent = formatGitCommitPreviewLabel(stalePreview, changedPaths.length);
                    } else {
                        elements.latestCommit.textContent = '커밋 예정 메시지: 계산 중...';
                    }
                    if (!gitCommitPreviewInFlightByKey.has(previewRequest.key)) {
                        void ensureGitCommitPreview(repoTarget, changedPaths).then(({ key, entry }) => {
                            if (!entry || !isGitSyncOverlayOpen()) return;
                            const activeTarget = normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget);
                            if (activeTarget !== repoTarget) return;
                            if (gitSyncOverlayPreviewKeyByTarget[repoTarget] !== key) return;
                            renderGitSyncOverlay(getGitSyncHistoryCache(repoTarget));
                        });
                    }
                }
            }
        }
    }
    let renderedChangedFileCount = changedFiles.length;
    if (elements.filesList) {
        const collapsedFolders = getGitSyncOverlayCollapsedFolders(repoTarget);
        const rendered = renderGitChangedFileTreeList({
            listElement: elements.filesList,
            files: changedFiles,
            collapsedFolders,
            selectable: false,
            onFolderCollapseToggle: (folderPath, shouldCollapse) => {
                if (!folderPath) return;
                if (shouldCollapse) {
                    collapsedFolders.add(folderPath);
                } else {
                    collapsedFolders.delete(folderPath);
                }
                renderGitSyncOverlay(getGitSyncHistoryCache(repoTarget));
            }
        });
        renderedChangedFileCount = rendered.fileCount;
        elements.filesList.classList.toggle('is-hidden', rendered.fileCount === 0);
    }
    if (elements.filesEmpty) {
        const fallbackFileMessage = repoMissing
            ? '현재 repository: None'
            : '커밋 대상 파일이 없습니다.';
        elements.filesEmpty.textContent = fallbackFileMessage;
        elements.filesEmpty.classList.toggle('is-hidden', renderedChangedFileCount !== 0);
    }
    if (elements.list) {
        elements.list.innerHTML = '';
        remoteHistory.forEach(entry => {
            const item = document.createElement('li');
            item.className = 'sync-overlay-history-item';
            item.tabIndex = 0;
            item.setAttribute('role', 'button');
            item.title = '클릭하면 상세 커밋 메시지를 표시합니다.';
            const main = document.createElement('div');
            main.className = 'sync-overlay-item-main';

            const hash = document.createElement('span');
            hash.className = 'sync-overlay-item-hash';
            hash.textContent = entry.shortHash || '-';
            if (entry.commitHash) {
                hash.title = entry.commitHash;
            }
            main.appendChild(hash);

            const subject = document.createElement('span');
            subject.className = 'sync-overlay-item-subject';
            subject.textContent = entry.subject || '(no subject)';
            main.appendChild(subject);

            const meta = document.createElement('div');
            meta.className = 'sync-overlay-item-meta';
            const authorText = entry.author || 'unknown';
            meta.textContent = `${formatGitHistoryTimestamp(entry.committedAt)} · ${authorText}`;

            item.appendChild(main);
            item.appendChild(meta);
            const showDetailToast = () => {
                showToast(formatGitHistoryDetailToastText(entry), { tone: 'default', durationMs: 5600 });
            };
            item.addEventListener('click', showDetailToast);
            item.addEventListener('keydown', event => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                showDetailToast();
            });
            elements.list.appendChild(item);
        });
        elements.list.classList.toggle('is-hidden', remoteHistory.length === 0);
    }
    if (elements.empty) {
        const fallbackMessage = remoteHistoryError || '표시할 이력이 없습니다.';
        elements.empty.textContent = fallbackMessage;
        elements.empty.classList.toggle('is-hidden', remoteHistory.length !== 0);
    }
    updateGitSyncOverlayActionButtonState({
        repoMissing,
        changedCount,
        changedFiles,
        aheadCount,
        behindCount,
        windowsInvalidFiles,
        windowsInvalidCount,
        hasWindowsPathIssues
    });
}

function isGitSyncOverlayOpen() {
    const overlay = document.getElementById('codex-sync-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function openGitSyncOverlay() {
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    if (isGitBranchOverlayOpen()) {
        closeGitBranchOverlay();
    }
    if (isFileBrowserOverlayOpen()) {
        closeFileBrowserOverlay();
    }
    if (isMessageLogOverlayOpen()) {
        closeMessageLogOverlay();
    }
    if (isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    if (isUsageHistoryOverlayOpen()) {
        closeUsageHistoryOverlay();
    }
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    gitSyncOverlayPreviewKeyByTarget[normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)] = '';
    if (elements.meta) {
        elements.meta.textContent = '히스토리를 불러오는 중...';
    }
    if (elements.latestCommit) {
        elements.latestCommit.textContent = '커밋 예정 메시지: 계산 중...';
    }
    if (elements.empty) {
        elements.empty.classList.add('is-hidden');
    }
    if (elements.list) {
        elements.list.classList.add('is-hidden');
        elements.list.innerHTML = '';
    }
    if (elements.filesEmpty) {
        elements.filesEmpty.classList.add('is-hidden');
    }
    if (elements.filesList) {
        elements.filesList.classList.add('is-hidden');
        elements.filesList.innerHTML = '';
    }
    setGitSyncOverlayRepoTarget(gitSyncOverlayRepoTarget);
    setGitSyncOverlayLoading(true);
    void refreshGitSyncOverlayHistory({ force: true });
}

function closeGitSyncOverlay() {
    const elements = getGitSyncOverlayElements();
    if (!elements) return;
    const activeTarget = normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget);
    gitSyncOverlayPreviewKeyByTarget[activeTarget] = '';
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    if (
        !isGitBranchOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isUsageHistoryOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function getUsageHistoryOverlayElements() {
    const overlay = document.getElementById('codex-usage-history-overlay');
    if (!overlay) return null;
    return {
        overlay,
        subtitle: document.getElementById('codex-usage-history-overlay-subtitle'),
        meta: document.getElementById('codex-usage-history-overlay-meta'),
        scale: document.getElementById('codex-usage-history-scale'),
        ratios: document.getElementById('codex-usage-history-ratios'),
        chartWrap: document.getElementById('codex-usage-history-chart-wrap'),
        chart: document.getElementById('codex-usage-history-chart'),
        legend: document.getElementById('codex-usage-history-legend'),
        empty: document.getElementById('codex-usage-history-empty')
    };
}

function isUsageHistoryOverlayOpen() {
    const overlay = document.getElementById('codex-usage-history-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function createUsageHistorySvgNode(tagName, attrs = {}) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tagName);
    Object.entries(attrs).forEach(([key, value]) => {
        if (value === null || value === undefined) return;
        node.setAttribute(key, String(value));
    });
    return node;
}

function formatUsageHistoryTickLabel(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString('ko-KR', {
        timeZone: KST_TIME_ZONE,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit'
    });
}

function resolveUsageHistoryPercentScale(maxUsedPercent) {
    const candidates = [5, 10, 25, 50, 75, 100];
    const peak = Number.isFinite(maxUsedPercent) ? Math.max(0, maxUsedPercent) : 0;
    const paddedPeak = peak <= 0 ? 1 : peak * 1.12;
    for (const candidate of candidates) {
        if (paddedPeak <= candidate) {
            return candidate;
        }
    }
    return 100;
}

function buildUsageHistoryPercentTicks(maxPercent) {
    const top = Math.max(1, Number(maxPercent) || 100);
    const step = top / 5;
    return Array.from({ length: 6 }, (_, index) => {
        const value = step * index;
        return Math.round(value * 100) / 100;
    });
}

function formatUsageHistoryPercentTick(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    if (Math.abs(numeric - Math.round(numeric)) < 0.001) {
        return `${Math.round(numeric)}%`;
    }
    return `${numeric.toFixed(1)}%`;
}

function resolveUsageHistoryRelationScope(history) {
    const relationScope = String(
        history?.relation?.scope || history?.token_delta_scope || ''
    ).trim().toLowerCase();
    return relationScope === 'account' ? 'account' : 'workspace';
}

function formatUsageHistoryTokenRate(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return '--';
    if (numeric >= 100) {
        return `${formatCompactTokenCount(Math.round(numeric))} tok/h`;
    }
    if (numeric >= 10) {
        return `${numeric.toFixed(1).replace(/\.0$/, '')} tok/h`;
    }
    return `${numeric.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')} tok/h`;
}

function formatUsageHistoryRatePercent(value, unit = '') {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return '--';
    let text = '';
    if (numeric >= 100) {
        text = formatNumber(Math.round(numeric));
    } else if (numeric >= 10) {
        text = numeric.toFixed(1).replace(/\.0$/, '');
    } else if (numeric >= 1) {
        text = numeric.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    } else {
        text = numeric.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    }
    return `${text}%${unit}`;
}

function resolveUsageHistoryAverageWeeklyPace(history, averageEntry) {
    const avgTokensPerHour = Number(averageEntry?.avg_tokens_per_hour);
    if (!Number.isFinite(avgTokensPerHour) || avgTokensPerHour < 0) {
        return null;
    }

    const weeklyRelation = history?.relation?.weekly || {};
    const reliableTokensPerPercent = Number(weeklyRelation?.tokens_per_percent);
    const estimatedTokensPerPercent = Number(weeklyRelation?.raw_tokens_per_percent);
    const tokensPerPercent = (
        Number.isFinite(reliableTokensPerPercent) && reliableTokensPerPercent > 0
    )
        ? reliableTokensPerPercent
        : (
            Number.isFinite(estimatedTokensPerPercent) && estimatedTokensPerPercent > 0
                ? estimatedTokensPerPercent
                : null
        );
    if (!Number.isFinite(tokensPerPercent) || tokensPerPercent <= 0) {
        return null;
    }

    const percentPerHour = Math.max(0, avgTokensPerHour / tokensPerPercent);
    return {
        percentPerHour,
        projectedWeeklyPercent: percentPerHour * 24 * 7,
        isReliable: Boolean(
            weeklyRelation?.is_reliable
            && Number.isFinite(reliableTokensPerPercent)
            && reliableTokensPerPercent > 0
        )
    };
}

function appendUsageHistoryMetricCard(container, {
    label = '',
    value = '--',
    subvalue = '',
    meta = '',
    lowConfidence = false
} = {}) {
    if (!(container instanceof HTMLElement)) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'usage-history-ratio-card';
    if (lowConfidence) {
        wrapper.classList.add('is-low-confidence');
    }

    const labelNode = document.createElement('div');
    labelNode.className = 'usage-history-ratio-label';
    labelNode.textContent = label;
    wrapper.appendChild(labelNode);

    const valueNode = document.createElement('div');
    valueNode.className = 'usage-history-ratio-value';
    valueNode.textContent = value;
    wrapper.appendChild(valueNode);

    if (subvalue) {
        const subvalueNode = document.createElement('div');
        subvalueNode.className = 'usage-history-ratio-subvalue';
        subvalueNode.textContent = subvalue;
        wrapper.appendChild(subvalueNode);
    }

    const metaNode = document.createElement('div');
    metaNode.className = 'usage-history-ratio-meta';
    metaNode.textContent = meta;
    wrapper.appendChild(metaNode);

    container.appendChild(wrapper);
}

function renderUsageHistoryRatioCards(history) {
    const elements = getUsageHistoryOverlayElements();
    if (!elements?.ratios) return;
    elements.ratios.innerHTML = '';

    const relationScope = resolveUsageHistoryRelationScope(history);
    const relation = history?.relation || {};
    const ratioItems = [
        { key: 'five_hour', label: '5h 1% token', entry: relation?.five_hour },
        { key: 'weekly', label: 'Weekly 1% token', entry: relation?.weekly }
    ];
    ratioItems.forEach(item => {
        const ratioValue = Number(item?.entry?.tokens_per_percent);
        const rawRatioValue = Number(item?.entry?.raw_tokens_per_percent);
        const sampleCount = Number(item?.entry?.sample_count);
        const confidence = String(item?.entry?.confidence || '').trim().toLowerCase();
        const reliable = Boolean(item?.entry?.is_reliable);
        const displayValue = Number.isFinite(ratioValue)
            ? `${formatCompactTokenCount(ratioValue)} tok`
            : (Number.isFinite(rawRatioValue) ? `~${formatCompactTokenCount(rawRatioValue)} tok` : '--');
        const fallbackValue = Number.isFinite(rawRatioValue)
            ? `${formatCompactTokenCount(rawRatioValue)} tok`
            : '--';
        const metaParts = [`scope ${relationScope}`];
        if (Number.isFinite(sampleCount)) {
            metaParts.push(`samples ${Math.max(0, Math.round(sampleCount))}`);
        }
        if (confidence && confidence !== 'none') {
            metaParts.push(`conf ${confidence}`);
        }
        if (!reliable && Number.isFinite(rawRatioValue)) {
            metaParts.push(`est ${fallbackValue}`);
        }
        appendUsageHistoryMetricCard(elements.ratios, {
            label: item.label,
            value: displayValue,
            meta: metaParts.join(' · '),
            lowConfidence: !reliable && Number.isFinite(rawRatioValue)
        });
    });

    const averageItems = [
        {
            label: '24h avg/hour',
            entry: history?.averages?.daily || history?.relation?.averages?.daily || null
        },
        {
            label: '7d avg/hour',
            entry: history?.averages?.weekly || history?.relation?.averages?.weekly || null
        }
    ];
    averageItems.forEach(item => {
        const avgTokensPerHour = Number(item?.entry?.avg_tokens_per_hour);
        const tokenTotal = Number(item?.entry?.token_total);
        const sampleCount = Number(item?.entry?.sample_count);
        const expectedSamples = Number(item?.entry?.expected_samples);
        const coverageRatio = Number(item?.entry?.coverage_ratio);
        const scope = String(item?.entry?.scope || relationScope || '').trim() || relationScope;
        const weeklyPace = resolveUsageHistoryAverageWeeklyPace(history, item?.entry);
        const metaParts = [`scope ${scope}`];
        if (weeklyPace) {
            metaParts.push(`wk rate ${formatUsageHistoryRatePercent(weeklyPace.percentPerHour, '/h')}`);
        }
        if (Number.isFinite(tokenTotal)) {
            metaParts.push(`total ${formatCompactTokenCount(Math.max(0, Math.round(tokenTotal)))} tok`);
        }
        if (Number.isFinite(sampleCount) && Number.isFinite(expectedSamples) && expectedSamples > 0) {
            metaParts.push(`samples ${Math.max(0, Math.round(sampleCount))}/${Math.max(1, Math.round(expectedSamples))}`);
        }
        appendUsageHistoryMetricCard(elements.ratios, {
            label: item.label,
            value: formatUsageHistoryTokenRate(avgTokensPerHour),
            subvalue: weeklyPace
                ? `Weekly pace ${formatUsageHistoryRatePercent(weeklyPace.projectedWeeklyPercent)}`
                : '',
            meta: metaParts.join(' · '),
            lowConfidence: (
                (Number.isFinite(coverageRatio) && coverageRatio < 0.6)
                || Boolean(weeklyPace && !weeklyPace.isReliable)
            )
        });
    });
}

function renderUsageHistoryScaleBadge(chartMetrics) {
    const elements = getUsageHistoryOverlayElements();
    if (!elements?.scale) return;
    if (!chartMetrics || !chartMetrics.rendered) {
        elements.scale.textContent = 'Scale --';
        return;
    }
    const maxPercent = Number(chartMetrics.percentScale);
    if (!Number.isFinite(maxPercent) || maxPercent <= 0) {
        elements.scale.textContent = 'Scale --';
        return;
    }
    const mode = maxPercent < 100 ? 'Auto' : 'Full';
    elements.scale.textContent = `${mode} scale 0-${Math.round(maxPercent)}%`;
}

function renderUsageHistoryLegend(history) {
    const elements = getUsageHistoryOverlayElements();
    if (!elements?.legend) return;
    elements.legend.innerHTML = '';

    const tokenDeltaTotal = Number(history?.token_delta_total);
    const workspaceDeltaTotal = Number(history?.token_delta_total_workspace);
    const accountDeltaTotal = Number(history?.token_delta_total_account);
    const resetCount = Number(history?.reset_detected_count);
    const relationScope = resolveUsageHistoryRelationScope(history);
    const scopeLabel = relationScope === 'account' ? 'account' : 'workspace';

    const legendItems = [
        {
            key: 'token',
            text: `Token delta (${scopeLabel}) ${Number.isFinite(tokenDeltaTotal) ? formatNumber(tokenDeltaTotal) : '0'}`
        }
    ];
    if (Number.isFinite(workspaceDeltaTotal) || Number.isFinite(accountDeltaTotal)) {
        legendItems.push({
            key: '',
            text: `Workspace Δ ${Number.isFinite(workspaceDeltaTotal) ? formatNumber(workspaceDeltaTotal) : '--'} · Account Δ ${Number.isFinite(accountDeltaTotal) ? formatNumber(accountDeltaTotal) : '--'}`
        });
    }
    if (Number.isFinite(resetCount) && resetCount > 0) {
        legendItems.push({
            key: '',
            text: `Reset 감지 ${formatNumber(resetCount)}회`
        });
    }

    legendItems.forEach(item => {
        const wrapper = document.createElement('span');
        wrapper.className = 'usage-history-legend-item';
        if (item.key) {
            const swatch = document.createElement('span');
            swatch.className = `usage-history-legend-swatch ${item.key}`;
            wrapper.appendChild(swatch);
        }
        const text = document.createElement('span');
        text.textContent = item.text;
        wrapper.appendChild(text);
        elements.legend.appendChild(wrapper);
    });
}

function resolveUsageHistoryChartDisplayHeight(containerWidth, mobileLayout) {
    const normalizedWidth = Math.max(280, Number(containerWidth) || 0);
    if (mobileLayout) {
        return clampToRange(Math.round(normalizedWidth * 0.92), 300, 520);
    }
    return clampToRange(Math.round(normalizedWidth * 0.42), 260, 420);
}

function resetUsageHistoryChartPresentation(chartWrap, chart) {
    if (chartWrap instanceof HTMLElement) {
        chartWrap.style.removeProperty('--usage-history-chart-height');
    }
    if (chart instanceof SVGElement) {
        chart.style.removeProperty('--usage-history-chart-axis-font-size');
        chart.style.removeProperty('--usage-history-chart-title-font-size');
    }
}

function applyUsageHistoryChartTypography(chart, containerWidth, displayHeight, mobileLayout) {
    const normalizedWidth = Math.max(280, Number(containerWidth) || 0);
    const normalizedHeight = Math.max(220, Number(displayHeight) || 0);
    const widthBase = mobileLayout ? 380 : 760;
    const heightBase = mobileLayout ? 340 : 320;
    const fontScale = clampToRange(
        Math.min(normalizedWidth / widthBase, normalizedHeight / heightBase),
        0.86,
        1.18
    );
    const axisFontSize = Math.round((11 * fontScale) * 100) / 100;
    const titleFontSize = Math.round((10 * fontScale) * 100) / 100;
    if (chart instanceof SVGElement) {
        chart.style.setProperty('--usage-history-chart-axis-font-size', `${axisFontSize}px`);
        chart.style.setProperty('--usage-history-chart-title-font-size', `${titleFontSize}px`);
    }
    return {
        axisFontSize,
        titleFontSize,
        axisLabelOffset: Math.max(3.5, Math.round(axisFontSize * 0.36 * 100) / 100),
        axisSideGap: Math.max(8, Math.round(axisFontSize * 0.72)),
        titleGap: Math.max(5, Math.round(titleFontSize * 0.74)),
        bottomLabelGap: Math.max(20, Math.round(axisFontSize * 2.05))
    };
}

function buildUsageHistorySubtitle(hours) {
    const normalizedHours = Number.isFinite(Number(hours)) && Number(hours) > 0
        ? Math.round(Number(hours))
        : USAGE_HISTORY_DEFAULT_HOURS;
    if (normalizedHours >= 24 && normalizedHours % 24 === 0) {
        const days = Math.max(1, Math.round(normalizedHours / 24));
        return `최근 ${days}일 · 1시간 단위 사용량 추이 (KST)`;
    }
    return `최근 ${normalizedHours}시간 · 1시간 단위 사용량 추이 (KST)`;
}

function renderUsageHistoryChart(history) {
    const elements = getUsageHistoryOverlayElements();
    if (!elements?.chart) return { rendered: false, percentScale: 100 };
    const chart = elements.chart;
    const chartWrap = elements.chartWrap || chart.parentElement;
    chart.innerHTML = '';

    const items = Array.isArray(history?.items) ? history.items : [];
    if (items.length < 2) {
        resetUsageHistoryChartPresentation(chartWrap, chart);
        return { rendered: false, percentScale: 100 };
    }

    const mobileLayout = isMobileLayout();
    const containerWidth = Number(chartWrap?.clientWidth)
        || Number(chart.clientWidth)
        || 360;
    const displayHeight = resolveUsageHistoryChartDisplayHeight(containerWidth, mobileLayout);
    if (chartWrap instanceof HTMLElement) {
        chartWrap.style.setProperty('--usage-history-chart-height', `${displayHeight}px`);
    }
    const typography = applyUsageHistoryChartTypography(chart, containerWidth, displayHeight, mobileLayout);
    const width = mobileLayout ? 920 : 1000;
    const aspectRatio = containerWidth > 0
        ? displayHeight / containerWidth
        : (mobileLayout ? 0.92 : 0.42);
    const height = clampToRange(
        Math.round(width * aspectRatio),
        mobileLayout ? 720 : 340,
        mobileLayout ? 980 : 520
    );
    const leftMargin = clampToRange(Math.round(typography.axisFontSize * 5.8), 58, mobileLayout ? 68 : 72);
    const rightMargin = clampToRange(Math.round(typography.axisFontSize * 5.5), 56, mobileLayout ? 66 : 72);
    const margin = mobileLayout
        ? { top: 16, right: rightMargin, bottom: Math.max(36, Math.round(typography.axisFontSize * 3.1)), left: leftMargin }
        : { top: 16, right: rightMargin, bottom: Math.max(38, Math.round(typography.axisFontSize * 3.25)), left: leftMargin };
    const plotWidth = Math.max(1, width - margin.left - margin.right);
    const plotAreaHeight = Math.max(1, height - margin.top - margin.bottom);
    chart.setAttribute('viewBox', `0 0 ${width} ${height}`);
    chart.setAttribute('preserveAspectRatio', 'none');

    const tokenDeltas = items.map(item => Math.max(0, Number(item?.delta_tokens) || 0));
    const fiveHourUsed = items.map(item => normalizeUsedPercent(item?.five_hour_used_percent));
    const weeklyUsed = items.map(item => normalizeUsedPercent(item?.weekly_used_percent));
    const percentValues = [...fiveHourUsed, ...weeklyUsed].filter(value => Number.isFinite(value));
    const maxUsedPercent = percentValues.length > 0 ? Math.max(...percentValues) : 0;
    const percentScale = resolveUsageHistoryPercentScale(maxUsedPercent);
    const percentTicks = buildUsageHistoryPercentTicks(percentScale);
    const maxTokenDelta = Math.max(1, ...tokenDeltas);

    const stackedGap = mobileLayout ? 30 : 0;
    const tokenPlotHeight = mobileLayout
        ? Math.max(90, Math.round((plotAreaHeight - stackedGap) * 0.53))
        : plotAreaHeight;
    const percentPlotHeight = mobileLayout
        ? Math.max(70, plotAreaHeight - stackedGap - tokenPlotHeight)
        : plotAreaHeight;
    const tokenTop = margin.top;
    const tokenBottom = tokenTop + tokenPlotHeight;
    const percentTop = mobileLayout ? tokenBottom + stackedGap : margin.top;
    const percentBottom = percentTop + percentPlotHeight;

    const xStep = items.length > 1 ? plotWidth / (items.length - 1) : 0;
    const barWidth = Math.max(2, Math.min(14, plotWidth / Math.max(items.length * 1.8, 1)));
    const xAt = index => margin.left + (xStep * index);
    const yToken = value => tokenBottom - ((Math.max(0, value) / maxTokenDelta) * tokenPlotHeight);
    const yPercent = value => {
        const normalized = Math.max(0, Math.min(percentScale, Number(value) || 0));
        return percentBottom - ((normalized / percentScale) * percentPlotHeight);
    };

    if (mobileLayout) {
        chart.appendChild(createUsageHistorySvgNode('text', {
            x: margin.left,
            y: tokenTop - typography.titleGap,
            'text-anchor': 'start',
            class: 'axis-title'
        })).textContent = 'Token delta';
        chart.appendChild(createUsageHistorySvgNode('text', {
            x: margin.left,
            y: percentTop - typography.titleGap,
            'text-anchor': 'start',
            class: 'axis-title'
        })).textContent = `Used % (0-${percentScale}%)`;
    }

    if (mobileLayout) {
        [0, 25, 50, 75, 100].forEach(percent => {
            const y = tokenTop + tokenPlotHeight - ((percent / 100) * tokenPlotHeight);
            chart.appendChild(createUsageHistorySvgNode('line', {
                x1: margin.left,
                y1: y,
                x2: margin.left + plotWidth,
                y2: y,
                class: 'grid-line'
            }));
            const leftToken = Math.round((maxTokenDelta * percent) / 100);
            chart.appendChild(createUsageHistorySvgNode('text', {
                x: margin.left - typography.axisSideGap,
                y: y + typography.axisLabelOffset,
                'text-anchor': 'end',
                class: 'axis-label'
            })).textContent = formatCompactTokenCount(leftToken);
        });
        percentTicks.forEach(percent => {
            const y = yPercent(percent);
            chart.appendChild(createUsageHistorySvgNode('line', {
                x1: margin.left,
                y1: y,
                x2: margin.left + plotWidth,
                y2: y,
                class: 'grid-line'
            }));
            chart.appendChild(createUsageHistorySvgNode('text', {
                x: margin.left + plotWidth + typography.axisSideGap,
                y: y + typography.axisLabelOffset,
                'text-anchor': 'start',
                class: 'axis-label'
            })).textContent = formatUsageHistoryPercentTick(percent);
        });
    } else {
        percentTicks.forEach(percent => {
            const y = yPercent(percent);
            chart.appendChild(createUsageHistorySvgNode('line', {
                x1: margin.left,
                y1: y,
                x2: margin.left + plotWidth,
                y2: y,
                class: 'grid-line'
            }));
            const leftToken = Math.round((maxTokenDelta * percent) / percentScale);
            chart.appendChild(createUsageHistorySvgNode('text', {
                x: margin.left - typography.axisSideGap,
                y: y + typography.axisLabelOffset,
                'text-anchor': 'end',
                class: 'axis-label'
            })).textContent = formatCompactTokenCount(leftToken);
            chart.appendChild(createUsageHistorySvgNode('text', {
                x: margin.left + plotWidth + typography.axisSideGap,
                y: y + typography.axisLabelOffset,
                'text-anchor': 'start',
                class: 'axis-label'
            })).textContent = formatUsageHistoryPercentTick(percent);
        });
    }

    tokenDeltas.forEach((delta, index) => {
        if (delta <= 0) return;
        const x = xAt(index);
        const y = yToken(delta);
        const barHeight = Math.max(1, tokenBottom - y);
        chart.appendChild(createUsageHistorySvgNode('rect', {
            x: x - (barWidth / 2),
            y,
            width: barWidth,
            height: barHeight,
            rx: 1.5,
            class: 'token-bar'
        }));
    });

    const appendPercentLine = (values, className, pointColor) => {
        const points = [];
        values.forEach((value, index) => {
            if (!Number.isFinite(value)) return;
            points.push({ x: xAt(index), y: yPercent(value), value });
        });
        if (points.length < 2) return;
        const d = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`).join(' ');
        chart.appendChild(createUsageHistorySvgNode('path', {
            d,
            class: className
        }));
        points.forEach(point => {
            chart.appendChild(createUsageHistorySvgNode('circle', {
                cx: point.x,
                cy: point.y,
                r: 2.2,
                fill: pointColor,
                class: 'line-point'
            }));
        });
    };

    appendPercentLine(fiveHourUsed, 'five-hour-line', 'rgba(220, 90, 52, 0.95)');
    appendPercentLine(weeklyUsed, 'weekly-line', 'rgba(61, 130, 197, 0.95)');

    const firstLabel = formatUsageHistoryTickLabel(items[0]?.bucket_start);
    const middleLabel = formatUsageHistoryTickLabel(items[Math.floor((items.length - 1) / 2)]?.bucket_start);
    const lastLabel = formatUsageHistoryTickLabel(items[items.length - 1]?.bucket_start);
    [
        { x: margin.left, anchor: 'start', text: firstLabel },
        { x: margin.left + (plotWidth / 2), anchor: 'middle', text: middleLabel },
        { x: margin.left + plotWidth, anchor: 'end', text: lastLabel }
    ].forEach(label => {
        chart.appendChild(createUsageHistorySvgNode('text', {
            x: label.x,
            y: percentBottom + typography.bottomLabelGap,
            'text-anchor': label.anchor,
            class: 'axis-label'
        })).textContent = label.text;
    });
    return {
        rendered: true,
        percentScale,
        maxUsedPercent,
        mobileLayout,
        displayHeight
    };
}

function scheduleUsageHistoryOverlayRerender() {
    if (usageHistoryResizeRaf) return;
    const rerender = () => {
        usageHistoryResizeRaf = 0;
        if (!isUsageHistoryOverlayOpen()) return;
        renderUsageHistoryOverlay(state.settings?.usageHistory || null, usageHistoryLastRequestedHours);
    };
    if (typeof window.requestAnimationFrame === 'function') {
        usageHistoryResizeRaf = window.requestAnimationFrame(rerender);
        return;
    }
    usageHistoryResizeRaf = window.setTimeout(rerender, 0);
}

function renderUsageHistoryOverlay(history, requestedHours = USAGE_HISTORY_DEFAULT_HOURS) {
    const elements = getUsageHistoryOverlayElements();
    if (!elements) return;

    usageHistoryLastRequestedHours = Number.isFinite(Number(requestedHours)) && Number(requestedHours) > 0
        ? Math.round(Number(requestedHours))
        : USAGE_HISTORY_DEFAULT_HOURS;
    const itemCount = Number(history?.count);
    const updatedAt = formatResetTimestamp(history?.updated_at);
    const hoursText = usageHistoryLastRequestedHours;
    if (elements.subtitle) {
        elements.subtitle.textContent = buildUsageHistorySubtitle(hoursText);
    }

    if (elements.meta) {
        const metaParts = [];
        if (Number.isFinite(itemCount)) {
            metaParts.push(`Samples ${formatNumber(itemCount)}`);
        }
        if (updatedAt) {
            metaParts.push(`Updated ${updatedAt}`);
        }
        const retentionDays = Number(history?.retention_days);
        if (Number.isFinite(retentionDays) && retentionDays > 0) {
            metaParts.push(`Retention ${Math.round(retentionDays)}d`);
        }
        const relationScope = String(history?.relation?.scope || history?.token_delta_scope || '').trim().toLowerCase();
        if (relationScope === 'account') {
            metaParts.push('Relation account scope');
        } else if (relationScope === 'workspace') {
            metaParts.push('Relation workspace scope');
        }
        const pathText = typeof history?.path === 'string' ? history.path.trim() : '';
        const workspaceTokenPath = typeof history?.scope?.workspace_token_usage_path === 'string'
            ? history.scope.workspace_token_usage_path.trim()
            : '';
        const accountTokenPath = typeof history?.scope?.account_token_usage_path === 'string'
            ? history.scope.account_token_usage_path.trim()
            : '';
        const titleParts = [pathText, workspaceTokenPath, accountTokenPath].filter(Boolean);
        if (pathText) {
            metaParts.push(pathText);
            elements.meta.setAttribute('title', titleParts.join('\n'));
        } else if (titleParts.length > 0) {
            elements.meta.setAttribute('title', titleParts.join('\n'));
        } else {
            elements.meta.removeAttribute('title');
        }
        elements.meta.textContent = metaParts.join(' · ') || 'Usage 이력을 불러오는 중...';
    }

    const chartMetrics = renderUsageHistoryChart(history);
    const hasChart = Boolean(chartMetrics?.rendered);
    renderUsageHistoryScaleBadge(chartMetrics);
    renderUsageHistoryRatioCards(history);
    if (elements.empty) {
        elements.empty.classList.toggle('is-hidden', hasChart);
    }
    if (!hasChart && elements.meta) {
        elements.meta.textContent = '그래프를 그릴 수 있는 Usage 이력이 부족합니다. (최소 2개 샘플 필요)';
    }
    renderUsageHistoryLegend(history);
}

async function refreshUsageHistory({ hours = USAGE_HISTORY_DEFAULT_HOURS, silent = true } = {}) {
    const normalizedHours = Number.isFinite(Number(hours)) && Number(hours) > 0
        ? Math.round(Number(hours))
        : USAGE_HISTORY_DEFAULT_HOURS;
    usageHistoryLastRequestedHours = normalizedHours;
    const query = new URLSearchParams({ hours: String(normalizedHours) }).toString();
    try {
        const result = await fetchJson(`/api/codex/usage/history?${query}`, {
            cache: 'no-store',
            timeoutMs: USAGE_HISTORY_REQUEST_TIMEOUT_MS
        });
        const usage = result?.usage ?? null;
        const usageHistory = result?.usage_history ?? null;
        if (usage) {
            state.settings.usage = usage;
            updateUsageSummary(usage);
        }
        state.settings.usageHistory = usageHistory;
        if (isUsageHistoryOverlayOpen()) {
            renderUsageHistoryOverlay(usageHistory, normalizedHours);
        }
    } catch (error) {
        const message = normalizeError(error, 'Usage 이력 로드에 실패했습니다.');
        if (!silent) {
            setStatus(message, true);
        }
        const elements = getUsageHistoryOverlayElements();
        if (elements?.meta) {
            elements.meta.textContent = message;
        }
        if (elements?.chart) {
            elements.chart.innerHTML = '';
        }
        resetUsageHistoryChartPresentation(elements?.chartWrap, elements?.chart);
        if (elements?.scale) {
            elements.scale.textContent = 'Scale --';
        }
        if (elements?.ratios) {
            elements.ratios.innerHTML = '';
        }
        if (elements?.legend) {
            elements.legend.innerHTML = '';
        }
        if (elements?.empty) {
            elements.empty.classList.remove('is-hidden');
            elements.empty.textContent = 'Usage 이력을 불러오지 못했습니다.';
        }
    }
}

async function openUsageHistoryOverlay() {
    const elements = getUsageHistoryOverlayElements();
    if (!elements) return;
    if (isGitSyncOverlayOpen()) {
        closeGitSyncOverlay();
    }
    if (isGitBranchOverlayOpen()) {
        closeGitBranchOverlay();
    }
    if (isMessageLogOverlayOpen()) {
        closeMessageLogOverlay();
    }
    if (isFileBrowserOverlayOpen()) {
        closeFileBrowserOverlay();
    }
    if (isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    if (elements.meta) {
        elements.meta.textContent = '사용량 이력을 불러오는 중...';
    }
    if (elements.scale) {
        elements.scale.textContent = 'Scale --';
    }
    if (elements.ratios) {
        elements.ratios.innerHTML = '';
    }
    if (elements.legend) {
        elements.legend.innerHTML = '';
    }
    if (elements.chart) {
        elements.chart.innerHTML = '';
    }
    resetUsageHistoryChartPresentation(elements.chartWrap, elements.chart);
    if (elements.empty) {
        elements.empty.classList.add('is-hidden');
    }
    await refreshUsageHistory({ hours: USAGE_HISTORY_DEFAULT_HOURS, silent: true });
}

function closeUsageHistoryOverlay() {
    const elements = getUsageHistoryOverlayElements();
    if (!elements) return;
    resetUsageHistoryChartPresentation(elements.chartWrap, elements.chart);
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    if (
        !isGitBranchOverlayOpen()
        && !isGitSyncOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function getMessageLogOverlayElements() {
    const overlay = document.getElementById('codex-message-log-overlay');
    if (!overlay) return null;
    return {
        overlay,
        title: document.getElementById('codex-message-log-overlay-title'),
        subtitle: document.getElementById('codex-message-log-overlay-subtitle'),
        content: document.getElementById('codex-message-log-overlay-content')
    };
}

function isMessageLogOverlayOpen() {
    const overlay = document.getElementById('codex-message-log-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function normalizeMessageLogOverlayMode(value) {
    if (value === MESSAGE_LOG_OVERLAY_MODE_PREVIEW) {
        return MESSAGE_LOG_OVERLAY_MODE_PREVIEW;
    }
    return MESSAGE_LOG_OVERLAY_MODE_DETAIL;
}

function normalizeFilesystemPath(value) {
    const raw = typeof value === 'string' ? value.trim() : '';
    if (!raw) return '';
    let normalized = raw.replace(/\\/g, '/');
    if (normalized.length > 1) {
        normalized = normalized.replace(/\/+$/g, '');
    }
    return normalized;
}

function normalizePositiveInteger(value) {
    const parsed = Number.parseInt(String(value || '').trim(), 10);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return parsed;
}

function normalizeSourceLineNumber(value) {
    return normalizePositiveInteger(value);
}

function normalizeSourceColumnNumber(value) {
    return normalizePositiveInteger(value);
}

function formatFilesystemPathWithLocation(path, line = null, column = null) {
    const normalizedPath = normalizeFilesystemPath(path);
    if (!normalizedPath) return '';
    const normalizedLine = normalizeSourceLineNumber(line);
    if (!normalizedLine) return normalizedPath;
    const normalizedColumn = normalizeSourceColumnNumber(column);
    if (!normalizedColumn) return `${normalizedPath}:${normalizedLine}`;
    return `${normalizedPath}:${normalizedLine}:${normalizedColumn}`;
}

function parseAbsoluteFilesystemTarget(value, roots = getMessageLogPathRoots()) {
    const normalized = normalizeFilesystemPath(value);
    if (!normalized) return null;

    let path = normalized;
    let line = null;
    let column = null;

    const fragmentMatch = path.match(/^(.*)#L(\d+)(?:C(\d+))?$/i);
    if (fragmentMatch) {
        path = normalizeFilesystemPath(fragmentMatch[1]);
        line = normalizeSourceLineNumber(fragmentMatch[2]);
        column = normalizeSourceColumnNumber(fragmentMatch[3]);
    }

    const lineSuffixMatch = path.match(/^(.*):(\d+)(?::(\d+))?$/);
    if (lineSuffixMatch) {
        const candidatePath = normalizeFilesystemPath(lineSuffixMatch[1]);
        const candidateLine = normalizeSourceLineNumber(lineSuffixMatch[2]);
        const candidateColumn = normalizeSourceColumnNumber(lineSuffixMatch[3]);
        if (
            candidatePath
            && !/^[A-Za-z]:$/.test(candidatePath)
            && candidateLine
            && isLikelyAbsoluteFilesystemPath(candidatePath, roots)
        ) {
            path = candidatePath;
            line = candidateLine;
            column = candidateColumn;
        }
    }

    if (!isLikelyAbsoluteFilesystemPath(path, roots)) {
        return null;
    }

    return {
        absolutePath: path,
        line: normalizeSourceLineNumber(line),
        column: normalizeSourceColumnNumber(column)
    };
}

function getMessageLogPathRoots() {
    const roots = [];
    if (typeof document === 'undefined' || !document.body) {
        return roots;
    }
    const workspacePath = normalizeFilesystemPath(document.body.dataset?.workspacePath || '');
    const serverPath = normalizeFilesystemPath(document.body.dataset?.serverPath || '');
    if (workspacePath) {
        roots.push({ path: workspacePath, label: '$workspace' });
    }
    if (serverPath && serverPath !== workspacePath) {
        roots.push({ path: serverPath, label: '$server' });
    }
    roots.sort((a, b) => b.path.length - a.path.length);
    return roots;
}

function splitTrailingPathPunctuation(value) {
    const source = String(value || '');
    const match = source.match(/([.,;:!?]+)$/);
    if (!match) {
        return {
            core: source,
            suffix: ''
        };
    }
    return {
        core: source.slice(0, -match[1].length),
        suffix: match[1]
    };
}

function isLikelyAbsoluteFilesystemPath(path, roots = []) {
    const normalized = normalizeFilesystemPath(path);
    if (!normalized) return false;
    if (/^[A-Za-z]:\//.test(normalized)) {
        return normalized.split('/').filter(Boolean).length >= 2;
    }
    if (!normalized.startsWith('/')) return false;
    if (roots.some(root => normalized === root.path || normalized.startsWith(`${root.path}/`))) {
        return true;
    }
    return ABSOLUTE_PATH_HINT_PREFIXES.some(prefix => normalized.startsWith(prefix));
}

function shortenAbsoluteFilesystemPath(path, roots = []) {
    const normalized = normalizeFilesystemPath(path);
    if (!normalized) return '';
    const mapped = roots.find(root => normalized === root.path || normalized.startsWith(`${root.path}/`));
    if (mapped) {
        if (normalized === mapped.path) {
            return mapped.label;
        }
        return `${mapped.label}/${normalized.slice(mapped.path.length + 1)}`;
    }
    if (/^[A-Za-z]:\//.test(normalized)) {
        const drive = normalized.slice(0, 2);
        const segments = normalized.slice(2).split('/').filter(Boolean);
        if (segments.length <= 3) {
            return `${drive}/${segments.join('/')}`;
        }
        return `${drive}/.../${segments.slice(-2).join('/')}`;
    }
    if (!normalized.startsWith('/')) return normalized;
    const segments = normalized.split('/').filter(Boolean);
    if (segments.length <= 4) return normalized;
    return `/${segments[0]}/.../${segments.slice(-2).join('/')}`;
}

function shortenAbsolutePathsInText(text) {
    const source = String(text || '');
    if (!source) return '';
    const roots = getMessageLogPathRoots();
    const pathPattern = /(^|[\s([{"'`])((?:[A-Za-z]:[\\/]|\/)[^\s<>"'`)\]}]+)/g;
    return source.replace(pathPattern, (match, prefix, candidate) => {
        const candidateText = String(candidate || '');
        if (!candidateText) return match;
        const { core, suffix } = splitTrailingPathPunctuation(candidateText);
        const normalizedCore = normalizeFilesystemPath(core);
        if (!isLikelyAbsoluteFilesystemPath(normalizedCore, roots)) {
            return match;
        }
        const shortened = shortenAbsoluteFilesystemPath(normalizedCore, roots);
        if (!shortened || shortened === normalizedCore) {
            return `${prefix}${core}${suffix}`;
        }
        return `${prefix}${shortened}${suffix}`;
    });
}

function openMessageLogOverlay(title, detailText, subtitleText = '', options = {}) {
    const elements = getMessageLogOverlayElements();
    if (!elements) return;
    const normalizedTitle = String(title || '').trim();
    const normalizedText = normalizeDetailText(detailText);
    const normalizedSubtitle = String(subtitleText || '').trim();
    const requestedMode = options && typeof options === 'object' ? options.mode : '';
    const overlayMode = normalizeMessageLogOverlayMode(requestedMode);
    if (!normalizedText) return;
    if (isGitSyncOverlayOpen()) {
        closeGitSyncOverlay();
    }
    if (isGitBranchOverlayOpen()) {
        closeGitBranchOverlay();
    }
    if (isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    if (isUsageHistoryOverlayOpen()) {
        closeUsageHistoryOverlay();
    }
    if (elements.overlay) {
        elements.overlay.classList.remove(MESSAGE_LOG_OVERLAY_CLASS_PREVIEW, MESSAGE_LOG_OVERLAY_CLASS_DETAIL);
        elements.overlay.classList.add(
            overlayMode === MESSAGE_LOG_OVERLAY_MODE_PREVIEW
                ? MESSAGE_LOG_OVERLAY_CLASS_PREVIEW
                : MESSAGE_LOG_OVERLAY_CLASS_DETAIL
        );
        elements.overlay.dataset.viewMode = overlayMode;
    }
    if (elements.title) {
        elements.title.textContent = normalizedTitle || '상세 로그';
    }
    if (elements.subtitle) {
        const defaultSubtitle = overlayMode === MESSAGE_LOG_OVERLAY_MODE_PREVIEW
            ? '메시지 전체 보기'
            : '최종응답과 별도로 수집된 상세 내용';
        elements.subtitle.textContent = normalizedSubtitle || defaultSubtitle;
    }
    if (elements.content) {
        elements.content.innerHTML = renderMarkdown(normalizedText, {
            showCodeLineNumbers: true
        });
        hydrateRenderedMarkdown(elements.content);
        elements.content.scrollTop = 0;
    }
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
}

function closeMessageLogOverlay() {
    const elements = getMessageLogOverlayElements();
    if (!elements) return;
    elements.overlay.classList.remove('is-visible');
    elements.overlay.classList.remove(MESSAGE_LOG_OVERLAY_CLASS_PREVIEW, MESSAGE_LOG_OVERLAY_CLASS_DETAIL);
    delete elements.overlay.dataset.viewMode;
    elements.overlay.setAttribute('aria-hidden', 'true');
    if (
        !isGitBranchOverlayOpen()
        && !isGitSyncOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isUsageHistoryOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function normalizeFileBrowserRoot(value) {
    void value;
    return FILE_BROWSER_ROOT_WORKSPACE;
}

function normalizeFileBrowserRelativePath(value) {
    const source = String(value || '').trim().replace(/\\/g, '/');
    if (!source || source === '.') return '';
    return source
        .replace(/^\/+/g, '')
        .replace(/\/+/g, '/')
        .replace(/\/+$/g, '');
}

function buildFileBrowserRawFileUrl(root, relativePath) {
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(relativePath);
    if (!normalizedPath) return '';
    const encodedRoot = encodeURIComponent(normalizedRoot);
    const encodedPath = normalizedPath
        .split('/')
        .filter(Boolean)
        .map(segment => encodeURIComponent(segment))
        .join('/');
    if (!encodedPath) return '';
    return `${FILE_BROWSER_RAW_FILE_ENDPOINT}/${encodedRoot}/${encodedPath}`;
}

function getFileBrowserParentPath(path) {
    const normalized = normalizeFileBrowserRelativePath(path);
    if (!normalized || !normalized.includes('/')) return '';
    return normalized.slice(0, normalized.lastIndexOf('/'));
}

function buildFileBrowserChildPath(parentPath = '', childPath = '') {
    const normalizedParent = normalizeFileBrowserRelativePath(parentPath);
    const normalizedChild = normalizeFileBrowserRelativePath(childPath);
    if (!normalizedChild) return '';
    return normalizeFileBrowserRelativePath(
        normalizedParent ? `${normalizedParent}/${normalizedChild}` : normalizedChild
    );
}

function getFileBrowserRootLabel(root) {
    const normalizedRoot = normalizeFileBrowserRoot(root);
    return FILE_BROWSER_ROOT_LABELS[normalizedRoot] || normalizedRoot;
}

function formatFileBrowserDisplayPath(root, relativePath = '') {
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(relativePath);
    const displayPrefix = normalizedRoot === FILE_BROWSER_ROOT_WORKSPACE
        ? '$workspace'
        : getFileBrowserRootLabel(normalizedRoot);
    return normalizedPath ? `${displayPrefix}/${normalizedPath}` : displayPrefix;
}

function getFileBrowserAbsoluteRoots() {
    if (typeof document === 'undefined' || !document.body) {
        return [];
    }
    const roots = [];
    const workspacePath = normalizeFilesystemPath(document.body.dataset?.workspacePath || '');
    if (workspacePath) {
        roots.push({
            root: FILE_BROWSER_ROOT_WORKSPACE,
            path: workspacePath,
            display: '$workspace'
        });
    }
    roots.sort((a, b) => b.path.length - a.path.length);
    return roots;
}

function resolveFileBrowserTargetFromAbsolutePath(value) {
    const normalized = normalizeFilesystemPath(value);
    if (!normalized) return null;
    const roots = getFileBrowserAbsoluteRoots();
    const matched = roots.find(root => normalized === root.path || normalized.startsWith(`${root.path}/`));
    if (!matched) return null;
    if (normalized === matched.path) {
        return {
            root: matched.root,
            path: ''
        };
    }
    return {
        root: matched.root,
        path: normalized.slice(matched.path.length + 1)
    };
}

function getFileBrowserElements() {
    const overlay = document.getElementById('codex-file-browser-overlay');
    if (!overlay) return null;
    const panel = getFilePanelElementsByPrefix({
        scopeElement: overlay,
        rootElement: overlay,
        prefix: 'codex-file-browser',
        pathElement: document.getElementById('codex-file-browser-path')
    });
    if (!panel) return null;
    return {
        ...panel,
        overlay,
        subtitle: document.getElementById('codex-file-browser-overlay-subtitle'),
        backBtn: document.getElementById('codex-file-browser-back'),
        upBtn: document.getElementById('codex-file-browser-up'),
        refreshBtn: document.getElementById('codex-file-browser-refresh'),
        fullscreenBtn: document.getElementById('codex-file-browser-fullscreen'),
        showHiddenToggle: document.getElementById('codex-file-browser-show-hidden'),
        showPycacheToggle: document.getElementById('codex-file-browser-show-pycache'),
        rootButtons: Array.from(
            overlay.querySelectorAll('.file-browser-root-target[data-root-target]')
        )
    };
}

function isFileBrowserOverlayOpen() {
    const overlay = document.getElementById('codex-file-browser-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function syncFileBrowserOpenButtonState(isOpen = isFileBrowserOverlayOpen()) {
    const button = document.getElementById('codex-file-browser-open');
    if (!button) return;
    const opened = Boolean(isOpen);
    button.classList.toggle('is-active', opened);
    button.setAttribute('aria-pressed', opened ? 'true' : 'false');
    const label = opened ? 'Close file browser' : 'Open file browser';
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    syncHoverTooltipFromLabel(button, label);
}

function updateFileBrowserRootButtons() {
    const elements = getFileBrowserElements();
    if (!elements || !Array.isArray(elements.rootButtons)) return;
    elements.rootButtons.forEach(button => {
        const buttonRoot = normalizeFileBrowserRoot(button.dataset?.rootTarget);
        const isActive = buttonRoot === fileBrowserRoot;
        button.classList.toggle('is-active', isActive);
        button.classList.toggle('secondary', isActive);
        button.classList.toggle('ghost', !isActive);
    });
}

function setFilePanelPathLabel(pathElement, relativePath = '', absoluteRootPath = '') {
    if (!pathElement) return;
    const normalizedPath = normalizeFileBrowserRelativePath(relativePath);
    const display = formatFileBrowserDisplayPath(FILE_BROWSER_ROOT_WORKSPACE, normalizedPath);
    pathElement.textContent = display;

    const absoluteRoot = normalizeFilesystemPath(absoluteRootPath || '');
    const absolutePath = absoluteRoot
        ? (normalizedPath ? `${absoluteRoot}/${normalizedPath}` : absoluteRoot)
        : display;
    setHoverTooltip(pathElement, absolutePath);
}

function setFileBrowserPathLabel(root, relativePath = '', absoluteRootPath = '') {
    void root;
    const elements = getFileBrowserElements();
    setFilePanelPathLabel(elements?.path, relativePath, absoluteRootPath);
}

function setWorkModeFilePathLabel(root, relativePath = '', absoluteRootPath = '') {
    void root;
    const elements = getWorkModeFileElements();
    setFilePanelPathLabel(elements?.path, relativePath, absoluteRootPath);
}

function syncWorkModeHtmlPreviewViewerScrollSnapshot(viewerSnapshot = null) {
    const normalizedSnapshot = normalizeWorkModeFileViewerScrollSnapshot(
        viewerSnapshot,
        { includeContext: true }
    );
    if (!normalizedSnapshot) return null;
    const selectedRoot = normalizeFileBrowserRoot(workModeFileRoot);
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    const previewRoot = normalizeFileBrowserRoot(workModeHtmlPreviewState?.root || selectedRoot);
    const previewPath = normalizeFileBrowserRelativePath(workModeHtmlPreviewState?.path);
    if (!selectedPath || selectedPath !== previewPath || selectedRoot !== previewRoot) {
        return normalizedSnapshot;
    }
    setWorkModeHtmlPreviewState({
        root: previewRoot,
        path: previewPath,
        previewUrl: workModeHtmlPreviewState?.previewUrl || '',
        suspended: Boolean(workModeHtmlPreviewState?.suspended),
        viewerScroll: normalizedSnapshot
    });
    return normalizedSnapshot;
}

function setWorkModeHtmlPreviewState({
    root = workModeFileRoot,
    path = '',
    previewUrl = '',
    suspended = false,
    viewerScroll = null
} = {}) {
    workModeHtmlPreviewState = {
        root: normalizeFileBrowserRoot(root),
        path: normalizeFileBrowserRelativePath(path),
        previewUrl: String(previewUrl || '').trim(),
        suspended: Boolean(suspended),
        viewerScroll: normalizeWorkModeFileViewerScrollSnapshot(viewerScroll, { includeContext: true })
    };
    syncWorkModeHtmlPreviewOpenButton();
}

function clearWorkModeHtmlPreviewState() {
    setWorkModeHtmlPreviewState({
        root: workModeFileRoot,
        path: '',
        previewUrl: '',
        suspended: false,
        viewerScroll: null
    });
}

function getWorkModeHtmlPreviewLaunchUrl() {
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    const previewPath = normalizeFileBrowserRelativePath(workModeHtmlPreviewState?.path);
    if (!selectedPath || !previewPath || selectedPath !== previewPath) return '';
    const selectedRoot = normalizeFileBrowserRoot(workModeFileRoot);
    const previewRoot = normalizeFileBrowserRoot(workModeHtmlPreviewState?.root || selectedRoot);
    if (selectedRoot !== previewRoot) return '';
    const previewUrl = String(workModeHtmlPreviewState?.previewUrl || '').trim();
    return previewUrl || buildFileBrowserRawFileUrl(previewRoot, previewPath);
}

function getWorkModePreviewLaunchUrl() {
    const htmlPreviewUrl = getWorkModeHtmlPreviewLaunchUrl();
    if (htmlPreviewUrl) return htmlPreviewUrl;
    const selectedRoot = normalizeFileBrowserRoot(workModeFileRoot);
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    if (!selectedPath) return '';
    return buildFileBrowserRawFileUrl(selectedRoot, selectedPath);
}

function canOpenWorkModePreviewInNewWindow() {
    if (!isWorkModeEnabled()) return false;
    return Boolean(getWorkModePreviewLaunchUrl());
}

function syncWorkModeHtmlPreviewOpenButton({ loading = false } = {}) {
    const elements = getWorkModeFileElements();
    const button = elements?.openNewBtn;
    if (!button) return;
    const htmlPreviewUrl = getWorkModeHtmlPreviewLaunchUrl();
    const label = workModeHtmlPreviewState?.suspended && htmlPreviewUrl
        ? '새 창에서 HTML 미리보기 다시 열기'
        : '선택 파일 새 창에서 열기';
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    button.disabled = Boolean(loading) || !canOpenWorkModePreviewInNewWindow();
    syncHoverTooltipFromLabel(button, label);
}

function openWorkModePreviewInNewWindow() {
    const previewUrl = getWorkModePreviewLaunchUrl();
    if (!previewUrl) {
        showToast('새 창으로 열 수 있는 선택 파일이 없습니다.', {
            tone: 'default',
            durationMs: 2800
        });
        return false;
    }
    const opened = window.open(previewUrl, '_blank', 'noopener,noreferrer');
    if (!opened) {
        showToast('팝업이 차단되어 새 창을 열지 못했습니다.', {
            tone: 'error',
            durationMs: 3200
        });
        return false;
    }
    return true;
}

function suspendWorkModeHtmlPreviewForMobileTransition(elements, { viewerSnapshot = null } = {}) {
    if (!elements?.viewerContent) return false;
    const iframe = elements.viewerContent.querySelector('.file-browser-html-preview');
    if (!(iframe instanceof HTMLIFrameElement)) return false;
    const previewUrl = getWorkModeHtmlPreviewLaunchUrl();
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    if (!previewUrl || !selectedPath) return false;
    const normalizedViewerSnapshot = syncWorkModeHtmlPreviewViewerScrollSnapshot(
        viewerSnapshot || captureWorkModeFileViewerScrollSnapshot({ includeContext: true })
    );
    if (normalizedViewerSnapshot) {
        pendingWorkModeFileViewerScrollRestore = normalizedViewerSnapshot;
    }
    setFilePanelViewerPlaceholder(elements, 'HTML 미리보기가 일시중지되었습니다. 목록에서 다시 열면 복원됩니다.');
    setWorkModeHtmlPreviewState({
        root: workModeFileRoot,
        path: selectedPath,
        previewUrl,
        suspended: true,
        viewerScroll: normalizedViewerSnapshot
    });
    return true;
}

function setFilePanelDirectoryLoadingState(elements, {
    loading = false,
    message = '디렉터리 목록을 불러오는 중...',
    disableRefresh = loading,
    disableUp = loading,
    disableBack = loading,
    disableFullscreen = loading,
    disableColumnResize = loading,
    disableDivider = loading,
    onAfterToggle = null,
    syncHorizontalMetrics = null
} = {}) {
    if (!elements) return;
    const isLoading = Boolean(loading);
    if (elements.loading) {
        elements.loading.textContent = message;
        elements.loading.classList.toggle('is-hidden', !isLoading);
    }
    if (elements.list) {
        elements.list.classList.toggle('is-hidden', isLoading);
    }
    if (elements.empty) {
        elements.empty.classList.add('is-hidden');
    }
    if (elements.refreshBtn) {
        elements.refreshBtn.disabled = Boolean(disableRefresh);
    }
    if (elements.upBtn) {
        elements.upBtn.disabled = Boolean(disableUp);
    }
    if (elements.backBtn) {
        elements.backBtn.disabled = Boolean(disableBack);
    }
    if (elements.fullscreenBtn) {
        elements.fullscreenBtn.disabled = Boolean(disableFullscreen);
    }
    if (Array.isArray(elements.colResizers)) {
        const shouldDisableResize = Boolean(disableColumnResize);
        elements.colResizers.forEach(handle => {
            handle.disabled = shouldDisableResize;
        });
    }
    if (elements.divider) {
        elements.divider.classList.toggle('is-disabled', Boolean(disableDivider));
    }
    if (typeof onAfterToggle === 'function') {
        onAfterToggle(elements, isLoading);
    }
    if (typeof syncHorizontalMetrics === 'function') {
        requestAnimationFrame(() => {
            syncHorizontalMetrics();
        });
    }
}

function setWorkModeFileDirectoryLoading(isLoading, message = '디렉터리 목록을 불러오는 중...') {
    const elements = getWorkModeFileElements();
    if (!elements) return;
    const loading = Boolean(isLoading);
    const mobile = isMobileLayout();
    const fold = isFoldLayout();
    const canGoBack = isWorkModeEnabled() && (
        (mobile && workModeMobileView === WORK_MODE_MOBILE_VIEW_VIEWER)
        || (fold && normalizeWorkModeMobileBrowseView(workModeMobileBrowseView) === WORK_MODE_MOBILE_VIEW_VIEWER)
    );
    setFilePanelDirectoryLoadingState(elements, {
        loading,
        message,
        disableRefresh: loading,
        disableUp: loading || !workModeFilePath,
        disableBack: loading || !canGoBack,
        disableFullscreen: loading || !isWorkModeEnabled() || mobile,
        disableColumnResize: loading || !isWorkModeEnabled() || mobile || fold || workModeFileViewerFullscreen,
        disableDivider: loading || workModeFileViewerFullscreen || mobile || fold || !isWorkModeEnabled(),
        onAfterToggle: () => {
            if (elements.chatBtn) {
                const canMoveToChat = isWorkModeEnabled()
                    && mobile
                    && workModeMobileView !== WORK_MODE_MOBILE_VIEW_CHAT;
                elements.chatBtn.disabled = loading || !canMoveToChat;
            }
            syncWorkModeFileFullscreenButtonState();
            syncWorkModeHtmlPreviewOpenButton({ loading });
        },
        syncHorizontalMetrics: () => {
            syncWorkModeFileHorizontalScrollMetrics();
        }
    });
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_WORK_MODE);
    syncFilePanelViewerActionState(FILE_PANEL_VARIANT_WORK_MODE);
}

function setFileBrowserDirectoryLoading(isLoading, message = '디렉터리 목록을 불러오는 중...') {
    const elements = getFileBrowserElements();
    if (!elements) return;
    const loading = Boolean(isLoading);
    setFilePanelDirectoryLoadingState(elements, {
        loading,
        message,
        disableRefresh: loading,
        disableUp: loading || !fileBrowserPath,
        disableBack: loading || !isMobileLayout(),
        disableFullscreen: loading,
        disableColumnResize: loading || isMobileLayout() || fileBrowserViewerFullscreen || !isFileBrowserOverlayOpen(),
        disableDivider: loading || isMobileLayout() || fileBrowserViewerFullscreen || !isFileBrowserOverlayOpen(),
        onAfterToggle: () => {
            if (elements.showHiddenToggle) {
                elements.showHiddenToggle.disabled = loading;
            }
            if (elements.showPycacheToggle) {
                elements.showPycacheToggle.disabled = loading;
            }
            if (Array.isArray(elements.rootButtons)) {
                elements.rootButtons.forEach(button => {
                    button.disabled = loading;
                });
            }
        },
        syncHorizontalMetrics: () => {
            syncFileBrowserHorizontalScrollMetrics();
        }
    });
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_OVERLAY);
    syncFilePanelViewerActionState(FILE_PANEL_VARIANT_OVERLAY);
}

function setFilePanelViewerPlaceholder(elements, message = '파일을 선택하세요.') {
    if (!elements) return;
    setFilePanelViewerMetaText(elements, '파일을 선택하면 미리보기가 표시됩니다.');
    if (elements.viewerContent) {
        elements.viewerContent.innerHTML = '';
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = message;
        elements.viewerContent.appendChild(placeholder);
    }
}

function clearWorkModeFileViewer(message = '파일을 선택하세요.') {
    const elements = getWorkModeFileElements();
    setFilePanelViewerPlaceholder(elements, message);
    clearWorkModeHtmlPreviewState();
    resetFilePanelEditState(FILE_PANEL_VARIANT_WORK_MODE);
}

function createNormalizedRelativePathSet(paths) {
    const values = paths instanceof Set ? Array.from(paths) : (Array.isArray(paths) ? paths : []);
    const normalized = new Set();
    values.forEach(value => {
        const candidate = normalizeFileBrowserRelativePath(value);
        if (candidate) {
            normalized.add(candidate);
        }
    });
    return normalized;
}

function applyFilePanelSelectionState(listElement, selectedPath, bulkSelectedPaths = null) {
    if (!(listElement instanceof Element)) return;
    const normalizedSelection = normalizeFileBrowserRelativePath(selectedPath);
    const bulkSelection = createNormalizedRelativePathSet(bulkSelectedPaths);
    listElement.querySelectorAll('.work-mode-file-row[data-entry-path]').forEach(row => {
        const candidate = normalizeFileBrowserRelativePath(row.dataset?.entryPath || '');
        const checkbox = row.querySelector('input.work-mode-file-checkbox[data-entry-path]');
        const isBulkSelected = Boolean(candidate) && bulkSelection.has(candidate);
        row.classList.toggle('is-bulk-selected', isBulkSelected);
        if (checkbox instanceof HTMLInputElement) {
            checkbox.checked = isBulkSelected;
        }
    });
    listElement.querySelectorAll('button.work-mode-file-entry[data-entry-path]').forEach(button => {
        const candidate = normalizeFileBrowserRelativePath(button.dataset?.entryPath || '');
        button.classList.toggle('is-active', Boolean(normalizedSelection) && candidate === normalizedSelection);
    });
}

function renderFilePanelList(entries, {
    elements,
    selectedPath = '',
    bulkSelectedPaths = null,
    includeParentEntry = false,
    parentEntryPath = '',
    onToggleSelection = null,
    onOpenDirectory = null,
    onOpenFile = null,
    onAfterRender = null
} = {}) {
    if (!elements?.list) return;
    elements.list.innerHTML = '';
    const rows = Array.isArray(entries) ? entries : [];
    const normalizedParentPath = normalizeFileBrowserRelativePath(parentEntryPath);
    const bulkSelection = createNormalizedRelativePathSet(bulkSelectedPaths);

    const appendEntryRow = (entry, { isParentEntry = false } = {}) => {
        const entryPath = normalizeFileBrowserRelativePath(entry?.path || '');
        const entryType = entry?.type === 'dir' ? 'dir' : 'file';
        if (!entryPath && !isParentEntry) return;
        const resolvedPath = isParentEntry ? normalizedParentPath : entryPath;

        const item = document.createElement('li');
        item.className = 'file-browser-list-item';

        const row = document.createElement('div');
        row.className = 'work-mode-file-row';
        row.dataset.entryPath = resolvedPath;
        row.dataset.entryType = entryType;
        if (bulkSelection.has(resolvedPath)) {
            row.classList.add('is-bulk-selected');
        }

        const selectCell = document.createElement('div');
        selectCell.className = 'work-mode-file-cell-select';
        if (entryType === 'file' && !isParentEntry) {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'work-mode-file-checkbox';
            checkbox.dataset.entryPath = resolvedPath;
            checkbox.checked = bulkSelection.has(resolvedPath);
            checkbox.setAttribute('aria-label', `${String(entry?.name || resolvedPath)} 선택`);
            checkbox.addEventListener('click', event => {
                event.stopPropagation();
                if (typeof onToggleSelection === 'function') {
                    onToggleSelection(resolvedPath, entry, {
                        checked: checkbox.checked,
                        shiftKey: Boolean(event.shiftKey)
                    });
                }
            });
            selectCell.appendChild(checkbox);
        } else {
            const spacer = document.createElement('span');
            spacer.className = 'work-mode-file-checkbox-spacer';
            spacer.setAttribute('aria-hidden', 'true');
            selectCell.appendChild(spacer);
        }
        row.appendChild(selectCell);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = `work-mode-file-entry${entryType === 'dir' ? ' is-dir' : ''}${isParentEntry ? ' is-parent-entry' : ''}`;
        button.dataset.entryPath = resolvedPath;
        button.dataset.entryType = entryType;
        if (isParentEntry) {
            button.dataset.parentEntry = 'true';
        }

        const name = document.createElement('span');
        name.className = 'work-mode-file-cell work-mode-file-cell-name';
        const baseName = isParentEntry ? '..' : String(entry?.name || entryPath);
        name.textContent = isParentEntry
            ? '..'
            : (entryType === 'dir' ? `${baseName}/` : baseName);
        name.title = isParentEntry ? '상위 폴더로 이동' : baseName;
        button.appendChild(name);

        const size = document.createElement('span');
        size.className = 'work-mode-file-cell work-mode-file-cell-size';
        const sizeText = formatFileBrowserSize(entry?.size);
        size.textContent = isParentEntry ? '-' : (entryType === 'dir' ? '-' : sizeText);
        button.appendChild(size);

        const modified = document.createElement('span');
        modified.className = 'work-mode-file-cell work-mode-file-cell-modified';
        const modifiedText = isParentEntry ? '-' : formatFileBrowserModifiedAt(entry?.modified_at);
        modified.textContent = modifiedText;
        modified.title = modifiedText;
        button.appendChild(modified);

        button.addEventListener('click', () => {
            if (entryType === 'dir') {
                if (typeof onOpenDirectory === 'function') {
                    onOpenDirectory(resolvedPath, entry);
                }
                return;
            }
            if (typeof onOpenFile === 'function') {
                onOpenFile(resolvedPath, entry);
            }
        });

        row.appendChild(button);
        item.appendChild(row);
        elements.list.appendChild(item);
    };

    if (includeParentEntry) {
        appendEntryRow({
            path: normalizedParentPath,
            type: 'dir',
            name: '..'
        }, { isParentEntry: true });
    }

    rows.forEach(entry => {
        appendEntryRow(entry);
    });
    applyFilePanelSelectionState(elements.list, selectedPath, bulkSelectedPaths);
    if (typeof onAfterRender === 'function') {
        onAfterRender();
    }
}

function applyWorkModeFileSelectionState() {
    const elements = getWorkModeFileElements();
    applyFilePanelSelectionState(elements?.list, workModeFileSelectedPath, workModeFileSelectedPaths);
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_WORK_MODE);
}

function getFilePanelSelectedPaths(variant) {
    return normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
        ? fileBrowserSelectedPaths
        : workModeFileSelectedPaths;
}

function setFilePanelSelectedPaths(variant, nextPaths) {
    const normalized = createNormalizedRelativePathSet(nextPaths);
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        fileBrowserSelectedPaths = normalized;
        return;
    }
    workModeFileSelectedPaths = normalized;
}

function getFilePanelSelectionAnchorPath(variant) {
    return normalizeFileBrowserRelativePath(
        normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
            ? fileBrowserSelectionAnchorPath
            : workModeFileSelectionAnchorPath
    );
}

function setFilePanelSelectionAnchorPath(variant, value = '') {
    const normalized = normalizeFileBrowserRelativePath(value);
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        fileBrowserSelectionAnchorPath = normalized;
        return;
    }
    workModeFileSelectionAnchorPath = normalized;
}

function getFilePanelCachedEntries(variant) {
    return normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
        ? fileBrowserCachedEntries
        : workModeFileCachedEntries;
}

function getFilePanelCurrentPath(variant) {
    return normalizeFileBrowserRelativePath(
        normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
            ? fileBrowserPath
            : workModeFilePath
    );
}

function getFilePanelCurrentRoot(variant) {
    return normalizeFileBrowserRoot(
        normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
            ? fileBrowserRoot
            : workModeFileRoot
    );
}

function getFilePanelPreviewPath(variant) {
    return normalizeFileBrowserRelativePath(
        normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
            ? fileBrowserSelectedPath
            : workModeFileSelectedPath
    );
}

function setFilePanelPreviewPath(variant, value = '') {
    const normalized = normalizeFileBrowserRelativePath(value);
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        fileBrowserSelectedPath = normalized;
        return;
    }
    workModeFileSelectedPath = normalized;
}

function isFilePanelBulkActionInFlight(variant) {
    return normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY
        ? fileBrowserBulkActionInFlight
        : workModeFileBulkActionInFlight;
}

function setFilePanelBulkActionInFlight(variant, inFlight) {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        fileBrowserBulkActionInFlight = Boolean(inFlight);
    } else {
        workModeFileBulkActionInFlight = Boolean(inFlight);
    }
    syncFilePanelSelectionBar(variant);
}

function getFilePanelVisibleFileEntries(variant) {
    const model = buildFilePanelDirectoryEntriesModel(
        getFilePanelCachedEntries(variant),
        getFilePanelCurrentPath(variant)
    );
    return Array.isArray(model?.visibleEntries)
        ? model.visibleEntries.filter(entry => entry?.type === 'file')
        : [];
}

function getFilePanelVisibleFilePaths(variant) {
    return getFilePanelVisibleFileEntries(variant)
        .map(entry => normalizeFileBrowserRelativePath(entry?.path || ''))
        .filter(Boolean);
}

function getFilePanelFileEntryMap(variant) {
    const entries = Array.isArray(getFilePanelCachedEntries(variant)) ? getFilePanelCachedEntries(variant) : [];
    const map = new Map();
    entries.forEach(entry => {
        const normalizedPath = normalizeFileBrowserRelativePath(entry?.path || '');
        if (!normalizedPath || entry?.type !== 'file') return;
        map.set(normalizedPath, entry);
    });
    return map;
}

function isFilePanelLoading(elements) {
    return Boolean(elements?.loading && !elements.loading.classList.contains('is-hidden'));
}

function syncFilePanelSelectionBar(variant) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    if (!elements) return;
    const root = getFilePanelCurrentRoot(variant);
    const currentPath = getFilePanelCurrentPath(variant);
    const currentDisplayPath = formatFileBrowserDisplayPath(root, currentPath);
    const selectedPaths = getFilePanelSelectedPaths(variant);
    const selectedCount = selectedPaths.size;
    const visibleFilePaths = getFilePanelVisibleFilePaths(variant);
    const visibleFileCount = visibleFilePaths.length;
    const allVisibleFilesSelected = visibleFileCount > 0
        && visibleFilePaths.every(path => selectedPaths.has(path));
    const entryMap = getFilePanelFileEntryMap(variant);
    let totalSelectedSize = 0;
    selectedPaths.forEach(path => {
        const numeric = Number(entryMap.get(path)?.size);
        if (Number.isFinite(numeric) && numeric > 0) {
            totalSelectedSize += numeric;
        }
    });
    if (elements.selectionSummary) {
        const parts = [`선택 ${selectedCount}개`];
        if (selectedCount > 0 && totalSelectedSize > 0) {
            parts.push(formatFileBrowserSize(totalSelectedSize));
        } else if (selectedCount === 0) {
            parts.push(`현재 파일 ${visibleFileCount}개`);
        }
        elements.selectionSummary.textContent = parts.join(' · ');
    }
    if (elements.selectionActions) {
        elements.selectionActions.classList.toggle('is-hidden', selectedCount <= 0);
    }
    const isBusy = isFilePanelLoading(elements) || isFilePanelBulkActionInFlight(variant);
    if (elements.newFileBtn) {
        updateFilePanelActionButtonLabel(
            elements.newFileBtn,
            `현재 폴더에 새 파일 만들기 (${currentDisplayPath})`
        );
        elements.newFileBtn.disabled = isBusy;
        syncHoverTooltipFromLabel(elements.newFileBtn);
    }
    if (elements.deleteDirectoryBtn) {
        updateFilePanelActionButtonLabel(
            elements.deleteDirectoryBtn,
            currentPath
                ? `현재 폴더 삭제 (${currentDisplayPath})`
                : '루트 폴더는 삭제할 수 없습니다.'
        );
        elements.deleteDirectoryBtn.disabled = isBusy || !currentPath;
        syncHoverTooltipFromLabel(elements.deleteDirectoryBtn);
    }
    if (elements.addContextBtn) {
        elements.addContextBtn.disabled = isBusy || selectedCount <= 0;
    }
    if (elements.moveBtn) {
        elements.moveBtn.disabled = isBusy || selectedCount <= 0;
    }
    if (elements.selectAllBtn) {
        const selectAllLabel = allVisibleFilesSelected
            ? '현재 목록의 파일 선택 해제'
            : '현재 목록의 파일 전체 선택';
        updateFilePanelActionButtonLabel(elements.selectAllBtn, selectAllLabel);
        elements.selectAllBtn.setAttribute('aria-pressed', String(allVisibleFilesSelected));
        elements.selectAllBtn.disabled = isBusy || visibleFileCount <= 0;
        syncHoverTooltipFromLabel(elements.selectAllBtn);
    }
    if (elements.clearSelectionBtn) {
        elements.clearSelectionBtn.disabled = isBusy || selectedCount <= 0;
    }
    if (elements.downloadBtn) {
        elements.downloadBtn.disabled = isBusy || selectedCount <= 0;
    }
    if (elements.deleteBtn) {
        elements.deleteBtn.disabled = isBusy || selectedCount <= 0;
    }
}

function applyFilePanelSelectionStateForVariant(variant) {
    const config = getFilePanelVariantConfig(variant);
    const elements = config.getElements();
    applyFilePanelSelectionState(
        elements?.list,
        getFilePanelPreviewPath(variant),
        getFilePanelSelectedPaths(variant)
    );
    syncFilePanelSelectionBar(variant);
}

function clearFilePanelSelection(variant, { keepAnchor = false } = {}) {
    setFilePanelSelectedPaths(variant, []);
    if (!keepAnchor) {
        setFilePanelSelectionAnchorPath(variant, '');
    }
    applyFilePanelSelectionStateForVariant(variant);
}

function setFilePanelSelectionToVisibleFiles(variant) {
    const visiblePaths = getFilePanelVisibleFilePaths(variant);
    setFilePanelSelectedPaths(variant, visiblePaths);
    setFilePanelSelectionAnchorPath(variant, visiblePaths[visiblePaths.length - 1] || '');
    applyFilePanelSelectionStateForVariant(variant);
}

function areAllFilePanelVisibleFilesSelected(variant) {
    const visiblePaths = getFilePanelVisibleFilePaths(variant);
    if (visiblePaths.length === 0) return false;
    const selectedPaths = getFilePanelSelectedPaths(variant);
    return visiblePaths.every(path => selectedPaths.has(path));
}

function toggleFilePanelVisibleFileSelection(variant) {
    if (areAllFilePanelVisibleFilesSelected(variant)) {
        clearFilePanelSelection(variant);
        return;
    }
    setFilePanelSelectionToVisibleFiles(variant);
}

function pruneFilePanelSelectionToEntries(variant, entries) {
    const filePaths = new Set();
    (Array.isArray(entries) ? entries : []).forEach(entry => {
        const normalizedPath = normalizeFileBrowserRelativePath(entry?.path || '');
        if (normalizedPath && entry?.type === 'file') {
            filePaths.add(normalizedPath);
        }
    });
    const currentSelection = getFilePanelSelectedPaths(variant);
    const nextSelection = Array.from(currentSelection).filter(path => filePaths.has(path));
    setFilePanelSelectedPaths(variant, nextSelection);
    const anchorPath = getFilePanelSelectionAnchorPath(variant);
    if (anchorPath && !filePaths.has(anchorPath)) {
        setFilePanelSelectionAnchorPath(variant, '');
    }
}

function toggleFilePanelEntrySelection(variant, entryPath, { checked = null, shiftKey = false } = {}) {
    const normalizedPath = normalizeFileBrowserRelativePath(entryPath);
    if (!normalizedPath) return;
    const visiblePaths = getFilePanelVisibleFilePaths(variant);
    if (!visiblePaths.includes(normalizedPath)) return;

    const nextSelection = new Set(getFilePanelSelectedPaths(variant));
    const anchorPath = getFilePanelSelectionAnchorPath(variant);
    const nextChecked = typeof checked === 'boolean' ? checked : !nextSelection.has(normalizedPath);

    if (shiftKey && anchorPath && visiblePaths.includes(anchorPath)) {
        const startIndex = visiblePaths.indexOf(anchorPath);
        const endIndex = visiblePaths.indexOf(normalizedPath);
        const [rangeStart, rangeEnd] = startIndex <= endIndex
            ? [startIndex, endIndex]
            : [endIndex, startIndex];
        visiblePaths.slice(rangeStart, rangeEnd + 1).forEach(path => {
            if (nextChecked) {
                nextSelection.add(path);
            } else {
                nextSelection.delete(path);
            }
        });
    } else if (nextChecked) {
        nextSelection.add(normalizedPath);
    } else {
        nextSelection.delete(normalizedPath);
    }

    setFilePanelSelectedPaths(variant, nextSelection);
    setFilePanelSelectionAnchorPath(variant, normalizedPath);
    applyFilePanelSelectionStateForVariant(variant);
}

function renderWorkModeFileList(entries, { includeParentEntry = false, parentEntryPath = '' } = {}) {
    const elements = getWorkModeFileElements();
    renderFilePanelList(entries, {
        elements,
        selectedPath: workModeFileSelectedPath,
        bulkSelectedPaths: workModeFileSelectedPaths,
        includeParentEntry,
        parentEntryPath,
        onToggleSelection: (entryPath, entry, options) => {
            void entry;
            toggleFilePanelEntrySelection(FILE_PANEL_VARIANT_WORK_MODE, entryPath, options);
        },
        onOpenDirectory: entryPath => {
            if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_WORK_MODE)) return;
            workModeFileSelectedPath = '';
            clearFilePanelSelection(FILE_PANEL_VARIANT_WORK_MODE);
            schedulePersistWorkModeFileViewState();
            if (isMobileLayout()) {
                setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_LIST);
            } else if (isFoldLayout()) {
                setWorkModeBrowseView(WORK_MODE_MOBILE_VIEW_LIST);
            }
            void refreshWorkModeFileDirectory({
                root: workModeFileRoot,
                path: entryPath,
                force: true
            }).then(result => {
                if (!result) return;
                clearWorkModeFileViewer('파일을 선택하세요.');
            });
        },
        onOpenFile: entryPath => {
            void openFileInWorkModePanel(entryPath, { root: workModeFileRoot });
        },
        onAfterRender: () => {
            requestAnimationFrame(() => {
                syncWorkModeFileHorizontalScrollMetrics();
            });
        }
    });
}

function buildFilePanelDirectoryEntriesModel(entries, currentPath = '') {
    const allEntries = Array.isArray(entries) ? entries : [];
    const visibleEntries = filterFileBrowserEntries(allEntries);
    const normalizedPath = normalizeFileBrowserRelativePath(currentPath);
    const hasParentEntry = Boolean(normalizedPath);
    return {
        allEntries,
        visibleEntries,
        hasParentEntry,
        parentEntryPath: getFileBrowserParentPath(normalizedPath),
        filteredCount: Math.max(0, allEntries.length - visibleEntries.length)
    };
}

function renderFilePanelDirectorySummary(elements, model, { truncated = false } = {}) {
    if (!elements || !model) return;
    const {
        allEntries = [],
        visibleEntries = [],
        hasParentEntry = false,
        filteredCount = 0
    } = model;
    if (elements.meta) {
        const countText = filteredCount > 0
            ? `항목 ${visibleEntries.length}/${allEntries.length}개`
            : `항목 ${visibleEntries.length}개`;
        const extra = [];
        if (filteredCount > 0) {
            extra.push(`숨김 ${filteredCount}개`);
        }
        if (truncated) {
            extra.push('일부만 표시됨');
        }
        elements.meta.textContent = extra.length > 0 ? `${countText} (${extra.join(', ')})` : countText;
    }
    if (elements.empty) {
        if (visibleEntries.length === 0 && allEntries.length > 0) {
            elements.empty.textContent = '필터 조건으로 모든 항목이 숨겨져 있습니다.';
        } else {
            elements.empty.textContent = '표시할 파일/폴더가 없습니다.';
        }
        const hasRows = visibleEntries.length > 0 || hasParentEntry;
        elements.empty.classList.toggle('is-hidden', hasRows);
    }
    if (elements.list) {
        const hasRows = visibleEntries.length > 0 || hasParentEntry;
        elements.list.classList.toggle('is-hidden', !hasRows);
    }
}

function renderWorkModeFileDirectoryEntries(entries, { truncated = false } = {}) {
    const elements = getWorkModeFileElements();
    if (!elements) return;
    const model = buildFilePanelDirectoryEntriesModel(entries, workModeFilePath);

    renderWorkModeFileList(model.visibleEntries, {
        includeParentEntry: model.hasParentEntry,
        parentEntryPath: model.parentEntryPath
    });
    renderFilePanelDirectorySummary(elements, model, { truncated });
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_WORK_MODE);
}

async function refreshWorkModeFileDirectory(
    {
        root = workModeFileRoot,
        path = workModeFilePath,
        force = false,
        restoreScrollSnapshot = null
    } = {}
) {
    void force;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_WORK_MODE)) {
        return null;
    }
    const elements = getWorkModeFileElements();
    if (!elements) return null;
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    const requestedScrollRestore = normalizeWorkModeFileScrollSnapshot(restoreScrollSnapshot);

    setWorkModeFileDirectoryLoading(true);
    if (elements.meta) {
        elements.meta.textContent = '디렉터리 목록을 불러오는 중...';
    }

    try {
        const result = await fetchFileBrowserDirectory(normalizedRoot, normalizedPath);
        workModeFileRoot = normalizeFileBrowserRoot(result?.root || normalizedRoot);
        workModeFilePath = normalizeFileBrowserRelativePath(result?.path || normalizedPath);
        setWorkModeFilePathLabel(workModeFileRoot, workModeFilePath, result?.root_path || '');

        const entries = Array.isArray(result?.entries) ? result.entries : [];
        workModeFileCachedEntries = entries;
        workModeFileCachedTruncated = Boolean(result?.truncated);
        pruneFilePanelSelectionToEntries(FILE_PANEL_VARIANT_WORK_MODE, entries);
        renderWorkModeFileDirectoryEntries(workModeFileCachedEntries, {
            truncated: workModeFileCachedTruncated
        });
        if (elements.upBtn) {
            const canGoUp = Boolean(result?.can_go_up) || Boolean(workModeFilePath);
            elements.upBtn.disabled = !canGoUp;
        }
        if (elements.loading) {
            elements.loading.classList.add('is-hidden');
        }
        const pendingRestore = requestedScrollRestore
            || consumePendingWorkModeFileScrollRestore(workModeFileRoot, workModeFilePath);
        if (pendingRestore) {
            requestAnimationFrame(() => {
                syncWorkModeFileHorizontalScrollMetrics();
                applyWorkModeFileScrollSnapshot(pendingRestore);
                syncWorkModeFileHorizontalScrollMetrics();
            });
        }
        schedulePersistWorkModeFileViewState();
        return result;
    } catch (error) {
        workModeFileCachedEntries = [];
        workModeFileCachedTruncated = false;
        if (elements.meta) {
            elements.meta.textContent = normalizeError(error, '디렉터리 목록을 불러오지 못했습니다.');
        }
        if (elements.list) {
            elements.list.classList.add('is-hidden');
            elements.list.innerHTML = '';
        }
        if (elements.empty) {
            elements.empty.textContent = '디렉터리 목록을 불러오지 못했습니다.';
            elements.empty.classList.remove('is-hidden');
        }
        showToast(normalizeError(error, '작업 모드 문서 목록 조회에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return null;
    } finally {
        setWorkModeFileDirectoryLoading(false);
    }
}

async function openFileInWorkModePanel(
    path,
    {
        root = workModeFileRoot,
        fallbackToDirectory = false,
        showViewerOnSuccess = true,
        line = null,
        column = null,
        restoreViewerScrollSnapshot = null
    } = {}
) {
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    if (!normalizedPath) return null;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_WORK_MODE)) {
        return null;
    }
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const requestedLine = normalizeSourceLineNumber(line);
    const requestedColumn = normalizeSourceColumnNumber(column);
    const elements = getWorkModeFileElements();
    if (!elements) return null;
    clearWorkModeHtmlPreviewState();
    resetFilePanelEditState(FILE_PANEL_VARIANT_WORK_MODE, { root: normalizedRoot });

    const displayPath = formatFilesystemPathWithLocation(normalizedPath, requestedLine, requestedColumn);
    setFilePanelViewerMetaText(elements, `${displayPath} · 불러오는 중...`);
    if (elements.viewerContent) {
        elements.viewerContent.innerHTML = '';
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = '파일을 불러오는 중...';
        elements.viewerContent.appendChild(placeholder);
    }

    try {
        const result = await fetchFileBrowserFile(normalizedRoot, normalizedPath);
        workModeFileSelectedPath = normalizeFileBrowserRelativePath(result?.path || normalizedPath);
        const viewerScrollSnapshot = !requestedLine
            ? (
                normalizeWorkModeFileViewerScrollSnapshot(restoreViewerScrollSnapshot)
                || consumePendingWorkModeFileViewerScrollRestore(
                    workModeFileRoot,
                    workModeFilePath,
                    workModeFileSelectedPath
                )
            )
            : null;
        await renderFileBrowserViewerIntoElements(elements, result, {
            root: normalizedRoot,
            line: requestedLine,
            column: requestedColumn
        });
        if (viewerScrollSnapshot && elements.viewerContent) {
            const viewerRenderToken = String(elements.viewerContent.dataset?.renderToken || '');
            applyWorkModeFileViewerScrollSnapshot(viewerScrollSnapshot, {
                renderToken: viewerRenderToken
            });
        }
        applyWorkModeFileSelectionState();
        if (showViewerOnSuccess && isMobileLayout()) {
            setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_VIEWER);
        } else if (showViewerOnSuccess && isFoldLayout()) {
            setWorkModeBrowseView(WORK_MODE_MOBILE_VIEW_VIEWER);
        }
        schedulePersistWorkModeFileViewState();
        return result;
    } catch (error) {
        const payload = getGitErrorPayload(error);
        if (fallbackToDirectory && payload?.error_code === 'not_file') {
            workModeFileSelectedPath = '';
            schedulePersistWorkModeFileViewState();
            if (isMobileLayout()) {
                setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_LIST);
            } else if (isFoldLayout()) {
                setWorkModeBrowseView(WORK_MODE_MOBILE_VIEW_LIST);
            }
            clearWorkModeFileViewer('폴더가 선택되었습니다. 목록에서 파일을 선택하세요.');
            await refreshWorkModeFileDirectory({
                root: normalizedRoot,
                path: normalizedPath,
                force: true
            });
            return {
                opened_directory: true,
                path: normalizedPath
            };
        }
        setFilePanelViewerMetaText(elements, normalizedPath);
        if (elements.viewerContent) {
            elements.viewerContent.innerHTML = '';
            const placeholder = document.createElement('div');
            placeholder.className = 'file-browser-placeholder';
            placeholder.textContent = normalizeError(error, '파일을 열지 못했습니다.');
            elements.viewerContent.appendChild(placeholder);
        }
        clearWorkModeHtmlPreviewState();
        showToast(normalizeError(error, '작업 모드 파일 열기에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return null;
    }
}

function openWorkModeFileTarget(target, options = {}) {
    if (!target) return false;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_WORK_MODE)) {
        return false;
    }
    const requestedLine = normalizeSourceLineNumber(options?.line);
    const requestedColumn = normalizeSourceColumnNumber(options?.column);
    const requestedRoot = normalizeFileBrowserRoot(target.root);
    const requestedFilePath = normalizeFileBrowserRelativePath(target.path || '');
    const requestedPath = normalizeFileBrowserRelativePath(
        requestedFilePath ? getFileBrowserParentPath(requestedFilePath) : ''
    );

    workModeFileRoot = requestedRoot;
    workModeFilePath = requestedPath;
    workModeFileSelectedPath = requestedFilePath;
    setFilePanelSelectedPaths(FILE_PANEL_VARIANT_WORK_MODE, []);
    setFilePanelSelectionAnchorPath(FILE_PANEL_VARIANT_WORK_MODE, '');
    schedulePersistWorkModeFileViewState();
    if (isMobileLayout()) {
        setWorkModeMobileView(
            requestedFilePath ? WORK_MODE_MOBILE_VIEW_VIEWER : WORK_MODE_MOBILE_VIEW_LIST
        );
    } else if (isFoldLayout()) {
        setWorkModeBrowseView(
            requestedFilePath ? WORK_MODE_MOBILE_VIEW_VIEWER : WORK_MODE_MOBILE_VIEW_LIST
        );
    }
    setWorkModeFilePathLabel(workModeFileRoot, workModeFilePath);
    if (requestedFilePath) {
        const lineSuffix = requestedLine
            ? (requestedColumn ? ` (line ${requestedLine}:${requestedColumn})` : ` (line ${requestedLine})`)
            : '';
        clearWorkModeFileViewer(`파일을 여는 중...${lineSuffix}`);
    } else {
        clearWorkModeFileViewer('파일을 선택하세요.');
    }

    void (async () => {
        const listed = await refreshWorkModeFileDirectory({
            root: requestedRoot,
            path: requestedPath,
            force: true
        });
        if (!listed || !requestedFilePath) return;
        await openFileInWorkModePanel(requestedFilePath, {
            root: requestedRoot,
            fallbackToDirectory: true,
            line: requestedLine,
            column: requestedColumn
        });
    })();
    return true;
}

async function ensureWorkModeFilePanelContent() {
    if (!isWorkModeEnabled()) return;
    const hasEntries = Array.isArray(workModeFileCachedEntries) && workModeFileCachedEntries.length > 0;
    const hasSelection = Boolean(normalizeFileBrowserRelativePath(workModeFileSelectedPath));
    if (!hasEntries) {
        const listed = await refreshWorkModeFileDirectory({
            root: workModeFileRoot,
            path: workModeFilePath,
            force: true
        });
        if (!listed) return;
    }
    if (isMobileLayout()) {
        if (workModeMobileView !== WORK_MODE_MOBILE_VIEW_VIEWER) {
            return;
        }
    }
    if (hasSelection) {
        await openFileInWorkModePanel(workModeFileSelectedPath, {
            root: workModeFileRoot,
            fallbackToDirectory: true,
            showViewerOnSuccess: false
        });
    } else if (!hasEntries) {
        clearWorkModeFileViewer('파일을 선택하세요.');
    }
}

async function refreshWorkModeFilePreviewSelection({ restoreViewerScrollSnapshot = null } = {}) {
    const selectedPath = normalizeFileBrowserRelativePath(workModeFileSelectedPath);
    if (!selectedPath) return null;
    return openFileInWorkModePanel(selectedPath, {
        root: workModeFileRoot,
        fallbackToDirectory: true,
        showViewerOnSuccess: false,
        restoreViewerScrollSnapshot
    });
}

function readFileBrowserSplitPreference() {
    try {
        return normalizeWorkModeFileSplitRatio(localStorage.getItem(FILE_BROWSER_SPLIT_KEY));
    } catch (error) {
        return WORK_MODE_FILE_DEFAULT_SPLIT;
    }
}

function persistFileBrowserSplitPreference(ratio) {
    try {
        localStorage.setItem(FILE_BROWSER_SPLIT_KEY, String(normalizeWorkModeFileSplitRatio(ratio)));
    } catch (error) {
        void error;
    }
}

function readFileBrowserColumnsPreference() {
    const fallback = {
        name: WORK_MODE_FILE_COLUMN_DEFAULTS.name,
        size: WORK_MODE_FILE_COLUMN_DEFAULTS.size,
        modified: WORK_MODE_FILE_COLUMN_DEFAULTS.modified
    };
    try {
        const raw = localStorage.getItem(FILE_BROWSER_COLUMNS_KEY);
        if (!raw) return fallback;
        const parsed = JSON.parse(raw);
        if (hasLegacyDefaultFileColumnWidths(parsed)) {
            return fallback;
        }
        return {
            name: normalizeWorkModeFileColumnWidth('name', parsed?.name),
            size: normalizeWorkModeFileColumnWidth('size', parsed?.size),
            modified: normalizeWorkModeFileColumnWidth('modified', parsed?.modified)
        };
    } catch (error) {
        return fallback;
    }
}

function persistFileBrowserColumnsPreference() {
    try {
        localStorage.setItem(FILE_BROWSER_COLUMNS_KEY, JSON.stringify(fileBrowserColumnWidths));
    } catch (error) {
        void error;
    }
}

function applyFileBrowserSplitRatio(ratio = fileBrowserSplitRatio, { persist = false } = {}) {
    applyFilePanelSplitRatio(FILE_PANEL_VARIANT_OVERLAY, ratio, { persist });
}

function updateFileBrowserSplitFromPointer(clientX, { persist = false } = {}) {
    updateFilePanelSplitFromPointer(FILE_PANEL_VARIANT_OVERLAY, clientX, { persist });
}

function applyFileBrowserColumnWidths({ persist = false } = {}) {
    applyFilePanelColumnWidthsCore(FILE_PANEL_VARIANT_OVERLAY, { persist });
}

function syncFileBrowserHorizontalScrollMetrics() {
    syncFilePanelHorizontalScrollMetricsCore(FILE_PANEL_VARIANT_OVERLAY);
}

function handleFileBrowserGridScroll() {
    syncFilePanelHorizontalScrollFromGrid(FILE_PANEL_VARIANT_OVERLAY);
}

function handleFileBrowserHScroll() {
    syncFilePanelHorizontalScrollFromRail(FILE_PANEL_VARIANT_OVERLAY);
}

function stopFileBrowserResize() {
    if (fileBrowserResizePointerId === null) return;
    fileBrowserResizePointerId = null;
    syncWorkModeResizeBodyClass();
    window.removeEventListener('pointermove', handleFileBrowserResizePointerMove);
    window.removeEventListener('pointerup', handleFileBrowserResizePointerUp);
    window.removeEventListener('pointercancel', handleFileBrowserResizePointerUp);
}

function handleFileBrowserResizePointerMove(event) {
    if (fileBrowserResizePointerId === null || event.pointerId !== fileBrowserResizePointerId) return;
    if (!isFileBrowserOverlayOpen() || isMobileLayout() || fileBrowserViewerFullscreen) return;
    event.preventDefault();
    updateFileBrowserSplitFromPointer(event.clientX, { persist: false });
}

function handleFileBrowserResizePointerUp(event) {
    if (fileBrowserResizePointerId === null || event.pointerId !== fileBrowserResizePointerId) return;
    event.preventDefault();
    updateFileBrowserSplitFromPointer(event.clientX, { persist: true });
    stopFileBrowserResize();
}

function startFileBrowserResize(event) {
    if (!event || event.button !== 0) return;
    if (!isFileBrowserOverlayOpen() || isMobileLayout() || fileBrowserViewerFullscreen) return;
    const elements = getFileBrowserElements();
    if (elements?.divider?.classList.contains('is-disabled')) return;
    event.preventDefault();
    fileBrowserResizePointerId = event.pointerId;
    syncWorkModeResizeBodyClass();
    window.addEventListener('pointermove', handleFileBrowserResizePointerMove);
    window.addEventListener('pointerup', handleFileBrowserResizePointerUp);
    window.addEventListener('pointercancel', handleFileBrowserResizePointerUp);
}

function stopFileBrowserColumnResize() {
    if (!fileBrowserColumnResizeState) return;
    fileBrowserColumnResizeState = null;
    syncWorkModeResizeBodyClass();
    window.removeEventListener('pointermove', handleFileBrowserColumnResizePointerMove);
    window.removeEventListener('pointerup', handleFileBrowserColumnResizePointerUp);
    window.removeEventListener('pointercancel', handleFileBrowserColumnResizePointerUp);
}

function handleFileBrowserColumnResizePointerMove(event) {
    const state = fileBrowserColumnResizeState;
    if (!state || event.pointerId !== state.pointerId) return;
    event.preventDefault();
    const delta = Number(event.clientX) - state.startX;
    const width = state.startWidth + delta;
    const normalized = normalizeWorkModeFileColumnWidth(state.column, width);
    if (!normalized) return;
    fileBrowserColumnWidths[state.column] = normalized;
    applyFileBrowserColumnWidths({ persist: false });
}

function handleFileBrowserColumnResizePointerUp(event) {
    const state = fileBrowserColumnResizeState;
    if (!state || event.pointerId !== state.pointerId) return;
    event.preventDefault();
    applyFileBrowserColumnWidths({ persist: true });
    stopFileBrowserColumnResize();
}

function startFileBrowserColumnResize(event, column) {
    const targetColumn = normalizeWorkModeFileColumnName(column);
    if (!targetColumn || !event || event.button !== 0) return;
    if (!isFileBrowserOverlayOpen() || isMobileLayout() || fileBrowserViewerFullscreen) return;
    event.preventDefault();
    fileBrowserColumnResizeState = {
        pointerId: event.pointerId,
        column: targetColumn,
        startX: Number(event.clientX),
        startWidth: normalizeWorkModeFileColumnWidth(targetColumn, fileBrowserColumnWidths[targetColumn])
    };
    syncWorkModeResizeBodyClass();
    window.addEventListener('pointermove', handleFileBrowserColumnResizePointerMove);
    window.addEventListener('pointerup', handleFileBrowserColumnResizePointerUp);
    window.addEventListener('pointercancel', handleFileBrowserColumnResizePointerUp);
}

function setFileBrowserViewerFullscreen(isFullscreen) {
    const elements = getFileBrowserElements();
    if (!elements?.overlay) return;
    fileBrowserViewerFullscreen = Boolean(isFullscreen);
    const overlayFullscreen = !isMobileLayout() && fileBrowserViewerFullscreen;
    if (overlayFullscreen) {
        stopFileBrowserResize();
        stopFileBrowserColumnResize();
    }
    elements.overlay.classList.toggle('is-viewer-fullscreen', overlayFullscreen);
    if (elements.divider) {
        elements.divider.classList.toggle('is-disabled', overlayFullscreen);
    }
    if (Array.isArray(elements.colResizers)) {
        const disableColumnResize = overlayFullscreen || isMobileLayout() || !isFileBrowserOverlayOpen();
        elements.colResizers.forEach(handle => {
            handle.disabled = disableColumnResize;
        });
    }
    if (elements.fullscreenBtn) {
        const buttonLabel = fileBrowserViewerFullscreen ? '목록 보기' : '내용 전체화면';
        elements.fullscreenBtn.setAttribute('aria-pressed', fileBrowserViewerFullscreen ? 'true' : 'false');
        elements.fullscreenBtn.setAttribute('title', buttonLabel);
        elements.fullscreenBtn.textContent = buttonLabel;
    }
    if (!overlayFullscreen && isFileBrowserOverlayOpen()) {
        applyFileBrowserSplitRatio(fileBrowserSplitRatio, { persist: false });
    }
    syncFileBrowserHorizontalScrollMetrics();
}

function normalizeFileBrowserMobileView(value) {
    return value === FILE_BROWSER_MOBILE_VIEW_VIEWER
        ? FILE_BROWSER_MOBILE_VIEW_VIEWER
        : FILE_BROWSER_MOBILE_VIEW_LIST;
}

function setFileBrowserMobileView(view = FILE_BROWSER_MOBILE_VIEW_LIST) {
    const elements = getFileBrowserElements();
    if (!elements?.overlay) return;
    fileBrowserMobileView = normalizeFileBrowserMobileView(view);
    const mobile = isMobileLayout();
    elements.overlay.classList.toggle(
        'is-mobile-list-view',
        mobile && fileBrowserMobileView === FILE_BROWSER_MOBILE_VIEW_LIST
    );
    elements.overlay.classList.toggle(
        'is-mobile-viewer-view',
        mobile && fileBrowserMobileView === FILE_BROWSER_MOBILE_VIEW_VIEWER
    );
    if (elements.backBtn) {
        const showBack = mobile && fileBrowserMobileView === FILE_BROWSER_MOBILE_VIEW_VIEWER;
        elements.backBtn.classList.toggle('is-hidden', !showBack);
        elements.backBtn.disabled = !mobile;
    }
    if (elements.divider) {
        const disableDivider = mobile || fileBrowserViewerFullscreen || !isFileBrowserOverlayOpen();
        elements.divider.classList.toggle('is-disabled', disableDivider);
    }
    if (Array.isArray(elements.colResizers)) {
        const disableColumnResize = mobile || fileBrowserViewerFullscreen || !isFileBrowserOverlayOpen();
        elements.colResizers.forEach(handle => {
            handle.disabled = disableColumnResize;
        });
    }
    if (!mobile && isFileBrowserOverlayOpen() && !fileBrowserViewerFullscreen) {
        applyFileBrowserSplitRatio(fileBrowserSplitRatio, { persist: false });
    }
    syncFileBrowserHorizontalScrollMetrics();
}

function formatFileBrowserModifiedAt(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '--';
    const date = new Date(numeric * 1000);
    if (!Number.isFinite(date.getTime())) return '--';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hour}:${minute}`;
}

function isFileBrowserHiddenEntry(entry) {
    const name = String(entry?.name || '').trim();
    return name.startsWith('.');
}

function isFileBrowserPycacheEntry(entry) {
    const entryType = entry?.type === 'dir' ? 'dir' : 'file';
    if (entryType !== 'dir') return false;
    const name = String(entry?.name || '').trim().toLowerCase();
    if (!name) return false;
    if (name === '__pycache__') return true;
    return name.includes('pycache');
}

function filterFileBrowserEntries(entries) {
    const rows = Array.isArray(entries) ? entries : [];
    return rows.filter(entry => {
        if (!fileBrowserShowHiddenEntries && isFileBrowserHiddenEntry(entry)) {
            return false;
        }
        if (!fileBrowserShowPycacheEntries && isFileBrowserPycacheEntry(entry)) {
            return false;
        }
        return true;
    });
}

function updateFileBrowserFilterToggleState() {
    const elements = getFileBrowserElements();
    if (!elements) return;
    if (elements.showHiddenToggle) {
        elements.showHiddenToggle.checked = fileBrowserShowHiddenEntries;
    }
    if (elements.showPycacheToggle) {
        elements.showPycacheToggle.checked = fileBrowserShowPycacheEntries;
    }
}

function clearFileBrowserViewer(message = '파일을 선택하세요.') {
    const elements = getFileBrowserElements();
    setFilePanelViewerPlaceholder(elements, message);
    resetFilePanelEditState(FILE_PANEL_VARIANT_OVERLAY);
}

function formatFileBrowserSize(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return '--';
    if (numeric < 1024) return `${Math.round(numeric)} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let amount = numeric / 1024;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
    }
    const rounded = amount >= 100 ? amount.toFixed(0) : amount.toFixed(1);
    return `${rounded.replace(/\.0$/, '')} ${units[unitIndex]}`;
}

function applyFileBrowserSelectionState() {
    const elements = getFileBrowserElements();
    applyFilePanelSelectionState(elements?.list, fileBrowserSelectedPath, fileBrowserSelectedPaths);
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_OVERLAY);
}

function renderFileBrowserDirectoryEntries(entries, { truncated = false } = {}) {
    const elements = getFileBrowserElements();
    if (!elements) return;
    const model = buildFilePanelDirectoryEntriesModel(entries, fileBrowserPath);

    renderFileBrowserList(model.visibleEntries, {
        includeParentEntry: model.hasParentEntry,
        parentEntryPath: model.parentEntryPath
    });
    renderFilePanelDirectorySummary(elements, model, { truncated });
    syncFilePanelSelectionBar(FILE_PANEL_VARIANT_OVERLAY);
}

function rerenderFileBrowserDirectoryFromCache() {
    renderFileBrowserDirectoryEntries(fileBrowserCachedEntries, {
        truncated: fileBrowserCachedTruncated
    });
}

function renderFileBrowserList(entries, { includeParentEntry = false, parentEntryPath = '' } = {}) {
    const elements = getFileBrowserElements();
    renderFilePanelList(entries, {
        elements,
        selectedPath: fileBrowserSelectedPath,
        bulkSelectedPaths: fileBrowserSelectedPaths,
        includeParentEntry,
        parentEntryPath,
        onToggleSelection: (entryPath, entry, options) => {
            void entry;
            toggleFilePanelEntrySelection(FILE_PANEL_VARIANT_OVERLAY, entryPath, options);
        },
        onOpenDirectory: entryPath => {
            if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) return;
            fileBrowserSelectedPath = '';
            clearFilePanelSelection(FILE_PANEL_VARIANT_OVERLAY);
            setFileBrowserMobileView(FILE_BROWSER_MOBILE_VIEW_LIST);
            void refreshFileBrowserDirectory({
                root: fileBrowserRoot,
                path: entryPath,
                force: true
            }).then(result => {
                if (!result) return;
                clearFileBrowserViewer();
            });
        },
        onOpenFile: entryPath => {
            void openFileInBrowserOverlay(entryPath, { root: fileBrowserRoot });
        },
        onAfterRender: () => {
            requestAnimationFrame(() => {
                syncFileBrowserHorizontalScrollMetrics();
            });
        }
    });
}

async function fetchFileBrowserDirectory(root, path = '') {
    return fetchJson('/api/codex/files/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_REQUEST_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path)
        })
    });
}

async function fetchFileBrowserFile(root, path) {
    return fetchJson('/api/codex/files/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_READ_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path)
        })
    });
}

async function writeFilePanelFile(root, path, content, expectedModifiedNs = '') {
    return fetchJson('/api/codex/files/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path),
            content: typeof content === 'string' ? content : '',
            expected_modified_ns: String(expectedModifiedNs || '').trim()
        })
    });
}

async function createFilePanelFile(root, path, content = '') {
    return fetchJson('/api/codex/files/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path),
            content: typeof content === 'string' ? content : ''
        })
    });
}

async function fetchFilePanelDownload(root, paths) {
    return fetchBlob('/api/codex/files/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            paths: Array.from(createNormalizedRelativePathSet(paths))
        })
    });
}

async function deleteFilePanelFiles(root, paths) {
    return fetchJson('/api/codex/files/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            paths: Array.from(createNormalizedRelativePathSet(paths))
        })
    });
}

async function deleteFilePanelDirectory(root, path) {
    return fetchJson('/api/codex/files/delete-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            path: normalizeFileBrowserRelativePath(path)
        })
    });
}

async function moveFilePanelFiles(root, paths, payload = {}) {
    const requestPayload = payload && typeof payload === 'object' ? payload : {};
    return fetchJson('/api/codex/files/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: FILE_BROWSER_MUTATION_TIMEOUT_MS,
        body: JSON.stringify({
            root: normalizeFileBrowserRoot(root),
            paths: Array.from(createNormalizedRelativePathSet(paths)),
            destination_path: normalizeFileBrowserRelativePath(requestPayload.destination_path),
            destination_directory: Object.prototype.hasOwnProperty.call(requestPayload, 'destination_directory')
                ? normalizeFileBrowserRelativePath(requestPayload.destination_directory)
                : undefined
        })
    });
}

function clearFilePanelViewerForVariant(variant, message = '파일을 선택하세요.') {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        clearFileBrowserViewer(message);
        return;
    }
    clearWorkModeFileViewer(message);
}

function refreshFilePanelDirectoryForVariant(variant, options = {}) {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        return refreshFileBrowserDirectory(options);
    }
    return refreshWorkModeFileDirectory(options);
}

function refreshFilePanelPreviewSelectionForVariant(variant, options = {}) {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        return refreshFileBrowserPreviewSelection();
    }
    return refreshWorkModeFilePreviewSelection(options);
}

function openFileInPanelVariant(variant, path, options = {}) {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        return openFileInBrowserOverlay(path, options);
    }
    return openFileInWorkModePanel(path, options);
}

function captureFilePanelListScrollSnapshot(variant) {
    if (normalizeFilePanelVariant(variant) === FILE_PANEL_VARIANT_OVERLAY) {
        return null;
    }
    return captureWorkModeFileScrollSnapshot();
}

function normalizeFileContextLanguage(language = '') {
    const normalized = String(language || '').trim().toLowerCase();
    return /^[a-z0-9_+-]+$/u.test(normalized) ? normalized : '';
}

function trimFileContextText(text, maxChars) {
    const source = typeof text === 'string' ? text : '';
    const limit = Number(maxChars);
    if (!Number.isFinite(limit) || limit <= 0) {
        return { text: '', truncated: Boolean(source) };
    }
    if (source.length <= limit) {
        return { text: source, truncated: false };
    }
    return {
        text: `${source.slice(0, Math.max(0, limit - 18)).replace(/\s+$/u, '')}\n... [truncated]`,
        truncated: true
    };
}

function buildFilePanelChatContextSection(path, result, maxChars = FILE_PANEL_CHAT_CONTEXT_MAX_CHARS_PER_FILE) {
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    const sizeText = formatFileBrowserSize(result?.size);
    const mimeType = String(result?.mime_type || '').trim();
    const language = normalizeFileContextLanguage(result?.language || '');
    const sectionHeader = `### ${normalizedPath || '(unknown path)'}`;
    if (result?.is_binary) {
        const binaryParts = ['binary file'];
        if (mimeType) {
            binaryParts.push(mimeType);
        }
        if (sizeText && sizeText !== '--') {
            binaryParts.push(sizeText);
        }
        return `${sectionHeader}\n${binaryParts.join(' · ')}`;
    }
    const trimmed = trimFileContextText(result?.content || '', maxChars);
    const codeFence = `\`\`\`${language}\n${trimmed.text}\n\`\`\``;
    const metaParts = [];
    if (sizeText && sizeText !== '--') {
        metaParts.push(sizeText);
    }
    if (mimeType) {
        metaParts.push(mimeType);
    }
    const metaLine = metaParts.length ? `${metaParts.join(' · ')}\n` : '';
    return `${sectionHeader}\n${metaLine}${codeFence}`;
}

async function buildFilePanelChatContextText(root, selectedPaths) {
    const paths = Array.from(createNormalizedRelativePathSet(selectedPaths));
    if (!paths.length) return '';
    const limitedPaths = paths.slice(0, FILE_PANEL_CHAT_CONTEXT_MAX_FILES);
    const sections = [];
    let remainingChars = FILE_PANEL_CHAT_CONTEXT_MAX_TOTAL_CHARS;
    for (const path of limitedPaths) {
        if (remainingChars <= 200 && sections.length > 0) break;
        try {
            const result = await fetchFileBrowserFile(root, path);
            const budget = Math.min(FILE_PANEL_CHAT_CONTEXT_MAX_CHARS_PER_FILE, Math.max(320, remainingChars - 160));
            const section = buildFilePanelChatContextSection(path, result, budget);
            sections.push(section);
            remainingChars -= section.length;
        } catch (error) {
            const section = `### ${path}\n불러오지 못함: ${normalizeError(error, '파일 내용을 읽지 못했습니다.')}`;
            sections.push(section);
            remainingChars -= section.length;
        }
    }
    if (paths.length > limitedPaths.length) {
        sections.push(`추가 ${paths.length - limitedPaths.length}개 파일은 생략했습니다.`);
    }
    return [
        `선택한 파일 컨텍스트입니다. 루트: ${getFileBrowserRootLabel(root)}`,
        ...sections
    ].join('\n\n');
}

async function createFileInFilePanel(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    if (!confirmDiscardFilePanelEditChanges(normalizedVariant)) {
        return false;
    }

    const root = getFilePanelCurrentRoot(normalizedVariant);
    const currentPath = getFilePanelCurrentPath(normalizedVariant);
    const initialName = 'untitled.txt';
    const requestedName = window.prompt(
        '현재 폴더 기준 새 파일 경로를 입력하세요.',
        initialName
    );
    if (requestedName === null) return false;

    const targetPath = buildFileBrowserChildPath(currentPath, requestedName);
    if (!targetPath) {
        showToast('새 파일 경로를 입력하세요.', {
            tone: 'error',
            durationMs: 3200
        });
        return false;
    }

    const scrollSnapshot = captureFilePanelListScrollSnapshot(normalizedVariant);
    setFilePanelBulkActionInFlight(normalizedVariant, true);
    try {
        await createFilePanelFile(root, targetPath, '');
        clearFilePanelSelection(normalizedVariant);
        setFilePanelPreviewPath(normalizedVariant, '');
        await refreshFilePanelDirectoryForVariant(normalizedVariant, {
            root,
            path: currentPath,
            force: true,
            restoreScrollSnapshot: scrollSnapshot
        });
        await openFileInPanelVariant(normalizedVariant, targetPath, { root });
        showToast(`새 파일을 만들었습니다: ${targetPath}`, {
            tone: 'success',
            durationMs: 2600
        });
        return true;
    } catch (error) {
        showToast(normalizeError(error, '새 파일 생성에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(normalizedVariant, false);
    }
}

async function deleteCurrentDirectoryFromFilePanel(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const root = getFilePanelCurrentRoot(normalizedVariant);
    const currentPath = getFilePanelCurrentPath(normalizedVariant);
    if (!currentPath) {
        showToast('루트 폴더는 삭제할 수 없습니다.', {
            tone: 'error',
            durationMs: 3200
        });
        return false;
    }
    if (!confirmDiscardFilePanelEditChanges(normalizedVariant)) {
        return false;
    }

    const displayPath = formatFileBrowserDisplayPath(root, currentPath);
    const confirmed = window.confirm(
        `현재 폴더를 삭제할까요?\n하위 파일과 폴더도 함께 삭제됩니다.\n\n${displayPath}`
    );
    if (!confirmed) return false;

    const parentPath = getFileBrowserParentPath(currentPath);
    const scrollSnapshot = captureFilePanelListScrollSnapshot(normalizedVariant);
    setFilePanelBulkActionInFlight(normalizedVariant, true);
    try {
        await deleteFilePanelDirectory(root, currentPath);
        clearFilePanelSelection(normalizedVariant);
        setFilePanelPreviewPath(normalizedVariant, '');
        clearFilePanelViewerForVariant(normalizedVariant, '삭제한 폴더입니다. 상위 폴더를 확인하세요.');
        await refreshFilePanelDirectoryForVariant(normalizedVariant, {
            root,
            path: parentPath,
            force: true,
            restoreScrollSnapshot: scrollSnapshot
        });
        showToast(`폴더를 삭제했습니다: ${displayPath}`, {
            tone: 'success',
            durationMs: 2600
        });
        return true;
    } catch (error) {
        showToast(normalizeError(error, '폴더 삭제에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(normalizedVariant, false);
    }
}

async function addSelectedFilesToChatContext(variant) {
    const selectedPaths = Array.from(getFilePanelSelectedPaths(variant));
    if (!selectedPaths.length) {
        showToast('채팅에 넣을 파일을 먼저 선택하세요.', {
            tone: 'error',
            durationMs: 3200
        });
        return false;
    }
    setFilePanelBulkActionInFlight(variant, true);
    try {
        const contextText = await buildFilePanelChatContextText(
            getFilePanelCurrentRoot(variant),
            selectedPaths
        );
        if (!appendTextToChatInput(contextText)) {
            throw new Error('채팅 입력창을 찾을 수 없습니다.');
        }
        if (variant === FILE_PANEL_VARIANT_WORK_MODE && isMobileLayout() && isWorkModeEnabled()) {
            setWorkModeMobileView(WORK_MODE_MOBILE_VIEW_CHAT);
        }
        showToast(`선택 파일 ${selectedPaths.length}개를 채팅 입력에 넣었습니다.`, {
            tone: 'success',
            durationMs: 2600
        });
        return true;
    } catch (error) {
        showToast(normalizeError(error, '선택 파일을 채팅 입력에 넣지 못했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(variant, false);
    }
}

async function downloadSelectedFilesFromFilePanel(variant) {
    const selectedPaths = Array.from(getFilePanelSelectedPaths(variant));
    if (!selectedPaths.length) return false;
    setFilePanelBulkActionInFlight(variant, true);
    try {
        const result = await fetchFilePanelDownload(getFilePanelCurrentRoot(variant), selectedPaths);
        const filename = extractFilenameFromContentDisposition(result?.contentDisposition)
            || (selectedPaths.length === 1
                ? selectedPaths[0].split('/').pop()
                : 'codex-files.zip');
        if (!saveBlobAsFile(result?.blob, filename)) {
            throw new Error('브라우저 다운로드를 시작하지 못했습니다.');
        }
        showToast(`선택 파일 ${selectedPaths.length}개 다운로드를 시작했습니다.`, {
            tone: 'success',
            durationMs: 2600
        });
        return true;
    } catch (error) {
        showToast(normalizeError(error, '파일 다운로드에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(variant, false);
    }
}

async function deleteSelectedFilesFromFilePanel(variant) {
    const selectedPaths = Array.from(getFilePanelSelectedPaths(variant));
    if (!selectedPaths.length) return false;
    const confirmed = window.confirm(`선택한 ${selectedPaths.length}개 파일을 삭제할까요? 이 작업은 되돌릴 수 없습니다.`);
    if (!confirmed) return false;

    const root = getFilePanelCurrentRoot(variant);
    const currentPath = getFilePanelCurrentPath(variant);
    const previewPath = getFilePanelPreviewPath(variant);
    const previewDeleted = Boolean(previewPath) && selectedPaths.includes(previewPath);
    const scrollSnapshot = captureFilePanelListScrollSnapshot(variant);

    setFilePanelBulkActionInFlight(variant, true);
    try {
        await deleteFilePanelFiles(root, selectedPaths);
        clearFilePanelSelection(variant);
        if (previewDeleted) {
            setFilePanelPreviewPath(variant, '');
            clearFilePanelViewerForVariant(variant, '삭제한 파일입니다. 다른 파일을 선택하세요.');
        }
        const listed = await refreshFilePanelDirectoryForVariant(variant, {
            root,
            path: currentPath,
            force: true,
            restoreScrollSnapshot: scrollSnapshot
        });
        if (listed && previewPath && !previewDeleted) {
            await refreshFilePanelPreviewSelectionForVariant(variant);
        }
        showToast(`선택 파일 ${selectedPaths.length}개를 삭제했습니다.`, {
            tone: 'success',
            durationMs: 2600
        });
        return true;
    } catch (error) {
        showToast(normalizeError(error, '파일 삭제에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(variant, false);
    }
}

async function moveSelectedFilesFromFilePanel(variant) {
    const selectedPaths = Array.from(getFilePanelSelectedPaths(variant));
    if (!selectedPaths.length) return false;

    let payload = null;
    if (selectedPaths.length === 1) {
        const nextPath = window.prompt('새 파일 경로를 입력하세요.', selectedPaths[0]);
        if (nextPath === null) return false;
        payload = {
            destination_path: normalizeFileBrowserRelativePath(nextPath)
        };
    } else {
        const nextDirectory = window.prompt(
            `선택한 ${selectedPaths.length}개 파일을 옮길 대상 폴더 경로를 입력하세요.`,
            getFilePanelCurrentPath(variant)
        );
        if (nextDirectory === null) return false;
        payload = {
            destination_directory: normalizeFileBrowserRelativePath(nextDirectory)
        };
    }

    const root = getFilePanelCurrentRoot(variant);
    const currentPath = getFilePanelCurrentPath(variant);
    const previewPath = getFilePanelPreviewPath(variant);
    const scrollSnapshot = captureFilePanelListScrollSnapshot(variant);

    setFilePanelBulkActionInFlight(variant, true);
    try {
        const result = await moveFilePanelFiles(root, selectedPaths, payload);
        const moved = Array.isArray(result?.moved) ? result.moved : [];
        const movedMap = new Map(
            moved.map(entry => [
                normalizeFileBrowserRelativePath(entry?.source_path || ''),
                normalizeFileBrowserRelativePath(entry?.destination_path || '')
            ])
        );
        const nextSelection = moved
            .map(entry => normalizeFileBrowserRelativePath(entry?.destination_path || ''))
            .filter(path => getFileBrowserParentPath(path) === currentPath);
        setFilePanelSelectedPaths(variant, nextSelection);
        setFilePanelSelectionAnchorPath(variant, nextSelection[nextSelection.length - 1] || '');

        let nextPreviewPath = previewPath;
        if (previewPath && movedMap.has(previewPath)) {
            const movedPreviewPath = movedMap.get(previewPath) || '';
            nextPreviewPath = getFileBrowserParentPath(movedPreviewPath) === currentPath
                ? movedPreviewPath
                : '';
            setFilePanelPreviewPath(variant, nextPreviewPath);
            if (!nextPreviewPath) {
                clearFilePanelViewerForVariant(variant, '이동한 파일은 현재 폴더에 없습니다.');
            }
        }

        const listed = await refreshFilePanelDirectoryForVariant(variant, {
            root,
            path: currentPath,
            force: true,
            restoreScrollSnapshot: scrollSnapshot
        });
        applyFilePanelSelectionStateForVariant(variant);
        if (listed) {
            if (nextPreviewPath) {
                await openFileInPanelVariant(variant, nextPreviewPath, {
                    root,
                    showViewerOnSuccess: false
                });
            } else if (previewPath && !movedMap.has(previewPath)) {
                await refreshFilePanelPreviewSelectionForVariant(variant);
            }
        }
        showToast(
            selectedPaths.length === 1 ? '파일 이름/경로를 변경했습니다.' : `선택 파일 ${selectedPaths.length}개를 이동했습니다.`,
            {
                tone: 'success',
                durationMs: 2600
            }
        );
        return true;
    } catch (error) {
        showToast(normalizeError(error, '파일 이동에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    } finally {
        setFilePanelBulkActionInFlight(variant, false);
    }
}

async function refreshFileBrowserDirectory({ root = fileBrowserRoot, path = fileBrowserPath, force = false } = {}) {
    void force;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) {
        return null;
    }
    const elements = getFileBrowserElements();
    if (!elements) return null;
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const normalizedPath = normalizeFileBrowserRelativePath(path);

    setFileBrowserDirectoryLoading(true);
    if (elements.meta) {
        elements.meta.textContent = '디렉터리 목록을 불러오는 중...';
    }

    try {
        const result = await fetchFileBrowserDirectory(normalizedRoot, normalizedPath);
        fileBrowserRoot = normalizeFileBrowserRoot(result?.root || normalizedRoot);
        fileBrowserPath = normalizeFileBrowserRelativePath(result?.path || normalizedPath);
        updateFileBrowserRootButtons();
        setFileBrowserPathLabel(fileBrowserRoot, fileBrowserPath, result?.root_path || '');

        const entries = Array.isArray(result?.entries) ? result.entries : [];
        fileBrowserCachedEntries = entries;
        fileBrowserCachedTruncated = Boolean(result?.truncated);
        pruneFilePanelSelectionToEntries(FILE_PANEL_VARIANT_OVERLAY, entries);
        renderFileBrowserDirectoryEntries(fileBrowserCachedEntries, {
            truncated: fileBrowserCachedTruncated
        });
        if (elements.subtitle) {
            elements.subtitle.textContent = `${getFileBrowserRootLabel(fileBrowserRoot)} · ${fileBrowserPath || '/'}`;
        }
        if (elements.upBtn) {
            const canGoUp = Boolean(result?.can_go_up) || Boolean(fileBrowserPath);
            elements.upBtn.disabled = !canGoUp;
        }
        if (elements.loading) {
            elements.loading.classList.add('is-hidden');
        }
        return result;
    } catch (error) {
        fileBrowserCachedEntries = [];
        fileBrowserCachedTruncated = false;
        if (elements.meta) {
            elements.meta.textContent = normalizeError(error, '디렉터리 목록을 불러오지 못했습니다.');
        }
        if (elements.list) {
            elements.list.classList.add('is-hidden');
            elements.list.innerHTML = '';
        }
        if (elements.empty) {
            elements.empty.textContent = '디렉터리 목록을 불러오지 못했습니다.';
            elements.empty.classList.remove('is-hidden');
        }
        showToast(normalizeError(error, '파일 브라우저 목록 조회에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return null;
    } finally {
        setFileBrowserDirectoryLoading(false);
    }
}

function isMarkdownLanguage(language) {
    return String(language || '').trim().toLowerCase() === 'markdown';
}

function buildFileBrowserSourceViewer(content, { language = '', isScript = false, highlightLine = null } = {}) {
    const normalizedContent = String(content || '').replace(/\r\n/g, '\n');
    const lines = normalizedContent.split('\n');
    const lineCount = Math.max(1, lines.length);
    const source = document.createElement('div');
    source.className = 'file-browser-source';
    source.style.setProperty('--file-browser-line-digit-width', String(Math.max(2, String(lineCount).length)));

    let highlightFound = false;
    for (let index = 0; index < lineCount; index += 1) {
        const lineNumber = index + 1;
        const lineText = lines[index] || '';

        const row = document.createElement('div');
        row.className = 'file-browser-source-line';
        row.dataset.lineNumber = String(lineNumber);
        if (highlightLine && lineNumber === highlightLine) {
            row.classList.add('is-target');
            highlightFound = true;
        }

        const number = document.createElement('span');
        number.className = 'file-browser-source-line-number';
        number.textContent = String(lineNumber);

        const line = document.createElement('span');
        line.className = 'file-browser-source-line-content';
        if (isScript) {
            const highlightedLine = highlightScriptContent(lineText, language);
            line.innerHTML = highlightedLine || '&nbsp;';
        } else {
            line.innerHTML = lineText ? escapeHtml(lineText) : '&nbsp;';
        }

        row.appendChild(number);
        row.appendChild(line);
        source.appendChild(row);
    }

    return {
        element: source,
        lineCount,
        highlightFound
    };
}

function revealFileBrowserSourceLineInContainer(container, lineNumber) {
    const requestedLine = normalizeSourceLineNumber(lineNumber);
    if (!requestedLine) return false;
    if (!(container instanceof Element)) return false;
    const target = container.querySelector(`.file-browser-source-line[data-line-number="${requestedLine}"]`);
    if (!(target instanceof HTMLElement)) return false;
    target.scrollIntoView({
        block: 'center',
        inline: 'nearest',
        behavior: 'smooth'
    });
    return true;
}

function revealFileBrowserSourceLine(lineNumber) {
    const elements = getFileBrowserElements();
    return revealFileBrowserSourceLineInContainer(elements?.viewerContent, lineNumber);
}

function getFileBrowserViewerRenderToken() {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function isSpreadsheetPreviewableFile(path, mimeType = '') {
    const normalizedPath = normalizeFileBrowserRelativePath(path).toLowerCase();
    const extensionMatch = normalizedPath.match(/(\.[^.\/]+)$/);
    const extension = extensionMatch ? extensionMatch[1] : '';
    if (extension && FILE_BROWSER_SPREADSHEET_EXTENSIONS.has(extension)) {
        return true;
    }
    const normalizedMime = String(mimeType || '').trim().toLowerCase();
    if (!normalizedMime) return false;
    return normalizedMime.includes('spreadsheet')
        || normalizedMime.includes('excel')
        || normalizedMime.includes('sheet.binary');
}

function isImagePreviewableFile(path, mimeType = '') {
    const normalizedPath = normalizeFileBrowserRelativePath(path).toLowerCase();
    if (/\.(avif|bmp|gif|jpe?g|png|svg|webp)$/u.test(normalizedPath)) {
        return true;
    }
    return String(mimeType || '').trim().toLowerCase().startsWith('image/');
}

function isPdfPreviewableFile(path, mimeType = '') {
    const normalizedPath = normalizeFileBrowserRelativePath(path).toLowerCase();
    if (normalizedPath.endsWith('.pdf')) {
        return true;
    }
    return String(mimeType || '').trim().toLowerCase().includes('application/pdf');
}

function containsTemplateLikeHtmlSyntax(text = '') {
    const source = typeof text === 'string' ? text : '';
    if (!source) return false;
    return source.includes('{%')
        || source.includes('{{')
        || source.includes('{#')
        || source.includes('<%');
}

function formatSpreadsheetColumnLabel(index) {
    let value = Number(index);
    if (!Number.isFinite(value) || value < 0) value = 0;
    let label = '';
    let cursor = Math.floor(value);
    do {
        label = String.fromCharCode(65 + (cursor % 26)) + label;
        cursor = Math.floor(cursor / 26) - 1;
    } while (cursor >= 0);
    return label;
}

function getSpreadsheetCellDisplayValue(cell) {
    if (!cell || typeof cell !== 'object') return '';
    if (cell.w != null && cell.w !== '') {
        return String(cell.w);
    }
    if (cell.v == null) {
        return '';
    }
    return String(cell.v);
}

function buildSpreadsheetSheetPreview(workbook, sheetName, sheetIndex, xlsxApi) {
    const sheet = workbook?.Sheets?.[sheetName];
    const panel = document.createElement('section');
    panel.className = 'file-browser-spreadsheet-sheet';
    panel.dataset.sheetIndex = String(sheetIndex);

    const title = document.createElement('div');
    title.className = 'file-browser-spreadsheet-sheet-title';
    title.textContent = sheetName || `Sheet ${sheetIndex + 1}`;
    panel.appendChild(title);

    if (!sheet || !sheet['!ref'] || !xlsxApi?.utils?.decode_range) {
        const emptyState = document.createElement('div');
        emptyState.className = 'file-browser-placeholder';
        emptyState.textContent = '시트에 표시할 데이터가 없습니다.';
        panel.appendChild(emptyState);
        return panel;
    }

    let range;
    try {
        range = xlsxApi.utils.decode_range(sheet['!ref']);
    } catch (error) {
        const invalidState = document.createElement('div');
        invalidState.className = 'file-browser-placeholder';
        invalidState.textContent = '시트 범위를 해석하지 못했습니다.';
        panel.appendChild(invalidState);
        return panel;
    }

    const totalRows = Math.max(0, (range.e.r - range.s.r) + 1);
    const totalCols = Math.max(0, (range.e.c - range.s.c) + 1);
    if (!totalRows || !totalCols) {
        const emptyState = document.createElement('div');
        emptyState.className = 'file-browser-placeholder';
        emptyState.textContent = '시트에 표시할 데이터가 없습니다.';
        panel.appendChild(emptyState);
        return panel;
    }

    const previewEndRow = Math.min(range.e.r, range.s.r + FILE_BROWSER_SPREADSHEET_MAX_ROWS - 1);
    const previewEndCol = Math.min(range.e.c, range.s.c + FILE_BROWSER_SPREADSHEET_MAX_COLS - 1);
    const isRowTruncated = previewEndRow < range.e.r;
    const isColTruncated = previewEndCol < range.e.c;

    const meta = document.createElement('div');
    meta.className = 'file-browser-spreadsheet-sheet-meta';
    const metaParts = [`${totalRows}행`, `${totalCols}열`];
    if (isRowTruncated || isColTruncated) {
        metaParts.push(`미리보기는 최대 ${FILE_BROWSER_SPREADSHEET_MAX_ROWS}행 / ${FILE_BROWSER_SPREADSHEET_MAX_COLS}열`);
    }
    meta.textContent = metaParts.join(' · ');
    panel.appendChild(meta);

    const grid = document.createElement('div');
    grid.className = 'file-browser-spreadsheet-grid';

    const table = document.createElement('table');
    table.className = 'file-browser-spreadsheet-table';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    const corner = document.createElement('th');
    corner.className = 'file-browser-spreadsheet-corner';
    corner.textContent = '#';
    headerRow.appendChild(corner);
    for (let colIndex = range.s.c; colIndex <= previewEndCol; colIndex += 1) {
        const headerCell = document.createElement('th');
        headerCell.textContent = formatSpreadsheetColumnLabel(colIndex);
        headerRow.appendChild(headerCell);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (let rowIndex = range.s.r; rowIndex <= previewEndRow; rowIndex += 1) {
        const row = document.createElement('tr');
        const rowHeader = document.createElement('th');
        rowHeader.className = 'file-browser-spreadsheet-row-header';
        rowHeader.textContent = String(rowIndex + 1);
        row.appendChild(rowHeader);

        for (let colIndex = range.s.c; colIndex <= previewEndCol; colIndex += 1) {
            const cellElement = document.createElement('td');
            const cellAddress = xlsxApi.utils.encode_cell({ r: rowIndex, c: colIndex });
            const cellValue = getSpreadsheetCellDisplayValue(sheet[cellAddress]);
            cellElement.textContent = cellValue;
            row.appendChild(cellElement);
        }
        tbody.appendChild(row);
    }
    table.appendChild(tbody);
    grid.appendChild(table);
    panel.appendChild(grid);
    return panel;
}

function activateSpreadsheetSheetPreview(wrapper, targetIndex) {
    if (!(wrapper instanceof Element)) return;
    const normalizedIndex = Number.isFinite(Number(targetIndex)) ? String(Number(targetIndex)) : '0';
    wrapper.querySelectorAll('.file-browser-spreadsheet-tab').forEach(button => {
        if (!(button instanceof HTMLButtonElement)) return;
        const isActive = button.dataset.sheetIndex === normalizedIndex;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-selected', isActive ? 'true' : 'false');
        button.tabIndex = isActive ? 0 : -1;
    });
    wrapper.querySelectorAll('.file-browser-spreadsheet-sheet').forEach(panel => {
        if (!(panel instanceof HTMLElement)) return;
        panel.classList.toggle('is-active', panel.dataset.sheetIndex === normalizedIndex);
    });
}

function buildSpreadsheetPreview(workbook, xlsxApi) {
    const wrapper = document.createElement('section');
    wrapper.className = 'file-browser-spreadsheet';

    const sheetNames = Array.isArray(workbook?.SheetNames) ? workbook.SheetNames : [];
    if (sheetNames.length === 0) {
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = '워크북에 표시할 시트가 없습니다.';
        wrapper.appendChild(placeholder);
        return wrapper;
    }

    const visibleSheetNames = sheetNames.slice(0, FILE_BROWSER_SPREADSHEET_MAX_SHEETS);
    const summary = document.createElement('div');
    summary.className = 'file-browser-spreadsheet-summary';
    const summaryParts = [`총 ${sheetNames.length}개 시트`];
    if (sheetNames.length > FILE_BROWSER_SPREADSHEET_MAX_SHEETS) {
        summaryParts.push(`앞 ${FILE_BROWSER_SPREADSHEET_MAX_SHEETS}개만 표시`);
    }
    summary.textContent = summaryParts.join(' · ');
    wrapper.appendChild(summary);

    if (visibleSheetNames.length > 1) {
        const tabs = document.createElement('div');
        tabs.className = 'file-browser-spreadsheet-tabs';
        tabs.setAttribute('role', 'tablist');
        tabs.setAttribute('aria-label', 'Workbook sheets');
        visibleSheetNames.forEach((sheetName, sheetIndex) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'file-browser-spreadsheet-tab';
            button.dataset.sheetIndex = String(sheetIndex);
            button.setAttribute('role', 'tab');
            button.textContent = sheetName || `Sheet ${sheetIndex + 1}`;
            button.addEventListener('click', () => {
                activateSpreadsheetSheetPreview(wrapper, sheetIndex);
            });
            tabs.appendChild(button);
        });
        wrapper.appendChild(tabs);
    }

    const body = document.createElement('div');
    body.className = 'file-browser-spreadsheet-body';
    visibleSheetNames.forEach((sheetName, sheetIndex) => {
        body.appendChild(buildSpreadsheetSheetPreview(workbook, sheetName, sheetIndex, xlsxApi));
    });
    wrapper.appendChild(body);
    activateSpreadsheetSheetPreview(wrapper, 0);
    return wrapper;
}

async function renderSpreadsheetPreviewIntoContainer(container, previewUrl, renderToken) {
    if (!(container instanceof HTMLElement)) return false;
    const currentToken = String(renderToken || '');

    container.innerHTML = '';
    const loadingState = document.createElement('div');
    loadingState.className = 'file-browser-placeholder';
    loadingState.textContent = '스프레드시트 미리보기를 준비하는 중...';
    container.appendChild(loadingState);

    if (!previewUrl) {
        loadingState.textContent = '스프레드시트 파일 주소를 만들지 못했습니다.';
        return false;
    }
    let xlsxApi = null;
    try {
        xlsxApi = await ensureXlsxApiLoaded();
    } catch (error) {
        void error;
    }
    if (!xlsxApi || typeof xlsxApi.read !== 'function') {
        loadingState.textContent = '스프레드시트 미리보기 라이브러리를 불러오지 못했습니다.';
        return false;
    }

    try {
        const response = await fetchArrayBuffer(previewUrl, {
            timeoutMs: FILE_BROWSER_READ_TIMEOUT_MS
        });
        if (container.dataset.renderToken !== currentToken) {
            return false;
        }
        const workbook = xlsxApi.read(response.buffer, {
            type: 'array',
            cellFormula: false,
            cellHTML: false,
            cellStyles: false
        });
        const spreadsheetView = buildSpreadsheetPreview(workbook, xlsxApi);
        if (container.dataset.renderToken !== currentToken) {
            return false;
        }
        container.innerHTML = '';
        container.appendChild(spreadsheetView);
        return true;
    } catch (error) {
        if (container.dataset.renderToken !== currentToken) {
            return false;
        }
        container.innerHTML = '';
        const errorState = document.createElement('div');
        errorState.className = 'file-browser-placeholder';
        errorState.textContent = normalizeError(error, '스프레드시트 미리보기를 불러오지 못했습니다.');
        container.appendChild(errorState);
        return false;
    }
}

function getFilePanelVariantFromElements(elements) {
    return elements?.viewerContent?.id === 'codex-work-mode-file-viewer-content'
        ? FILE_PANEL_VARIANT_WORK_MODE
        : FILE_PANEL_VARIANT_OVERLAY;
}

function buildFilePanelEditorStatusText(variant) {
    const state = getFilePanelEditState(variant);
    const dirtyLabel = state.dirty ? '변경 사항 있음' : '변경 사항 없음';
    return `${dirtyLabel} · Ctrl/Cmd+S로 저장`;
}

function renderFilePanelEditor(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const config = getFilePanelVariantConfig(normalizedVariant);
    const elements = config.getElements();
    const state = getFilePanelEditState(normalizedVariant);
    if (!elements?.viewerContent || !state.previewResult) return false;

    if (normalizedVariant === FILE_PANEL_VARIANT_WORK_MODE) {
        clearWorkModeHtmlPreviewState();
    }

    elements.viewerContent.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'file-browser-editor';

    const textarea = document.createElement('textarea');
    textarea.className = 'file-browser-editor-input';
    textarea.spellcheck = false;
    textarea.autocapitalize = 'off';
    textarea.autocomplete = 'off';
    textarea.autocorrect = 'off';
    textarea.value = typeof state.editBuffer === 'string'
        ? state.editBuffer
        : String(state.previewResult?.content || '');

    const status = document.createElement('div');
    status.className = 'file-browser-editor-status';
    status.textContent = buildFilePanelEditorStatusText(normalizedVariant);

    textarea.addEventListener('input', () => {
        state.editBuffer = textarea.value;
        state.dirty = textarea.value !== String(state.previewResult?.content || '');
        status.textContent = buildFilePanelEditorStatusText(normalizedVariant);
        syncFilePanelViewerActionState(normalizedVariant);
    });
    textarea.addEventListener('keydown', event => {
        const key = String(event.key || '').toLowerCase();
        if ((event.metaKey || event.ctrlKey) && key === 's') {
            event.preventDefault();
            void saveFilePanelEdits(normalizedVariant);
        }
    });

    wrapper.appendChild(textarea);
    wrapper.appendChild(status);
    elements.viewerContent.appendChild(wrapper);
    syncFilePanelViewerActionState(normalizedVariant);
    requestAnimationFrame(() => {
        textarea.focus();
        const end = textarea.value.length;
        textarea.setSelectionRange(end, end);
    });
    return true;
}

async function rerenderFilePanelPreviewFromState(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const config = getFilePanelVariantConfig(normalizedVariant);
    const elements = config.getElements();
    const state = getFilePanelEditState(normalizedVariant);
    if (!elements?.viewerContent || !state.previewResult) return false;
    await renderFileBrowserViewerIntoElements(elements, state.previewResult, {
        root: state.root
    });
    return true;
}

async function toggleFilePanelEditMode(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const state = getFilePanelEditState(normalizedVariant);
    if (!state.path || !state.previewResult) return false;
    if (!state.editing) {
        if (!state.editable) {
            showToast('이 파일 형식은 편집 모드에서 열 수 없습니다.', {
                tone: 'error',
                durationMs: 3200
            });
            return false;
        }
        state.editing = true;
        state.dirty = false;
        state.saving = false;
        state.editBuffer = String(state.previewResult?.content || '');
        return renderFilePanelEditor(normalizedVariant);
    }

    if (!confirmDiscardFilePanelEditChanges(normalizedVariant)) {
        return false;
    }
    return rerenderFilePanelPreviewFromState(normalizedVariant);
}

async function saveFilePanelEdits(variant) {
    const normalizedVariant = normalizeFilePanelVariant(variant);
    const state = getFilePanelEditState(normalizedVariant);
    if (!state.editing || !state.dirty || state.saving || !state.path) return false;

    state.saving = true;
    syncFilePanelViewerActionState(normalizedVariant);
    try {
        const result = await writeFilePanelFile(
            state.root || getFilePanelCurrentRoot(normalizedVariant),
            state.path,
            state.editBuffer,
            state.modifiedNs
        );
        setFilePanelPreviewPath(normalizedVariant, result?.path || state.path);
        await renderFileBrowserViewerIntoElements(
            getFilePanelVariantConfig(normalizedVariant).getElements(),
            result,
            {
                root: state.root || result?.root || getFilePanelCurrentRoot(normalizedVariant)
            }
        );
        if (normalizedVariant === FILE_PANEL_VARIANT_OVERLAY) {
            applyFileBrowserSelectionState();
        } else {
            applyWorkModeFileSelectionState();
        }
        showToast('파일을 저장했습니다.', {
            tone: 'success',
            durationMs: 2400
        });
        return true;
    } catch (error) {
        state.saving = false;
        syncFilePanelViewerActionState(normalizedVariant);
        showToast(normalizeError(error, '파일 저장에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return false;
    }
}

async function renderFileBrowserViewerIntoElements(elements, result, options = {}) {
    if (!elements?.viewerContent) return;

    const renderToken = getFileBrowserViewerRenderToken();
    elements.viewerContent.dataset.renderToken = renderToken;
    const requestedLine = normalizeSourceLineNumber(options?.line);
    const requestedColumn = normalizeSourceColumnNumber(options?.column);
    const previewRoot = normalizeFileBrowserRoot(options?.root || result?.root || fileBrowserRoot);
    const isWorkModeViewer = elements.viewerContent.id === 'codex-work-mode-file-viewer-content';
    const variant = getFilePanelVariantFromElements(elements);

    const normalizedPath = normalizeFileBrowserRelativePath(result?.path || '');
    const language = typeof result?.language === 'string' ? result.language.trim() : '';
    const isHtml = Boolean(result?.is_html);
    const isScript = Boolean(result?.is_script);
    const isBinary = Boolean(result?.is_binary);
    const isSpreadsheet = isSpreadsheetPreviewableFile(normalizedPath, result?.mime_type);
    const isImage = isImagePreviewableFile(normalizedPath, result?.mime_type);
    const isPdf = isPdfPreviewableFile(normalizedPath, result?.mime_type);
    const text = typeof result?.content === 'string' ? result.content : '';
    const canRenderHtmlPreview = isHtml
        && result?.html_previewable !== false
        && !containsTemplateLikeHtmlSyntax(text);
    const sizeText = formatFileBrowserSize(result?.size);
    const infoParts = [normalizedPath || '(unknown path)'];
    if (sizeText && sizeText !== '--') {
        infoParts.push(sizeText);
    }
    if (language) {
        infoParts.push(language);
    } else if (isSpreadsheet) {
        infoParts.push('spreadsheet');
    } else if (isImage) {
        infoParts.push('image');
    } else if (isPdf) {
        infoParts.push('pdf');
    } else if (isBinary) {
        infoParts.push('binary');
    }
    if (requestedLine && !isSpreadsheet) {
        const lineInfo = requestedColumn ? `line ${requestedLine}:${requestedColumn}` : `line ${requestedLine}`;
        infoParts.push(lineInfo);
    }
    hydrateFilePanelEditStateFromResult(variant, result, { root: previewRoot });
    setFilePanelViewerMetaText(elements, infoParts.join(' · '), {
        truncated: Boolean(result?.truncated)
    });

    elements.viewerContent.innerHTML = '';
    if (isWorkModeViewer) {
        clearWorkModeHtmlPreviewState();
    }
    if (isSpreadsheet) {
        const previewUrl = buildFileBrowserRawFileUrl(previewRoot, normalizedPath);
        await renderSpreadsheetPreviewIntoContainer(elements.viewerContent, previewUrl, renderToken);
        return;
    }

    if (isImage) {
        const previewUrl = buildFileBrowserRawFileUrl(previewRoot, normalizedPath);
        const wrapper = document.createElement('div');
        wrapper.className = 'file-browser-media-preview';
        const image = document.createElement('img');
        image.alt = normalizedPath || 'Image preview';
        if (previewUrl) {
            image.src = previewUrl;
        }
        wrapper.appendChild(image);
        elements.viewerContent.appendChild(wrapper);
        return;
    }

    if (isPdf) {
        const previewUrl = buildFileBrowserRawFileUrl(previewRoot, normalizedPath);
        if (!previewUrl) {
            const placeholder = document.createElement('div');
            placeholder.className = 'file-browser-placeholder';
            placeholder.textContent = 'PDF 파일 주소를 만들지 못했습니다.';
            elements.viewerContent.appendChild(placeholder);
            return;
        }
        const wrapper = document.createElement('div');
        wrapper.className = 'file-browser-pdf-preview-wrap';
        const iframe = document.createElement('iframe');
        iframe.className = 'file-browser-pdf-preview';
        iframe.src = previewUrl;
        iframe.title = normalizedPath || 'PDF preview';
        wrapper.appendChild(iframe);
        elements.viewerContent.appendChild(wrapper);
        return;
    }

    if (isBinary) {
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = 'Binary 파일은 미리보기에서 지원되지 않습니다.';
        elements.viewerContent.appendChild(placeholder);
        return;
    }

    if (!text) {
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = '표시할 파일 내용이 없습니다.';
        elements.viewerContent.appendChild(placeholder);
        return;
    }

    if (canRenderHtmlPreview && !requestedLine) {
        const previewUrl = buildFileBrowserRawFileUrl(previewRoot, normalizedPath);
        if (isWorkModeViewer) {
            setWorkModeHtmlPreviewState({
                root: previewRoot,
                path: normalizedPath,
                previewUrl,
                suspended: false
            });
        }
        const iframe = document.createElement('iframe');
        iframe.className = 'file-browser-html-preview';
        iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts allow-forms');
        if (previewUrl) {
            iframe.src = previewUrl;
        } else {
            iframe.srcdoc = text;
        }
        elements.viewerContent.appendChild(iframe);
        return;
    }

    if (isMarkdownLanguage(language) && !requestedLine) {
        const article = document.createElement('article');
        article.className = 'file-browser-markdown';
        article.innerHTML = renderMarkdown(text);
        elements.viewerContent.appendChild(article);
        hydrateRenderedMarkdown(article);
        return;
    }

    const sourceView = buildFileBrowserSourceViewer(text, {
        language,
        isScript,
        highlightLine: requestedLine
    });
    elements.viewerContent.appendChild(sourceView.element);

    if (!requestedLine) return;
    if (!sourceView.highlightFound) {
        showToast(`요청한 라인 ${requestedLine}을 찾을 수 없습니다. (총 ${sourceView.lineCount}줄)`, {
            tone: 'default',
            durationMs: 3400
        });
        return;
    }
    requestAnimationFrame(() => {
        revealFileBrowserSourceLineInContainer(elements.viewerContent, requestedLine);
    });
}

async function renderFileBrowserViewer(result, options = {}) {
    const elements = getFileBrowserElements();
    await renderFileBrowserViewerIntoElements(elements, result, options);
}

async function openFileInBrowserOverlay(
    path,
    {
        root = fileBrowserRoot,
        fallbackToDirectory = false,
        showViewerOnSuccess = true,
        line = null,
        column = null
    } = {}
) {
    const normalizedPath = normalizeFileBrowserRelativePath(path);
    if (!normalizedPath) return null;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) {
        return null;
    }
    const normalizedRoot = normalizeFileBrowserRoot(root);
    const requestedLine = normalizeSourceLineNumber(line);
    const requestedColumn = normalizeSourceColumnNumber(column);
    const elements = getFileBrowserElements();
    if (!elements) return null;
    resetFilePanelEditState(FILE_PANEL_VARIANT_OVERLAY, { root: normalizedRoot });

    const displayPath = formatFilesystemPathWithLocation(normalizedPath, requestedLine, requestedColumn);
    setFilePanelViewerMetaText(elements, `${displayPath} · 불러오는 중...`);
    if (elements.viewerContent) {
        elements.viewerContent.innerHTML = '';
        const placeholder = document.createElement('div');
        placeholder.className = 'file-browser-placeholder';
        placeholder.textContent = '파일을 불러오는 중...';
        elements.viewerContent.appendChild(placeholder);
    }

    try {
        const result = await fetchFileBrowserFile(normalizedRoot, normalizedPath);
        fileBrowserSelectedPath = normalizeFileBrowserRelativePath(result?.path || normalizedPath);
        await renderFileBrowserViewer(result, {
            root: normalizedRoot,
            line: requestedLine,
            column: requestedColumn
        });
        applyFileBrowserSelectionState();
        if (showViewerOnSuccess) {
            setFileBrowserMobileView(FILE_BROWSER_MOBILE_VIEW_VIEWER);
        }
        return result;
    } catch (error) {
        const payload = getGitErrorPayload(error);
        if (fallbackToDirectory && payload?.error_code === 'not_file') {
            fileBrowserSelectedPath = '';
            clearFileBrowserViewer('폴더가 선택되었습니다. 왼쪽 목록에서 파일을 선택하세요.');
            await refreshFileBrowserDirectory({
                root: normalizedRoot,
                path: normalizedPath,
                force: true
            });
            return {
                opened_directory: true,
                path: normalizedPath
            };
        }
        setFilePanelViewerMetaText(elements, normalizedPath);
        if (elements.viewerContent) {
            elements.viewerContent.innerHTML = '';
            const placeholder = document.createElement('div');
            placeholder.className = 'file-browser-placeholder';
            placeholder.textContent = normalizeError(error, '파일을 열지 못했습니다.');
            elements.viewerContent.appendChild(placeholder);
        }
        showToast(normalizeError(error, '파일 열기에 실패했습니다.'), {
            tone: 'error',
            durationMs: 4200
        });
        return null;
    }
}

async function refreshFileBrowserPreviewSelection() {
    const selectedPath = normalizeFileBrowserRelativePath(fileBrowserSelectedPath);
    if (!selectedPath) return null;
    return openFileInBrowserOverlay(selectedPath, {
        root: fileBrowserRoot,
        fallbackToDirectory: true,
        showViewerOnSuccess: false
    });
}

function openFileBrowserOverlay(options = {}) {
    const elements = getFileBrowserElements();
    if (!elements) return;
    if (!confirmDiscardFilePanelEditChanges(FILE_PANEL_VARIANT_OVERLAY)) {
        return;
    }
    if (isGitSyncOverlayOpen()) {
        closeGitSyncOverlay();
    }
    if (isGitBranchOverlayOpen()) {
        closeGitBranchOverlay();
    }
    if (isMessageLogOverlayOpen()) {
        closeMessageLogOverlay();
    }
    if (isMobileSessionOverlayOpen()) {
        closeMobileSessionOverlay();
    }
    if (isUsageHistoryOverlayOpen()) {
        closeUsageHistoryOverlay();
    }

    const hasRoot = Object.prototype.hasOwnProperty.call(options, 'root');
    const hasFilePath = Object.prototype.hasOwnProperty.call(options, 'filePath');
    const hasPath = Object.prototype.hasOwnProperty.call(options, 'path');
    const hasLine = Object.prototype.hasOwnProperty.call(options, 'line');
    const hasColumn = Object.prototype.hasOwnProperty.call(options, 'column');

    const requestedRoot = normalizeFileBrowserRoot(
        hasRoot ? options?.root : fileBrowserRoot
    );
    const requestedFilePath = normalizeFileBrowserRelativePath(
        hasFilePath ? options?.filePath : (hasPath ? '' : fileBrowserSelectedPath)
    );
    const requestedLine = normalizeSourceLineNumber(hasLine ? options?.line : null);
    const requestedColumn = normalizeSourceColumnNumber(hasColumn ? options?.column : null);
    const requestedPathSource = hasPath
        ? options?.path
        : (hasFilePath ? getFileBrowserParentPath(requestedFilePath) : fileBrowserPath);
    const requestedPath = normalizeFileBrowserRelativePath(requestedPathSource);

    fileBrowserRoot = requestedRoot;
    fileBrowserPath = requestedPath;
    fileBrowserSelectedPath = requestedFilePath;
    setFilePanelSelectedPaths(FILE_PANEL_VARIANT_OVERLAY, []);
    setFilePanelSelectionAnchorPath(FILE_PANEL_VARIANT_OVERLAY, '');

    updateFileBrowserRootButtons();
    updateFileBrowserFilterToggleState();
    applyFileBrowserColumnWidths({ persist: false });
    setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
    const initialMobileView = (hasPath || hasFilePath)
        ? (requestedFilePath ? FILE_BROWSER_MOBILE_VIEW_VIEWER : FILE_BROWSER_MOBILE_VIEW_LIST)
        : fileBrowserMobileView;
    setFileBrowserMobileView(initialMobileView);
    setFileBrowserPathLabel(fileBrowserRoot, fileBrowserPath);
    if (requestedFilePath) {
        const lineSuffix = requestedLine
            ? (requestedColumn ? ` (line ${requestedLine}:${requestedColumn})` : ` (line ${requestedLine})`)
            : '';
        clearFileBrowserViewer(`파일을 여는 중...${lineSuffix}`);
    } else {
        clearFileBrowserViewer('파일을 선택하세요.');
    }

    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    syncFileBrowserOpenButtonState(true);
    requestAnimationFrame(() => {
        applyFileBrowserColumnWidths({ persist: false });
        applyFileBrowserSplitRatio(fileBrowserSplitRatio, { persist: false });
        setFileBrowserViewerFullscreen(fileBrowserViewerFullscreen);
        setFileBrowserMobileView(fileBrowserMobileView);
        syncFileBrowserHorizontalScrollMetrics();
    });

    void (async () => {
        const listed = await refreshFileBrowserDirectory({
            root: requestedRoot,
            path: requestedPath,
            force: true
        });
        if (!listed || !requestedFilePath) return;
        await openFileInBrowserOverlay(requestedFilePath, {
            root: requestedRoot,
            fallbackToDirectory: true,
            line: requestedLine,
            column: requestedColumn
        });
    })();
}

function closeFileBrowserOverlay() {
    const elements = getFileBrowserElements();
    if (!elements) return;
    stopFileBrowserResize();
    stopFileBrowserColumnResize();
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    syncFileBrowserOpenButtonState(false);
    if (
        !isGitBranchOverlayOpen()
        && !isGitSyncOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isMobileSessionOverlayOpen()
        && !isUsageHistoryOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function openFileBrowserFromAbsolutePath(absolutePath, options = {}) {
    const target = resolveFileBrowserTargetFromAbsolutePath(absolutePath);
    const requestedLine = normalizeSourceLineNumber(options?.line);
    const requestedColumn = normalizeSourceColumnNumber(options?.column);
    if (!target) {
        return false;
    }
    if (isWorkModeEnabled()) {
        return openWorkModeFileTarget(target, {
            line: requestedLine,
            column: requestedColumn
        });
    }
    if (!target.path) {
        openFileBrowserOverlay({
            root: target.root,
            path: '',
            line: requestedLine,
            column: requestedColumn
        });
        return true;
    }
    openFileBrowserOverlay({
        root: target.root,
        filePath: target.path,
        line: requestedLine,
        column: requestedColumn
    });
    return true;
}

async function fetchGitSyncHistory(force = false, repoTarget = gitSyncOverlayRepoTarget, options = {}) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    const cache = getGitSyncHistoryCache(target);
    const requestedBranch = resolveGitSyncRequestBranch(
        target,
        options && typeof options === 'object' ? options.branch : ''
    ) || 'main';
    const now = Date.now();
    if (!force && cache.fetchedAt) {
        const delta = now - cache.fetchedAt;
        if (delta >= 0 && delta < GIT_BRANCH_STATUS_CACHE_MS) {
            return cache;
        }
    }
    if (gitSyncHistoryInFlightByTarget[target]) {
        return getGitSyncHistoryCache(target);
    }
    gitSyncHistoryInFlightByTarget[target] = true;
    try {
        const result = await fetchJson('/api/codex/git/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_HISTORY_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                repo_target: target,
                remote: 'origin',
                branch: requestedBranch,
                limit: 10
            })
        });
        const detailedFiles = Array.isArray(result?.changed_files_detail) ? result.changed_files_detail : [];
        const changedFiles = detailedFiles.length
            ? detailedFiles
            : (Array.isArray(result?.changed_files) ? result.changed_files : []);
        const changedCount = normalizeGitChangedFilesCount(result?.changed_files_count);
        const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(result?.windows_invalid_files);
        const windowsInvalidCount = normalizeGitWindowsInvalidCount(
            result?.windows_invalid_count,
            windowsInvalidFiles.length
        );
        const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
            result?.has_windows_path_issues,
            windowsInvalidCount
        );
        return setGitSyncHistoryCache(target, {
            repoRoot: typeof result?.repo_root === 'string' ? result.repo_root : '',
            repoMissing: Boolean(result?.repo_missing),
            currentBranch: typeof result?.current_branch === 'string' ? result.current_branch : '',
            currentBranchHistory: Array.isArray(result?.current_branch_history) ? result.current_branch_history : [],
            requestedMainBranch: typeof result?.requested_main_branch === 'string'
                ? result.requested_main_branch
                : 'main',
            mainBranch: typeof result?.main_branch === 'string' ? result.main_branch : 'main',
            mainBranchFallback: Boolean(result?.main_branch_fallback),
            remoteName: typeof result?.remote_name === 'string' ? result.remote_name : 'origin',
            remoteMainRef: typeof result?.remote_main_ref === 'string' ? result.remote_main_ref : 'origin/main',
            remoteMainHistory: Array.isArray(result?.remote_main_history) ? result.remote_main_history : [],
            remoteMainHistoryError: typeof result?.remote_main_history_error === 'string'
                ? result.remote_main_history_error
                : '',
            windowsInvalidFiles,
            windowsInvalidCount,
            hasWindowsPathIssues,
            changedCount: Number.isFinite(changedCount) ? changedCount : normalizeGitChangedFiles(changedFiles).length,
            changedFiles,
            aheadCount: Number.isFinite(result?.ahead_count) ? result.ahead_count : null,
            behindCount: Number.isFinite(result?.behind_count) ? result.behind_count : null,
            fetchedAt: Date.now(),
            isStale: false
        });
    } catch (error) {
        const payload = getGitErrorPayload(error);
        const isRepoMissing = payload?.error_code === 'repo_not_found';
        const message = normalizeGitActionError(error, 'sync 이력 조회에 실패했습니다.');
        const cached = setGitSyncHistoryCache(target, {
            repoRoot: '',
            repoMissing: isRepoMissing,
            currentBranch: resolveGitSyncRequestBranch(target),
            currentBranchHistory: getGitSyncHistoryCache(target).currentBranchHistory || [],
            remoteMainHistory: [],
            remoteMainHistoryError: isRepoMissing ? '현재 repository: None' : message,
            windowsInvalidFiles: [],
            windowsInvalidCount: 0,
            hasWindowsPathIssues: false,
            changedCount: isRepoMissing ? 0 : null,
            changedFiles: [],
            isStale: !isRepoMissing,
            fetchedAt: Date.now()
        });
        if (isRepoMissing) {
            return cached;
        }
        throw error;
    } finally {
        gitSyncHistoryInFlightByTarget[target] = false;
    }
}

async function refreshGitSyncOverlayHistory({ force = false, silent = false } = {}) {
    const elements = getGitSyncOverlayElements();
    if (!elements) return null;
    const target = normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget);
    setGitSyncOverlayLoading(true);
    try {
        const status = await fetchGitStatusForRepoTarget(target, force).catch(() => null);
        const statusBranchRaw = normalizeGitSyncBranchName(status?.branch, { allowDetached: true });
        const statusBranch = normalizeGitSyncBranchName(status?.branch);
        if (statusBranchRaw) {
            setGitSyncHistoryCache(target, { currentBranch: statusBranchRaw });
        }
        const history = await fetchGitSyncHistory(force, target, {
            branch: statusBranch
        });
        const statusFiles = normalizeGitChangedFiles(status?.changedFiles);
        const historyFiles = normalizeGitChangedFiles(history?.changedFiles);
        const mergedFiles = statusFiles.length ? statusFiles : historyFiles;
        const statusChangedCount = status ? getGitChangedFilesCountFromStatus(status) : null;
        const changedCount = Number.isFinite(statusChangedCount)
            ? statusChangedCount
            : normalizeGitChangedFilesCount(history?.changedCount);
        const statusWindowsInvalidFiles = normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles);
        const historyWindowsInvalidFiles = normalizeGitWindowsInvalidFiles(history?.windowsInvalidFiles);
        const mergedWindowsInvalidFiles = status
            ? statusWindowsInvalidFiles
            : historyWindowsInvalidFiles;
        const windowsInvalidCount = status
            ? normalizeGitWindowsInvalidCount(
                status?.windowsInvalidCount,
                mergedWindowsInvalidFiles.length
            )
            : normalizeGitWindowsInvalidCount(
                history?.windowsInvalidCount,
                mergedWindowsInvalidFiles.length
            );
        const hasWindowsPathIssues = status
            ? normalizeGitWindowsPathIssueState(status?.hasWindowsPathIssues, windowsInvalidCount)
            : normalizeGitWindowsPathIssueState(history?.hasWindowsPathIssues, windowsInvalidCount);
        const merged = setGitSyncHistoryCache(target, {
            currentBranch: statusBranchRaw || normalizeGitSyncBranchName(history?.currentBranch, { allowDetached: true }),
            changedCount: Number.isFinite(changedCount) ? changedCount : mergedFiles.length,
            changedFiles: mergedFiles,
            aheadCount: Number.isFinite(status?.aheadCount) ? status.aheadCount : history?.aheadCount,
            behindCount: Number.isFinite(status?.behindCount) ? status.behindCount : history?.behindCount,
            windowsInvalidFiles: mergedWindowsInvalidFiles,
            windowsInvalidCount,
            hasWindowsPathIssues
        });
        renderGitSyncOverlay(merged);
        return merged;
    } catch (error) {
        renderGitSyncOverlay(getGitSyncHistoryCache(target));
        if (!silent) {
            const message = normalizeGitActionError(error, 'sync 이력 조회에 실패했습니다.');
            showToast(`sync 이력 조회 실패: ${message}`, { tone: 'error', durationMs: 5200 });
        }
        return null;
    } finally {
        setGitSyncOverlayLoading(false);
    }
}

async function fetchGitStatus(force = false) {
    const now = Date.now();
    if (!force && gitBranchStatusCache.fetchedAt) {
        const delta = now - gitBranchStatusCache.fetchedAt;
        if (delta >= 0 && delta < GIT_BRANCH_STATUS_CACHE_MS) {
            return gitBranchStatusCache;
        }
    }
    if (gitBranchStatusInFlight) {
        return gitBranchStatusCache;
    }
    gitBranchStatusInFlight = true;
    try {
        const result = await fetchJson('/api/codex/git/status', {
            method: 'POST',
            timeoutMs: GIT_STATUS_REQUEST_TIMEOUT_MS
        });
        const count = normalizeGitChangedFilesCount(result?.changed_files_count);
        const branch = typeof result?.branch === 'string' ? result.branch : '';
        const detailedFiles = Array.isArray(result?.changed_files_detail) ? result.changed_files_detail : [];
        const changedFiles = detailedFiles.length
            ? detailedFiles
            : (Array.isArray(result?.changed_files) ? result.changed_files : []);
        const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(result?.windows_invalid_files);
        const windowsInvalidCount = normalizeGitWindowsInvalidCount(
            result?.windows_invalid_count,
            windowsInvalidFiles.length
        );
        const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
            result?.has_windows_path_issues,
            windowsInvalidCount
        );
        const aheadCount = normalizeGitDivergenceCount(result?.ahead_count);
        const behindCount = normalizeGitDivergenceCount(result?.behind_count);
        gitBranchStatusCache = {
            count,
            branch,
            aheadCount,
            behindCount,
            windowsInvalidFiles,
            windowsInvalidCount,
            hasWindowsPathIssues,
            changedFiles,
            isStale: false,
            fetchedAt: Date.now()
        };
        return gitBranchStatusCache;
    } catch (error) {
        gitBranchStatusCache = {
            count: null,
            branch: gitBranchStatusCache.branch || '',
            aheadCount: null,
            behindCount: null,
            windowsInvalidFiles: [],
            windowsInvalidCount: 0,
            hasWindowsPathIssues: false,
            changedFiles: [],
            isStale: true,
            fetchedAt: Date.now()
        };
        return gitBranchStatusCache;
    } finally {
        gitBranchStatusInFlight = false;
    }
}

async function fetchGitChangedFilesCount(force = false) {
    const status = await fetchGitStatus(force);
    return status?.count ?? null;
}

async function refreshGitBranchStatus({ force = false, updateOverlay = false } = {}) {
    const shouldRenderBranchOverlay = Boolean(updateOverlay && isGitBranchOverlayOpen());
    const status = await fetchGitStatus(force);
    const branchElement = document.getElementById('codex-git-branch');
    if (branchElement) {
        applyGitBranchStatusToElement(branchElement, status);
    }
    updateGitCommitButtonState(status);
    updateGitPushButtonState(status);
    if (isGitSyncOverlayOpen() && normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget) === GIT_SYNC_TARGET_WORKSPACE) {
        const mergedWorkspaceSync = setGitSyncHistoryCache(GIT_SYNC_TARGET_WORKSPACE, {
            changedCount: getGitChangedFilesCountFromStatus(status),
            changedFiles: normalizeGitChangedFiles(status?.changedFiles),
            aheadCount: Number.isFinite(status?.aheadCount) ? status.aheadCount : null,
            behindCount: Number.isFinite(status?.behindCount) ? status.behindCount : null,
            windowsInvalidFiles: normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles),
            windowsInvalidCount: normalizeGitWindowsInvalidCount(
                status?.windowsInvalidCount,
                normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles).length
            ),
            hasWindowsPathIssues: normalizeGitWindowsPathIssueState(
                status?.hasWindowsPathIssues,
                status?.windowsInvalidCount
            )
        });
        renderGitSyncOverlay(mergedWorkspaceSync);
    }
    syncGitSyncOverlayActionButtonsFromCache();
    if (shouldRenderBranchOverlay) {
        renderGitBranchOverlay(gitBranchStatusCache);
    }
    recoverGitPushButtonsIfIdle();
    return gitBranchStatusCache;
}

function startGitBranchPolling() {
    const branchElement = document.getElementById('codex-git-branch');
    if (!branchElement || gitBranchPollTimer) return;
    const tick = async (force = false) => {
        await refreshGitBranchStatus({ force, updateOverlay: true });
    };
    void tick(true);
    gitBranchPollTimer = setInterval(tick, GIT_BRANCH_POLL_MS);
    window.addEventListener('focus', () => {
        void tick(true);
    });
}

async function showGitBranchInfoToast(element) {
    if (!element) return;
    const now = Date.now();
    if (gitBranchToastAt && now - gitBranchToastAt < GIT_BRANCH_TOAST_COOLDOWN_MS) {
        return;
    }
    gitBranchToastAt = now;
    const branchName = getGitBranchFullName(element);
    if (!branchName) return;
    const changeCount = await fetchGitChangedFilesCount();
    const countText = Number.isFinite(changeCount)
        ? `변경 파일 ${changeCount}개`
        : '변경 파일 수를 불러올 수 없습니다';
    showToast(`브랜치: ${branchName} · ${countText}`, { tone: 'success', durationMs: 2400 });
}

function getGitPushButtons(preferredButton = null) {
    const candidates = [
        preferredButton,
        document.getElementById('codex-git-push'),
        document.getElementById('codex-branch-overlay-push'),
        document.getElementById('codex-sync-overlay-push')
    ];
    const seen = new Set();
    return candidates.filter(button => {
        if (!button || seen.has(button)) return false;
        seen.add(button);
        return true;
    });
}

function recoverGitPushButtonsIfIdle() {
    if (gitMutationInFlight) return;
    getGitPushButtons().forEach(button => {
        const appearsBusy = button.disabled
            || button.classList.contains('is-loading')
            || button.getAttribute('aria-busy') === 'true';
        if (appearsBusy) {
            setGitButtonBusy(button, false);
        }
    });
}

async function fetchGitStatusForRepoTarget(repoTarget, force = false) {
    const target = normalizeGitSyncRepoTarget(repoTarget);
    if (target === GIT_SYNC_TARGET_WORKSPACE) {
        return fetchGitStatus(force);
    }
    const result = await fetchJson('/api/codex/git/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: GIT_STATUS_REQUEST_TIMEOUT_MS,
        body: JSON.stringify({
            repo_target: target
        })
    });
    const count = normalizeGitChangedFilesCount(result?.changed_files_count);
    const branch = typeof result?.branch === 'string' ? result.branch : '';
    const aheadCount = normalizeGitDivergenceCount(result?.ahead_count);
    const behindCount = normalizeGitDivergenceCount(result?.behind_count);
    const detailedFiles = Array.isArray(result?.changed_files_detail) ? result.changed_files_detail : [];
    const changedFiles = detailedFiles.length
        ? detailedFiles
        : (Array.isArray(result?.changed_files) ? result.changed_files : []);
    const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(result?.windows_invalid_files);
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        result?.windows_invalid_count,
        windowsInvalidFiles.length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        result?.has_windows_path_issues,
        windowsInvalidCount
    );
    return {
        count,
        branch,
        aheadCount,
        behindCount,
        windowsInvalidFiles,
        windowsInvalidCount,
        hasWindowsPathIssues,
        changedFiles,
        isStale: false,
        fetchedAt: Date.now()
    };
}

async function handleGitCommit(button) {
    if (gitMutationInFlight) {
        console.warn('[codex-ui] git commit blocked: git mutation is already in flight');
        showToast('다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.', {
            tone: 'error',
            durationMs: 3800
        });
        return;
    }
    const selectedFiles = Array.from(gitOverlaySelectedFiles);
    if (!selectedFiles.length) {
        showToast('커밋할 파일을 먼저 선택해주세요.', { tone: 'error', durationMs: 3400 });
        return;
    }
    const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(gitBranchStatusCache?.windowsInvalidFiles);
    const windowsInvalidCount = normalizeGitWindowsInvalidCount(
        gitBranchStatusCache?.windowsInvalidCount,
        windowsInvalidFiles.length
    );
    const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
        gitBranchStatusCache?.hasWindowsPathIssues,
        windowsInvalidCount
    );
    if (hasWindowsPathIssues) {
        showToast(buildGitWindowsPathIssueToastMessage(windowsInvalidFiles, windowsInvalidCount), {
            tone: 'error',
            durationMs: 5200
        });
        return;
    }

    const elements = getGitBranchOverlayElements();
    const commitMessage = elements?.commitMessage?.value?.trim() || '';
    const commitButton = elements?.commitBtn;
    gitMutationInFlight = true;
    setGitButtonBusy(button, true, 'Committing...');
    if (commitButton && commitButton !== button) {
        setGitButtonBusy(commitButton, true, 'Committing...');
    }
    try {
        await fetchJson('/api/codex/git/stage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_STAGE_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                files: selectedFiles,
                replace: true
            })
        });
        const result = await fetchJson('/api/codex/git/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_COMMIT_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                message: commitMessage
            })
        });
        const commitHash = typeof result?.commit_hash === 'string' && result.commit_hash.trim()
            ? ` (${result.commit_hash.trim()})`
            : '';
        const commitSummary = summarizeGitOutput(result?.stdout || result?.stderr);
        const commitSuffix = commitSummary ? `: ${commitSummary}` : '';
        showToast(`git commit 완료${commitHash}${commitSuffix}`, { tone: 'success', durationMs: 3600 });
        if (elements?.commitMessage) {
            elements.commitMessage.value = '';
        }
        gitOverlaySelectionTouched = false;
        gitOverlaySelectedFiles = new Set();
    } catch (error) {
        let message = normalizeGitActionError(error, 'git commit 작업에 실패했습니다.');
        const cancelNotice = await requestGitCancelAfterTimeout(error, GIT_SYNC_TARGET_WORKSPACE);
        if (cancelNotice) {
            message = `${message} · ${cancelNotice}`;
        }
        showToast(`git commit 실패: ${message}`, { tone: 'error', durationMs: 5200 });
    } finally {
        gitMutationInFlight = false;
        setGitButtonBusy(button, false);
        if (commitButton && commitButton !== button) {
            setGitButtonBusy(commitButton, false);
        }
        void refreshGitBranchStatus({ force: true, updateOverlay: true });
    }
}

async function handleGitQuickCommit(button, options = {}) {
    if (gitMutationInFlight) {
        console.warn('[codex-ui] git quick commit blocked: git mutation is already in flight');
        showToast('다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.', {
            tone: 'error',
            durationMs: 3800
        });
        return;
    }
    const requestedRepoTarget = options && typeof options === 'object' ? options.repoTarget : '';
    const repoTarget = normalizeGitSyncRepoTarget(requestedRepoTarget || GIT_SYNC_TARGET_WORKSPACE);
    const repoLabel = getGitSyncRepoLabel(repoTarget);

    gitMutationInFlight = true;
    setGitButtonBusy(button, true, 'Committing...');
    try {
        const status = await fetchGitStatusForRepoTarget(repoTarget, true);
        const windowsInvalidFiles = normalizeGitWindowsInvalidFiles(status?.windowsInvalidFiles);
        const windowsInvalidCount = normalizeGitWindowsInvalidCount(
            status?.windowsInvalidCount,
            windowsInvalidFiles.length
        );
        const hasWindowsPathIssues = normalizeGitWindowsPathIssueState(
            status?.hasWindowsPathIssues,
            windowsInvalidCount
        );
        if (hasWindowsPathIssues) {
            showToast(`${repoLabel} · ${buildGitWindowsPathIssueToastMessage(windowsInvalidFiles, windowsInvalidCount)}`, {
                tone: 'error',
                durationMs: 5200
            });
            return;
        }
        const allFiles = normalizeGitChangedFiles(status?.changedFiles).map(file => file.path);
        if (!allFiles.length) {
            showToast(`${repoLabel} · 커밋할 변경 파일이 없습니다.`, { tone: 'error', durationMs: 3200 });
            return;
        }
        await fetchJson('/api/codex/git/stage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_STAGE_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                repo_target: repoTarget,
                files: allFiles,
                replace: true
            })
        });
        const result = await fetchJson('/api/codex/git/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_COMMIT_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                repo_target: repoTarget,
                message: ''
            })
        });
        const commitHash = typeof result?.commit_hash === 'string' && result.commit_hash.trim()
            ? ` (${result.commit_hash.trim()})`
            : '';
        const commitSummary = summarizeGitOutput(result?.stdout || result?.stderr);
        const commitSuffix = commitSummary ? `: ${commitSummary}` : '';
        showToast(`${repoLabel} · git commit 완료${commitHash}${commitSuffix}`, { tone: 'success', durationMs: 3600 });
        if (repoTarget === GIT_SYNC_TARGET_WORKSPACE && isGitBranchOverlayOpen()) {
            gitOverlaySelectionTouched = false;
            gitOverlaySelectedFiles = new Set();
            const overlayElements = getGitBranchOverlayElements();
            if (overlayElements?.commitMessage) {
                overlayElements.commitMessage.value = '';
            }
        }
        setGitSyncHistoryCache(repoTarget, { fetchedAt: 0 });
        if (isGitSyncOverlayOpen() && repoTarget === normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)) {
            await refreshGitSyncOverlayHistory({ force: true, silent: true });
        }
    } catch (error) {
        let message = normalizeGitActionError(error, 'git commit 작업에 실패했습니다.');
        const cancelNotice = await requestGitCancelAfterTimeout(error, repoTarget);
        if (cancelNotice) {
            message = `${message} · ${cancelNotice}`;
        }
        showToast(`${repoLabel} · git commit 실패: ${message}`, { tone: 'error', durationMs: 5200 });
    } finally {
        gitMutationInFlight = false;
        setGitButtonBusy(button, false);
        void refreshGitBranchStatus({ force: true, updateOverlay: true });
    }
}

async function handleGitPush(button, options = {}) {
    recoverGitPushButtonsIfIdle();
    if (gitMutationInFlight) {
        console.warn('[codex-ui] git push blocked: git mutation is already in flight');
        showToast('다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.', {
            tone: 'error',
            durationMs: 3800
        });
        return;
    }
    const requestedRepoTarget = options && typeof options === 'object' ? options.repoTarget : '';
    const repoTarget = normalizeGitSyncRepoTarget(requestedRepoTarget || GIT_SYNC_TARGET_WORKSPACE);
    const repoLabel = getGitSyncRepoLabel(repoTarget);
    const confirmed = window.confirm(
        `${repoLabel} 기준으로 현재 브랜치를 원격 저장소로 push하고, 이어서 fetch까지 실행할까요?`
    );
    if (!confirmed) {
        return;
    }

    const pushButtons = getGitPushButtons(button);
    gitMutationInFlight = true;
    try {
        pushButtons.forEach(pushButton => {
            setGitButtonBusy(pushButton, true, 'Pushing...');
        });
        const result = await fetchJson('/api/codex/git/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: GIT_PUSH_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({
                confirm: true,
                repo_target: repoTarget
            })
        });
        const summary = summarizeGitOutput(result?.stdout || result?.stderr);
        const suffix = summary ? `: ${summary}` : '';
        if (result?.post_fetch_ok === false) {
            const postFetchSummary = summarizeGitOutput(
                result?.post_fetch_error || result?.post_fetch_stderr || result?.post_fetch_stdout
            );
            const postFetchSuffix = postFetchSummary ? ` (${postFetchSummary})` : '';
            showToast(`${repoLabel} · git push 완료, post-fetch 실패${postFetchSuffix}`, {
                tone: 'error',
                durationMs: 5200
            });
        } else {
            showToast(`${repoLabel} · git push + fetch 완료${suffix}`, { tone: 'success', durationMs: 3600 });
            setGitSyncHistoryCache(repoTarget, { fetchedAt: 0 });
            if (isGitSyncOverlayOpen() && repoTarget === normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)) {
                await refreshGitSyncOverlayHistory({ force: true, silent: true });
            }
        }
    } catch (error) {
        let message = normalizeGitActionError(error, 'git push 작업에 실패했습니다.');
        const cancelNotice = await requestGitCancelAfterTimeout(error, repoTarget);
        if (cancelNotice) {
            message = `${message} · ${cancelNotice}`;
        }
        showToast(`${repoLabel} · git push 실패: ${message}`, { tone: 'error', durationMs: 5200 });
    } finally {
        gitMutationInFlight = false;
        pushButtons.forEach(pushButton => {
            setGitButtonBusy(pushButton, false);
        });
        void refreshGitBranchStatus({ force: true, updateOverlay: true });
    }
}

async function handleGitSync(button, options = {}) {
    if (gitMutationInFlight) {
        console.warn('[codex-ui] git sync blocked: git mutation is already in flight');
        showToast('다른 git 작업이 진행 중입니다. 잠시 후 다시 시도해주세요.', {
            tone: 'error',
            durationMs: 3800
        });
        return;
    }
    const requestedRepoTarget = options && typeof options === 'object' ? options.repoTarget : '';
    const repoTarget = normalizeGitSyncRepoTarget(requestedRepoTarget || gitSyncOverlayRepoTarget);
    const repoLabel = getGitSyncRepoLabel(repoTarget);
    const applyAfterFetch = Boolean(options && typeof options === 'object' && options.applyAfterFetch);
    const requestTimeoutMs = applyAfterFetch
        ? GIT_FETCH_SYNC_REQUEST_TIMEOUT_MS
        : GIT_FETCH_ONLY_REQUEST_TIMEOUT_MS;
    const syncStatus = await fetchGitStatusForRepoTarget(repoTarget, true).catch(() => null);
    const statusBranchRaw = normalizeGitSyncBranchName(syncStatus?.branch, { allowDetached: true });
    if (statusBranchRaw) {
        setGitSyncHistoryCache(repoTarget, { currentBranch: statusBranchRaw });
    }
    let branchName = normalizeGitSyncBranchName(syncStatus?.branch);
    if (!branchName) {
        branchName = resolveGitSyncRequestBranch(
            repoTarget,
            options && typeof options === 'object' ? options.branch : ''
        );
    }
    if (!branchName && applyAfterFetch) {
        showToast(`${repoLabel} · 현재 브랜치를 확인할 수 없어 fast-forward를 적용할 수 없습니다.`, {
            tone: 'error',
            durationMs: 4200
        });
        return;
    }

    gitMutationInFlight = true;
    setGitButtonBusy(button, true, applyAfterFetch ? 'Fetch + fast-forward...' : 'Fetching...');
    try {
        const result = await fetchJson('/api/codex/git/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: requestTimeoutMs,
            body: JSON.stringify({
                repo_target: repoTarget,
                remote: 'origin',
                branch: branchName || '',
                apply_after_fetch: applyAfterFetch
            })
        });
        const summary = summarizeGitOutput(result?.stdout || result?.stderr);
        const suffix = summary ? `: ${summary}` : '';
        const syncTarget = typeof result?.sync_target === 'string' && result.sync_target.trim()
            ? result.sync_target.trim()
            : (branchName ? `origin/${branchName}` : 'origin/(unknown)');
        if (applyAfterFetch) {
            showToast(`${repoLabel} · ${syncTarget} fetch + fast-forward 완료${suffix}`, {
                tone: 'success',
                durationMs: 3600
            });
        } else {
            showToast(`${repoLabel} · ${syncTarget} fetch 완료${suffix}`, { tone: 'success', durationMs: 3600 });
        }
        setGitSyncHistoryCache(repoTarget, { fetchedAt: 0 });
        if (isGitSyncOverlayOpen() && repoTarget === normalizeGitSyncRepoTarget(gitSyncOverlayRepoTarget)) {
            await refreshGitSyncOverlayHistory({ force: true, silent: true });
        }
    } catch (error) {
        const fallbackMessage = applyAfterFetch
            ? 'git fetch + fast-forward 작업에 실패했습니다.'
            : 'git fetch 작업에 실패했습니다.';
        let message = normalizeGitActionError(error, fallbackMessage);
        const cancelNotice = await requestGitCancelAfterTimeout(error, repoTarget);
        if (cancelNotice) {
            message = `${message} · ${cancelNotice}`;
        }
        const actionLabel = applyAfterFetch ? 'fetch + fast-forward' : 'fetch';
        showToast(`${repoLabel} · ${actionLabel} 실패: ${message}`, { tone: 'error', durationMs: 5200 });
    } finally {
        gitMutationInFlight = false;
        setGitButtonBusy(button, false);
        void refreshGitBranchStatus({ force: true, updateOverlay: true });
    }
}

function isStreamNotFoundError(error) {
    if (error && typeof error === 'object' && error.status === 404) {
        return true;
    }
    const message = normalizeError(error, '').toLowerCase();
    return message.includes('스트림을 찾을 수 없습니다') || message.includes('stream not found');
}

async function recoverMissingStream(stream) {
    if (!stream?.id || !stream?.sessionId) return;
    const sessionId = stream.sessionId;
    clearPersistedStream(stream.id);
    clearStreamState(stream.id);
    const sessionState = getSessionState(sessionId);
    if (sessionState) {
        sessionState.sending = false;
    }
    unpinAutoScrollForSession(sessionId);
    setSessionStatus(sessionId, 'Stream completed. Reloading...');
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }
    await loadSessions({ preserveActive: true, reloadActive: sessionId === state.activeSessionId });
    setSessionStatus(sessionId, 'Idle');
}

async function resumeStreamsFromStorage(pendingStreams) {
    if (!Array.isArray(pendingStreams) || pendingStreams.length === 0) return;
    const sessionIds = new Set(state.sessions.map(session => session.id));

    for (const pending of pendingStreams) {
        if (!pending?.id || !pending?.sessionId) continue;
        if (!sessionIds.has(pending.sessionId)) {
            clearPersistedStream(pending.id);
            continue;
        }
        const sessionState = ensureSessionState(pending.sessionId);
        if (sessionState?.streamId) {
            continue;
        }
        if (sessionState) {
            sessionState.sending = true;
        }
        setSessionStatus(pending.sessionId, 'Reconnecting to Codex...');
        if (pending.sessionId === state.activeSessionId) {
            syncActiveSessionControls();
        }
        try {
            const response = await fetch(`/api/codex/streams/${pending.id}?offset=0&error_offset=0`);
            const result = await response.json();
            if (!response.ok) {
                const err = new Error(result?.error || 'Failed to resume stream.');
                err.status = response.status;
                throw err;
            }
            if (result?.done) {
                clearPersistedStream(pending.id);
                if (sessionState) {
                    sessionState.sending = false;
                }
                setSessionStatus(pending.sessionId, 'Idle');
                if (pending.sessionId === state.activeSessionId) {
                    syncActiveSessionControls();
                }
                continue;
            }

            const output = result?.output || '';
            const errorText = result?.error || '';
            const outputOffset = Number.isFinite(result?.output_length)
                ? result.output_length
                : output.length;
            const errorOffset = Number.isFinite(result?.error_length)
                ? result.error_length
                : errorText.length;
            const eventOffset = Number.isFinite(result?.event_length)
                ? result.event_length
                : 0;
            const messageId = typeof result?.assistant_message_id === 'string' && result.assistant_message_id.trim()
                ? result.assistant_message_id.trim()
                : (typeof pending?.messageId === 'string' ? pending.messageId.trim() : '');

            let assistantEntry = null;
            if (pending.sessionId === state.activeSessionId) {
                assistantEntry = findMessageEntryById(messageId);
                if (!assistantEntry) {
                    assistantEntry = appendMessageToDOM({
                        id: messageId || '',
                        role: 'assistant',
                        content: '',
                        created_at: new Date().toISOString()
                    }, 'assistant');
                }
                if (assistantEntry) {
                    setMessageStreaming(assistantEntry.wrapper, true);
                }
            }

            const stream = createStreamState({
                id: pending.id,
                sessionId: pending.sessionId,
                output,
                error: errorText,
                outputOffset,
                errorOffset,
                eventOffset,
                entry: assistantEntry,
                messageId,
                startedAt: normalizeStartedAt(result?.started_at)
                    || normalizeStartedAt(result?.created_at)
                    || normalizeStartedAt(pending.startedAt)
                    || Date.now()
            });
            if (!stream) {
                clearPersistedStream(pending.id);
                if (sessionState) {
                    sessionState.sending = false;
                }
                continue;
            }
            persistActiveStream(stream);
            if (typeof result?.process_running === 'boolean') {
                stream.processRunning = result.process_running;
            }
            stream.processPid = Number.isFinite(result?.process_pid) ? result.process_pid : null;
            stream.runtimeMs = Number.isFinite(result?.runtime_ms) ? result.runtime_ms : stream.runtimeMs;
            stream.idleMs = Number.isFinite(result?.idle_ms) ? result.idle_ms : stream.idleMs;
            if (assistantEntry) {
                updateStreamEntry(stream);
            }
            beginStreamPolling(stream.id);
            setSessionStatus(pending.sessionId, buildActiveStreamStatus(stream.processRunning));
        } catch (error) {
            if (isStreamNotFoundError(error)) {
                await recoverMissingStream({ id: pending.id, sessionId: pending.sessionId });
                continue;
            }
            clearPersistedStream(pending.id);
            if (sessionState) {
                sessionState.sending = false;
            }
            setSessionStatus(pending.sessionId, normalizeError(error, 'Failed to resume stream.'), true);
            if (pending.sessionId === state.activeSessionId) {
                syncActiveSessionControls();
            }
        }
    }
}

async function syncActiveSessionMessagesFromServer(sessionId) {
    if (!sessionId || sessionId !== state.activeSessionId) return false;
    try {
        const result = await fetchJson(`/api/codex/sessions/${sessionId}`, {
            timeoutMs: SESSION_DETAIL_REQUEST_TIMEOUT_MS
        });
        const session = result?.session;
        if (!session) return false;
        if ((session?.id || sessionId) !== state.activeSessionId) {
            return false;
        }
        if (session?.id) {
            upsertSessionSummary(session);
        }
        renderSessions();
        renderMessages(session?.messages || []);
        updateHeader(session || null);
        syncActiveSessionControls();
        syncActiveSessionStatus();
        return true;
    } catch (error) {
        console.warn('[codex-ui] failed to sync active session messages from server', error);
        return false;
    }
}

async function connectToExistingStream(sessionId, streamId, startedAt = null) {
    if (!sessionId || !streamId) return false;
    const sessionState = ensureSessionState(sessionId);
    if (sessionState?.streamId === streamId) {
        return true;
    }
    if (sessionState?.streamId && sessionState.streamId !== streamId) {
        return false;
    }
    const normalizedStartedAt = normalizeStartedAt(startedAt) || Date.now();
    if (sessionId === state.activeSessionId) {
        await syncActiveSessionMessagesFromServer(sessionId);
    }
    persistActiveStream({
        id: streamId,
        sessionId,
        startedAt: normalizedStartedAt
    });
    await resumeStreamsFromStorage([{
        id: streamId,
        sessionId,
        startedAt: normalizedStartedAt
    }]);
    await refreshRemoteStreams({ force: true });
    const attachedState = getSessionState(sessionId);
    if (attachedState?.streamId === streamId) {
        return true;
    }
    if (state.remoteStreamSessions?.has(sessionId)) {
        if (attachedState) {
            attachedState.sending = false;
        }
        return true;
    }
    return false;
}

function renderSessionsIntoList(list, { closeOverlayOnSelect = false } = {}) {
    if (!(list instanceof HTMLElement)) return;
    list.innerHTML = '';

    if (!state.sessions.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No sessions yet.';
        list.appendChild(empty);
        return;
    }

    state.sessions.forEach(session => {
        const item = document.createElement('div');
        item.className = 'session-item';
        if (session.id === state.activeSessionId) {
            item.classList.add('active');
        }

        const selectBtn = document.createElement('button');
        selectBtn.type = 'button';
        selectBtn.className = 'session-select';

        const title = document.createElement('div');
        title.className = 'session-title';
        const sessionTitle = session.title || 'New session';
        title.textContent = sessionTitle;
        setHoverTooltip(title, sessionTitle);
        selectBtn.setAttribute('title', sessionTitle);

        const meta = document.createElement('div');
        meta.className = 'session-meta';
        const updated = formatTimestamp(session.updated_at);
        const count = resolveSessionMessageCount(session);
        const tokenSummary = formatSessionTokenSummary(session);
        const metaText = document.createElement('span');
        metaText.className = 'session-meta-text';
        const metaParts = [];
        if (updated) {
            metaParts.push(`Updated ${updated}`);
        }
        metaParts.push(`${count} msgs`);
        if (tokenSummary) {
            metaParts.push(tokenSummary);
        }
        metaText.textContent = metaParts.join(' · ');
        meta.appendChild(metaText);
        if (isSessionStreaming(session.id)) {
            const spinner = document.createElement('span');
            spinner.className = 'session-spinner';
            spinner.setAttribute('aria-label', 'Streaming');
            spinner.setAttribute('title', 'Streaming');
            meta.appendChild(spinner);
        }

        selectBtn.appendChild(title);
        selectBtn.appendChild(meta);
        selectBtn.addEventListener('click', async () => {
            if (closeOverlayOnSelect) {
                closeMobileSessionOverlay();
            }
            await loadSession(session.id);
        });

        const footer = document.createElement('div');
        footer.className = 'session-footer';
        const responseModeBadge = createSessionResponseModeBadge(session);
        if (responseModeBadge) {
            footer.appendChild(responseModeBadge);
        }

        const actions = document.createElement('div');
        actions.className = 'session-actions';

        const renameBtn = document.createElement('button');
        renameBtn.type = 'button';
        renameBtn.className = 'session-action';
        renameBtn.textContent = 'Rename';
        renameBtn.addEventListener('click', async event => {
            event.stopPropagation();
            await renameSession(session);
        });

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'session-action danger';
        deleteBtn.textContent = 'Delete';
        deleteBtn.addEventListener('click', async event => {
            event.stopPropagation();
            await deleteSession(session.id);
        });

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        footer.appendChild(actions);
        item.appendChild(selectBtn);
        item.appendChild(footer);
        list.appendChild(item);
    });
}

function renderSessions() {
    const primaryList = document.getElementById('codex-session-list');
    const mobileOverlayList = document.getElementById('codex-mobile-session-list');
    const targets = [];
    if (primaryList) {
        targets.push({ list: primaryList, closeOverlayOnSelect: false });
    }
    if (mobileOverlayList) {
        targets.push({ list: mobileOverlayList, closeOverlayOnSelect: true });
    }
    if (targets.length === 0) return;
    updateSessionsHeaderSummary();
    updateChatSessionNavigationButtons();
    targets.forEach(target => {
        renderSessionsIntoList(target.list, {
            closeOverlayOnSelect: Boolean(target.closeOverlayOnSelect)
        });
    });
    renderRunningJobsMonitor();
}

function getMobileSessionOverlayElements() {
    const overlay = document.getElementById('codex-mobile-session-overlay');
    if (!overlay) return null;
    return {
        overlay,
        list: document.getElementById('codex-mobile-session-list')
    };
}

function isMobileSessionOverlayOpen() {
    const overlay = document.getElementById('codex-mobile-session-overlay');
    return overlay ? overlay.classList.contains('is-visible') : false;
}

function openMobileSessionOverlay() {
    const canOpenOverlay = isPhoneLayout() || isWorkModeEnabled();
    if (!canOpenOverlay) return;
    const elements = getMobileSessionOverlayElements();
    if (!elements) return;
    if (isGitBranchOverlayOpen()) {
        closeGitBranchOverlay();
    }
    if (isGitSyncOverlayOpen()) {
        closeGitSyncOverlay();
    }
    if (isMessageLogOverlayOpen()) {
        closeMessageLogOverlay();
    }
    if (isFileBrowserOverlayOpen()) {
        closeFileBrowserOverlay();
    }
    if (isUsageHistoryOverlayOpen()) {
        closeUsageHistoryOverlay();
    }
    renderSessions();
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    const trigger = document.getElementById('codex-chat-title');
    if (trigger) {
        trigger.setAttribute('aria-expanded', 'true');
    }
    document.body.classList.add('is-overlay-open');
}

function closeMobileSessionOverlay() {
    const elements = getMobileSessionOverlayElements();
    if (!elements) return;
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    const trigger = document.getElementById('codex-chat-title');
    if (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
    }
    if (
        !isGitBranchOverlayOpen()
        && !isGitSyncOverlayOpen()
        && !isMessageLogOverlayOpen()
        && !isFileBrowserOverlayOpen()
        && !isUsageHistoryOverlayOpen()
        && !isTerminalOverlayOpen()
    ) {
        document.body.classList.remove('is-overlay-open');
    }
}

function upsertSessionSummary(session) {
    if (!session || !session.id) return;
    const fallbackMessages = Array.isArray(session.messages) ? session.messages : [];
    const usage = resolveSessionTokenUsage(session, fallbackMessages);
    const resolvedCount = Number.isFinite(Number(session.message_count))
        ? Math.max(0, Math.round(Number(session.message_count)))
        : fallbackMessages.length;
    const lastResponseMode = resolveSessionLastResponseMode(session);
    const summary = {
        id: session.id,
        title: session.title || 'New session',
        created_at: session.created_at,
        updated_at: session.updated_at,
        message_count: resolvedCount,
        last_response_mode: lastResponseMode || null,
        token_count: usage.totalTokens,
        input_token_count: usage.inputTokens,
        cached_input_token_count: usage.cachedInputTokens,
        output_token_count: usage.outputTokens,
        reasoning_output_token_count: usage.reasoningOutputTokens,
        token_estimated: usage.estimated
    };
    const existingIndex = state.sessions.findIndex(item => item.id === session.id);
    if (existingIndex >= 0) {
        state.sessions[existingIndex] = summary;
    } else {
        state.sessions.push(summary);
    }
    state.sessions.sort((a, b) => {
        const aKey = a.updated_at || a.created_at || '';
        const bKey = b.updated_at || b.created_at || '';
        return bKey.localeCompare(aKey);
    });
}

function removeSessionSummary(sessionId) {
    state.sessions = state.sessions.filter(session => session.id !== sessionId);
    const sessionState = state.sessionStates[sessionId];
    if (sessionState?.streamId) {
        clearStreamState(sessionState.streamId);
        clearPersistedStream(sessionState.streamId);
    }
    delete state.sessionStates[sessionId];
    updateSessionsHeaderSummary();
}

async function createSession(selectAfter = true) {
    setStatus('Creating session...');
    try {
        const result = await fetchJson('/api/codex/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: SESSION_MUTATION_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({})
        });
        if (result?.session_storage) {
            state.sessionStorage = result.session_storage;
            updateSessionStorageSummary(state.sessionStorage);
        }
        const sessionId = result?.session?.id;
        upsertSessionSummary(result?.session);
        if (selectAfter && sessionId) {
            state.activeSessionId = sessionId;
            ensureSessionState(sessionId);
            renderSessions();
            await loadSession(sessionId);
        } else {
            renderSessions();
        }
        syncActiveSessionStatus();
        return result?.session;
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to create session.'), true);
        return null;
    }
}

async function loadSession(sessionId) {
    if (!sessionId) return;
    setStatus('Loading session...');
    try {
        const result = await fetchJson(`/api/codex/sessions/${sessionId}`, {
            timeoutMs: SESSION_DETAIL_REQUEST_TIMEOUT_MS
        });
        const session = result?.session;
        const previousSessionId = state.activeSessionId;
        state.activeSessionId = session?.id || sessionId;
        ensureSessionState(state.activeSessionId);
        if (session?.id) {
            upsertSessionSummary(session);
        }
        if (previousSessionId && previousSessionId !== state.activeSessionId) {
            detachSessionStreamEntry(previousSessionId);
        }
        renderSessions();
        renderMessages(session?.messages || []);
        attachSessionStreamEntry(state.activeSessionId);
        updateHeader(session || null);
        syncActiveSessionControls();
        syncActiveSessionStatus();
        void maybeAttachRemoteStreamToActiveSession(state.remoteStreams);
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to load session.'), true);
    }
}

function renderMessages(messages) {
    const container = document.getElementById('codex-chat-messages');
    if (!container) return;
    container.innerHTML = '';

    if (!messages || messages.length === 0) {
        const placeholder = document.createElement('div');
        placeholder.className = 'chat-placeholder';
        placeholder.textContent = 'No messages yet.';
        container.appendChild(placeholder);
        scrollToBottom(true);
        return;
    }

    messages.forEach(message => {
        const wrapper = document.createElement('div');
        wrapper.className = 'message';
        const roleClass = message?.role || 'assistant';
        wrapper.classList.add(roleClass);
        const timestampValue = getMessageTimestampValue(message);
        setMessageWrapperIdentity(wrapper, roleClass, timestampValue, message?.id);

        const metaText = buildMessageMetaText(roleClass, timestampValue, message);
        const meta = buildMessageMeta(metaText, wrapper);

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        setMarkdownContent(bubble, message?.content || '', { message });
        const streamIndicator = createMessageStreamIndicatorElement();

        const footer = createMessageFooter();
        const durationMs = Number(message?.duration_ms);
        if (Number.isFinite(durationMs)) {
            setMessageDuration(footer, durationMs);
        }
        setMessageTimingBreakdown(footer, message);
        setMessageFinalizeReason(footer, message?.finalize_reason);
        setMessageFinalizeComparison(footer, message);
        setMessageDetailLogLink(footer, message);
        setMessagePreviewLink(footer, message?.content || '', message, wrapper);
        setMessageTokenUsage(footer, message);

        wrapper.appendChild(meta);
        wrapper.appendChild(bubble);
        wrapper.appendChild(streamIndicator);
        wrapper.appendChild(footer);
        container.appendChild(wrapper);
    });

    scrollToBottom(true);
}

function createMessageStreamIndicatorElement() {
    const indicator = document.createElement('div');
    indicator.className = 'message-stream-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    const bar = document.createElement('span');
    bar.className = 'message-stream-indicator-bar';
    const dot = document.createElement('span');
    dot.className = 'message-stream-indicator-dot';
    bar.appendChild(dot);
    const text = document.createElement('span');
    text.className = 'message-stream-indicator-text';
    text.textContent = 'Responding...';
    indicator.appendChild(bar);
    indicator.appendChild(text);
    return indicator;
}

function appendMessageToDOM(message, roleOverride = null) {
    const container = document.getElementById('codex-chat-messages');
    if (!container) return null;
    const placeholder = container.querySelector('.chat-placeholder');
    if (placeholder) placeholder.remove();

    const wrapper = document.createElement('div');
    wrapper.className = 'message';
    const role = roleOverride || message?.role || 'assistant';
    wrapper.classList.add(role);
    const timestampValue = getMessageTimestampValue(message);
    setMessageWrapperIdentity(wrapper, role, timestampValue, message?.id);

    const metaText = buildMessageMetaText(role, timestampValue, message);
    const meta = buildMessageMeta(metaText, wrapper);

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    setMarkdownContent(bubble, message?.content || '', { message });
    const streamIndicator = createMessageStreamIndicatorElement();

    const footer = createMessageFooter();
    const durationMs = Number(message?.duration_ms);
    if (Number.isFinite(durationMs)) {
        setMessageDuration(footer, durationMs);
    }
    setMessageTimingBreakdown(footer, message);
    setMessageFinalizeReason(footer, message?.finalize_reason);
    setMessageFinalizeComparison(footer, message);
    setMessageDetailLogLink(footer, message);
    setMessagePreviewLink(footer, message?.content || '', message, wrapper);
    setMessageTokenUsage(footer, message);

    wrapper.appendChild(meta);
    wrapper.appendChild(bubble);
    wrapper.appendChild(streamIndicator);
    wrapper.appendChild(footer);
    container.appendChild(wrapper);
    scrollToBottom();
    return { wrapper, bubble, meta, footer };
}

function updateHeader(session) {
    const title = document.getElementById('codex-chat-title');
    const meta = document.getElementById('codex-chat-meta');
    if (!title || !meta) return;
    if (!session) {
        title.textContent = 'Select a session';
        title.setAttribute('title', 'Select a session');
        title.setAttribute('aria-label', 'Select a session');
        meta.textContent = '';
        return;
    }
    const sessionTitle = session.title || 'New session';
    title.textContent = sessionTitle;
    title.setAttribute('title', sessionTitle);
    title.setAttribute('aria-label', sessionTitle);
    const updated = formatTimestamp(session.updated_at);
    const count = resolveSessionMessageCount(session);
    const tokenSummary = formatSessionTokenSummary(session);
    const parts = [];
    if (updated) {
        parts.push(`Updated ${updated}`);
    }
    parts.push(`${count} msgs`);
    if (tokenSummary) {
        parts.push(tokenSummary);
    }
    meta.textContent = parts.join(' · ');
}

function normalizePlanModeState(value) {
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (normalized === PLAN_MODE_STATE_PLAN_ONLY || normalized === 'true' || normalized === '1') {
            return PLAN_MODE_STATE_PLAN_ONLY;
        }
        if (
            normalized === PLAN_MODE_STATE_PLAN_AND_EXECUTE
            || normalized === 'auto'
            || normalized === '2'
        ) {
            return PLAN_MODE_STATE_PLAN_AND_EXECUTE;
        }
    } else if (value === true) {
        return PLAN_MODE_STATE_PLAN_ONLY;
    }
    return PLAN_MODE_STATE_OFF;
}

function getPlanModeState() {
    return normalizePlanModeState(state.settings.planModeState);
}

function shouldUsePlanModeForRequest(planModeState = getPlanModeState()) {
    return planModeState !== PLAN_MODE_STATE_OFF;
}

function shouldAutoExecuteAfterPlan(planModeState = getPlanModeState()) {
    return planModeState === PLAN_MODE_STATE_PLAN_AND_EXECUTE;
}

function getNextPlanModeState(currentState = getPlanModeState()) {
    if (currentState === PLAN_MODE_STATE_OFF) {
        return PLAN_MODE_STATE_PLAN_ONLY;
    }
    if (currentState === PLAN_MODE_STATE_PLAN_ONLY) {
        return PLAN_MODE_STATE_PLAN_AND_EXECUTE;
    }
    return PLAN_MODE_STATE_OFF;
}

async function queuePromptOnServer(sessionId, prompt, { planMode = false, attachments = [] } = {}) {
    if (!sessionId) {
        return { ok: false, reason: 'missing_session' };
    }
    const normalizedAttachments = Array.isArray(attachments)
        ? attachments.map(normalizeChatAttachment).filter(Boolean)
        : [];
    const response = await fetch(`/api/codex/sessions/${sessionId}/message/queue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt,
            plan_mode: Boolean(planMode),
            attachments: normalizedAttachments
        })
    });
    const result = await response.json();
    if (!response.ok) {
        const err = new Error(result?.error || 'Failed to queue message.');
        err.status = response.status;
        err.payload = result;
        throw err;
    }

    const queueCount = Number.isFinite(Number(result?.queue_count))
        ? Math.max(0, Number(result.queue_count))
        : 0;
    if (result?.started && result?.stream_id) {
        processStartedStreamResponse(
            sessionId,
            prompt,
            result,
            Date.now(),
            resolveRequestResponseMetadata({
                planMode,
                responseMode: result?.response_mode,
                responseModel: result?.response_model
            })
        );
        return {
            ok: true,
            reason: 'started',
            sessionId,
            queueCount
        };
    }
    return {
        ok: true,
        reason: 'queued',
        sessionId,
        queueCount,
        activeStreamId: result?.active_stream_id || null
    };
}

async function queuePromptWithPlanMode(sessionId, prompt, planModeState = getPlanModeState(), { attachments = [] } = {}) {
    const normalizedPrompt = String(prompt || '').trim();
    if (!sessionId || !normalizedPrompt) {
        return {
            addedCount: 0,
            totalQueued: 0,
            lastResult: null
        };
    }
    const normalizedPlanModeState = normalizePlanModeState(planModeState);
    const queueItems = [];
    if (normalizedPlanModeState === PLAN_MODE_STATE_PLAN_AND_EXECUTE) {
        queueItems.push({ prompt: normalizedPrompt, planMode: true, attachments });
        queueItems.push({ prompt: PLAN_MODE_AUTO_EXECUTE_PROMPT, planMode: false });
    } else {
        queueItems.push({
            prompt: normalizedPrompt,
            planMode: normalizedPlanModeState === PLAN_MODE_STATE_PLAN_ONLY,
            attachments
        });
    }

    let lastResult = null;
    let totalQueued = 0;
    for (const item of queueItems) {
        lastResult = await queuePromptOnServer(sessionId, item.prompt, {
            planMode: item.planMode,
            attachments: item.attachments || []
        });
        const queueCount = Number(lastResult?.queueCount);
        if (Number.isFinite(queueCount)) {
            totalQueued = Math.max(0, queueCount);
        }
    }
    return {
        addedCount: queueItems.length,
        totalQueued,
        lastResult
    };
}

function setPlanModeToggleState(nextState) {
    const normalized = normalizePlanModeState(nextState);
    state.settings.planModeState = normalized;
    const button = document.getElementById('codex-plan-mode-toggle');
    if (!button) return;
    const isActive = normalized !== PLAN_MODE_STATE_OFF;
    const isPlanAndExecute = normalized === PLAN_MODE_STATE_PLAN_AND_EXECUTE;
    button.classList.toggle('is-active', isActive);
    button.classList.toggle('is-plan-and-execute', isPlanAndExecute);
    button.setAttribute('aria-pressed', String(isActive));
    let label = 'Plan mode off';
    let buttonText = 'Plan';
    if (normalized === PLAN_MODE_STATE_PLAN_ONLY) {
        label = 'Plan mode on (planning only)';
    } else if (isPlanAndExecute) {
        label = 'Plan then execute mode on';
        buttonText = 'Plan+';
    }
    button.dataset.planModeState = normalized;
    button.textContent = buttonText;
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
}

async function handleSubmit(event) {
    if (event) event.preventDefault();
    const input = document.getElementById('codex-chat-input');
    if (!input) return;
    const draftPrompt = input.value;
    const prompt = draftPrompt.trim();
    const attachments = getPendingAttachmentPayload();
    const activeSessionId = state.activeSessionId;
    const sessionState = activeSessionId ? getSessionState(activeSessionId) : null;
    const sessionBusy = activeSessionId ? isSessionBusy(activeSessionId) : false;
    if (activeSessionId && sessionBusy) {
        if (prompt) {
            input.value = '';
            try {
                const queueResult = await queuePromptWithPlanMode(activeSessionId, prompt, getPlanModeState(), {
                    attachments
                });
                clearPendingAttachments();
                const queuedCount = Number(queueResult?.totalQueued) || 0;
                if (queueResult?.lastResult?.reason === 'queued') {
                    setSessionStatus(activeSessionId, `Queued ${queuedCount} prompt${queuedCount === 1 ? '' : 's'}...`);
                    showToast(`Queued (${queuedCount})`, {
                        tone: 'success',
                        durationMs: 1800
                    });
                }
            } catch (error) {
                setSessionStatus(activeSessionId, normalizeError(error, 'Failed to queue message.'), true);
                if (state.activeSessionId === activeSessionId) {
                    const latestInput = document.getElementById('codex-chat-input');
                    if (latestInput && latestInput.value === '') {
                        latestInput.value = draftPrompt;
                        latestInput.focus();
                    }
                }
            }
            syncActiveSessionControls();
            return;
        }
        if (getSessionStream(activeSessionId)) {
            await stopStream(activeSessionId);
            return;
        }
        if (cancelPendingSend(activeSessionId)) {
            return;
        }
        if (sessionState) {
            sessionState.sending = false;
        }
        syncActiveSessionControls();
        void flushQueuedPrompts(activeSessionId);
    }
    if (!prompt) return;
    input.value = '';
    const planModeState = getPlanModeState();
    const sendResult = await sendPrompt(prompt, {
        sessionId: activeSessionId,
        planMode: shouldUsePlanModeForRequest(planModeState),
        attachments
    });
    if (
        sendResult?.ok
        && shouldAutoExecuteAfterPlan(planModeState)
        && (sendResult?.reason === 'started' || sendResult?.reason === 'queued')
    ) {
        clearPendingAttachments();
        const targetSessionId = sendResult.sessionId || state.activeSessionId || activeSessionId;
        if (targetSessionId) {
            await queuePromptWithPlanMode(targetSessionId, PLAN_MODE_AUTO_EXECUTE_PROMPT, PLAN_MODE_STATE_OFF);
            syncActiveSessionControls();
        }
    }
    if (sendResult?.ok) {
        clearPendingAttachments();
        return;
    }
    const latestInput = document.getElementById('codex-chat-input');
    if (!latestInput) return;
    if (state.activeSessionId !== activeSessionId) return;
    if (latestInput.value !== '') return;
    latestInput.value = draftPrompt;
    latestInput.focus();
    syncActiveSessionControls();
}

function beginPendingSend(sessionId) {
    const sessionState = ensureSessionState(sessionId);
    const controller = new AbortController();
    if (sessionState) {
        sessionState.pendingSend = {
            controller,
            startedAt: Date.now()
        };
    }
    return controller;
}

function clearPendingSend(sessionId, controller = null) {
    const sessionState = getSessionState(sessionId);
    if (!sessionState?.pendingSend) return;
    if (controller && sessionState.pendingSend.controller !== controller) return;
    sessionState.pendingSend = null;
}

function cancelPendingSend(sessionId) {
    const sessionState = getSessionState(sessionId);
    const pending = sessionState?.pendingSend;
    if (!pending?.controller) return false;
    pending.controller.abort();
    sessionState.pendingSend = null;
    sessionState.sending = false;
    unpinAutoScrollForSession(sessionId);
    setSessionStatus(sessionId, 'Canceled');
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }
    void flushQueuedPrompts(sessionId);
    return true;
}

function processStartedStreamResponse(
    sessionId,
    prompt,
    result,
    startedAtFallback = Date.now(),
    responseMetadata = {}
) {
    const userMessage = result?.user_message;
    if (userMessage) {
        if (sessionId === state.activeSessionId) {
            const existingUserEntry = findMessageEntryById(userMessage?.id);
            if (!existingUserEntry) {
                appendMessageToDOMIfActive(sessionId, userMessage, 'user');
            }
        }
    } else {
        appendMessageToDOMIfActive(sessionId, {
            role: 'user',
            content: prompt,
            created_at: new Date().toISOString()
        }, 'user');
    }

    const assistantMessage = result?.assistant_message;
    const assistantMessageId = typeof result?.assistant_message_id === 'string' && result.assistant_message_id.trim()
        ? result.assistant_message_id.trim()
        : (typeof assistantMessage?.id === 'string' ? assistantMessage.id.trim() : '');
    let assistantEntry = null;
    if (sessionId === state.activeSessionId && assistantMessageId) {
        assistantEntry = findMessageEntryById(assistantMessageId);
    }
    if (!assistantEntry) {
        assistantEntry = appendMessageToDOMIfActive(sessionId, assistantMessage || {
            id: assistantMessageId || '',
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
            response_mode: responseMetadata?.response_mode,
            response_model: responseMetadata?.response_model
        }, 'assistant');
    }

    const streamId = result?.stream_id;
    if (!streamId) {
        throw new Error('Failed to start stream.');
    }
    if (assistantEntry) {
        setMessageStreaming(assistantEntry.wrapper, true);
    }
    startStream(streamId, sessionId, assistantEntry, result?.started_at || startedAtFallback, {
        messageId: assistantMessageId
    });
}

async function sendPrompt(prompt, { sessionId: sessionIdOverride = null, planMode = false, attachments = [] } = {}) {
    let sessionId = sessionIdOverride || state.activeSessionId;
    const normalizedAttachments = Array.isArray(attachments)
        ? attachments.map(normalizeChatAttachment).filter(Boolean)
        : [];
    if (!sessionId) {
        const session = await createSession(true);
        sessionId = session?.id;
    }

    if (!sessionId) {
        setStatus('Failed to create a session.', true);
        return { ok: false, reason: 'session_create_failed', sessionId: null };
    }

    const sessionState = ensureSessionState(sessionId);
    if (sessionState?.sending) {
        setSessionStatus(sessionId, 'Session is already sending.', true);
        return { ok: false, reason: 'already_sending', sessionId };
    }
    if (sessionState) {
        sessionState.sending = true;
    }
    setSessionStatus(sessionId, 'Waiting for Codex...');
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }

    const startedAt = Date.now();
    try {
        const controller = beginPendingSend(sessionId);
        const response = await fetch(`/api/codex/sessions/${sessionId}/message/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt,
                plan_mode: Boolean(planMode),
                attachments: normalizedAttachments
            }),
            signal: controller.signal
        });
        clearPendingSend(sessionId, controller);
        const result = await response.json();
        if (!response.ok) {
            const err = new Error(result?.error || 'Failed to send message.');
            err.status = response.status;
            err.payload = result;
            throw err;
        }
        processStartedStreamResponse(
            sessionId,
            prompt,
            result,
            startedAt,
            resolveRequestResponseMetadata({
                planMode,
                responseMode: result?.response_mode,
                responseModel: result?.response_model
            })
        );
        return { ok: true, reason: 'started', sessionId };
    } catch (error) {
        clearPendingSend(sessionId);
        if (error?.name === 'AbortError') {
            if (sessionState) {
                sessionState.sending = false;
            }
            unpinAutoScrollForSession(sessionId);
            setSessionStatus(sessionId, 'Canceled');
            if (sessionId === state.activeSessionId) {
                syncActiveSessionControls();
            }
            void flushQueuedPrompts(sessionId);
            return { ok: false, reason: 'canceled', sessionId };
        }
        if (error?.status === 409 && error?.payload?.already_running) {
            try {
                const queueResult = await queuePromptOnServer(sessionId, prompt, {
                    planMode: Boolean(planMode),
                    attachments: normalizedAttachments
                });
                if (sessionState) {
                    sessionState.sending = false;
                }
                unpinAutoScrollForSession(sessionId);
                if (queueResult?.reason === 'queued') {
                    const queuedCount = Number(queueResult?.queueCount) || 0;
                    setSessionStatus(sessionId, `Queued ${queuedCount} prompt${queuedCount === 1 ? '' : 's'}...`);
                    showToast(`Queued (${queuedCount})`, {
                        tone: 'success',
                        durationMs: 1800
                    });
                    if (sessionId === state.activeSessionId) {
                        syncActiveSessionControls();
                    }
                    return { ok: true, reason: 'queued', sessionId, queueCount: queuedCount };
                }
                if (sessionId === state.activeSessionId) {
                    syncActiveSessionControls();
                }
                return { ok: true, reason: queueResult?.reason || 'started', sessionId };
            } catch (queueError) {
                // Fall back to remote attach behavior when queue endpoint fails.
            }

            const activeStreamId = error?.payload?.active_stream_id;
            if (activeStreamId) {
                setSessionStatus(sessionId, 'Another client is already responding. Connecting...');
                const attached = await connectToExistingStream(
                    sessionId,
                    activeStreamId,
                    error?.payload?.started_at
                );
                if (attached) {
                    showToast('다른 브라우저에서 실행 중인 응답에 연결했습니다.', {
                        tone: 'success',
                        durationMs: 3000
                    });
                    if (sessionId === state.activeSessionId) {
                        syncActiveSessionControls();
                    }
                    return { ok: true, reason: 'attached_existing_stream', sessionId };
                }
            }
            if (sessionState) {
                sessionState.sending = false;
            }
            unpinAutoScrollForSession(sessionId);
            setSessionStatus(sessionId, normalizeError(error, 'Another response is already running.'), true);
            if (sessionId === state.activeSessionId) {
                syncActiveSessionControls();
            }
            void flushQueuedPrompts(sessionId);
            return { ok: false, reason: 'already_running', sessionId };
        }
        if (sessionState) {
            sessionState.sending = false;
        }
        unpinAutoScrollForSession(sessionId);
        setSessionStatus(sessionId, normalizeError(error, 'Failed to send message.'), true);
        if (sessionId === state.activeSessionId) {
            syncActiveSessionControls();
        }
        void flushQueuedPrompts(sessionId);
        return { ok: false, reason: 'send_failed', sessionId };
    }
}

function startStream(streamId, sessionId, assistantEntry, startedAt, options = {}) {
    const optionMessageId = typeof options?.messageId === 'string' ? options.messageId.trim() : '';
    const entryMessageId = typeof assistantEntry?.wrapper?.dataset?.messageId === 'string'
        ? assistantEntry.wrapper.dataset.messageId.trim()
        : '';
    const stream = createStreamState({
        id: streamId,
        sessionId,
        entry: assistantEntry,
        messageId: optionMessageId || entryMessageId,
        outputOffset: 0,
        errorOffset: 0,
        output: '',
        error: '',
        startedAt: startedAt || Date.now()
    });
    if (!stream) return;
    stream.processRunning = true;
    persistActiveStream(stream);
    beginStreamPolling(stream.id);
    setSessionStatus(sessionId, buildActiveStreamStatus(true));
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }
}

function beginStreamPolling(streamId) {
    const stream = state.streams[streamId];
    if (!stream) return;
    stream.failureCount = 0;
    stream.pollDelay = STREAM_POLL_BASE_MS;
    scheduleSessionsRender();
    scheduleStreamPoll(streamId, 0);
}

function scheduleStreamPoll(streamId, delay) {
    const stream = state.streams[streamId];
    if (!stream) return;
    if (stream.timer) {
        clearTimeout(stream.timer);
    }
    stream.timer = setTimeout(() => {
        pollStream(streamId);
    }, delay);
}

async function stopStream(sessionId) {
    const stream = getSessionStream(sessionId);
    if (!stream) return;
    setSessionStatus(sessionId, 'Stopping...');
    try {
        const response = await fetch(`/api/codex/streams/${stream.id}/stop`, { method: 'POST' });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to stop stream.');
        }
        const wrapper = stream.entry?.wrapper;
        const bubble = stream.entry?.bubble;
        if (wrapper) {
            wrapper.classList.remove('assistant');
            wrapper.classList.add('error');
        }
        if (bubble) {
            const combined = stream.output + (stream.error ? `\n${stream.error}` : '');
            const messageText = combined ? `${combined}\n\n[Stopped by user]` : '[Stopped by user]';
            setMarkdownContent(bubble, messageText);
        }
        setMessageTokenUsage(
            stream.entry?.footer,
            { role: 'error', token_usage: stream.tokenUsage, content: stream.output || stream.error || '' }
        );
        const durationMs = getStreamDuration(stream);
        setMessageDuration(stream.entry?.footer, durationMs);
        setMessageTimingBreakdown(stream.entry?.footer, result?.saved_message || null);
        setMessageStreaming(stream.entry?.wrapper, false);
        clearPersistedStream(stream.id);
        clearStreamState(stream.id);
        const sessionState = getSessionState(sessionId);
        if (sessionState) {
            sessionState.sending = false;
        }
        unpinAutoScrollForSession(sessionId);
        setSessionStatus(sessionId, 'Stopped');
        if (sessionId === state.activeSessionId) {
            syncActiveSessionControls();
        }
        await loadSessions({ preserveActive: true, reloadActive: false });
        void refreshUsageSummary({ silent: true });
        void flushQueuedPrompts(sessionId);
    } catch (error) {
        setSessionStatus(sessionId, normalizeError(error, 'Failed to stop stream.'), true);
    }
}

async function pollStream(streamId) {
    const stream = state.streams[streamId];
    if (!stream || stream.polling) return;
    stream.polling = true;

    try {
        const result = await fetchJson(`/api/codex/streams/${stream.id}?offset=${stream.outputOffset}&error_offset=${stream.errorOffset}&event_offset=${stream.eventOffset || 0}`);
        const current = state.streams[streamId];
        if (!current) {
            return;
        }

        current.failureCount = 0;
        current.pollDelay = STREAM_POLL_BASE_MS;
        if (typeof result?.process_running === 'boolean') {
            current.processRunning = result.process_running;
        }
        current.processPid = Number.isFinite(result?.process_pid) ? result.process_pid : null;
        if (Number.isFinite(result?.runtime_ms)) {
            current.runtimeMs = result.runtime_ms;
        }
        if (Number.isFinite(result?.idle_ms)) {
            current.idleMs = result.idle_ms;
        }
        const resultMessageId = typeof result?.assistant_message_id === 'string'
            ? result.assistant_message_id.trim()
            : '';
        if (resultMessageId && resultMessageId !== current.messageId) {
            current.messageId = resultMessageId;
            persistActiveStream(current);
            if (current.entry?.wrapper) {
                setMessageWrapperIdentity(
                    current.entry.wrapper,
                    resolveMessageRoleFromWrapper(current.entry.wrapper),
                    current.entry.wrapper.dataset.messageTimestampValue,
                    resultMessageId
                );
            }
        }

        if (result?.output) {
            current.output += result.output;
            current.outputOffset = Number.isFinite(result.output_length)
                ? result.output_length
                : current.output.length;
        }
        if (result?.error) {
            current.error += result.error;
            current.errorOffset = Number.isFinite(result.error_length)
                ? result.error_length
                : current.error.length;
        }
        if (Number.isFinite(result?.event_length)) {
            current.eventOffset = result.event_length;
        }

        if (result?.output || result?.error) {
            updateStreamEntry(current);
        }
        setSessionStatus(current.sessionId, buildActiveStreamStatus(current.processRunning));

        if (result?.done) {
            await finishStream(streamId, result);
            return;
        }
        if (current.processRunning === false && Number.isFinite(current.idleMs) && current.idleMs >= STREAM_IDLE_WARNING_MS) {
            setSessionStatus(current.sessionId, 'Receiving response... (CLI finalizing, no recent output)');
        }
        scheduleStreamPoll(streamId, STREAM_POLL_BASE_MS);
    } catch (error) {
        const current = state.streams[streamId];
        if (!current) {
            return;
        }
        if (isStreamNotFoundError(error)) {
            await recoverMissingStream(current);
            return;
        }
        current.failureCount += 1;
        const backoff = Math.min(
            STREAM_POLL_MAX_MS,
            STREAM_POLL_BASE_MS * Math.pow(2, Math.min(current.failureCount, 3))
        );
        current.pollDelay = backoff;
        setSessionStatus(current.sessionId, 'Connection lost. Retrying...', true);
        scheduleStreamPoll(streamId, backoff);
    } finally {
        const current = state.streams[streamId];
        if (current) {
            current.polling = false;
        }
    }
}

function updateStreamEntry(stream) {
    const bubble = stream?.entry?.bubble;
    if (!bubble) return;
    const combined = stream.output + (stream.error ? `\n${stream.error}` : '');
    setMarkdownContent(bubble, combined, {
        streaming: true,
        skipPreviewUpdate: true
    });
    if (stream?.entry?.footer) {
        setMessageTokenUsage(
            stream.entry.footer,
            { role: 'assistant', token_usage: stream.tokenUsage, content: combined }
        );
    }
    if (stream?.entry?.wrapper?.classList.contains('is-streaming')) {
        bubble.scrollTop = bubble.scrollHeight;
    }
    scrollToBottom();
}

async function finishStream(streamId, result) {
    const stream = state.streams[streamId];
    if (!stream) return;

    const durationMs = getStreamDuration(stream);
    setMessageDuration(stream.entry?.footer, durationMs);
    setMessageStreaming(stream.entry?.wrapper, false);
    clearPersistedStream(stream.id);
    const exitCode = result?.exit_code;
    const wrapper = stream.entry?.wrapper;
    const bubble = stream.entry?.bubble;
    const savedMessage = result?.saved_message || null;
    if (savedMessage && typeof savedMessage.content === 'string' && bubble) {
        setMarkdownContent(bubble, savedMessage.content, { message: savedMessage });
    } else if (bubble) {
        const finalContent = stream.output + (stream.error ? `\n${stream.error}` : '');
        setMarkdownContent(bubble, finalContent);
    }
    if (savedMessage && wrapper) {
        wrapper.classList.remove('assistant', 'error');
        wrapper.classList.add(savedMessage.role === 'error' ? 'error' : 'assistant');
    }
    if (savedMessage && stream.entry?.meta) {
        setMessageMetaLabel(
            stream.entry.meta,
            savedMessage.role || 'assistant',
            getMessageTimestampValue(savedMessage),
            savedMessage
        );
    }
    const savedDurationMs = Number(savedMessage?.duration_ms);
    if (Number.isFinite(savedDurationMs)) {
        setMessageDuration(stream.entry?.footer, savedDurationMs);
    }
    setMessageTimingBreakdown(
        stream.entry?.footer,
        savedMessage || result || null
    );
    setMessageFinalizeReason(
        stream.entry?.footer,
        savedMessage?.finalize_reason || result?.finalize_reason
    );
    setMessageFinalizeComparison(
        stream.entry?.footer,
        savedMessage || result || null
    );
    setMessageDetailLogLink(
        stream.entry?.footer,
        savedMessage || result || null
    );
    setMessageTokenUsage(
        stream.entry?.footer,
        savedMessage || { role: 'assistant', token_usage: result?.token_usage || stream.tokenUsage, content: stream.output || '' }
    );
    if (exitCode !== 0) {
        if (wrapper) {
            wrapper.classList.remove('assistant');
            wrapper.classList.add('error');
        }
        const errorText = savedMessage?.content || stream.error || stream.output || 'Codex execution failed.';
        if (bubble) setMarkdownContent(bubble, errorText, { message: savedMessage || null });
    }
    clearStreamState(stream.id);
    const sessionId = stream.sessionId;
    const sessionState = getSessionState(sessionId);
    if (sessionState) {
        sessionState.sending = false;
    }
    unpinAutoScrollForSession(sessionId);
    setSessionStatus(sessionId, exitCode === 0 ? 'Idle' : 'Failed', exitCode !== 0);
    const shouldReloadActive = sessionId === state.activeSessionId;
    if (shouldReloadActive) {
        syncActiveSessionControls();
    }
    await loadSessions({ preserveActive: true, reloadActive: shouldReloadActive });
    void refreshUsageSummary({ silent: true });
    void flushQueuedPrompts(sessionId);
}

async function renameSession(session) {
    if (!session?.id) return;
    if (isSessionBusy(session.id)) {
        console.warn(`[codex-ui] rename blocked: session ${session.id} is busy`);
        const message = 'Cannot rename a session while it is running.';
        setStatus(message, true);
        showToast(message, { tone: 'error', durationMs: 3200 });
        return;
    }
    const currentTitle = session.title || 'New session';
    const nextTitle = window.prompt('Enter a session name.', currentTitle);
    if (nextTitle === null) return;
    const trimmed = String(nextTitle).trim();
    if (!trimmed) {
        setStatus('Session name is empty.', true);
        return;
    }
    setStatus('Renaming session...');
    try {
        const result = await fetchJson(`/api/codex/sessions/${session.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            timeoutMs: SESSION_MUTATION_REQUEST_TIMEOUT_MS,
            body: JSON.stringify({ title: trimmed })
        });
        const updated = result?.session;
        upsertSessionSummary(updated);
        renderSessions();
        if (state.activeSessionId === updated?.id) {
            updateHeader(updated);
        }
        syncActiveSessionStatus();
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to rename session.'), true);
    }
}

async function deleteSession(sessionId) {
    if (!sessionId) return;
    if (isSessionBusy(sessionId)) {
        console.warn(`[codex-ui] delete blocked: session ${sessionId} is busy`);
        const message = 'Cannot delete a session while it is running.';
        setStatus(message, true);
        showToast(message, { tone: 'error', durationMs: 3200 });
        return;
    }
    const confirmed = window.confirm('Delete this session? This will remove all messages.');
    if (!confirmed) return;
    setStatus('Deleting session...');
    try {
        const result = await fetchJson(`/api/codex/sessions/${sessionId}`, {
            method: 'DELETE',
            timeoutMs: SESSION_MUTATION_REQUEST_TIMEOUT_MS
        });
        if (result?.session_storage) {
            state.sessionStorage = result.session_storage;
            updateSessionStorageSummary(state.sessionStorage);
        }
        removeSessionSummary(sessionId);
        if (state.activeSessionId === sessionId) {
            state.activeSessionId = null;
        }
        renderSessions();
        if (!state.activeSessionId && state.sessions.length > 0) {
            await loadSession(state.sessions[0].id);
        } else if (!state.activeSessionId) {
            renderMessages([]);
            updateHeader(null);
        }
        syncActiveSessionStatus();
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to delete session.'), true);
    }
}

function setStatus(message, isError = false) {
    state.statusMessage = message;
    state.statusIsError = isError;
    updateStatusDisplay();
}

function formatTimestamp(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('ko-KR', { timeZone: KST_TIME_ZONE });
}

function getMessageTimestampValue(message) {
    if (!message || typeof message !== 'object') return '';
    return message.completed_at || message.created_at || '';
}

function setMessageMetaLabel(meta, role, timestampValue, message = null) {
    if (!meta) return;
    const textElement = meta.querySelector('.message-meta-text');
    if (!textElement) return;
    textElement.textContent = buildMessageMetaText(role, timestampValue, message);
    setMessageWrapperIdentity(meta.closest('.message'), role, timestampValue, message?.id);
}

function getRoleLabel(role) {
    if (role === 'user') return 'You';
    if (role === 'assistant') return 'Codex';
    if (role === 'system') return 'System';
    if (role === 'error') return 'Error';
    return 'Message';
}

function normalizeResponseModeLabel(value) {
    const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
    return normalized === 'plan' ? 'plan' : 'basic';
}

function resolveSessionLastResponseMode(session) {
    const explicitMode = typeof session?.last_response_mode === 'string'
        ? session.last_response_mode.trim()
        : '';
    if (explicitMode) {
        return normalizeResponseModeLabel(explicitMode);
    }
    const messages = Array.isArray(session?.messages) ? session.messages : [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const message = messages[index];
        const role = typeof message?.role === 'string' ? message.role.trim().toLowerCase() : '';
        if (role !== 'assistant' && role !== 'error') {
            continue;
        }
        return normalizeResponseModeLabel(message?.response_mode || 'basic');
    }
    return '';
}

function resolveResponseModeText(modeLabel) {
    return normalizeResponseModeLabel(modeLabel) === 'plan' ? 'plan모드' : '기본모드';
}

function createSessionResponseModeBadge(session) {
    const mode = resolveSessionLastResponseMode(session);
    if (!mode) {
        return null;
    }
    const badge = document.createElement('button');
    badge.type = 'button';
    badge.className = `session-response-mode is-${mode}`;
    badge.disabled = true;
    badge.textContent = mode === 'plan' ? 'Plan' : 'Basic';
    const label = `마지막 응답: ${resolveResponseModeText(mode)}`;
    badge.setAttribute('aria-label', label);
    badge.setAttribute('title', label);
    return badge;
}

function resolveResponseModelForRequest(planMode = false) {
    const defaultModel = typeof state.settings?.model === 'string'
        ? state.settings.model.trim()
        : '';
    const planModeModel = typeof state.settings?.planModeModel === 'string'
        ? state.settings.planModeModel.trim()
        : '';
    if (planMode) {
        return planModeModel || defaultModel || 'codex-default';
    }
    return defaultModel || 'codex-default';
}

function resolveRequestResponseMetadata({ planMode = false, responseMode = '', responseModel = '' } = {}) {
    const normalizedMode = normalizeResponseModeLabel(responseMode || (planMode ? 'plan' : 'basic'));
    const normalizedModel = typeof responseModel === 'string' ? responseModel.trim() : '';
    return {
        response_mode: normalizedMode,
        response_model: normalizedModel || resolveResponseModelForRequest(normalizedMode === 'plan')
    };
}

function buildMessageMetaText(role, timestampValue, message = null) {
    let label = getRoleLabel(role);
    if (role === 'assistant' && message && typeof message === 'object') {
        const hasResponseMetadata = Object.prototype.hasOwnProperty.call(message, 'response_mode')
            || Object.prototype.hasOwnProperty.call(message, 'response_model');
        if (hasResponseMetadata) {
            const modeValue = resolveResponseModeText(message.response_mode);
            const modelValue = typeof message.response_model === 'string'
                ? message.response_model.trim()
                : '';
            const modeModelLabel = modelValue ? `${modeValue} · ${modelValue}` : modeValue;
            if (modeModelLabel) {
                label = `${label} · ${modeModelLabel}`;
            }
        }
    }
    const timestamp = formatTimestamp(timestampValue);
    return timestamp ? `${label} - ${timestamp}` : label;
}

function getChatMessagesContainer() {
    return document.getElementById('codex-chat-messages');
}

function isMessageListNearBottom(container) {
    if (!container) return true;
    const threshold = Number.isFinite(state.autoScrollThreshold) ? state.autoScrollThreshold : 0;
    const distanceFromBottom = Math.max(
        0,
        container.scrollHeight - container.scrollTop - container.clientHeight
    );
    return distanceFromBottom <= threshold;
}

function setScrollToBottomButtonVisible(isVisible) {
    const button = document.getElementById('codex-chat-scroll-bottom');
    if (!button) return;
    const visible = Boolean(isVisible);
    button.classList.toggle('is-visible', visible);
    button.setAttribute('aria-hidden', visible ? 'false' : 'true');
    button.tabIndex = visible ? 0 : -1;
}

function syncScrollToBottomButton(container = null) {
    const target = container || getChatMessagesContainer();
    if (!target) {
        setScrollToBottomButtonVisible(false);
        return;
    }
    const hasOverflow = target.scrollHeight - target.clientHeight > 1;
    const shouldShow = hasOverflow && !isMessageListNearBottom(target);
    setScrollToBottomButtonVisible(shouldShow);
}

function scrollToBottom(force = false) {
    const container = getChatMessagesContainer();
    if (!container) return;
    if (!force && !state.autoScrollEnabled) {
        syncScrollToBottomButton(container);
        return;
    }
    if (force) {
        setAutoScrollEnabled(true);
    }
    const scroll = () => {
        container.scrollTop = container.scrollHeight;
        syncScrollToBottomButton(container);
    };
    if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(scroll);
    } else {
        scroll();
    }
}

function handleMessageScroll(container) {
    if (!container) return;
    setAutoScrollEnabled(isMessageListNearBottom(container));
}

function setAutoScrollEnabled(isEnabled) {
    state.autoScrollEnabled = Boolean(isEnabled);
    syncScrollToBottomButton();
}

function pinAutoScrollForSession(sessionId) {
    void sessionId;
}

function unpinAutoScrollForSession(sessionId = null) {
    void sessionId;
}

function normalizeDetailText(value) {
    if (typeof value === 'string') {
        return value.trim();
    }
    if (value === null || value === undefined) {
        return '';
    }
    return String(value).trim();
}

function parseMessageDate(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date;
}

function formatFinalizeLag(durationMs) {
    if (!Number.isFinite(durationMs)) return '';
    const roundedMs = Math.max(0, Math.round(durationMs));
    if (roundedMs < 1000) {
        return `${roundedMs}ms`;
    }
    if (roundedMs < 10000) {
        return `${(roundedMs / 1000).toFixed(2)}초`;
    }
    return formatDuration(roundedMs);
}

function buildFinalizeComparison(message) {
    if (!message || typeof message !== 'object') return null;
    const cliDate = parseMessageDate(message.completed_at);
    const finalDate = parseMessageDate(message.saved_at);
    if (!cliDate || !finalDate) return null;

    let lagMs = Number(message.finalize_lag_ms);
    if (!Number.isFinite(lagMs)) {
        lagMs = finalDate.getTime() - cliDate.getTime();
    }
    lagMs = Math.max(0, lagMs);
    return {
        cliAtText: formatTimestamp(cliDate.toISOString()),
        finalAtText: formatTimestamp(finalDate.toISOString()),
        lagMs,
        lagText: formatFinalizeLag(lagMs)
    };
}

function buildMessageDetailText(message) {
    if (!message || typeof message !== 'object') return '';
    const sections = [];
    const attachments = getMessageAttachments(message);
    if (attachments.length > 0) {
        sections.push([
            '## 이미지 첨부',
            ...attachments.map((attachment, index) => {
                const label = attachment.name || attachment.original_name || `image-${index + 1}`;
                const path = attachment.relative_path || attachment.path || '';
                return `- ${index + 1}. ${label}${path ? `: ${path}` : ''}`;
            })
        ].join('\n'));
    }
    const comparison = buildFinalizeComparison(message);
    if (comparison) {
        sections.push([
            '## 응답 종료 시각 비교',
            `- CLI 답변 종료: ${comparison.cliAtText}`,
            `- 최종응답 종료: ${comparison.finalAtText}`,
            `- 차이: ${comparison.lagText} (${Math.max(0, Math.round(comparison.lagMs))}ms)`
        ].join('\n'));
    }

    const workDetails = normalizeDetailText(message.work_details);
    if (workDetails) {
        sections.push([
            '## 작업 세부 로그',
            workDetails
        ].join('\n\n'));
    }

    const codexEvents = buildCodexEventsDetailText(message.codex_events);
    if (codexEvents) {
        sections.push([
            '## Codex JSON 이벤트',
            codexEvents
        ].join('\n\n'));
    }

    return sections.join('\n\n').trim();
}

function getMessageAttachments(message) {
    if (!message || typeof message !== 'object' || !Array.isArray(message.attachments)) {
        return [];
    }
    return message.attachments.map(normalizeChatAttachment).filter(Boolean);
}

function buildCodexEventsDetailText(events) {
    if (!Array.isArray(events) || events.length === 0) return '';
    return events.map(event => {
        const index = Number.isFinite(Number(event?.index)) ? Math.max(0, Math.round(Number(event.index))) : 0;
        const type = typeof event?.type === 'string' && event.type.trim() ? event.type.trim() : 'event';
        const payloadType = typeof event?.payload_type === 'string' && event.payload_type.trim()
            ? ` payload=${event.payload_type.trim()}`
            : '';
        const itemType = typeof event?.item_type === 'string' && event.item_type.trim()
            ? ` item=${event.item_type.trim()}`
            : '';
        const detail = typeof event?.detail === 'string' && event.detail.trim()
            ? ` - ${event.detail.trim()}`
            : '';
        return `- ${index || '-'}: ${type}${payloadType}${itemType}${detail}`;
    }).join('\n');
}

function renderMessageAttachments(element, message) {
    if (!element) return;
    element.querySelectorAll(':scope > .message-attachments').forEach(node => node.remove());
    const attachments = getMessageAttachments(message);
    if (attachments.length === 0) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'message-attachments';
    attachments.forEach(attachment => {
        const item = document.createElement('span');
        item.className = 'message-attachment';
        item.textContent = attachment.name || attachment.original_name || 'image';
        item.title = attachment.relative_path || attachment.path || item.textContent;
        wrapper.appendChild(item);
    });
    element.appendChild(wrapper);
}

function setMarkdownContent(element, content, options = {}) {
    if (!element) return;
    const messageContent = String(content || '');
    const renderOptions = options && typeof options === 'object' ? options : {};
    const messageData = renderOptions.message || null;
    const streaming = Boolean(renderOptions.streaming);
    const skipPreviewUpdate = Boolean(renderOptions.skipPreviewUpdate);
    const renderMode = streaming ? 'streaming' : 'markdown';
    const previousMode = element.dataset.renderMode || '';
    const previousContent = element.dataset.messageContent || '';
    const needsRender = previousMode !== renderMode || previousContent !== messageContent;

    if (needsRender) {
        if (streaming) {
            element.textContent = messageContent;
        } else {
            element.innerHTML = renderMessageContent(messageContent);
            hydrateRenderedMarkdown(element);
            renderMessageAttachments(element, messageData);
        }
    }

    element.dataset.renderMode = renderMode;
    element.dataset.messageContent = messageContent;
    if (!streaming && !needsRender) {
        renderMessageAttachments(element, messageData);
    }
    const wrapper = element.closest('.message');
    if (wrapper) {
        wrapper.dataset.messageContent = messageContent;
        const footer = wrapper.querySelector('.message-footer');
        if (footer && !skipPreviewUpdate) {
            setMessagePreviewLink(footer, messageContent, messageData, wrapper);
        }
    }
}

function buildMessageMeta(text, wrapper) {
    const meta = document.createElement('div');
    meta.className = 'message-meta';

    const label = document.createElement('span');
    label.className = 'message-meta-text';
    label.textContent = text || '';

    const actions = document.createElement('div');
    actions.className = 'message-meta-actions';
    actions.appendChild(createMessageCopyButton(wrapper));

    meta.appendChild(label);
    meta.appendChild(actions);
    return meta;
}

function createMessageCopyButton(wrapper) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'message-copy';
    button.setAttribute('aria-label', 'Copy message');
    button.setAttribute('title', 'Copy');
    button.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <rect x="7" y="4" width="10" height="4" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.6"></rect>
            <rect x="5" y="8" width="14" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"></rect>
        </svg>
    `;
    button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        copyMessageContent(wrapper, button);
    });
    return button;
}

async function copyMessageContent(wrapper, button) {
    if (!wrapper) return;
    const bubble = wrapper.querySelector('.message-bubble');
    const text = wrapper.dataset.messageContent
        || bubble?.dataset.messageContent
        || bubble?.textContent
        || '';
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            copyMessageFallback(text);
        }
        showMessageCopyFeedback(button);
    } catch (error) {
        copyMessageFallback(text);
        showMessageCopyFeedback(button);
    }
}

function copyMessageFallback(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', 'readonly');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
    } catch (error) {
        void error;
    }
    document.body.removeChild(textarea);
}

function showMessageCopyFeedback(button) {
    if (!button) return;
    button.classList.add('is-copied');
    button.setAttribute('title', 'Copied');
    button.setAttribute('aria-label', 'Copied');
    window.setTimeout(() => {
        button.classList.remove('is-copied');
        button.setAttribute('title', 'Copy');
        button.setAttribute('aria-label', 'Copy message');
    }, 1500);
}

function toNonNegativeInt(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return null;
    return Math.round(numeric);
}

function resolveMessageTokenUsage(message, { fallbackToEstimate = true } = {}) {
    const role = String(message?.role || 'assistant').trim().toLowerCase();
    const usage = (message && typeof message.token_usage === 'object') ? message.token_usage : null;

    let inputTokens = toNonNegativeInt(usage?.input_tokens);
    let cachedInputTokens = toNonNegativeInt(usage?.cached_input_tokens);
    let outputTokens = toNonNegativeInt(usage?.output_tokens);
    let reasoningOutputTokens = toNonNegativeInt(usage?.reasoning_output_tokens);
    let totalTokens = toNonNegativeInt(usage?.total_tokens);

    if (inputTokens === null) inputTokens = toNonNegativeInt(message?.input_tokens);
    if (cachedInputTokens === null) cachedInputTokens = toNonNegativeInt(message?.cached_input_tokens);
    if (outputTokens === null) outputTokens = toNonNegativeInt(message?.output_tokens);
    if (reasoningOutputTokens === null) reasoningOutputTokens = toNonNegativeInt(message?.reasoning_output_tokens);
    if (totalTokens === null) totalTokens = toNonNegativeInt(message?.total_tokens);
    if (totalTokens === null) totalTokens = toNonNegativeInt(message?.token_count);

    if (inputTokens === null) inputTokens = 0;
    if (cachedInputTokens === null) cachedInputTokens = 0;
    if (outputTokens === null) outputTokens = 0;
    if (reasoningOutputTokens === null) reasoningOutputTokens = 0;

    let estimated = false;
    const hasAnyExplicit = inputTokens > 0
        || cachedInputTokens > 0
        || outputTokens > 0
        || reasoningOutputTokens > 0
        || (totalTokens !== null && totalTokens > 0);

    if (!hasAnyExplicit && fallbackToEstimate) {
        const estimatedTokens = estimateTokensFromText(message?.content || '');
        if (role === 'assistant' || role === 'error') {
            outputTokens = estimatedTokens;
        } else {
            inputTokens = estimatedTokens;
        }
        totalTokens = estimatedTokens;
        estimated = true;
    }

    if (totalTokens === null) {
        totalTokens = inputTokens + outputTokens;
        if (outputTokens === 0 && reasoningOutputTokens > 0) {
            totalTokens += reasoningOutputTokens;
        }
    }

    if (inputTokens === 0 && outputTokens === 0 && totalTokens > 0) {
        if (role === 'assistant' || role === 'error') {
            outputTokens = totalTokens;
        } else {
            inputTokens = totalTokens;
        }
    }

    const hasData = inputTokens > 0
        || cachedInputTokens > 0
        || outputTokens > 0
        || reasoningOutputTokens > 0
        || totalTokens > 0;

    return {
        inputTokens,
        cachedInputTokens,
        outputTokens,
        reasoningOutputTokens,
        totalTokens,
        estimated,
        hasData
    };
}

function estimateSessionTokenUsageFromMessages(messages) {
    if (!Array.isArray(messages)) {
        return {
            inputTokens: 0,
            cachedInputTokens: 0,
            outputTokens: 0,
            reasoningOutputTokens: 0,
            totalTokens: 0,
            estimated: false
        };
    }

    const aggregated = {
        inputTokens: 0,
        cachedInputTokens: 0,
        outputTokens: 0,
        reasoningOutputTokens: 0,
        totalTokens: 0,
        estimated: false
    };
    messages.forEach(message => {
        const usage = resolveMessageTokenUsage(message, { fallbackToEstimate: true });
        aggregated.inputTokens += usage.inputTokens;
        aggregated.cachedInputTokens += usage.cachedInputTokens;
        aggregated.outputTokens += usage.outputTokens;
        aggregated.reasoningOutputTokens += usage.reasoningOutputTokens;
        aggregated.totalTokens += usage.totalTokens;
        aggregated.estimated = aggregated.estimated || usage.estimated;
    });
    return aggregated;
}

function resolveSessionTokenUsage(session, fallbackMessages = []) {
    const sourceMessages = Array.isArray(session?.messages)
        ? session.messages
        : (Array.isArray(fallbackMessages) ? fallbackMessages : []);

    const inputTokenCount = toNonNegativeInt(session?.input_token_count);
    const cachedInputTokenCount = toNonNegativeInt(session?.cached_input_token_count);
    const outputTokenCount = toNonNegativeInt(session?.output_token_count);
    const reasoningOutputTokenCount = toNonNegativeInt(session?.reasoning_output_token_count);
    const totalTokenCount = toNonNegativeInt(session?.token_count);

    const hasSessionTokenData = inputTokenCount !== null
        || cachedInputTokenCount !== null
        || outputTokenCount !== null
        || reasoningOutputTokenCount !== null
        || totalTokenCount !== null;

    if (hasSessionTokenData) {
        const inputTokens = inputTokenCount !== null ? inputTokenCount : 0;
        const cachedInputTokens = cachedInputTokenCount !== null ? cachedInputTokenCount : 0;
        const outputTokens = outputTokenCount !== null ? outputTokenCount : 0;
        const reasoningOutputTokens = reasoningOutputTokenCount !== null ? reasoningOutputTokenCount : 0;
        let totalTokens = totalTokenCount;
        if (totalTokens === null) {
            totalTokens = inputTokens + outputTokens;
            if (outputTokenCount === null && reasoningOutputTokens > 0) {
                totalTokens += reasoningOutputTokens;
            }
        }
        return {
            inputTokens,
            cachedInputTokens,
            outputTokens,
            reasoningOutputTokens,
            totalTokens,
            estimated: Boolean(session?.token_estimated),
        };
    }

    return estimateSessionTokenUsageFromMessages(sourceMessages);
}

function resolveSessionMessageCount(session) {
    const explicitCount = Number(session?.message_count);
    if (Number.isFinite(explicitCount) && explicitCount >= 0) {
        return Math.round(explicitCount);
    }
    if (Array.isArray(session?.messages)) {
        return session.messages.length;
    }
    return 0;
}

function formatSessionTokenSummary(session) {
    const usage = resolveSessionTokenUsage(session);
    if (!usage || usage.totalTokens <= 0) return '';
    const text = `In ${formatCompactTokenCount(usage.inputTokens)} / Out ${formatCompactTokenCount(usage.outputTokens)}`;
    return usage.estimated ? `${text} ~` : text;
}

function formatMessageTokenSummary(message) {
    const usage = resolveMessageTokenUsage(message, { fallbackToEstimate: true });
    if (!usage.hasData) return '';
    const parts = [
        `Tok In ${formatCompactTokenCount(usage.inputTokens)}`,
        `Out ${formatCompactTokenCount(usage.outputTokens)}`
    ];
    if (usage.cachedInputTokens > 0) {
        parts.push(`Cached ${formatCompactTokenCount(usage.cachedInputTokens)}`);
    }
    if (usage.estimated) {
        parts.push('~');
    }
    return parts.join(' · ');
}

function setMessageTokenUsage(footer, message) {
    if (!footer) return;
    footer.dataset.tokenText = formatMessageTokenSummary(message) || '';
    syncMessageFooter(footer);
}

function createMessageFooter() {
    const footer = document.createElement('div');
    footer.className = 'message-footer';
    footer.dataset.tokenText = '';
    footer.dataset.durationText = '';
    footer.dataset.cliRuntimeText = '';
    footer.dataset.queueWaitText = '';
    footer.dataset.finalizeText = '';
    footer.dataset.finalizeTimingText = '';
    footer.dataset.previewText = '';
    footer.dataset.previewTitle = '';
    footer.dataset.previewSubtitle = '';
    footer.dataset.detailText = '';
    footer.dataset.detailTitle = '';

    const text = document.createElement('span');
    text.className = 'message-footer-text';
    footer.appendChild(text);

    const linkGroup = document.createElement('div');
    linkGroup.className = 'message-footer-links is-hidden';
    footer.appendChild(linkGroup);

    const previewLink = document.createElement('button');
    previewLink.type = 'button';
    previewLink.className = 'message-preview-link message-detail-link is-hidden';
    previewLink.textContent = '🔎 자세히 보기';
    previewLink.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const previewText = normalizeDetailText(footer.dataset.previewText);
        if (!previewText) return;
        openMessageLogOverlay(
            footer.dataset.previewTitle || '전체 메시지',
            previewText,
            footer.dataset.previewSubtitle || '미리보기에서 생략된 전체 메시지',
            { mode: MESSAGE_LOG_OVERLAY_MODE_PREVIEW }
        );
    });
    linkGroup.appendChild(previewLink);

    const detailLink = document.createElement('button');
    detailLink.type = 'button';
    detailLink.className = 'message-log-link message-detail-link is-hidden';
    detailLink.textContent = '🧾 상세 로그 보기';
    detailLink.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        const detailText = normalizeDetailText(footer.dataset.detailText);
        if (!detailText) return;
        openMessageLogOverlay(
            footer.dataset.detailTitle || '상세 로그',
            detailText,
            '',
            { mode: MESSAGE_LOG_OVERLAY_MODE_DETAIL }
        );
    });
    linkGroup.appendChild(detailLink);
    return footer;
}

function getFinalizeReasonLabel(reason) {
    const value = typeof reason === 'string' ? reason.trim() : '';
    if (!value || value === 'process_exit') return '';
    if (value === 'post_output_idle_timeout') return 'Delayed finalize';
    if (value === 'exec_timeout') return 'Timed out';
    if (value === 'final_response_timeout') return 'Final response timeout';
    if (value === 'user_cancelled') return 'Stopped by user';
    if (value === 'process_start_failed') return 'CLI start failed';
    if (value === 'process_exit_error') return 'Exited with error';
    return `Finalize: ${value}`;
}

function syncMessageFooter(footer) {
    if (!footer) return;
    const tokenText = footer.dataset.tokenText || '';
    const durationText = footer.dataset.durationText || '';
    const cliRuntimeText = footer.dataset.cliRuntimeText || '';
    const queueWaitText = footer.dataset.queueWaitText || '';
    const finalizeText = footer.dataset.finalizeText || '';
    const finalizeTimingText = footer.dataset.finalizeTimingText || '';
    const previewText = normalizeDetailText(footer.dataset.previewText);
    const detailText = normalizeDetailText(footer.dataset.detailText);
    const parts = [];
    if (tokenText) {
        parts.push(tokenText);
    }
    if (durationText) {
        parts.push(`총 걸린시간 ${durationText}`);
    }
    if (cliRuntimeText) {
        parts.push(`실행 ${cliRuntimeText}`);
    }
    if (queueWaitText) {
        parts.push(`대기 ${queueWaitText}`);
    }
    if (finalizeTimingText) {
        parts.push(finalizeTimingText);
    }
    if (finalizeText) {
        parts.push(finalizeText);
    }
    const textElement = footer.querySelector('.message-footer-text');
    if (textElement) {
        textElement.textContent = parts.join(' · ');
    } else {
        footer.textContent = parts.join(' · ');
    }
    const previewLink = footer.querySelector('.message-preview-link');
    if (previewLink) {
        previewLink.classList.toggle('is-hidden', !previewText);
    }
    const detailLink = footer.querySelector('.message-log-link');
    if (detailLink) {
        detailLink.classList.toggle('is-hidden', !detailText);
    }
    const linkGroup = footer.querySelector('.message-footer-links');
    if (linkGroup) {
        linkGroup.classList.toggle('is-hidden', !previewText && !detailText);
    }
    footer.classList.toggle('is-visible', parts.length > 0 || Boolean(previewText) || Boolean(detailText));
}

function setMessageDuration(footer, durationMs) {
    if (!footer) return;
    const formatted = formatDuration(durationMs);
    footer.dataset.durationText = formatted || '';
    syncMessageFooter(footer);
}

function setMessageTimingBreakdown(footer, message) {
    if (!footer) return;
    const cliRuntimeMs = Number(message?.cli_runtime_ms);
    const queueWaitMs = Number(message?.queue_wait_ms);
    footer.dataset.cliRuntimeText = Number.isFinite(cliRuntimeMs) && cliRuntimeMs > 0
        ? (formatDuration(cliRuntimeMs) || '')
        : '';
    footer.dataset.queueWaitText = Number.isFinite(queueWaitMs) && queueWaitMs > 0
        ? (formatDuration(queueWaitMs) || '')
        : '';
    syncMessageFooter(footer);
}

function setMessageFinalizeReason(footer, finalizeReason) {
    if (!footer) return;
    footer.dataset.finalizeText = getFinalizeReasonLabel(finalizeReason);
    syncMessageFooter(footer);
}

function setMessageFinalizeComparison(footer, message) {
    if (!footer) return;
    const comparison = buildFinalizeComparison(message);
    if (!comparison) {
        footer.dataset.finalizeTimingText = '';
        syncMessageFooter(footer);
        return;
    }
    footer.dataset.finalizeTimingText = `CLI 종료→최종응답 ${comparison.lagText}`;
    syncMessageFooter(footer);
}

function setMessageDetailLogLink(footer, message) {
    if (!footer) return;
    const detailText = buildMessageDetailText(message);
    if (!detailText) {
        footer.dataset.detailText = '';
        footer.dataset.detailTitle = '';
        syncMessageFooter(footer);
        return;
    }
    const timestamp = formatTimestamp(getMessageTimestampValue(message));
    const roleLabel = getRoleLabel(message?.role);
    footer.dataset.detailText = detailText;
    footer.dataset.detailTitle = timestamp
        ? `${roleLabel} · ${timestamp} · 상세 로그`
        : `${roleLabel} · 상세 로그`;
    syncMessageFooter(footer);
}

function resolveMessageRoleFromWrapper(wrapper) {
    if (!wrapper) return '';
    if (wrapper.classList.contains('user')) return 'user';
    if (wrapper.classList.contains('assistant')) return 'assistant';
    if (wrapper.classList.contains('system')) return 'system';
    if (wrapper.classList.contains('error')) return 'error';
    return '';
}

function setMessageWrapperIdentity(wrapper, role, timestampValue, messageId = undefined) {
    if (!wrapper) return;
    const normalizedRole = typeof role === 'string' ? role.trim() : '';
    const normalizedTimestampValue = timestampValue === undefined || timestampValue === null
        ? ''
        : String(timestampValue).trim();
    wrapper.dataset.messageRole = normalizedRole;
    wrapper.dataset.messageTimestampValue = normalizedTimestampValue;
    if (messageId !== undefined) {
        const normalizedMessageId = messageId === null ? '' : String(messageId).trim();
        wrapper.dataset.messageId = normalizedMessageId;
    }
}

function buildMessagePreviewTitle(role, timestampValue) {
    const roleLabel = getRoleLabel(role);
    const timestamp = formatTimestamp(timestampValue);
    return timestamp
        ? `${roleLabel} · ${timestamp} · 전체 메시지`
        : `${roleLabel} · 전체 메시지`;
}

function setMessagePreviewLink(footer, content, message = null, wrapper = null) {
    if (!footer) return;
    const messageText = String(content || '');
    const normalizedText = normalizeDetailText(messageText);
    if (!normalizedText) {
        footer.dataset.previewText = '';
        footer.dataset.previewTitle = '';
        footer.dataset.previewSubtitle = '';
        syncMessageFooter(footer);
        return;
    }

    const messageRole = typeof message?.role === 'string' ? message.role.trim() : '';
    const wrapperRole = typeof wrapper?.dataset?.messageRole === 'string'
        ? wrapper.dataset.messageRole.trim()
        : '';
    const role = messageRole || wrapperRole || resolveMessageRoleFromWrapper(wrapper) || 'message';
    if (role === 'user') {
        footer.dataset.previewText = '';
        footer.dataset.previewTitle = '';
        footer.dataset.previewSubtitle = '';
        syncMessageFooter(footer);
        return;
    }

    const messageTimestamp = typeof getMessageTimestampValue(message) === 'string'
        ? getMessageTimestampValue(message).trim()
        : '';
    const wrapperTimestamp = typeof wrapper?.dataset?.messageTimestampValue === 'string'
        ? wrapper.dataset.messageTimestampValue.trim()
        : '';
    const timestampValue = messageTimestamp || wrapperTimestamp;

    footer.dataset.previewText = normalizedText;
    footer.dataset.previewTitle = buildMessagePreviewTitle(role, timestampValue);
    footer.dataset.previewSubtitle = '메시지 전체 보기';
    syncMessageFooter(footer);
}

function formatDuration(durationMs) {
    if (!Number.isFinite(durationMs)) return '';
    const totalSeconds = Math.max(0, durationMs / 1000);
    if (totalSeconds < 10) {
        return `${totalSeconds.toFixed(1)}초`;
    }
    const rounded = Math.round(totalSeconds);
    if (rounded < 60) {
        return `${rounded}초`;
    }
    const minutes = Math.floor(rounded / 60);
    const seconds = String(rounded % 60).padStart(2, '0');
    return `${minutes}분 ${seconds}초`;
}

function formatNumber(value) {
    if (!Number.isFinite(value)) return '0';
    return value.toLocaleString('en-US');
}

function formatStorageBytes(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return '--';
    if (numeric < 1024) return `${Math.round(numeric)} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let amount = numeric / 1024;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
    }
    const rounded = amount >= 100 ? amount.toFixed(0) : amount.toFixed(1);
    return `${rounded.replace(/\.0$/, '')} ${units[unitIndex]}`;
}

function updateSessionStorageSummary(storage) {
    const element = document.getElementById('codex-session-storage');
    if (!element) return;

    const totalBytes = Number(storage?.total_bytes);
    if (!Number.isFinite(totalBytes) || totalBytes < 0) {
        element.textContent = '세션 저장 용량 --';
        element.setAttribute('title', '세션 저장소 정보를 불러오지 못했습니다.');
        return;
    }

    const totalText = formatStorageBytes(totalBytes);
    const detailBytes = Number(storage?.work_details_bytes);
    const hasDetailBytes = Number.isFinite(detailBytes) && detailBytes > 0;
    const detailText = hasDetailBytes ? formatStorageBytes(detailBytes) : '0 B';

    const messageCount = Number(storage?.message_count);
    const detailCount = Number(storage?.work_details_count);
    const pathText = typeof storage?.path === 'string' ? storage.path : '';

    element.textContent = hasDetailBytes
        ? `세션 저장 용량 ${totalText} · 상세로그 ${detailText}`
        : `세션 저장 용량 ${totalText}`;

    const tooltipParts = [
        `총 용량 ${totalText}`,
        `상세로그 ${detailText}`,
    ];
    if (Number.isFinite(messageCount)) {
        tooltipParts.push(`메시지 ${formatNumber(messageCount)}개`);
    }
    if (Number.isFinite(detailCount)) {
        tooltipParts.push(`상세로그 항목 ${formatNumber(detailCount)}개`);
    }
    if (pathText) {
        tooltipParts.push(pathText);
    }
    element.setAttribute('title', tooltipParts.join(' · '));
}

function normalizeUsedPercent(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    if (numeric < 0) return 0;
    if (numeric > 0 && numeric < 1) {
        return Math.min(100, numeric * 100);
    }
    return Math.min(100, numeric);
}

function formatUsagePercent(value) {
    if (!Number.isFinite(value)) return '--';
    const clamped = Math.max(0, Math.min(100, value));
    if (clamped === 0 || clamped === 100) {
        return String(Math.round(clamped));
    }
    const floored = Math.floor(clamped * 10) / 10;
    if (!Number.isFinite(floored)) return '--';
    return floored % 1 === 0 ? String(Math.trunc(floored)) : floored.toFixed(1);
}

function formatRemainingPercent(usedPercent) {
    const normalizedUsed = normalizeUsedPercent(usedPercent);
    if (!Number.isFinite(normalizedUsed)) return '--';
    const remaining = Math.max(0, 100 - normalizedUsed);
    return formatUsagePercent(remaining);
}

function formatResetTimestamp(value) {
    if (!value) return '';
    let date = null;
    if (typeof value === 'number') {
        const ms = value < 1000000000000 ? value * 1000 : value;
        date = new Date(ms);
    } else {
        date = new Date(value);
    }
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('ko-KR', { timeZone: KST_TIME_ZONE });
}

function formatLimitUsage(entry, label) {
    const resetText = formatResetTimestamp(entry?.resets_at);
    const normalizedUsed = normalizeUsedPercent(entry?.used_percent);
    if (!entry || !Number.isFinite(normalizedUsed)) {
        return {
            label,
            remainingText: '--',
            resetText
        };
    }
    const remaining = formatRemainingPercent(normalizedUsed);
    return {
        label,
        remainingText: `${remaining}% left`,
        resetText
    };
}

function estimateTokensFromText(text) {
    const value = typeof text === 'string' ? text : String(text || '');
    const normalized = value.trim();
    if (!normalized) return 0;
    return Math.max(1, Math.ceil(normalized.length / 4));
}

function estimateSessionTokenCountFromMessages(messages) {
    const usage = estimateSessionTokenUsageFromMessages(messages);
    return usage.totalTokens;
}

function formatCompactTokenCount(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return '0';
    const absolute = Math.abs(numeric);
    if (absolute >= 1_000_000_000) {
        return `${(numeric / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`;
    }
    if (absolute >= 1_000_000) {
        return `${(numeric / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
    }
    if (absolute >= 1_000) {
        return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
    }
    return String(Math.round(numeric));
}

function countLiveSessionCount() {
    if (!Array.isArray(state.sessions) || state.sessions.length === 0) return 0;
    return state.sessions.reduce((count, session) => {
        const sessionId = session?.id;
        if (!sessionId) return count;
        const sessionState = getSessionState(sessionId);
        const hasPending = Boolean(sessionState?.sending || sessionState?.pendingSend);
        return count + (isSessionStreaming(sessionId) || hasPending ? 1 : 0);
    }, 0);
}

function updateSessionsHeaderSummary() {
    const titleElement = document.getElementById('codex-sessions-title');
    const sessionsPanel = document.querySelector('.sessions');
    if (!titleElement || !sessionsPanel) return;
    const isCollapsed = sessionsPanel.classList.contains('is-collapsed');
    if (!isCollapsed) {
        titleElement.textContent = 'Sessions';
        titleElement.setAttribute('title', 'Sessions');
        return;
    }
    const sessionCount = Array.isArray(state.sessions) ? state.sessions.length : 0;
    const totalTokens = Array.isArray(state.sessions)
        ? state.sessions.reduce((sum, session) => {
            const tokenCount = Number(session?.token_count);
            return sum + (Number.isFinite(tokenCount) ? Math.max(0, tokenCount) : 0);
        }, 0)
        : 0;
    const liveCount = countLiveSessionCount();
    const summaryText = `${liveCount} live · ${sessionCount}s · ${formatCompactTokenCount(totalTokens)} tok`;
    titleElement.textContent = summaryText;
    titleElement.setAttribute(
        'title',
        `Live sessions ${formatNumber(liveCount)} · Total sessions ${formatNumber(sessionCount)} · Total tokens ${formatNumber(totalTokens)}`
    );
}

function buildUsageEntry(entry, label) {
    const details = formatLimitUsage(entry, label);
    if (!details) return null;
    const wrapper = document.createElement('div');
    wrapper.className = 'usage-entry';
    const row = document.createElement('div');
    row.className = 'usage-row';
    const pill = document.createElement('button');
    pill.type = 'button';
    pill.className = 'usage-pill';
    pill.disabled = true;
    pill.textContent = details.label;
    const value = document.createElement('span');
    value.className = 'usage-remaining';
    value.textContent = details.remainingText;
    row.appendChild(pill);
    row.appendChild(value);
    wrapper.appendChild(row);
    const reset = document.createElement('div');
    reset.className = 'usage-reset';
    reset.textContent = details.resetText ? `Reset ${details.resetText}` : 'Reset --';
    wrapper.appendChild(reset);
    return wrapper;
}

function buildUsageAccount(name) {
    if (!name) return null;
    const wrapper = document.createElement('div');
    wrapper.className = 'usage-account';
    wrapper.textContent = `Account: ${name}`;
    return wrapper;
}

function normalizeTokenUsageEntry(entry) {
    if (!entry || typeof entry !== 'object') return null;
    const inputTokens = Number(entry.input_tokens);
    const cachedInputTokens = Number(entry.cached_input_tokens);
    const outputTokens = Number(entry.output_tokens);
    const totalTokens = Number(entry.total_tokens);
    const requests = Number(entry.requests);
    const hasTokenData = [inputTokens, cachedInputTokens, outputTokens, totalTokens]
        .some(value => Number.isFinite(value) && value > 0);
    const hasRequestData = Number.isFinite(requests) && requests > 0;
    if (!hasTokenData && !hasRequestData) return null;
    return {
        inputTokens: Number.isFinite(inputTokens) ? Math.max(0, Math.round(inputTokens)) : 0,
        cachedInputTokens: Number.isFinite(cachedInputTokens) ? Math.max(0, Math.round(cachedInputTokens)) : 0,
        outputTokens: Number.isFinite(outputTokens) ? Math.max(0, Math.round(outputTokens)) : 0,
        totalTokens: Number.isFinite(totalTokens) ? Math.max(0, Math.round(totalTokens)) : 0,
        requests: Number.isFinite(requests) ? Math.max(0, Math.round(requests)) : 0,
        date: typeof entry.date === 'string' ? entry.date.trim() : ''
    };
}

function buildTokenUsageEntry(entry, label) {
    const details = normalizeTokenUsageEntry(entry);
    if (!details) return null;
    const wrapper = document.createElement('div');
    wrapper.className = 'usage-entry';
    const row = document.createElement('div');
    row.className = 'usage-row';
    const pill = document.createElement('button');
    pill.type = 'button';
    pill.className = 'usage-pill';
    pill.disabled = true;
    pill.textContent = label;
    const value = document.createElement('span');
    value.className = 'usage-remaining';
    value.textContent = `In ${formatCompactTokenCount(details.inputTokens)} · Out ${formatCompactTokenCount(details.outputTokens)}`;
    row.appendChild(pill);
    row.appendChild(value);
    wrapper.appendChild(row);

    const reset = document.createElement('div');
    reset.className = 'usage-reset';
    const totalText = formatNumber(details.totalTokens);
    const cachedText = formatNumber(details.cachedInputTokens);
    const requestText = formatNumber(details.requests);
    const dateText = details.date ? ` (${details.date})` : '';
    reset.textContent = `Total ${totalText} · Cached ${cachedText} · Req ${requestText}${dateText}`;
    wrapper.appendChild(reset);
    return wrapper;
}

function setMessageStreaming(wrapper, isStreaming) {
    if (!wrapper) return;
    wrapper.classList.toggle('is-streaming', Boolean(isStreaming));
}

function getStreamDuration(stream) {
    if (!stream?.startedAt) return null;
    return Math.max(0, Date.now() - stream.startedAt);
}

function renderMessageContent(content) {
    const text = String(content || '');
    return renderMarkdown(text, {
        showCodeLineNumbers: true
    });
}

function shouldCollapseMessage(text) {
    if (!text) return false;
    const lines = text.split(/\r?\n/);
    if (lines.length > MESSAGE_COLLAPSE_LINES) return true;
    return text.length > MESSAGE_COLLAPSE_CHARS;
}

function buildMessagePreview(text) {
    if (!text) return '';
    const lines = text.split(/\r?\n/);
    if (lines.length > MESSAGE_COLLAPSE_LINES) {
        const previewLines = lines.slice(-MESSAGE_COLLAPSE_LINES);
        return `...\n${previewLines.join('\n')}`;
    }
    if (text.length > MESSAGE_COLLAPSE_CHARS) {
        const tail = text.slice(-MESSAGE_COLLAPSE_CHARS);
        return `...${tail}`;
    }
    return text;
}

function normalizeMarkdownRenderOptions(options = {}) {
    const source = options && typeof options === 'object' ? options : {};
    return {
        showCodeLineNumbers: Boolean(source.showCodeLineNumbers)
    };
}

function renderMarkdown(text, options = {}) {
    const normalized = String(text || '').replace(/\r\n/g, '\n');
    return renderInlineMarkdown(normalized, options);
}

function encodeMermaidDiagramSource(value) {
    return encodeURIComponent(String(value || ''));
}

function decodeMermaidDiagramSource(value) {
    const source = String(value || '');
    if (!source) return '';
    try {
        return decodeURIComponent(source);
    } catch (error) {
        return source;
    }
}

function getNormalizedMermaidFenceLanguage(language) {
    const normalized = String(language || '').trim().toLowerCase();
    if (normalized === 'mermaid') return 'mermaid';
    if (normalized === 'flowchart' || normalized === 'graph') return 'flowchart';
    if (normalized === 'gantt') return 'gantt';
    return '';
}

function isMermaidFenceLanguage(language) {
    return Boolean(getNormalizedMermaidFenceLanguage(language));
}

function normalizeMermaidFenceSource(language, source) {
    const normalizedLanguage = getNormalizedMermaidFenceLanguage(language);
    const text = String(source || '');
    const trimmedLeading = text.replace(/^\s+/, '');

    if (normalizedLanguage === 'flowchart') {
        if (/^(?:flowchart|graph)\b/i.test(trimmedLeading)) {
            return text;
        }
        return `flowchart TD\n${text}`;
    }
    if (normalizedLanguage === 'gantt') {
        if (/^gantt\b/i.test(trimmedLeading)) {
            return text;
        }
        return `gantt\n${text}`;
    }
    return text;
}

function getMermaidThemeName() {
    return document.documentElement?.dataset?.theme === 'dark'
        ? 'dark'
        : 'default';
}

function hydrateRenderedMarkdown(container) {
    if (!container || !(container instanceof Element)) return;
    hydrateMessageLabelLinks(container);
    if (container.querySelector('.file-browser-mermaid[data-mermaid-source]')) {
        void hydrateMermaidDiagrams(container);
    }
}

async function hydrateMermaidDiagrams(container) {
    if (!container || !(container instanceof Element)) return;
    const diagrams = Array.from(container.querySelectorAll('.file-browser-mermaid[data-mermaid-source]'));
    if (!diagrams.length) return;
    let mermaidApi = null;
    try {
        mermaidApi = await ensureMermaidApiLoaded();
    } catch (error) {
        void error;
        return;
    }
    if (
        !mermaidApi
        || typeof mermaidApi.initialize !== 'function'
        || typeof mermaidApi.render !== 'function'
    ) {
        return;
    }

    const theme = getMermaidThemeName();
    mermaidApi.initialize({
        startOnLoad: false,
        theme
    });
    for (const node of diagrams) {
        if (!(node instanceof HTMLElement)) continue;
        const source = decodeMermaidDiagramSource(node.dataset.mermaidSource || '');
        if (!source.trim()) continue;
        if (node.dataset.mermaidRendered === '1' && node.dataset.mermaidRenderedTheme === theme) {
            continue;
        }
        try {
            const renderId = `codex-mermaid-${mermaidRenderSerial += 1}`;
            const renderResult = await mermaidApi.render(renderId, source);
            if (decodeMermaidDiagramSource(node.dataset.mermaidSource || '') !== source) continue;
            node.innerHTML = renderResult?.svg || '';
            node.classList.remove('is-error');
            node.dataset.mermaidRendered = '1';
            node.dataset.mermaidRenderedTheme = theme;
            if (typeof renderResult?.bindFunctions === 'function') {
                renderResult.bindFunctions(node);
            }
        } catch (error) {
            node.classList.add('is-error');
            node.dataset.mermaidRendered = '0';
            node.dataset.mermaidRenderedTheme = theme;
            node.innerHTML = [
                `<div class="file-browser-mermaid-error">${escapeHtml(normalizeError(error, 'Mermaid 렌더링에 실패했습니다.'))}</div>`,
                `<pre class="file-browser-mermaid-source"><code>${escapeHtml(source)}</code></pre>`
            ].join('');
        }
    }
}

function getScriptHighlightConfig(language) {
    const normalized = String(language || '').trim().toLowerCase();
    const javascriptKeywords = new Set([
        'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'debugger',
        'default', 'delete', 'do', 'else', 'export', 'extends', 'finally', 'for', 'function',
        'if', 'import', 'in', 'instanceof', 'let', 'new', 'of', 'return', 'static', 'super',
        'switch', 'throw', 'try', 'typeof', 'var', 'void', 'while', 'with', 'yield'
    ]);
    const typescriptKeywords = new Set([
        ...javascriptKeywords,
        'abstract', 'declare', 'enum', 'implements', 'interface', 'keyof', 'namespace',
        'private', 'protected', 'public', 'readonly', 'type'
    ]);
    const pythonKeywords = new Set([
        'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del',
        'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in',
        'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while',
        'with', 'yield'
    ]);
    const shellKeywords = new Set([
        'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'until', 'do', 'done', 'case',
        'esac', 'function', 'select', 'in'
    ]);
    const powershellKeywords = new Set([
        'begin', 'break', 'catch', 'class', 'continue', 'data', 'do', 'else', 'elseif', 'end',
        'exit', 'filter', 'finally', 'for', 'foreach', 'from', 'function', 'if', 'in', 'param',
        'return', 'switch', 'throw', 'trap', 'try', 'until', 'using', 'var', 'while'
    ]);

    if (normalized === 'javascript' || normalized === 'jsx') {
        return {
            allowDollar: true,
            lineComment: '//',
            blockComment: true,
            keywords: javascriptKeywords,
            literals: new Set(['false', 'null', 'true', 'undefined'])
        };
    }
    if (normalized === 'typescript' || normalized === 'tsx') {
        return {
            allowDollar: true,
            lineComment: '//',
            blockComment: true,
            keywords: typescriptKeywords,
            literals: new Set(['false', 'null', 'true', 'undefined'])
        };
    }
    if (normalized === 'python') {
        return {
            allowDollar: false,
            lineComment: '#',
            blockComment: false,
            tripleQuote: true,
            keywords: pythonKeywords,
            literals: new Set(['false', 'none', 'true'])
        };
    }
    if (normalized === 'bash' || normalized === 'shell') {
        return {
            allowDollar: false,
            lineComment: '#',
            blockComment: false,
            keywords: shellKeywords,
            literals: new Set([])
        };
    }
    if (normalized === 'powershell') {
        return {
            allowDollar: true,
            lineComment: '#',
            blockComment: false,
            keywords: powershellKeywords,
            literals: new Set(['$false', '$null', '$true'])
        };
    }
    return null;
}

function wrapScriptToken(type, text) {
    return `<span class="file-code-token-${type}">${escapeHtml(text)}</span>`;
}

function isScriptIdentifierStart(char, allowDollar = false) {
    if (!char) return false;
    if (allowDollar && char === '$') return true;
    return /[A-Za-z_]/.test(char);
}

function isScriptIdentifierPart(char, allowDollar = false) {
    if (!char) return false;
    if (allowDollar && char === '$') return true;
    return /[A-Za-z0-9_]/.test(char);
}

function highlightScriptContent(content, language) {
    const source = String(content || '');
    const config = getScriptHighlightConfig(language);
    if (!config) {
        return escapeHtml(source);
    }

    let cursor = 0;
    let output = '';
    while (cursor < source.length) {
        const current = source[cursor];
        const next = source[cursor + 1] || '';

        if (config.lineComment === '//' && current === '/' && next === '/') {
            const end = source.indexOf('\n', cursor);
            const sliceEnd = end === -1 ? source.length : end;
            output += wrapScriptToken('comment', source.slice(cursor, sliceEnd));
            cursor = sliceEnd;
            continue;
        }
        if (config.lineComment === '#' && current === '#') {
            const end = source.indexOf('\n', cursor);
            const sliceEnd = end === -1 ? source.length : end;
            output += wrapScriptToken('comment', source.slice(cursor, sliceEnd));
            cursor = sliceEnd;
            continue;
        }
        if (config.blockComment && current === '/' && next === '*') {
            const end = source.indexOf('*/', cursor + 2);
            const sliceEnd = end === -1 ? source.length : end + 2;
            output += wrapScriptToken('comment', source.slice(cursor, sliceEnd));
            cursor = sliceEnd;
            continue;
        }

        const isQuote = current === '\'' || current === '"' || current === '`';
        if (isQuote) {
            const quote = current;
            if (config.tripleQuote && (quote === '\'' || quote === '"') && source.startsWith(quote.repeat(3), cursor)) {
                const end = source.indexOf(quote.repeat(3), cursor + 3);
                const sliceEnd = end === -1 ? source.length : end + 3;
                output += wrapScriptToken('string', source.slice(cursor, sliceEnd));
                cursor = sliceEnd;
                continue;
            }
            let index = cursor + 1;
            while (index < source.length) {
                const char = source[index];
                if (char === '\\') {
                    index += 2;
                    continue;
                }
                if (char === quote) {
                    index += 1;
                    break;
                }
                index += 1;
            }
            output += wrapScriptToken('string', source.slice(cursor, Math.min(index, source.length)));
            cursor = Math.min(index, source.length);
            continue;
        }

        const previous = cursor > 0 ? source[cursor - 1] : '';
        const numberMatch = source.slice(cursor).match(
            /^(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/
        );
        if (
            numberMatch
            && numberMatch[0]
            && !isScriptIdentifierPart(previous, config.allowDollar)
        ) {
            output += wrapScriptToken('number', numberMatch[0]);
            cursor += numberMatch[0].length;
            continue;
        }

        if (isScriptIdentifierStart(current, config.allowDollar)) {
            let index = cursor + 1;
            while (index < source.length && isScriptIdentifierPart(source[index], config.allowDollar)) {
                index += 1;
            }
            const word = source.slice(cursor, index);
            const lowered = word.toLowerCase();
            if (config.keywords.has(lowered)) {
                output += wrapScriptToken('keyword', word);
            } else if (config.literals.has(lowered) || config.literals.has(word)) {
                output += wrapScriptToken('literal', word);
            } else {
                output += escapeHtml(word);
            }
            cursor = index;
            continue;
        }

        output += escapeHtml(current);
        cursor += 1;
    }
    return output;
}

function decodeHtmlEntities(value) {
    const source = String(value || '');
    if (!source.includes('&')) return source;
    return source
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, '\'')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>');
}

function normalizeMarkdownLinkHref(value) {
    const decoded = decodeHtmlEntities(value);
    if (!decoded) return '';
    return decoded.trim();
}

function isHttpMarkdownHref(value) {
    return /^https?:\/\//i.test(String(value || ''));
}

function normalizeFileSchemePath(value) {
    const source = String(value || '').trim();
    if (!source) return '';
    if (!/^file:\/\//i.test(source)) return source;
    let pathText = source.replace(/^file:\/\//i, '');
    if (!pathText) return '';
    if (/^\/[A-Za-z]:\//.test(pathText)) {
        pathText = pathText.slice(1);
    } else if (!/^[A-Za-z]:\//.test(pathText) && !pathText.startsWith('/')) {
        pathText = `/${pathText}`;
    }
    return pathText;
}

function resolveAbsoluteFilesystemTargetFromMarkdownHref(value) {
    const normalizedHref = normalizeMarkdownLinkHref(value);
    if (!normalizedHref) return null;
    const candidate = normalizeFilesystemPath(normalizeFileSchemePath(normalizedHref));
    if (!candidate) return null;
    return parseAbsoluteFilesystemTarget(candidate, getMessageLogPathRoots());
}

function renderMarkdownLink(label, href) {
    const rawLabel = String(label || '');
    const displayLabel = rawLabel.trim() || '링크';
    const safeLabel = escapeHtml(displayLabel);
    const normalizedHref = normalizeMarkdownLinkHref(href);
    if (!normalizedHref) {
        return safeLabel;
    }

    if (isHttpMarkdownHref(normalizedHref)) {
        return `<a href="${escapeHtml(normalizedHref)}" target="_blank" rel="noopener noreferrer">${safeLabel}</a>`;
    }

    const fileTarget = resolveAbsoluteFilesystemTargetFromMarkdownHref(normalizedHref);
    if (!fileTarget?.absolutePath) {
        return safeLabel;
    }

    const absolutePath = fileTarget.absolutePath;
    const line = normalizeSourceLineNumber(fileTarget.line);
    const column = normalizeSourceColumnNumber(fileTarget.column);
    const hasLocationInLabel = /(?:#L\d+(?:C\d+)?|:\d+(?::\d+)?)$/i.test(displayLabel);
    const visibleLabel = (!hasLocationInLabel && line)
        ? `${displayLabel}:${line}${column ? `:${column}` : ''}`
        : displayLabel;
    const safeVisibleLabel = escapeHtml(visibleLabel);

    const shortenedPath = shortenAbsoluteFilesystemPath(absolutePath, getMessageLogPathRoots()) || absolutePath;
    const shortenedPathWithLocation = formatFilesystemPathWithLocation(shortenedPath, line, column);
    const tooltipText = `파일 경로: ${shortenedPathWithLocation}`;
    return `<a href="#" class="message-label-link hover-tooltip" data-file-path="${escapeHtml(absolutePath)}" data-file-line="${line || ''}" data-file-column="${column || ''}" data-tooltip="${escapeHtml(tooltipText)}" title="${escapeHtml(tooltipText)}">${safeVisibleLabel}</a>`;
}

function hydrateMessageLabelLinks(container) {
    if (!container || !(container instanceof Element)) return;
    container.querySelectorAll('a.message-label-link').forEach(link => {
        if (!(link instanceof HTMLAnchorElement)) return;
        if (link.dataset.linkBound === '1') return;
        link.dataset.linkBound = '1';
        link.addEventListener('click', event => {
            event.preventDefault();
            const absolutePath = normalizeFilesystemPath(link.dataset?.filePath || '');
            if (!absolutePath) return;
            const targetLine = normalizeSourceLineNumber(link.dataset?.fileLine || '');
            const targetColumn = normalizeSourceColumnNumber(link.dataset?.fileColumn || '');
            const opened = openFileBrowserFromAbsolutePath(absolutePath, {
                line: targetLine,
                column: targetColumn
            });
            if (!opened) {
                showToast('현재 브라우저 루트에서 접근할 수 없는 파일입니다.', {
                    tone: 'error',
                    durationMs: 3600
                });
            }
        });
    });
}

function renderInlineMarkdownSpans(text) {
    const source = String(text || '');
    const inlineCodeTokens = [];
    let html = source.replace(/`([^`\n]+)`/g, (match, codeText) => {
        const token = `@@MDCODE${inlineCodeTokens.length}@@`;
        inlineCodeTokens.push(`<code>${escapeHtml(codeText)}</code>`);
        return token;
    });

    html = escapeHtml(html);
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, href) => {
        return renderMarkdownLink(decodeHtmlEntities(label), decodeHtmlEntities(href));
    });
    html = html.replace(/@@MDCODE(\d+)@@/g, (match, indexText) => {
        const index = Number(indexText);
        return inlineCodeTokens[index] || '';
    });
    return html;
}

function parseMarkdownFenceStart(line) {
    const source = String(line || '');
    const match = source.match(/^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+.#-]*)\s*$/);
    if (!match) return null;
    const fence = match[1];
    return {
        markerChar: fence[0],
        markerSize: fence.length,
        language: String(match[2] || '').trim().toLowerCase()
    };
}

function parseMarkdownCodeBlockLineNumbers(lineCount) {
    const normalizedCount = Math.max(1, Number.isFinite(lineCount) ? Math.round(lineCount) : 1);
    const numbers = [];
    for (let index = 1; index <= normalizedCount; index += 1) {
        numbers.push(String(index));
    }
    return numbers.join('\n');
}

function parseMarkdownFencedCodeBlock(lines, startIndex, options = {}) {
    if (!Array.isArray(lines) || startIndex < 0 || startIndex >= lines.length) return null;
    const opener = parseMarkdownFenceStart(lines[startIndex]);
    if (!opener) return null;
    const renderOptions = normalizeMarkdownRenderOptions(options);

    let index = startIndex + 1;
    const codeLines = [];
    while (index < lines.length) {
        const current = String(lines[index] || '');
        const closeMatch = current.match(/^\s*(`{3,}|~{3,})\s*$/);
        if (
            closeMatch
            && closeMatch[1]
            && closeMatch[1][0] === opener.markerChar
            && closeMatch[1].length >= opener.markerSize
        ) {
            index += 1;
            break;
        }
        codeLines.push(current);
        index += 1;
    }

    const codeText = codeLines.join('\n');
    if (isMermaidFenceLanguage(opener.language)) {
        const mermaidSource = normalizeMermaidFenceSource(opener.language, codeText);
        const encodedSource = escapeHtml(encodeMermaidDiagramSource(mermaidSource));
        const safeSource = escapeHtml(mermaidSource);
        return {
            html: [
                `<div class="file-browser-mermaid" data-mermaid-source="${encodedSource}" data-mermaid-rendered="0">`,
                `<pre class="file-browser-mermaid-source"><code>${safeSource}</code></pre>`,
                '</div>'
            ].join(''),
            nextIndex: index
        };
    }
    const codeHtml = opener.language
        ? highlightScriptContent(codeText, opener.language)
        : escapeHtml(codeText);
    const languageClass = opener.language ? ` class="language-${escapeHtml(opener.language)}"` : '';
    if (renderOptions.showCodeLineNumbers) {
        const lineCount = Math.max(1, codeLines.length);
        const digitWidth = Math.max(2, String(lineCount).length);
        const gutterText = parseMarkdownCodeBlockLineNumbers(lineCount);
        return {
            html: [
                `<pre class="markdown-code-block" style="--markdown-code-line-digit-width:${digitWidth}">`,
                `<span class="markdown-code-gutter" aria-hidden="true">${gutterText}</span>`,
                `<code${languageClass}>${codeHtml}</code>`,
                '</pre>'
            ].join(''),
            nextIndex: index
        };
    }
    return {
        html: `<pre><code${languageClass}>${codeHtml}</code></pre>`,
        nextIndex: index
    };
}

function parseMarkdownHeadingLine(line) {
    const source = String(line || '');
    const match = source.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (!match) return null;
    return {
        level: Math.max(1, Math.min(6, match[1].length)),
        text: match[2]
    };
}

function isMarkdownHorizontalRule(line) {
    const source = String(line || '').trim();
    if (!source) return false;
    return /^(-\s*){3,}$/.test(source)
        || /^(\*\s*){3,}$/.test(source)
        || /^(_\s*){3,}$/.test(source);
}

function parseMarkdownListLine(line) {
    const source = String(line || '');
    const unordered = source.match(/^\s*([-+*])\s+(.+)$/);
    if (unordered) {
        return {
            ordered: false,
            number: null,
            content: unordered[2]
        };
    }
    const ordered = source.match(/^\s*(\d+)[.)]\s+(.+)$/);
    if (ordered) {
        return {
            ordered: true,
            number: Number(ordered[1]) || 1,
            content: ordered[2]
        };
    }
    return null;
}

function parseMarkdownList(lines, startIndex) {
    if (!Array.isArray(lines) || startIndex < 0 || startIndex >= lines.length) return null;
    const first = parseMarkdownListLine(lines[startIndex]);
    if (!first) return null;

    const ordered = first.ordered;
    const startNumber = first.number || 1;
    const items = [];
    let index = startIndex;
    while (index < lines.length) {
        const parsed = parseMarkdownListLine(lines[index]);
        if (!parsed || parsed.ordered !== ordered) break;

        const content = String(parsed.content || '').trim();
        const taskMatch = content.match(/^\[( |x|X)\]\s+(.*)$/);
        if (taskMatch) {
            const checked = /x/i.test(taskMatch[1]);
            const labelHtml = renderInlineMarkdownSpans(taskMatch[2]);
            items.push(
                `<li class="markdown-task-item"><label><input type="checkbox" disabled${checked ? ' checked' : ''}><span>${labelHtml}</span></label></li>`
            );
        } else {
            items.push(`<li>${renderInlineMarkdownSpans(content)}</li>`);
        }
        index += 1;
    }

    if (items.length === 0) return null;
    const tag = ordered ? 'ol' : 'ul';
    const startAttr = ordered && startNumber > 1 ? ` start="${startNumber}"` : '';
    const hasTaskItems = items.some(item => item.includes('markdown-task-item'));
    const classAttr = hasTaskItems ? ' class="markdown-task-list"' : '';
    return {
        html: `<${tag}${startAttr}${classAttr}>${items.join('')}</${tag}>`,
        nextIndex: index
    };
}

function parseMarkdownBlockquote(lines, startIndex, options = {}) {
    if (!Array.isArray(lines) || startIndex < 0 || startIndex >= lines.length) return null;
    const quoteLines = [];
    let index = startIndex;
    let matched = false;
    while (index < lines.length) {
        const source = String(lines[index] || '');
        if (!source.trim()) {
            if (!matched) break;
            quoteLines.push('');
            index += 1;
            continue;
        }
        const marker = source.match(/^\s{0,3}>\s?(.*)$/);
        if (!marker) break;
        matched = true;
        quoteLines.push(marker[1] || '');
        index += 1;
    }
    if (!matched) return null;
    const innerHtml = renderInlineMarkdown(quoteLines.join('\n'), options);
    return {
        html: `<blockquote>${innerHtml}</blockquote>`,
        nextIndex: index
    };
}

function splitMarkdownTableRow(line) {
    const source = String(line || '').trim();
    if (!source.includes('|')) return [];
    let row = source;
    if (row.startsWith('|')) row = row.slice(1);
    if (row.endsWith('|')) row = row.slice(0, -1);
    if (!row.includes('|')) return [];
    return row.split('|').map(cell => cell.trim());
}

function parseMarkdownTableAlignment(cell) {
    const compact = String(cell || '').replace(/\s+/g, '');
    if (!/^:?-{3,}:?$/.test(compact)) return '';
    if (compact.startsWith(':') && compact.endsWith(':')) return 'center';
    if (compact.endsWith(':')) return 'right';
    return 'left';
}

function getMarkdownTableAlignAttr(alignment) {
    if (alignment === 'center') return ' style="text-align:center"';
    if (alignment === 'right') return ' style="text-align:right"';
    if (alignment === 'left') return ' style="text-align:left"';
    return '';
}

function parseMarkdownTable(lines, startIndex) {
    if (!Array.isArray(lines) || startIndex + 1 >= lines.length) return null;
    const headerLine = lines[startIndex];
    const separatorLine = lines[startIndex + 1];
    if (!headerLine?.includes('|') || !separatorLine?.includes('|')) return null;

    const headerCells = splitMarkdownTableRow(headerLine);
    const separatorCells = splitMarkdownTableRow(separatorLine);
    if (headerCells.length < 2 || separatorCells.length !== headerCells.length) {
        return null;
    }

    const alignments = separatorCells.map(parseMarkdownTableAlignment);
    if (alignments.some(alignment => !alignment)) {
        return null;
    }

    const bodyRows = [];
    let index = startIndex + 2;
    while (index < lines.length) {
        const line = lines[index];
        if (!line || !line.includes('|')) break;
        const cells = splitMarkdownTableRow(line);
        if (!cells.length) break;
        const normalizedCells = [];
        for (let cellIndex = 0; cellIndex < headerCells.length; cellIndex += 1) {
            normalizedCells.push(cells[cellIndex] || '');
        }
        bodyRows.push(normalizedCells);
        index += 1;
    }

    const headHtml = headerCells.map((cell, cellIndex) => {
        const attr = getMarkdownTableAlignAttr(alignments[cellIndex]);
        return `<th${attr}>${renderInlineMarkdownSpans(cell)}</th>`;
    }).join('');

    const bodyHtml = bodyRows.length > 0
        ? `<tbody>${bodyRows.map(row => {
            const rowHtml = row.map((cell, cellIndex) => {
                const attr = getMarkdownTableAlignAttr(alignments[cellIndex]);
                return `<td${attr}>${renderInlineMarkdownSpans(cell)}</td>`;
            }).join('');
            return `<tr>${rowHtml}</tr>`;
        }).join('')}</tbody>`
        : '';

    return {
        html: `<table class="markdown-table"><thead><tr>${headHtml}</tr></thead>${bodyHtml}</table>`,
        nextIndex: index
    };
}

function isMarkdownBlockBoundary(lines, index) {
    const line = String(lines[index] || '');
    if (!line.trim()) return true;
    if (parseMarkdownFenceStart(line)) return true;
    if (parseMarkdownHeadingLine(line)) return true;
    if (isMarkdownHorizontalRule(line)) return true;
    if (parseMarkdownListLine(line)) return true;
    if (/^\s{0,3}>\s?/.test(line)) return true;
    if (parseMarkdownTable(lines, index)) return true;
    return false;
}

function renderInlineMarkdown(text, options = {}) {
    const renderOptions = normalizeMarkdownRenderOptions(options);
    const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
    const parts = [];
    let lineIndex = 0;
    while (lineIndex < lines.length) {
        while (lineIndex < lines.length && !String(lines[lineIndex] || '').trim()) {
            lineIndex += 1;
        }
        if (lineIndex >= lines.length) break;

        const fenced = parseMarkdownFencedCodeBlock(lines, lineIndex, renderOptions);
        if (fenced) {
            parts.push(fenced.html);
            lineIndex = fenced.nextIndex;
            continue;
        }

        const table = parseMarkdownTable(lines, lineIndex);
        if (table) {
            parts.push(table.html);
            lineIndex = table.nextIndex;
            continue;
        }

        const heading = parseMarkdownHeadingLine(lines[lineIndex]);
        if (heading) {
            parts.push(`<h${heading.level}>${renderInlineMarkdownSpans(heading.text)}</h${heading.level}>`);
            lineIndex += 1;
            continue;
        }

        if (isMarkdownHorizontalRule(lines[lineIndex])) {
            parts.push('<hr>');
            lineIndex += 1;
            continue;
        }

        const blockquote = parseMarkdownBlockquote(lines, lineIndex, renderOptions);
        if (blockquote) {
            parts.push(blockquote.html);
            lineIndex = blockquote.nextIndex;
            continue;
        }

        const list = parseMarkdownList(lines, lineIndex);
        if (list) {
            parts.push(list.html);
            lineIndex = list.nextIndex;
            continue;
        }

        const paragraphLines = [];
        while (lineIndex < lines.length) {
            const candidate = String(lines[lineIndex] || '');
            if (!candidate.trim()) break;
            if (paragraphLines.length > 0 && isMarkdownBlockBoundary(lines, lineIndex)) break;
            paragraphLines.push(candidate.trim());
            lineIndex += 1;
        }
        if (paragraphLines.length > 0) {
            parts.push(`<p>${paragraphLines.map(renderInlineMarkdownSpans).join('<br>')}</p>`);
        }
    }
    return parts.join('');
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function normalizeError(error, fallback) {
    if (typeof error === 'string' && error.trim()) return error.trim();
    if (error instanceof Error && error.message) return error.message;
    if (error && typeof error === 'object') {
        try {
            const serialized = JSON.stringify(error);
            if (serialized && serialized !== '{}') return serialized;
        } catch (err) {
            return fallback || 'An unknown error occurred.';
        }
    }
    return fallback || 'An unknown error occurred.';
}
