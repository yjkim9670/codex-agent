const state = {
    sessions: [],
    activeSessionId: null,
    loading: false,
    sending: false,
    stream: null,
    streamTimer: null,
    streamPolling: false,
    streamFailureCount: 0,
    streamPollDelay: 800,
    liveClockTimer: null,
    weatherRefreshTimer: null,
    autoScrollEnabled: true,
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

let hasManualTheme = false;

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

    setBusy(false);
    initializeTheme(themeToggle, themeMedia);
    initializeLiveWeatherPanel();
    void initializeApp();
});

async function initializeApp() {
    if (!state.settings.loaded) {
        void loadSettings({ silent: true });
    }
    const pending = getPersistedStream();
    const targetSessionId = pending?.sessionId || null;
    await loadSessions({ preserveActive: true, selectSessionId: targetSessionId });
    if (pending) {
        await resumeStreamFromStorage(pending);
    }
}

function initializeLiveWeatherPanel() {
    const toggle = document.getElementById('codex-live-weather-toggle');
    if (!toggle) return;
    setLiveWeatherExpanded(false);
    updateLiveDatetime();
    if (state.liveClockTimer) {
        window.clearInterval(state.liveClockTimer);
    }
    state.liveClockTimer = window.setInterval(updateLiveDatetime, 1000);
    toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        setLiveWeatherExpanded(!expanded);
    });
    void loadLiveWeatherData();
    if (state.weatherRefreshTimer) {
        window.clearInterval(state.weatherRefreshTimer);
    }
    state.weatherRefreshTimer = window.setInterval(() => {
        void loadLiveWeatherData({ silent: true });
    }, WEATHER_REFRESH_MS);
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

async function loadLiveWeatherData({ silent = false } = {}) {
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
        const position = await resolveWeatherPosition();
        if (!position) {
            renderWeatherError('Location unavailable', 'Allow browser location permission.');
            return;
        }

        const [locationName, weather] = await Promise.all([
            fetchLocationName(position.latitude, position.longitude),
            fetchWeatherForecast(position.latitude, position.longitude)
        ]);

        renderWeatherSummary({
            locationName: locationName || 'Unknown location',
            weather
        });
    } catch (error) {
        renderWeatherError('Weather unavailable', normalizeError(error, 'Failed to load weather.'));
    }
}

async function resolveWeatherPosition() {
    try {
        const current = await getCurrentGeoPosition();
        writeStoredWeatherPosition(current);
        return current;
    } catch (error) {
        const stored = readStoredWeatherPosition();
        if (stored) return stored;
        return null;
    }
}

