const state = {
    sessions: [],
    activeSessionId: null,
    loading: false,
    sessionStates: {},
    streams: {},
    remoteStreamSessions: new Set(),
    remoteStreams: [],
    liveClockTimer: null,
    responseTimerId: null,
    responseTimerSessionId: null,
    weatherRefreshTimer: null,
    weatherLocationFailureNotified: false,
    autoScrollEnabled: true,
    autoScrollPinnedSessionId: null,
    autoScrollThreshold: 48,
    statusMessage: 'Idle',
    statusIsError: false,
    settings: {
        model: null,
        modelOptions: [],
        reasoningEffort: null,
        reasoningOptions: [],
        usage: null,
        loaded: false
    }
};

const SESSION_COLLAPSE_KEY = 'codexSessionsCollapsed';
const ACTIVE_STREAM_KEY = 'codexActiveStream';
const CONTROLS_COLLAPSE_KEY = 'codexControlsCollapsed';
const MOBILE_MEDIA_QUERY = '(max-width: 960px)';
const MOBILE_VIEWPORT_HEIGHT_VAR = '--mobile-viewport-height';
const MOBILE_SETTINGS_FOCUS_CLASS = 'is-settings-input-focused';
const MOBILE_KEYBOARD_OPEN_CLASS = 'is-mobile-keyboard-open';
const MOBILE_KEYBOARD_VIEWPORT_DELTA = 120;
const CHAT_FULLSCREEN_CLASS = 'is-chat-fullscreen';
const THEME_KEY = 'codexTheme';
const THEME_MEDIA_QUERY = '(prefers-color-scheme: dark)';
const STREAM_POLL_BASE_MS = 800;
const STREAM_POLL_MAX_MS = 5000;
const REMOTE_STREAM_POLL_MS = 2500;
const MESSAGE_COLLAPSE_LINES = 12;
const MESSAGE_COLLAPSE_CHARS = 1200;
const KST_TIME_ZONE = 'Asia/Seoul';
const WEATHER_REFRESH_MS = 10 * 60 * 1000;
const WEATHER_POSITION_KEY = 'codexWeatherPosition';
const WEATHER_COMPACT_KEY = 'codexWeatherCompact';
const WEATHER_LOCATION_FAILURE_TOAST_MS = 3800;
const TOAST_LAYER_ID = 'codex-toast-layer';
const DEFAULT_WEATHER_LOCATION_LABEL = '화성시 동탄(신동)';
const DEFAULT_WEATHER_POSITION = Object.freeze({
    latitude: 37.2053,
    longitude: 127.1067,
    label: DEFAULT_WEATHER_LOCATION_LABEL,
    isDefault: true
});
const CHAT_INPUT_DEFAULT_PLACEHOLDER = 'Type a prompt for Codex. (Shift+Enter for newline)';
const GIT_ACTION_LABELS = Object.freeze({
    submit: 'git commit',
    sync: 'git fetch + push'
});
const GIT_BRANCH_STATUS_CACHE_MS = 5000;
const GIT_BRANCH_TOAST_COOLDOWN_MS = 900;
const GIT_BRANCH_POLL_MS = 10000;

let hasManualTheme = false;
let gitBranchStatusCache = {
    count: null,
    branch: '',
    changedFiles: [],
    fetchedAt: 0
};
let gitBranchToastAt = 0;
let gitBranchStatusInFlight = false;
let gitBranchPollTimer = null;
let remoteStreamStatusCache = {
    streams: [],
    fetchedAt: 0
};
let remoteStreamPollTimer = null;
let remoteStreamStatusInFlight = false;
let streamMonitorState = null;
let hoverTooltipInteractionsBound = false;

