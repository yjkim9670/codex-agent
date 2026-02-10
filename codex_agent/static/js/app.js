const state = {
    sessions: [],
    activeSessionId: null,
    loading: false,
    sessionStates: {},
    streams: {},
    liveClockTimer: null,
    weatherRefreshTimer: null,
    weatherLocationFailureNotified: false,
    autoScrollEnabled: true,
    autoScrollPinnedSessionId: null,
    autoScrollThreshold: 48,
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
const THEME_KEY = 'codexTheme';
const THEME_MEDIA_QUERY = '(prefers-color-scheme: dark)';
const STREAM_POLL_BASE_MS = 800;
const STREAM_POLL_MAX_MS = 5000;
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

let hasManualTheme = false;

function ensureSessionState(sessionId) {
    if (!sessionId) return null;
    if (!state.sessionStates[sessionId]) {
        state.sessionStates[sessionId] = {
            sending: false,
            pendingSend: null,
            streamId: null,
            status: 'Idle',
            statusIsError: false
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
    return Boolean(getSessionStream(sessionId));
}

function isSessionBusy(sessionId) {
    const sessionState = getSessionState(sessionId);
    if (!sessionState) return false;
    const stream = getSessionStream(sessionId);
    return Boolean(sessionState.sending || sessionState.pendingSend || stream);
}

function setSessionStatus(sessionId, message, isError = false) {
    const sessionState = ensureSessionState(sessionId);
    if (!sessionState) return;
    sessionState.status = message;
    sessionState.statusIsError = isError;
    if (sessionId === state.activeSessionId) {
        setStatus(message, isError);
    }
}

function syncActiveSessionStatus() {
    const sessionId = state.activeSessionId;
    const sessionState = getSessionState(sessionId);
    if (!sessionState) {
        setStatus('Idle');
        return;
    }
    setStatus(sessionState.status || 'Idle', Boolean(sessionState.statusIsError));
}

function syncActiveSessionControls() {
    const input = document.getElementById('codex-chat-input');
    const sendBtn = document.getElementById('codex-chat-send');
    const sessionId = state.activeSessionId;
    const isBusy = sessionId ? isSessionBusy(sessionId) : false;
    const showStop = sessionId ? isBusy : false;
    if (input) {
        input.disabled = isBusy;
        input.readOnly = isBusy;
        input.setAttribute('aria-disabled', String(isBusy));
        input.placeholder = isBusy
            ? 'Response in progress for this session...'
            : CHAT_INPUT_DEFAULT_PLACEHOLDER;
    }
    if (sendBtn) {
        sendBtn.disabled = false;
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
    const messages = document.getElementById('codex-chat-messages');
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
    const controlsRefresh = document.getElementById('codex-controls-refresh');

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

    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            await loadSessions({ preserveActive: true });
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

    if (controlsRefresh) {
        controlsRefresh.addEventListener('click', () => {
            void loadSettings({ silent: false });
        });
    }

    primeSettingsOptionsFromDom(modelSelect, reasoningSelect);

    syncSessionsLayout(mobileMedia.matches);
    syncControlsLayout();
    if (typeof mobileMedia.addEventListener === 'function') {
        mobileMedia.addEventListener('change', event => {
            syncSessionsLayout(event.matches);
        });
    } else if (typeof mobileMedia.addListener === 'function') {
        mobileMedia.addListener(event => {
            syncSessionsLayout(event.matches);
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
}

function initializeLiveWeatherPanel(mobileMedia) {
    const panel = document.getElementById('codex-live-weather-panel');
    const toggle = document.getElementById('codex-live-weather-toggle');
    const compactToggle = document.getElementById('codex-live-weather-compact');
    const permissionToggle = document.getElementById('codex-weather-permission');
    if (!panel || !toggle || !compactToggle || !permissionToggle) return;

    const defaultCompact = Boolean(mobileMedia?.matches);
    const initialCompact = readLiveWeatherCompactPreference(defaultCompact);
    setLiveWeatherCompact(initialCompact, { persist: false });
    setLiveWeatherExpanded(false);
    updateLiveDatetime();
    if (state.liveClockTimer) {
        window.clearInterval(state.liveClockTimer);
    }
    state.liveClockTimer = window.setInterval(updateLiveDatetime, 1000);
    toggle.addEventListener('click', () => {
        if (panel.classList.contains('is-compact')) {
            setLiveWeatherCompact(false);
            void maybeRequestWeatherPermissionOnTap();
            return;
        }
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        setLiveWeatherExpanded(!expanded);
    });
    permissionToggle.addEventListener('click', event => {
        event.stopPropagation();
        void requestWeatherPermission();
    });
    compactToggle.addEventListener('click', () => {
        const isCompact = panel.classList.contains('is-compact');
        setLiveWeatherCompact(!isCompact);
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
    const compactToggle = document.getElementById('codex-live-weather-compact');
    if (!panel || !compactToggle) return;
    const isCompact = Boolean(compact);
    panel.classList.toggle('is-compact', isCompact);
    compactToggle.setAttribute('aria-pressed', String(isCompact));
    compactToggle.textContent = isCompact ? 'Expand' : 'Minimize';
    compactToggle.setAttribute(
        'aria-label',
        isCompact ? 'Expand weather panel' : 'Minimize weather panel'
    );
    if (isCompact) {
        setLiveWeatherExpanded(false);
    }
    if (persist) {
        try {
            localStorage.setItem(WEATHER_COMPACT_KEY, isCompact ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function setLiveWeatherExpanded(expanded) {
    const toggle = document.getElementById('codex-live-weather-toggle');
    const forecast = document.getElementById('codex-live-weather-forecast');
    if (!toggle || !forecast) return;
    const isExpanded = Boolean(expanded);
    toggle.setAttribute('aria-expanded', String(isExpanded));
    forecast.hidden = !isExpanded;
}

function updateLiveDatetime() {
    const datetime = document.getElementById('codex-live-datetime');
    if (!datetime) return;
    datetime.textContent = formatKstNow();
}

function formatKstNow() {
    return new Intl.DateTimeFormat('ko-KR', {
        timeZone: KST_TIME_ZONE,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).format(new Date());
}

async function loadLiveWeatherData({ silent = false, positionOverride = null } = {}) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;

    if (!silent) {
        locationElement.textContent = 'Locating...';
        currentElement.textContent = 'Loading weather...';
        todayElement.textContent = 'Loading...';
        tomorrowElement.textContent = 'Loading...';
    }

    try {
        const position = positionOverride || await resolveWeatherPosition();
        if (!position) {
            renderWeatherError('Location unavailable', 'Allow browser location permission.');
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
            locationName: locationName || defaultLabel || 'Unknown location',
            weather
        });
    } catch (error) {
        renderWeatherError('Weather unavailable', normalizeError(error, 'Failed to load weather.'));
    }
}

async function requestWeatherPermission({ silentFailure = false, skipPermissionCheck = false } = {}) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    if (locationElement) {
        locationElement.textContent = 'Requesting location...';
    }
    if (currentElement) {
        currentElement.textContent = 'Waiting for browser permission...';
    }
    try {
        if (!skipPermissionCheck) {
            const permissionState = await readGeolocationPermissionState();
            if (permissionState === 'denied') {
                notifyWeatherLocationFailure(
                    new Error('Location permission denied.'),
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
            reject(new Error('Location access requires HTTPS or localhost.'));
            return;
        }
        if (!navigator.geolocation) {
            reject(new Error('Geolocation is not supported.'));
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
                reject(error || new Error('Unable to get position.'));
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
    url.searchParams.set('language', 'en');

    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`Failed to resolve location (${response.status}).`);
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
        throw new Error(`Failed to load weather (${response.status}).`);
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

    locationElement.textContent = locationName || 'Unknown location';
    currentElement.textContent = `Now ${currentTemp} · ${weatherText} · Feels ${feelsLike} · Humidity ${humidity} · Wind ${wind}`;
    todayElement.textContent = renderDailyForecast(weather?.daily, 0);
    tomorrowElement.textContent = renderDailyForecast(weather?.daily, 1);
}

function renderWeatherError(locationText, detailText) {
    const locationElement = document.getElementById('codex-weather-location');
    const currentElement = document.getElementById('codex-weather-current');
    const todayElement = document.getElementById('codex-weather-today');
    const tomorrowElement = document.getElementById('codex-weather-tomorrow');
    if (!locationElement || !currentElement || !todayElement || !tomorrowElement) return;
    locationElement.textContent = locationText;
    currentElement.textContent = detailText;
    todayElement.textContent = '--';
    tomorrowElement.textContent = '--';
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
    const highLow = `High ${formatTemperatureValue(maxTemp)} / Low ${formatTemperatureValue(minTemp)}`;
    const rainText = `Rain ${formatPercentValue(rainChance)}`;
    const sunriseText = `Sunrise ${formatKstHourMinute(sunrise)}`;
    const sunsetText = `Sunset ${formatKstHourMinute(sunset)}`;
    return `${weatherText} · ${highLow} · ${rainText} · ${sunriseText} · ${sunsetText}`;
}

function formatWeatherCode(code, isDay) {
    const normalized = Number(code);
    if (!Number.isFinite(normalized)) return 'Unknown';
    if (normalized === 0) return isDay ? 'Clear' : 'Clear night';
    if ([1, 2, 3].includes(normalized)) return 'Cloudy';
    if ([45, 48].includes(normalized)) return 'Fog';
    if ([51, 53, 55, 56, 57].includes(normalized)) return 'Drizzle';
    if ([61, 63, 65, 66, 67, 80, 81, 82].includes(normalized)) return 'Rain';
    if ([71, 73, 75, 77, 85, 86].includes(normalized)) return 'Snow';
    if ([95, 96, 99].includes(normalized)) return 'Thunderstorm';
    return 'Mixed';
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

function setSessionsCollapsed(collapsed, { persist = true } = {}) {
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    if (!sessionsPanel || !sessionsToggle) return;
    sessionsPanel.classList.toggle('is-collapsed', collapsed);
    sessionsToggle.setAttribute('aria-expanded', String(!collapsed));
    sessionsToggle.textContent = collapsed ? 'Show sessions' : 'Hide sessions';
    if (persist) {
        try {
            localStorage.setItem(SESSION_COLLAPSE_KEY, collapsed ? '1' : '0');
        } catch (error) {
            void error;
        }
    }
}

function syncSessionsLayout(isMobile) {
    const sessionsPanel = document.querySelector('.sessions');
    const sessionsToggle = document.getElementById('codex-sessions-toggle');
    if (!sessionsPanel || !sessionsToggle) return;
    if (!isMobile) {
        sessionsPanel.classList.remove('is-collapsed');
        sessionsToggle.setAttribute('aria-expanded', 'true');
        sessionsToggle.textContent = 'Hide sessions';
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

function updateUsageSummary(usage) {
    const element = document.getElementById('codex-usage-summary');
    if (!element) return;
    if (!usage || (!usage.five_hour && !usage.weekly)) {
        element.textContent = state.settings.loaded ? 'Usage unavailable' : 'Refresh to load';
        return;
    }
    element.innerHTML = '';
    const entries = [
        buildUsageEntry(usage.five_hour, '5h'),
        buildUsageEntry(usage.weekly, 'Weekly')
    ].filter(Boolean);
    if (entries.length === 0) {
        element.textContent = state.settings.loaded ? 'Usage unavailable' : 'Refresh to load';
        return;
    }
    entries.forEach(entry => {
        element.appendChild(entry);
    });
}

function updateModelControls(model, options) {
    const select = document.getElementById('codex-model-select');
    const input = document.getElementById('codex-model-input');
    const row = select ? select.closest('.model-row') : null;
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
    if (row) {
        row.classList.toggle('is-select-only', hasOptions);
    }
    setSettingsStatus(model, state.settings.reasoningEffort);
}

function updateReasoningControls(reasoning, options) {
    const select = document.getElementById('codex-reasoning-select');
    const input = document.getElementById('codex-reasoning-input');
    const row = select ? select.closest('.model-row') : null;
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
    if (row) {
        row.classList.toggle('is-select-only', hasOptions);
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
            throw new Error(data?.error || `Request failed (${response.status})`);
        }
        return data;
    }
    const text = await response.text();
    if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
    }
    throw new Error(text || 'Unexpected response format.');
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
                throw new Error(result?.error || 'Failed to resume stream.');
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
        title.textContent = session.title || 'New session';

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
    if (sessionId === state.activeSessionId) {
        syncActiveSessionControls();
    }
    await loadSessions({ preserveActive: true, reloadActive: false });
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
    const status = document.getElementById('codex-chat-status');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('is-error', isError);
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
            <rect x="9" y="9" width="11" height="11" rx="0" fill="none" stroke="currentColor" stroke-width="1.6"></rect>
            <rect x="4" y="4" width="11" height="11" rx="0" fill="none" stroke="currentColor" stroke-width="1.6"></rect>
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