function getCurrentGeoPosition() {
    return new Promise((resolve, reject) => {
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
    if (!app) return;
    app.classList.toggle(MOBILE_KEYBOARD_OPEN_CLASS, Boolean(open));
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

function setupMobileViewportBehavior(mobileMedia, input) {
    applyMobileViewportHeight(mobileMedia.matches);
    syncMobileKeyboardState(mobileMedia.matches);

    const handleViewportChange = () => {
        applyMobileViewportHeight(mobileMedia.matches);
        syncMobileKeyboardState(mobileMedia.matches);
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
        window.setTimeout(handleViewportChange, 80);
    });
    input.addEventListener('blur', () => {
        if (!mobileMedia.matches) return;
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
    let collapsed = true;
    try {
        const stored = localStorage.getItem(CONTROLS_COLLAPSE_KEY);
        if (stored !== null) {
            collapsed = stored === '1';
        }
    } catch (error) {
        void error;
    }
    setControlsCollapsed(collapsed, { persist: false });
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

function getPersistedStream() {
    try {
        const raw = localStorage.getItem(ACTIVE_STREAM_KEY);
        if (!raw) return null;
        const data = JSON.parse(raw);
        if (!data?.id || !data?.sessionId) return null;
        return data;
    } catch (error) {
        return null;
    }
}

function persistActiveStream(stream) {
    if (!stream?.id || !stream?.sessionId) return;
    try {
        localStorage.setItem(
            ACTIVE_STREAM_KEY,
            JSON.stringify({
                id: stream.id,
                sessionId: stream.sessionId,
                startedAt: stream.startedAt || Date.now()
            })
        );
    } catch (error) {
        void error;
    }
}

function clearPersistedStream() {
    try {
        localStorage.removeItem(ACTIVE_STREAM_KEY);
    } catch (error) {
        void error;
    }
}

async function loadSessions({ preserveActive = true, selectSessionId = null } = {}) {
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

        if (activeId) {
            await loadSession(activeId);
        } else {
            renderMessages([]);
            updateHeader(null);
        }
        setStatus('Idle');
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

async function resumeStreamFromStorage(pending) {
    if (!pending || state.stream || state.sending) return;
    const sessionExists = state.sessions.some(session => session.id === pending.sessionId);
    if (!sessionExists) {
        clearPersistedStream();
        return;
    }
    setStatus('Reconnecting to Codex...');
    setBusy(true);
    state.sending = true;
    try {
        const response = await fetch(`/api/codex/streams/${pending.id}?offset=0&error_offset=0`);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to resume stream.');
        }
        if (result?.done) {
            clearPersistedStream();
            setBusy(false);
            state.sending = false;
            setStatus('Idle');
            await loadSessions({ preserveActive: true, selectSessionId: pending.sessionId });
            return;
        }

        const assistantEntry = appendMessageToDOM({
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString()
        }, 'assistant');
        if (!assistantEntry) {
            clearPersistedStream();
            setBusy(false);
            state.sending = false;
            return;
        }
        setMessageStreaming(assistantEntry.wrapper, true);

        const output = result?.output || '';
        const errorText = result?.error || '';
        const stream = {
            id: pending.id,
            sessionId: pending.sessionId,
            output,
            error: errorText,
            outputOffset: Number.isFinite(result?.output_length)
                ? result.output_length
                : output.length,
            errorOffset: Number.isFinite(result?.error_length)
                ? result.error_length
                : errorText.length,
            entry: assistantEntry,
            startedAt: Number.isFinite(pending.startedAt) ? pending.startedAt : Date.now()
        };
        updateStreamEntry(stream);
        beginStreamPolling(stream);
        setStatus('Receiving response...');
    } catch (error) {
        clearPersistedStream();
        setBusy(false);
        state.sending = false;
        setStatus(normalizeError(error, 'Failed to resume stream.'), true);
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
            if (state.sending) {
                setStatus('Cannot switch sessions while receiving a response.', true);
                return;
            }
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

function isSessionStreaming(sessionId) {
    if (!sessionId) return false;
    return Boolean(state.stream && state.stream.sessionId === sessionId);
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
}

async function createSession(selectAfter = true) {
    setStatus('Creating session...');
    setBusy(true);
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
            renderSessions();
            await loadSession(sessionId);
        } else {
            renderSessions();
        }
        setStatus('Idle');
        return result?.session;
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to create session.'), true);
        return null;
    } finally {
        setBusy(false);
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
        state.activeSessionId = session?.id || sessionId;
        renderSessions();
        renderMessages(session?.messages || []);
        updateHeader(session || null);
        setStatus('Idle');
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
    if (state.sending && state.stream) {
        await stopStream();
        return;
    }
    if (state.sending) return;
    const input = document.getElementById('codex-chat-input');
    if (!input) return;
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = '';
    await sendPrompt(prompt);
}

async function sendPrompt(prompt) {
    setBusy(true);
    state.sending = true;
    setStatus('Waiting for Codex...');

    let sessionId = state.activeSessionId;
    if (!sessionId) {
        const session = await createSession(true);
        sessionId = session?.id;
    }

    if (!sessionId) {
        setStatus('Failed to create a session.', true);
        setBusy(false);
        state.sending = false;
        return;
    }

    const startedAt = Date.now();
    try {
        const response = await fetch(`/api/codex/sessions/${sessionId}/message/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result?.error || 'Failed to send message.');
        }
        const userMessage = result?.user_message;
        if (userMessage) {
            appendMessageToDOM(userMessage, 'user');
        } else {
            appendMessageToDOM({
                role: 'user',
                content: prompt,
                created_at: new Date().toISOString()
            }, 'user');
        }

        const assistantEntry = appendMessageToDOM({
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString()
        }, 'assistant');

        const streamId = result?.stream_id;
        if (!streamId || !assistantEntry) {
            throw new Error('Failed to start stream.');
        }
        setMessageStreaming(assistantEntry.wrapper, true);
        startStream(streamId, sessionId, assistantEntry, startedAt);
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to send message.'), true);
        setBusy(false);
        state.sending = false;
    }
}

function startStream(streamId, sessionId, assistantEntry, startedAt) {
    const stream = {
        id: streamId,
        sessionId,
        outputOffset: 0,
        errorOffset: 0,
        output: '',
        error: '',
        entry: assistantEntry,
        startedAt: startedAt || Date.now()
    };
    persistActiveStream(stream);
    beginStreamPolling(stream);
}

function stopStreamPolling() {
    if (state.streamTimer) {
        clearTimeout(state.streamTimer);
        state.streamTimer = null;
    }
    if (state.stream?.entry?.wrapper) {
        setMessageStreaming(state.stream.entry.wrapper, false);
    }
    state.stream = null;
    state.streamPolling = false;
    state.streamFailureCount = 0;
    state.streamPollDelay = STREAM_POLL_BASE_MS;
    renderSessions();
}

function beginStreamPolling(stream) {
    stopStreamPolling();
    state.stream = stream;
    state.streamFailureCount = 0;
    state.streamPollDelay = STREAM_POLL_BASE_MS;
    renderSessions();
    scheduleStreamPoll(0);
}

function scheduleStreamPoll(delay) {
    if (state.streamTimer) {
        clearTimeout(state.streamTimer);
    }
    state.streamTimer = setTimeout(() => {
        pollStream();
    }, delay);
}

async function stopStream() {
    const stream = state.stream;
    if (!stream) return;
    setStatus('Stopping...');
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
        clearPersistedStream();
        stopStreamPolling();
        setBusy(false);
        state.sending = false;
        setStatus('Stopped');
        await loadSessions({ preserveActive: true, selectSessionId: stream.sessionId });
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to stop stream.'), true);
    }
}

async function pollStream() {
    const stream = state.stream;
    if (!stream || state.streamPolling) return;
    state.streamPolling = true;

    try {
        const result = await fetchJson(`/api/codex/streams/${stream.id}?offset=${stream.outputOffset}&error_offset=${stream.errorOffset}`);

        if (!state.stream || state.stream.id !== stream.id) {
            return;
        }

        state.streamFailureCount = 0;
        state.streamPollDelay = STREAM_POLL_BASE_MS;

        if (result?.output) {
            stream.output += result.output;
            stream.outputOffset = Number.isFinite(result.output_length)
                ? result.output_length
                : stream.output.length;
        }
        if (result?.error) {
            stream.error += result.error;
            stream.errorOffset = Number.isFinite(result.error_length)
                ? result.error_length
                : stream.error.length;
        }

        if (result?.output || result?.error) {
            updateStreamEntry(stream);
            setStatus('Receiving response...');
        }

        if (result?.done) {
            await finishStream(result);
            return;
        }
        scheduleStreamPoll(STREAM_POLL_BASE_MS);
    } catch (error) {
        state.streamFailureCount += 1;
        const backoff = Math.min(
            STREAM_POLL_MAX_MS,
            STREAM_POLL_BASE_MS * Math.pow(2, Math.min(state.streamFailureCount, 3))
        );
        state.streamPollDelay = backoff;
        setStatus('Connection lost. Retrying...', true);
        scheduleStreamPoll(backoff);
    } finally {
        state.streamPolling = false;
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

async function finishStream(result) {
    const stream = state.stream;
    if (!stream) return;

    const durationMs = getStreamDuration(stream);
    setMessageDuration(stream.entry?.footer, durationMs);
    setMessageStreaming(stream.entry?.wrapper, false);
    clearPersistedStream();
    stopStreamPolling();
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

    setBusy(false);
    state.sending = false;
    setStatus(exitCode === 0 ? 'Idle' : 'Failed', exitCode !== 0);
    await loadSessions({ preserveActive: true, selectSessionId: stream.sessionId });
}

async function renameSession(session) {
    if (!session?.id || state.sending) return;
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
        setStatus('Idle');
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to rename session.'), true);
    }
}

async function deleteSession(sessionId) {
    if (!sessionId || state.sending) return;
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
        setStatus('Idle');
    } catch (error) {
        setStatus(normalizeError(error, 'Failed to delete session.'), true);
    }
}

function setBusy(isBusy) {
    const input = document.getElementById('codex-chat-input');
    const sendBtn = document.getElementById('codex-chat-send');
    const newBtn = document.getElementById('codex-chat-new-session');
    const refreshBtn = document.getElementById('codex-chat-refresh');
    if (input) input.disabled = isBusy;
    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.dataset.mode = isBusy ? 'stop' : 'send';
        sendBtn.setAttribute('aria-label', isBusy ? 'Stop' : 'Send');
        sendBtn.setAttribute('title', isBusy ? 'Stop' : 'Send');
        const srLabel = sendBtn.querySelector('.sr-only');
        if (srLabel) {
            srLabel.textContent = isBusy ? 'Stop' : 'Send';
        }
    }
    if (newBtn) newBtn.disabled = isBusy;
    if (refreshBtn) refreshBtn.disabled = isBusy;
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
    if (!force && !state.autoScrollEnabled) return;
    if (force) {
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
    const threshold = Number.isFinite(state.autoScrollThreshold) ? state.autoScrollThreshold : 0;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    setAutoScrollEnabled(distanceFromBottom <= threshold);
}

function setAutoScrollEnabled(isEnabled) {
    state.autoScrollEnabled = Boolean(isEnabled);
}

function setMarkdownContent(element, content) {
    if (!element) return;
    const wasExpanded = Boolean(element.querySelector('details.message-details')?.open);
    element.innerHTML = renderMessageContent(content || '', wasExpanded);
    const wrapper = element.closest('.message');
    if (wrapper) {
        wrapper.dataset.messageContent = String(content || '');
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
        event.stopPropagation();
        copyMessageContent(wrapper, button);
    });
    return button;
}

async function copyMessageContent(wrapper, button) {
    if (!wrapper) return;
    const text = wrapper.dataset.messageContent || '';
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