function ensureSessionState(sessionId) {
    if (!sessionId) return null;
    if (!state.sessionStates[sessionId]) {
        state.sessionStates[sessionId] = {
            sending: false,
            pendingSend: null,
            streamId: null,
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
    const responseStatus = message === 'Waiting for Codex...' || message === 'Receiving response...';
    if (!isError && responseStatus) {
        if (!sessionState.responseStartedAt) {
            const pendingStartedAt = sessionState.pendingSend?.startedAt;
            const streamStartedAt = getSessionStream(sessionId)?.startedAt;
            sessionState.responseStartedAt = pendingStartedAt || streamStartedAt || Date.now();
        }
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
    const isBusy = sessionId ? (localBusy || remoteBusy) : false;
    const showStop = sessionId ? localBusy : false;
    if (input) {
        input.disabled = isBusy;
        input.readOnly = isBusy;
        input.setAttribute('aria-disabled', String(isBusy));
        input.placeholder = isBusy
            ? 'Response in progress for this session...'
            : CHAT_INPUT_DEFAULT_PLACEHOLDER;
    }
    if (sendBtn) {
        sendBtn.disabled = remoteBusy && !localBusy;
        sendBtn.dataset.mode = showStop ? 'stop' : 'send';
        sendBtn.setAttribute('aria-label', showStop ? 'Stop' : 'Send');
        sendBtn.setAttribute('title', showStop ? 'Stop' : 'Send');
        const srLabel = sendBtn.querySelector('.sr-only');
        if (srLabel) {
            srLabel.textContent = showStop ? 'Stop' : 'Send';
        }
    }
}

function appendMessageToDOMIfActive(sessionId, message, roleOverride = null) {
    if (sessionId !== state.activeSessionId) return null;
    return appendMessageToDOM(message, roleOverride);
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
    const assistantEntry = appendMessageToDOM({
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString()
    }, 'assistant');
    if (!assistantEntry) return;
    stream.entry = assistantEntry;
    setMessageStreaming(assistantEntry.wrapper, true);
    updateStreamEntry(stream);
}

function createStreamState({
    id,
    sessionId,
    entry = null,
    output = '',
    error = '',
    outputOffset = 0,
    errorOffset = 0,
    startedAt = null
}) {
    if (!id || !sessionId) return null;
    const stream = {
        id,
        sessionId,
        outputOffset,
        errorOffset,
        output,
        error,
        entry,
        startedAt: startedAt || Date.now(),
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
        if (!sessionState.responseStartedAt && stream.startedAt) {
            sessionState.responseStartedAt = stream.startedAt;
        }
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

function primeSettingsOptionsFromDom(modelSelect, reasoningSelect) {
    const modelOptions = readOptionsFromData(modelSelect);
    const reasoningOptions = readOptionsFromData(reasoningSelect);
    if (modelOptions.length > 0) {
        state.settings.modelOptions = modelOptions;
    }
    if (reasoningOptions.length > 0) {
        state.settings.reasoningOptions = reasoningOptions;
    }
    if (modelOptions.length > 0 || reasoningOptions.length > 0) {
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('codex-chat-form');
    const input = document.getElementById('codex-chat-input');
    const newSessionBtn = document.getElementById('codex-chat-new-session');
    const refreshBtn = document.getElementById('codex-chat-refresh');
    const chatFullscreenBtn = document.getElementById('codex-chat-fullscreen');
    const messages = document.getElementById('codex-chat-messages');
    const streamMonitorCloseBtn = document.getElementById('codex-stream-monitor-close');
    const streamMonitorToggle = document.getElementById('codex-stream-monitor-toggle');
    const streamMonitor = document.getElementById('codex-stream-monitor');
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    const mobileMedia = window.matchMedia(MOBILE_MEDIA_QUERY);
    const themeToggle = document.getElementById('codex-theme-toggle');
    const themeMedia = window.matchMedia(THEME_MEDIA_QUERY);
    const modelSelect = document.getElementById('codex-model-select');
    const modelInput = document.getElementById('codex-model-input');
    const modelApply = document.getElementById('codex-model-apply');
    const reasoningSelect = document.getElementById('codex-reasoning-select');
    const reasoningInput = document.getElementById('codex-reasoning-input');
    const controlsToggle = document.getElementById('codex-controls-toggle');
    const controls = document.getElementById('codex-controls');
    const gitBranch = document.getElementById('codex-git-branch');
    const gitSubmitBtn = document.getElementById('codex-git-submit');
    const gitSyncBtn = document.getElementById('codex-git-sync');
    const branchOverlaySubmitBtn = document.getElementById('codex-branch-overlay-submit');
    const branchOverlaySyncBtn = document.getElementById('codex-branch-overlay-sync');

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
    }

    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', async () => {
            await createSession(true);
        });
    }

    if (gitSubmitBtn) {
        gitSubmitBtn.addEventListener('click', () => {
            void handleGitAction('submit', gitSubmitBtn);
        });
    }

    if (gitSyncBtn) {
        gitSyncBtn.addEventListener('click', () => {
            void handleGitAction('sync', gitSyncBtn);
        });
    }
    if (branchOverlaySubmitBtn) {
        branchOverlaySubmitBtn.addEventListener('click', () => {
            void handleGitAction('submit', branchOverlaySubmitBtn);
        });
    }
    if (branchOverlaySyncBtn) {
        branchOverlaySyncBtn.addEventListener('click', () => {
            void handleGitAction('sync', branchOverlaySyncBtn);
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
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && isGitBranchOverlayOpen()) {
            closeGitBranchOverlay();
        }
    });

    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            if (refreshBtn.classList.contains('is-loading')) return;
            refreshBtn.classList.add('is-loading');
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
            }
        });
    }

    if (chatFullscreenBtn) {
        chatFullscreenBtn.addEventListener('click', () => {
            const app = document.querySelector('.app');
            const isEnabled = app?.classList.contains(CHAT_FULLSCREEN_CLASS);
            setChatFullscreen(!isEnabled);
        });
        const app = document.querySelector('.app');
        updateChatFullscreenButton(chatFullscreenBtn, app?.classList.contains(CHAT_FULLSCREEN_CLASS));
    }

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

    primeSettingsOptionsFromDom(modelSelect, reasoningSelect);

    syncSessionsLayout(mobileMedia.matches);
    syncControlsLayout();
    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', event => {
            syncSessionsLayout(event.matches);
            syncLiveWeatherLayout(event.matches);
        });
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(event => {
            syncSessionsLayout(event.matches);
            syncLiveWeatherLayout(event.matches);
        });
    }

    setupMobileViewportBehavior(mobileMedia, input);
    setupMobileSettingsInputBehavior(mobileMedia, [modelInput, reasoningInput, modelSelect, reasoningSelect]);

    if (messages) {
        messages.addEventListener('scroll', () => {
            handleMessageScroll(messages);
        });
    }

    if (modelSelect) {
        modelSelect.addEventListener('change', () => {
            if (modelSelect.value && modelInput) {
                modelInput.value = modelSelect.value;
            }
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

    if (reasoningSelect) {
        reasoningSelect.addEventListener('change', () => {
            if (reasoningSelect.value && reasoningInput) {
                reasoningInput.value = reasoningSelect.value;
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

    syncActiveSessionControls();
    syncActiveSessionStatus();
    initializeTheme(themeToggle, themeMedia);
    initializeLiveWeatherPanel(mobileMedia);
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
    const permissionToggle = document.getElementById('codex-weather-permission');
    if (!panel || !toggle || !permissionToggle) return;

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
        if (isCompact) {
            void maybeRequestWeatherPermissionOnTap();
        }
    });
    permissionToggle.addEventListener('click', event => {
        event.stopPropagation();
        void requestWeatherPermission();
    });
    void loadLiveWeatherData();
    if (state.weatherRefreshTimer) {
        window.clearInterval(state.weatherRefreshTimer);
    }
    state.weatherRefreshTimer = window.setInterval(() => {
        void loadLiveWeatherData({ silent: true });
    }, WEATHER_REFRESH_MS);
}

async function maybeRequestWeatherPermissionOnTap() {
    const storedPosition = readStoredWeatherPosition();
    if (storedPosition) return;
    const permissionState = await readGeolocationPermissionState();
    if (permissionState === 'granted') {
        void loadLiveWeatherData({ silent: true });
        return;
    }
    await requestWeatherPermission({ silentFailure: true, skipPermissionCheck: true });
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
    toggle.setAttribute('title', toggleLabel);
    syncSidebarStackLayout();
    if (persist) {
        try {
            localStorage.setItem(WEATHER_COMPACT_KEY, isCompact ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function syncLiveWeatherLayout(isMobile) {
    if (!isMobile) {
        setLiveWeatherCompact(false, { persist: false });
        return;
    }
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
}

function formatKstNow() {
    const parts = getKstNowParts();
    if (!parts) return '--';
    const datePart = `${parts.year}. ${parts.month}. ${parts.day}.`;
    const timePart = `${parts.hour}:${parts.minute}:${parts.second}`;
    const weekday = parts.weekday || '';
    return `${datePart} (${weekday}) ${timePart}`;
}

function setHoverTooltip(element, text) {
    if (!element) return;
    const resolved = text == null ? '' : String(text);
    if (resolved.trim()) {
        element.classList.add('hover-tooltip');
        element.setAttribute('data-tooltip', resolved);
        element.setAttribute('title', resolved);
        if (!element.hasAttribute('tabindex')) {
            element.setAttribute('tabindex', '0');
            element.setAttribute('data-tooltip-tabindex', '1');
        }
    } else {
        element.classList.remove('hover-tooltip');
        element.classList.remove('is-open');
        element.removeAttribute('data-tooltip');
        element.removeAttribute('title');
        if (element.getAttribute('data-tooltip-tabindex') === '1') {
            element.removeAttribute('tabindex');
            element.removeAttribute('data-tooltip-tabindex');
        }
    }
}

function closeOpenHoverTooltips(exceptElement = null) {
    document.querySelectorAll('.hover-tooltip.is-open').forEach(element => {
        if (exceptElement && element === exceptElement) return;
        element.classList.remove('is-open');
    });
}

function initializeHoverTooltipInteractions() {
    if (hoverTooltipInteractionsBound) return;
    hoverTooltipInteractionsBound = true;
    document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target.closest('.hover-tooltip') : null;
        if (!target || !target.getAttribute('data-tooltip')) {
            closeOpenHoverTooltips();
            return;
        }
        const willOpen = !target.classList.contains('is-open');
        closeOpenHoverTooltips(target);
        target.classList.toggle('is-open', willOpen);
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        closeOpenHoverTooltips();
    });
}

function setTextWithTooltip(element, text) {
    if (!element) return;
    const resolved = text == null ? '' : String(text);
    element.textContent = resolved;
    setHoverTooltip(element, resolved);
}

async function loadLiveWeatherData({ silent = false, positionOverride = null } = {}) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;

    if (!silent) {
        setTextWithTooltip(locationElement, '위치 확인 중...');
        setTextWithTooltip(currentElement, '날씨 불러오는 중...');
        setTextWithTooltip(todayElement, '불러오는 중...');
        setTextWithTooltip(tomorrowElement, '불러오는 중...');
    }

    try {
        const position = positionOverride || await resolveWeatherPosition();
        if (!position) {
            renderWeatherError('위치 확인 불가', '브라우저 위치 권한을 허용해 주세요.');
            return;
        }

        const defaultLabel = position?.label || '';
        const useDefaultLabel = Boolean(position?.isDefault && defaultLabel);
        const [locationName, weather] = await Promise.all([
            useDefaultLabel
                ? Promise.resolve(defaultLabel)
                : fetchLocationName(position.latitude, position.longitude).catch(() => ''),
            fetchWeatherForecast(position.latitude, position.longitude)
        ]);

        renderWeatherSummary({
            locationName: locationName || defaultLabel || '알 수 없는 위치',
            weather
        });
    } catch (error) {
        renderWeatherError('날씨 정보를 불러올 수 없음', normalizeError(error, '날씨 정보를 불러오지 못했습니다.'));
    }
}

async function requestWeatherPermission({ silentFailure = false, skipPermissionCheck = false } = {}) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    if (locationElement) {
        setTextWithTooltip(locationElement, '위치 권한 요청 중...');
    }
    if (currentElement) {
        setTextWithTooltip(currentElement, '브라우저 권한 응답 대기 중...');
    }
    try {
        if (!skipPermissionCheck) {
            const permissionState = await readGeolocationPermissionState();
            if (permissionState === 'denied') {
                notifyWeatherLocationFailure(
                    new Error('위치 권한이 거부되었습니다.'),
                    DEFAULT_WEATHER_LOCATION_LABEL
                );
                await loadLiveWeatherData({
                    silent: true,
                    positionOverride: getDefaultWeatherPosition()
                });
                return;
            }
        }
        const position = await getCurrentGeoPosition();
        writeStoredWeatherPosition(position);
        state.weatherLocationFailureNotified = false;
        await loadLiveWeatherData({ silent: true, positionOverride: position });
    } catch (error) {
        notifyWeatherLocationFailure(error, DEFAULT_WEATHER_LOCATION_LABEL);
        await loadLiveWeatherData({
            silent: true,
            positionOverride: getDefaultWeatherPosition()
        });
        if (silentFailure) return;
        void error;
    }
}

async function readGeolocationPermissionState() {
    try {
        if (!navigator.permissions || typeof navigator.permissions.query !== 'function') {
            return '';
        }
        const status = await navigator.permissions.query({ name: 'geolocation' });
        return status?.state || '';
    } catch (error) {
        return '';
    }
}

async function resolveWeatherPosition() {
    try {
        const current = await getCurrentGeoPosition();
        writeStoredWeatherPosition(current);
        state.weatherLocationFailureNotified = false;
        return current;
    } catch (error) {
        const stored = readStoredWeatherPosition();
        if (stored) {
            notifyWeatherLocationFailure(error, '저장된 위치');
            return stored;
        }
        notifyWeatherLocationFailure(error, DEFAULT_WEATHER_LOCATION_LABEL);
        return getDefaultWeatherPosition();
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

function getCurrentGeoPosition() {
    return new Promise((resolve, reject) => {
        if (!isGeolocationAllowedContext()) {
            reject(new Error('위치 접근은 HTTPS 또는 localhost에서만 가능합니다.'));
            return;
        }
        if (!navigator.geolocation) {
            reject(new Error('이 브라우저는 위치 정보를 지원하지 않습니다.'));
            return;
        }
        navigator.geolocation.getCurrentPosition(
            position => {
                resolve({
                    latitude: Number(position.coords?.latitude),
                    longitude: Number(position.coords?.longitude)
                });
            },
            error => {
                reject(error || new Error('현재 위치를 가져오지 못했습니다.'));
            },
            {
                enableHighAccuracy: false,
                timeout: 12000,
                maximumAge: 10 * 60 * 1000
            }
        );
    });
}

function isGeolocationAllowedContext() {
    if (window.isSecureContext) return true;
    const hostname = window.location?.hostname || '';
    return ['localhost', '127.0.0.1', '::1'].includes(hostname);
}

function readStoredWeatherPosition() {
    try {
        const raw = localStorage.getItem(WEATHER_POSITION_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        const latitude = Number(parsed?.latitude);
        const longitude = Number(parsed?.longitude);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
        return { latitude, longitude };
    } catch (error) {
        return null;
    }
}

function writeStoredWeatherPosition(position) {
    const latitude = Number(position?.latitude);
    const longitude = Number(position?.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    try {
        localStorage.setItem(
            WEATHER_POSITION_KEY,
            JSON.stringify({
                latitude,
                longitude,
                updatedAt: Date.now()
            })
        );
    } catch (error) {
        void error;
    }
}

function notifyWeatherLocationFailure(error, fallbackLabel = DEFAULT_WEATHER_LOCATION_LABEL) {
    if (state.weatherLocationFailureNotified) return;
    const fallback = String(fallbackLabel || '').trim() || DEFAULT_WEATHER_LOCATION_LABEL;
    const message = `현재 위치를 불러오지 못했습니다. ${fallback} 날씨를 표시합니다.`;
    void error;
    showToast(message, { tone: 'error', durationMs: WEATHER_LOCATION_FAILURE_TOAST_MS });
    state.weatherLocationFailureNotified = true;
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

async function fetchLocationName(latitude, longitude) {
    const url = new URL('https://geocoding-api.open-meteo.com/v1/reverse');
    url.searchParams.set('latitude', String(latitude));
    url.searchParams.set('longitude', String(longitude));
    url.searchParams.set('count', '1');
    url.searchParams.set('language', 'ko');

    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`위치 정보를 확인하지 못했습니다. (${response.status})`);
    }
    const payload = await response.json();
    const first = Array.isArray(payload?.results) ? payload.results[0] : null;
    if (!first) return '';

    const city = first.city || first.town || first.village || first.name || '';
    const region = first.admin1 || first.country_code || '';
    return [city, region].filter(Boolean).join(', ');
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

    setTextWithTooltip(locationElement, locationName || '알 수 없는 위치');
    setTextWithTooltip(
        currentElement,
        `현재 ${currentTemp} · ${weatherText} · 체감 ${feelsLike} · 습도 ${humidity} · 바람 ${wind}`
    );
    setTextWithTooltip(todayElement, renderDailyForecast(weather?.daily, 0));
    setTextWithTooltip(tomorrowElement, renderDailyForecast(weather?.daily, 1));
}

function renderWeatherError(locationText, detailText) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;
    setTextWithTooltip(locationElement, locationText);
    setTextWithTooltip(currentElement, detailText);
    setTextWithTooltip(todayElement, '--');
    setTextWithTooltip(tomorrowElement, '--');
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

function setChatFullscreen(enabled) {
    const app = document.querySelector('.app');
    const button = document.getElementById('codex-chat-fullscreen');
    if (!app || !button) return;
    const isEnabled = Boolean(enabled);
    app.classList.toggle(CHAT_FULLSCREEN_CLASS, isEnabled);
    updateChatFullscreenButton(button, isEnabled);
}

function syncSessionsLayout(isMobile) {
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    if (!sessionsPanel || !sessionsToggle) return;
    if (!isMobile) {
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

function isMobileLayout() {
    return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

function isEditableElement(element) {
    if (!element || typeof element.tagName !== 'string') return false;
    const tag = element.tagName.toLowerCase();
    if (tag === 'textarea' || tag === 'select') return true;
    if (tag !== 'input') return false;
    const type = (element.getAttribute('type') || 'text').toLowerCase();
    return !['button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit'].includes(type);
}

function isMobileKeyboardOpen(isMobile = isMobileLayout()) {
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
    return hasEditableFocus;
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

function syncMobileKeyboardState(isMobile = isMobileLayout()) {
    setMobileKeyboardOpen(isMobileKeyboardOpen(isMobile));
}

function applyMobileViewportHeight(isMobile = isMobileLayout()) {
    const root = document.documentElement;
    if (!root) return;
    if (!isMobile) {
        root.style.removeProperty(MOBILE_VIEWPORT_HEIGHT_VAR);
        return;
    }
    const visualHeight = Number(window.visualViewport?.height);
    const fallbackHeight = Number(window.innerHeight);
    const nextHeight = Number.isFinite(visualHeight) && visualHeight > 0
        ? visualHeight
        : fallbackHeight;
    if (!Number.isFinite(nextHeight) || nextHeight <= 0) return;
    const clamped = Math.max(320, Math.round(nextHeight));
    root.style.setProperty(MOBILE_VIEWPORT_HEIGHT_VAR, `${clamped}px`);
}

function normalizeMobileDocumentScroll(isMobile = isMobileLayout()) {
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
    applyMobileViewportHeight(mobileMedia.matches);
    syncMobileKeyboardState(mobileMedia.matches);
    normalizeMobileDocumentScroll(mobileMedia.matches);

    const handleViewportChange = () => {
        applyMobileViewportHeight(mobileMedia.matches);
        syncMobileKeyboardState(mobileMedia.matches);
        normalizeMobileDocumentScroll(mobileMedia.matches);
    };

    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', handleViewportChange);
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(handleViewportChange);
    }

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', handleViewportChange);
        window.visualViewport.addEventListener('scroll', handleViewportChange);
    }
    window.addEventListener('resize', handleViewportChange);

    if (!input) return;
    input.addEventListener('focus', () => {
        if (!mobileMedia.matches) return;
        syncMobileKeyboardState(true);
        normalizeMobileDocumentScroll(true);
        window.setTimeout(handleViewportChange, 80);
    });
    input.addEventListener('blur', () => {
        if (!mobileMedia.matches) return;
        normalizeMobileDocumentScroll(true);
        window.setTimeout(handleViewportChange, 120);
    });
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
        applyMobileViewportHeight(true);
        keepFieldVisible(focusedField, behavior);
    };

    const scheduleFocusedFieldVisibility = () => {
        if (!mobileMedia.matches) return;
        window.requestAnimationFrame(() => {
            keepFocusedFieldVisible('auto');
        });
        window.setTimeout(() => {
            keepFocusedFieldVisible('auto');
        }, 120);
        window.setTimeout(() => {
            keepFocusedFieldVisible('auto');
        }, 280);
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
    };

    const handleMobileViewportChange = () => {
        if (!mobileMedia.matches) {
            setMobileKeyboardOpen(false);
            return;
        }
        syncMobileKeyboardState(true);
        scheduleFocusedFieldVisibility();
    };

    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', handleLayoutModeChange);
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(handleLayoutModeChange);
    }
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', handleMobileViewportChange);
        window.visualViewport.addEventListener('scroll', handleMobileViewportChange);
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
                applyMobileViewportHeight(true);
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
    if (toggle) toggle.checked = normalized === 'dark';
    if (persist) {
        try {
            localStorage.setItem(THEME_KEY, normalized);
        } catch (error) {
            void error;
        }
    }
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
    try {
        const existing = getPersistedStreams().filter(item => item.id !== stream.id);
        existing.push({
            id: stream.id,
            sessionId: stream.sessionId,
            startedAt: stream.startedAt || Date.now()
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
        elements.outputStatus.textContent = streamMonitorState.done ? 'Completed' : 'Streaming...';
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
        const updated = formatStreamTimestamp(stream.updated_at);
        meta.textContent = updated ? `Updated ${updated}` : `Stream ${stream.id.slice(0, 6)}`;

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
        renderSessions();
        syncActiveSessionControls();
        syncRemoteActiveSessionStatus();
    }
}

function syncRemoteActiveSessionStatus() {
    const sessionId = state.activeSessionId;
    if (!sessionId) return;
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    const hasRemote = state.remoteStreamSessions?.has(sessionId);
    const hasLocal = Boolean(sessionState.sending || sessionState.pendingSend || getSessionStream(sessionId));
    if (hasRemote && !hasLocal) {
        if (sessionState.status !== 'Receiving response (remote)...') {
            setSessionStatus(sessionId, 'Receiving response (remote)...');
        }
        return;
    }
    if (!hasRemote && sessionState.status === 'Receiving response (remote)...') {
        setSessionStatus(sessionId, 'Idle');
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
        output: '',
        error: '',
        done: false,
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
            `/api/codex/streams/${current.id}?offset=${current.outputOffset}&error_offset=${current.errorOffset}`
        );
        if (!streamMonitorState || streamMonitorState.id !== current.id) return;
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
        if (result?.output || result?.error) {
            renderStreamMonitorOutput();
        }
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
    if (state.loading) return;
    state.loading = true;
    setStatus('Loading sessions...');
    try {
        const response = await fetch('/api/codex/sessions');
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to load sessions.');
        }
        state.sessions = Array.isArray(result?.sessions) ? result.sessions : [];
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
        syncActiveSessionControls();
        syncActiveSessionStatus();
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to load sessions.'), true);
    } finally {
        state.loading = false;
    }
}

async function loadSettings({ silent = true } = {}) {
    const refreshBtn = document.getElementById('codex-controls-refresh');
    if (refreshBtn) refreshBtn.classList.add('is-loading');
    try {
        const result = await fetchJson('/api/codex/settings');
        state.settings = {
            model: result?.settings?.model || null,
            modelOptions: Array.isArray(result?.model_options) ? result.model_options : [],
            reasoningEffort: result?.settings?.reasoning_effort || null,
            reasoningOptions: Array.isArray(result?.reasoning_options)
                ? result.reasoning_options
                : [],
            usage: result?.usage || null,
            loaded: true
        };
        updateUsageSummary(state.settings.usage);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        setSettingsStatus(state.settings.model, state.settings.reasoningEffort);
    } catch (error) {
        updateUsageSummary(null);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        setSettingsStatus(null, null, normalizeError(error, 'Failed to load settings.'));
        if (!silent) {
            setStatus(normalizeError(error, 'Failed to load settings.'), true);
        }
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('is-loading');
    }
}

async function refreshUsageSummary({ silent = true } = {}) {
    try {
        const result = await fetchJson('/api/codex/usage', { cache: 'no-store' });
        const usage = result?.usage ?? null;
        state.settings.usage = usage;
        updateUsageSummary(usage);
    } catch (error) {
        const message = normalizeError(error, '사용량 갱신에 실패했습니다.');
        setStatus(message, true);
    }
}

function updateUsageSummary(usage) {
    const element = document.getElementById('codex-usage-summary');
    if (!element) return;
    const accountName = typeof usage?.account_name === 'string' ? usage.account_name.trim() : '';
    element.innerHTML = '';
    if (accountName) {
        element.appendChild(buildUsageAccount(accountName));
    }
    const hasUsage = Boolean(usage && (usage.five_hour || usage.weekly));
    if (!hasUsage) {
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
    const hasOptions = Array.isArray(options) && options.length > 0;
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select model';
            select.appendChild(placeholder);
            options.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (model) {
                select.value = options.includes(model) ? model : '';
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

function updateReasoningControls(reasoning, options) {
    const select = document.getElementById('codex-reasoning-select');
    const input = document.getElementById('codex-reasoning-input');
    const field = select ? select.closest('.model-field') : null;
    const hasOptions = Array.isArray(options) && options.length > 0;
    if (select) {
        select.innerHTML = '';
        if (hasOptions) {
            select.classList.remove('is-hidden');
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select effort';
            select.appendChild(placeholder);
            options.forEach(item => {
                const option = document.createElement('option');
                option.value = item;
                option.textContent = item;
                select.appendChild(option);
            });
            if (reasoning) {
                select.value = options.includes(reasoning) ? reasoning : '';
            } else {
                select.value = '';
            }
        } else {
            select.classList.add('is-hidden');
        }
    }
    if (input) {
        input.value = reasoning || '';
        input.placeholder = reasoning ? reasoning : 'Default effort';
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
        if (summary) summary.textContent = overrideText;
        return;
    }
    if (!state.settings.loaded && !model && !reasoning) {
        status.textContent = 'Refresh to load';
        if (summary) summary.textContent = 'Refresh to load';
        return;
    }
    const modelText = model ? model : 'default';
    const reasoningText = reasoning ? reasoning : 'default';
    const text = `Model: ${modelText} · Reasoning: ${reasoningText}`;
    status.textContent = text;
    if (summary) summary.textContent = text;
}

async function updateSettings() {
    const input = document.getElementById('codex-model-input');
    const status = document.getElementById('codex-model-status');
    const refreshBtn = document.getElementById('codex-controls-refresh');
    const modelSelect = document.getElementById('codex-model-select');
    const reasoningInput = document.getElementById('codex-reasoning-input');
    const reasoningSelect = document.getElementById('codex-reasoning-select');
    const model = modelSelect && !modelSelect.classList.contains('is-hidden')
        ? modelSelect.value.trim()
        : (input ? input.value.trim() : '');
    const reasoning_effort = reasoningSelect && !reasoningSelect.classList.contains('is-hidden')
        ? reasoningSelect.value.trim()
        : (reasoningInput ? reasoningInput.value.trim() : '');
    if (status) status.textContent = 'Saving...';
    if (refreshBtn) refreshBtn.classList.add('is-loading');
    try {
        const result = await fetchJson('/api/codex/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model, reasoning_effort })
        });
        state.settings.model = result?.settings?.model || null;
        state.settings.reasoningEffort = result?.settings?.reasoning_effort || null;
        state.settings.modelOptions = Array.isArray(result?.model_options)
            ? result.model_options
            : state.settings.modelOptions;
        state.settings.reasoningOptions = Array.isArray(result?.reasoning_options)
            ? result.reasoning_options
            : state.settings.reasoningOptions;
        state.settings.usage = result?.usage || state.settings.usage;
        state.settings.loaded = true;
        updateUsageSummary(state.settings.usage);
        updateModelControls(state.settings.model, state.settings.modelOptions);
        updateReasoningControls(state.settings.reasoningEffort, state.settings.reasoningOptions);
        setSettingsStatus(state.settings.model, state.settings.reasoningEffort);
        if (status) status.textContent = 'Saved';
    } catch (error) {
        if (status) status.textContent = normalizeError(error, 'Failed to update settings.');
    } finally {
        if (refreshBtn) refreshBtn.classList.remove('is-loading');
    }
}

async function fetchJson(url, options) {
    const response = await fetch(url, options);
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

function applyGitBranchStatusToElement(element, status) {
    if (!element || !status) return;
    const branchName = typeof status.branch === 'string' ? status.branch.trim() : '';
    if (!branchName) return;
    if (element.textContent.trim() !== branchName) {
        element.textContent = branchName;
    }
    element.dataset.branchFull = branchName;
    element.setAttribute('title', branchName);
}

function getGitBranchOverlayElements() {
    const overlay = document.getElementById('codex-branch-overlay');
    if (!overlay) return null;
    return {
        overlay,
        subtitle: document.getElementById('codex-branch-overlay-subtitle'),
        meta: document.getElementById('codex-branch-overlay-meta'),
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
}

function normalizeGitChangedFiles(files) {
    if (!Array.isArray(files)) return [];
    return files.map(file => {
        if (!file) return null;
        if (typeof file === 'string') {
            const path = file.trim();
            return path ? { path, status: '' } : null;
        }
        const path = typeof file.path === 'string' ? file.path.trim() : '';
        if (!path) return null;
        const status = typeof file.status === 'string' ? file.status.trim() : '';
        return { path, status };
    }).filter(Boolean);
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

function renderGitBranchOverlay(status) {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    const branchElement = document.getElementById('codex-git-branch');
    const branchName = (status?.branch || getGitBranchFullName(branchElement) || '').trim();
    if (elements.subtitle) {
        elements.subtitle.textContent = branchName ? `브랜치: ${branchName}` : '브랜치 정보를 불러오는 중...';
    }
    const files = normalizeGitChangedFiles(status?.changedFiles);
    const count = Number.isFinite(status?.count) ? status.count : files.length;
    if (elements.meta) {
        elements.meta.textContent = Number.isFinite(count)
            ? `변경 파일 ${count}개`
            : '변경 파일 수를 불러올 수 없습니다.';
    }
    if (elements.list) {
        elements.list.innerHTML = '';
        files.forEach(file => {
            const item = document.createElement('li');
            if (file.status) {
                const badge = document.createElement('span');
                badge.className = `branch-overlay-status ${getGitStatusBadgeClass(file.status)}`.trim();
                badge.textContent = file.status.toUpperCase();
                item.appendChild(badge);
            }
            const path = document.createElement('span');
            path.className = 'branch-overlay-file-path';
            path.textContent = file.path;
            item.appendChild(path);
            elements.list.appendChild(item);
        });
        elements.list.classList.toggle('is-hidden', files.length === 0);
    }
    if (elements.empty) {
        elements.empty.textContent = Number.isFinite(count)
            ? '변경 파일이 없습니다.'
            : '변경 파일 정보를 불러올 수 없습니다.';
        elements.empty.classList.toggle('is-hidden', files.length !== 0);
    }
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
    elements.overlay.classList.add('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-overlay-open');
    setGitBranchOverlayLoading(true);
    void refreshGitBranchStatus({ force: true, updateOverlay: true });
}

function closeGitBranchOverlay() {
    const elements = getGitBranchOverlayElements();
    if (!elements) return;
    elements.overlay.classList.remove('is-visible');
    elements.overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-overlay-open');
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
        const result = await fetchJson('/api/codex/git/status', { method: 'POST' });
        const count = Number.isFinite(result?.changed_files_count)
            ? result.changed_files_count
            : null;
        const branch = typeof result?.branch === 'string' ? result.branch : '';
        const detailedFiles = Array.isArray(result?.changed_files_detail) ? result.changed_files_detail : [];
        const changedFiles = detailedFiles.length
            ? detailedFiles
            : (Array.isArray(result?.changed_files) ? result.changed_files : []);
        gitBranchStatusCache = {
            count,
            branch,
            changedFiles,
            fetchedAt: Date.now()
        };
        return gitBranchStatusCache;
    } catch (error) {
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
    const status = await fetchGitStatus(force);
    const branchElement = document.getElementById('codex-git-branch');
    if (branchElement) {
        applyGitBranchStatusToElement(branchElement, status);
    }
    if (updateOverlay && isGitBranchOverlayOpen()) {
        renderGitBranchOverlay(status);
    }
    return status;
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

async function handleGitAction(action, button) {
    const label = GIT_ACTION_LABELS[action] || `git ${action}`;
    const busyLabel = action === 'submit' ? 'Committing...' : 'Syncing...';
    setGitButtonBusy(button, true, busyLabel);
    try {
        let result = null;
        try {
            result = await fetchJson(`/api/codex/git/${action}`, { method: 'POST' });
        } catch (error) {
            const message = normalizeError(error, '');
            if (message.toLowerCase().includes('method not allowed')) {
                const ts = Date.now();
                result = await fetchJson(`/api/codex/git/${action}?confirm=1&ts=${ts}`, {
                    method: 'GET',
                    cache: 'no-store'
                });
            } else {
                throw error;
            }
        }
        const summary = summarizeGitOutput(result?.stdout || result?.stderr);
        const suffix = summary ? `: ${summary}` : '';
        showToast(`${label} 완료${suffix}`, { tone: 'success', durationMs: 3200 });
    } catch (error) {
        const message = normalizeError(error, `${label} 작업에 실패했습니다.`);
        showToast(`${label} 실패: ${message}`, { tone: 'error', durationMs: 5200 });
    } finally {
        setGitButtonBusy(button, false);
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

            let assistantEntry = null;
            if (pending.sessionId === state.activeSessionId) {
                assistantEntry = appendMessageToDOM({
                    role: 'assistant',
                    content: '',
                    created_at: new Date().toISOString()
                }, 'assistant');
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
                entry: assistantEntry,
                startedAt: Number.isFinite(pending.startedAt) ? pending.startedAt : Date.now()
            });
            if (!stream) {
                clearPersistedStream(pending.id);
                if (sessionState) {
                    sessionState.sending = false;
                }
                continue;
            }
            if (assistantEntry) {
                updateStreamEntry(stream);
            }
            beginStreamPolling(stream.id);
            setSessionStatus(pending.sessionId, 'Receiving response...');
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

function renderSessions() {
    const list = document.getElementById('codex-session-list');
    if (!list) return;
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
        const count = Number.isFinite(session.message_count) ? session.message_count : 0;
        const metaText = document.createElement('span');
        metaText.textContent = updated ? `Updated ${updated} - ${count} msgs` : `Messages ${count}`;
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
            await loadSession(session.id);
        });

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

        item.appendChild(selectBtn);
        item.appendChild(actions);
        list.appendChild(item);
    });
}

function upsertSessionSummary(session) {
    if (!session || !session.id) return;
    const summary = {
        id: session.id,
        title: session.title || 'New session',
        created_at: session.created_at,
        updated_at: session.updated_at,
        message_count: Array.isArray(session.messages) ? session.messages.length : 0
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
}

async function createSession(selectAfter = true) {
    setStatus('Creating session...');
    try {
        const response = await fetch('/api/codex/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to create session.');
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
        const response = await fetch(`/api/codex/sessions/${sessionId}`);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to load session.');
        }
        const session = result?.session;
        const previousSessionId = state.activeSessionId;
        state.activeSessionId = session?.id || sessionId;
        ensureSessionState(state.activeSessionId);
        if (previousSessionId && previousSessionId !== state.activeSessionId) {
            detachSessionStreamEntry(previousSessionId);
        }
        renderSessions();
        renderMessages(session?.messages || []);
        attachSessionStreamEntry(state.activeSessionId);
        updateHeader(session || null);
        syncActiveSessionControls();
        syncActiveSessionStatus();
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

        const label = getRoleLabel(message?.role);
        const timestamp = formatTimestamp(message?.created_at);
        const metaText = timestamp ? `${label} - ${timestamp}` : label;
        const meta = buildMessageMeta(metaText, wrapper);

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        setMarkdownContent(bubble, message?.content || '');

        const footer = createMessageFooter();
        const durationMs = Number(message?.duration_ms);
        if (Number.isFinite(durationMs)) {
            setMessageDuration(footer, durationMs);
        }

        wrapper.appendChild(meta);
        wrapper.appendChild(bubble);
        wrapper.appendChild(footer);
        container.appendChild(wrapper);
    });

    scrollToBottom(true);
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

    const label = getRoleLabel(role);
    const timestamp = formatTimestamp(message?.created_at);
    const metaText = timestamp ? `${label} - ${timestamp}` : label;
    const meta = buildMessageMeta(metaText, wrapper);

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    setMarkdownContent(bubble, message?.content || '');

    const footer = createMessageFooter();
    const durationMs = Number(message?.duration_ms);
    if (Number.isFinite(durationMs)) {
        setMessageDuration(footer, durationMs);
    }

    wrapper.appendChild(meta);
    wrapper.appendChild(bubble);
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
        meta.textContent = '';
        return;
    }
    title.textContent = session.title || 'New session';
    const updated = formatTimestamp(session.updated_at);
    meta.textContent = updated ? `Updated ${updated}` : '';
}

async function handleSubmit(event) {
    if (event) event.preventDefault();
    const activeSessionId = state.activeSessionId;
    if (activeSessionId && isSessionBusy(activeSessionId)) {
        if (getSessionStream(activeSessionId)) {
            await stopStream(activeSessionId);
            return;
        }
        if (cancelPendingSend(activeSessionId)) {
            return;
        }
        const sessionState = getSessionState(activeSessionId);
        if (sessionState) {
            sessionState.sending = false;
        }
        syncActiveSessionControls();
    }
    const input = document.getElementById('codex-chat-input');
    if (!input) return;
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = '';
    await sendPrompt(prompt);
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
    return true;
}

async function sendPrompt(prompt) {
    let sessionId = state.activeSessionId;
    if (!sessionId) {
        const session = await createSession(true);
        sessionId = session?.id;
    }

    if (!sessionId) {
        setStatus('Failed to create a session.', true);
        return;
    }

    const sessionState = ensureSessionState(sessionId);
    if (sessionState?.sending) {
        setSessionStatus(sessionId, 'Session is already sending.', true);
        return;
    }
    pinAutoScrollForSession(sessionId);
    scrollToBottom(true);
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
            body: JSON.stringify({ prompt }),
            signal: controller.signal
        });
        clearPendingSend(sessionId, controller);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to send message.');
        }
        const userMessage = result?.user_message;
        if (userMessage) {
            appendMessageToDOMIfActive(sessionId, userMessage, 'user');
        } else {
            appendMessageToDOMIfActive(sessionId, {
                role: 'user',
                content: prompt,
                created_at: new Date().toISOString()
            }, 'user');
        }

        const assistantEntry = appendMessageToDOMIfActive(sessionId, {
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString()
        }, 'assistant');

        const streamId = result?.stream_id;
        if (!streamId) {
            throw new Error('Failed to start stream.');
        }
        if (assistantEntry) {
            setMessageStreaming(assistantEntry.wrapper, true);
        }
        startStream(streamId, sessionId, assistantEntry, startedAt);
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
            return;
        }
        if (sessionState) {
            sessionState.sending = false;
        }
        unpinAutoScrollForSession(sessionId);
        setSessionStatus(sessionId, normalizeError(error, 'Failed to send message.'), true);
        if (sessionId === state.activeSessionId) {
            syncActiveSessionControls();
        }
    }
}

function startStream(streamId, sessionId, assistantEntry, startedAt) {
    const stream = createStreamState({
        id: streamId,
        sessionId,
        entry: assistantEntry,
        outputOffset: 0,
        errorOffset: 0,
        output: '',
        error: '',
        startedAt: startedAt || Date.now()
    });
    if (!stream) return;
    persistActiveStream(stream);
    beginStreamPolling(stream.id);
    setSessionStatus(sessionId, 'Receiving response...');
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }
}

function beginStreamPolling(streamId) {
    const stream = state.streams[streamId];
    if (!stream) return;
    stream.failureCount = 0;
    stream.pollDelay = STREAM_POLL_BASE_MS;
    renderSessions();
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
        const durationMs = getStreamDuration(stream);
        setMessageDuration(stream.entry?.footer, durationMs);
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
    } catch (error) {
        setSessionStatus(sessionId, normalizeError(error, 'Failed to stop stream.'), true);
    }
}

async function pollStream(streamId) {
    const stream = state.streams[streamId];
    if (!stream || stream.polling) return;
    stream.polling = true;

    try {
        const result = await fetchJson(`/api/codex/streams/${stream.id}?offset=${stream.outputOffset}&error_offset=${stream.errorOffset}`);
        const current = state.streams[streamId];
        if (!current) {
            return;
        }

        current.failureCount = 0;
        current.pollDelay = STREAM_POLL_BASE_MS;

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

        if (result?.output || result?.error) {
            updateStreamEntry(current);
            setSessionStatus(current.sessionId, 'Receiving response...');
        }

        if (result?.done) {
            await finishStream(streamId, result);
            return;
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
    setMarkdownContent(bubble, combined);
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
        setMarkdownContent(bubble, savedMessage.content);
    }
    if (savedMessage && wrapper) {
        wrapper.classList.remove('assistant', 'error');
        wrapper.classList.add(savedMessage.role === 'error' ? 'error' : 'assistant');
    }
    const savedDurationMs = Number(savedMessage?.duration_ms);
    if (Number.isFinite(savedDurationMs)) {
        setMessageDuration(stream.entry?.footer, savedDurationMs);
    }
    if (exitCode !== 0) {
        if (wrapper) {
            wrapper.classList.remove('assistant');
            wrapper.classList.add('error');
        }
        const errorText = stream.error || stream.output || 'Codex execution failed.';
        if (bubble) setMarkdownContent(bubble, errorText);
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
}

async function renameSession(session) {
    if (!session?.id) return;
    if (isSessionBusy(session.id)) {
        setStatus('Cannot rename a session while it is running.', true);
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
        const response = await fetch(`/api/codex/sessions/${session.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: trimmed })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to rename session.');
        }
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
        setStatus('Cannot delete a session while it is running.', true);
        return;
    }
    const confirmed = window.confirm('Delete this session? This will remove all messages.');
    if (!confirmed) return;
    setStatus('Deleting session...');
    try {
        const response = await fetch(`/api/codex/sessions/${sessionId}`, { method: 'DELETE' });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to delete session.');
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

function getRoleLabel(role) {
    if (role === 'user') return 'You';
    if (role === 'assistant') return 'Codex';
    if (role === 'system') return 'System';
    if (role === 'error') return 'Error';
    return 'Message';
}

function scrollToBottom(force = false) {
    const container = document.getElementById('codex-chat-messages');
    if (!container) return;
    const forceByPinnedSession = shouldForceAutoScroll();
    if (!force && !state.autoScrollEnabled && !forceByPinnedSession) return;
    if (force || forceByPinnedSession) {
        setAutoScrollEnabled(true);
    }
    const scroll = () => {
        container.scrollTop = container.scrollHeight;
    };
    if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(scroll);
    } else {
        scroll();
    }
}

function handleMessageScroll(container) {
    if (!container) return;
    if (shouldForceAutoScroll()) {
        setAutoScrollEnabled(true);
        return;
    }
    const threshold = Number.isFinite(state.autoScrollThreshold) ? state.autoScrollThreshold : 0;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    setAutoScrollEnabled(distanceFromBottom <= threshold);
}

function setAutoScrollEnabled(isEnabled) {
    state.autoScrollEnabled = Boolean(isEnabled);
}

function pinAutoScrollForSession(sessionId) {
    if (!sessionId) return;
    state.autoScrollPinnedSessionId = sessionId;
    setAutoScrollEnabled(true);
}

function unpinAutoScrollForSession(sessionId = null) {
    if (!state.autoScrollPinnedSessionId) return;
    if (sessionId && state.autoScrollPinnedSessionId !== sessionId) return;
    state.autoScrollPinnedSessionId = null;
}

function shouldForceAutoScroll() {
    const pinnedSessionId = state.autoScrollPinnedSessionId;
    if (!pinnedSessionId) return false;
    if (pinnedSessionId !== state.activeSessionId) return false;
    return isSessionBusy(pinnedSessionId);
}

function setMarkdownContent(element, content) {
    if (!element) return;
    const messageContent = String(content || '');
    const wasExpanded = Boolean(element.querySelector('details.message-details')?.open);
    element.innerHTML = renderMessageContent(messageContent, wasExpanded);
    element.dataset.messageContent = messageContent;
    const wrapper = element.closest('.message');
    if (wrapper) {
        wrapper.dataset.messageContent = messageContent;
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

function createMessageFooter() {
    const footer = document.createElement('div');
    footer.className = 'message-footer';
    return footer;
}

function setMessageDuration(footer, durationMs) {
    if (!footer) return;
    const formatted = formatDuration(durationMs);
    if (!formatted) {
        footer.textContent = '';
        footer.classList.remove('is-visible');
        return;
    }
    footer.textContent = `총 걸린시간 ${formatted}`;
    footer.classList.add('is-visible');
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

function formatRemainingPercent(usedPercent) {
    if (!Number.isFinite(usedPercent)) return '--';
    const remaining = 100 - usedPercent;
    return Math.max(0, Math.min(100, Math.round(remaining)));
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
    if (!entry || !Number.isFinite(entry.used_percent)) {
        return {
            label,
            remainingText: '--',
            resetText
        };
    }
    const remaining = formatRemainingPercent(entry.used_percent);
    return {
        label,
        remainingText: `${remaining}% left`,
        resetText
    };
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

function setMessageStreaming(wrapper, isStreaming) {
    if (!wrapper) return;
    wrapper.classList.toggle('is-streaming', Boolean(isStreaming));
}

function getStreamDuration(stream) {
    if (!stream?.startedAt) return null;
    return Math.max(0, Date.now() - stream.startedAt);
}

function renderMessageContent(content, expanded = false) {
    const text = String(content || '');
    if (!shouldCollapseMessage(text)) {
        return renderMarkdown(text);
    }
    const previewText = buildMessagePreview(text);
    const openAttr = expanded ? ' open' : '';
    const summaryText = expanded ? 'Hide full message' : 'Show full message';
    return [
        `<div class="message-preview">${renderMarkdown(previewText)}</div>`,
        `<details class="message-details"${openAttr}>`,
        `<summary>${summaryText}</summary>`,
        `<div class="message-full">${renderMarkdown(text)}</div>`,
        `</details>`
    ].join('');
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

function renderMarkdown(text) {
    const safe = escapeHtml(String(text || ''));
    const blocks = safe.split(/```/);
    return blocks.map((block, index) => {
        if (index % 2 === 1) {
            const trimmed = block.replace(/^\n+|\n+$/g, '');
            return `<pre><code>${trimmed}</code></pre>`;
        }
        return renderInlineMarkdown(block);
    }).join('');
}

function renderInlineMarkdown(text) {
    let html = text;
    html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/\n/g, '<br>');
    return html;
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
