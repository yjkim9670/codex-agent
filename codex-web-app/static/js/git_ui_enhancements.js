(() => {
    'use strict';

    const DRAFT_STORAGE_KEY = 'codex.gitCommitDrafts.v1';
    const TARGET_WORKSPACE = 'workspace';
    const TARGET_CODEX_AGENT = 'codex_agent';
    const VALID_TARGETS = new Set([TARGET_WORKSPACE, TARGET_CODEX_AGENT]);
    const BRANCH_LIST_ENDPOINT = '/api/codex/git/branches/remote';
    const BRANCH_SWITCH_ENDPOINT = '/api/codex/git/branches/switch';
    let remoteBranchLoadSerial = 0;
    let remoteBranchSwitchInFlight = false;
    let lastSyncTarget = '';

    function normalizeTarget(value) {
        const target = String(value || '').trim();
        return VALID_TARGETS.has(target) ? target : TARGET_WORKSPACE;
    }

    function getBranchTarget() {
        try {
            if (typeof gitBranchRepoTarget !== 'undefined') {
                return normalizeTarget(gitBranchRepoTarget);
            }
        } catch (error) {
            void error;
        }
        const subtitle = document.getElementById('codex-branch-overlay-subtitle')?.textContent || '';
        return subtitle.includes('codex_workbench') ? TARGET_CODEX_AGENT : TARGET_WORKSPACE;
    }

    function getSyncTarget() {
        try {
            if (typeof gitSyncOverlayRepoTarget !== 'undefined') {
                return normalizeTarget(gitSyncOverlayRepoTarget);
            }
        } catch (error) {
            void error;
        }
        const active = document.querySelector('#codex-sync-overlay .sync-overlay-target.is-active[data-repo-target]');
        return normalizeTarget(active?.dataset?.repoTarget);
    }

    function readDraftStore() {
        try {
            const raw = window.localStorage?.getItem(DRAFT_STORAGE_KEY);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function writeDraftStore(store) {
        try {
            const keys = Object.keys(store || {}).filter(key => store[key]);
            if (!keys.length) {
                window.localStorage?.removeItem(DRAFT_STORAGE_KEY);
                return;
            }
            window.localStorage?.setItem(DRAFT_STORAGE_KEY, JSON.stringify(store));
        } catch (error) {
            void error;
        }
    }

    function getDraft(target) {
        const store = readDraftStore();
        const entry = store[normalizeTarget(target)];
        return entry && typeof entry === 'object' ? entry : null;
    }

    function saveDraft(target, subject, body, status = '') {
        const normalizedTarget = normalizeTarget(target);
        const normalizedSubject = String(subject || '').trim();
        const normalizedBody = String(body || '').trim();
        const store = readDraftStore();
        if (!normalizedSubject && !normalizedBody) {
            delete store[normalizedTarget];
            writeDraftStore(store);
            return;
        }
        store[normalizedTarget] = {
            subject: normalizedSubject,
            body: normalizedBody,
            status: String(status || '').trim(),
            updatedAt: Date.now(),
        };
        writeDraftStore(store);
    }

    function clearDraft(target) {
        const store = readDraftStore();
        delete store[normalizeTarget(target)];
        writeDraftStore(store);
    }

    function getOverlayElements(kind) {
        const prefix = kind === 'sync' ? 'codex-sync-overlay' : 'codex-branch-overlay';
        return {
            overlay: document.getElementById(prefix),
            subject: document.getElementById(`${prefix}-commit-message`),
            body: document.getElementById(`${prefix}-commit-body`),
            status: document.getElementById(`${prefix}-message-status`),
            generate: document.getElementById(`${prefix}-generate-message`),
            model: document.getElementById(`${prefix}-message-model`),
        };
    }

    function targetForKind(kind) {
        return kind === 'sync' ? getSyncTarget() : getBranchTarget();
    }

    function generationInFlight() {
        try {
            return typeof gitCommitMessageGenerationInFlight !== 'undefined'
                && Boolean(gitCommitMessageGenerationInFlight);
        } catch (error) {
            return false;
        }
    }

    function setFields(elements, subject, body, { emitInput = false } = {}) {
        if (elements?.subject) elements.subject.value = String(subject || '');
        if (elements?.body) elements.body.value = String(body || '');
        if (emitInput) {
            elements?.subject?.dispatchEvent(new Event('input', { bubbles: true }));
            elements?.body?.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    function persistElements(kind, explicitTarget = '') {
        const elements = getOverlayElements(kind);
        const target = normalizeTarget(explicitTarget || targetForKind(kind));
        const subject = elements.subject?.value || '';
        const body = elements.body?.value || '';
        const status = elements.status?.textContent || '';
        saveDraft(target, subject, body, status);
    }

    function restoreElements(kind, explicitTarget = '', { clearIfMissing = true } = {}) {
        const elements = getOverlayElements(kind);
        const target = normalizeTarget(explicitTarget || targetForKind(kind));
        const draft = getDraft(target);
        if (draft) {
            setFields(elements, draft.subject || '', draft.body || '');
            if (elements.status && draft.status && !/생성 중/.test(draft.status)) {
                elements.status.textContent = draft.status;
                elements.status.classList.remove('is-error');
            }
        } else if (clearIfMissing) {
            setFields(elements, '', '');
            if (elements.status && !generationInFlight()) {
                elements.status.textContent = '';
                elements.status.classList.remove('is-error');
            }
        }
        if (generationInFlight() && elements.status) {
            elements.status.textContent = 'AI 상세 메시지 생성 중... 창을 닫아도 백그라운드에서 계속됩니다.';
            elements.status.classList.remove('is-error');
        }
        updateClearButton(kind);
    }

    function notify(message, tone = 'default', durationMs = 3000) {
        try {
            if (typeof showToast === 'function') {
                showToast(message, { tone, durationMs });
                return;
            }
        } catch (error) {
            void error;
        }
        console.info(`[codex-ui] ${message}`);
    }

    function buildClearIcon() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M7 7l10 10M17 7L7 17');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'currentColor');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-linecap', 'round');
        svg.appendChild(path);
        return svg;
    }

    function installClearButton(kind) {
        const elements = getOverlayElements(kind);
        if (!elements.subject) return;
        const id = kind === 'sync'
            ? 'codex-sync-overlay-clear-message'
            : 'codex-branch-overlay-clear-message';
        if (document.getElementById(id)) return;
        const tools = elements.subject.closest('.branch-overlay-commit, .sync-overlay-commit')
            ?.querySelector('.git-message-tool-actions');
        if (!tools) return;

        const button = document.createElement('button');
        button.type = 'button';
        button.id = id;
        button.className = 'btn ghost icon-only git-message-clear';
        button.setAttribute('aria-label', 'Commit message clear');
        button.setAttribute('title', 'Commit message clear');
        button.appendChild(buildClearIcon());
        const sr = document.createElement('span');
        sr.className = 'sr-only';
        sr.textContent = 'Commit message clear';
        button.appendChild(sr);
        button.addEventListener('click', () => {
            if (generationInFlight()) return;
            const target = targetForKind(kind);
            clearDraft(target);
            setFields(elements, '', '', { emitInput: true });
            if (elements.status) {
                elements.status.textContent = '';
                elements.status.classList.remove('is-error');
            }
            updateClearButton(kind);
            try {
                if (kind === 'branch' && typeof updateGitBranchOverlayCommitPreview === 'function') {
                    updateGitBranchOverlayCommitPreview(gitBranchStatusCache);
                } else if (kind === 'sync' && typeof renderGitSyncOverlay === 'function') {
                    renderGitSyncOverlay(getGitSyncHistoryCache(getSyncTarget()));
                }
            } catch (error) {
                void error;
            }
        });
        tools.appendChild(button);
        updateClearButton(kind);
    }

    function updateClearButton(kind) {
        const id = kind === 'sync'
            ? 'codex-sync-overlay-clear-message'
            : 'codex-branch-overlay-clear-message';
        const button = document.getElementById(id);
        if (!button) return;
        const elements = getOverlayElements(kind);
        const hasValue = Boolean(
            String(elements.subject?.value || '').trim()
            || String(elements.body?.value || '').trim()
        );
        button.disabled = generationInFlight() || !hasValue;
    }

    function installDraftPersistence(kind) {
        const elements = getOverlayElements(kind);
        if (!elements.overlay || !elements.subject || !elements.body) return;
        installClearButton(kind);

        const onInput = () => {
            persistElements(kind);
            updateClearButton(kind);
        };
        elements.subject.addEventListener('input', onInput);
        elements.body.addEventListener('input', onInput);

        if (elements.status) {
            const statusObserver = new MutationObserver(() => {
                const text = String(elements.status?.textContent || '').trim();
                if (/상세 메시지 생성 완료/.test(text)) {
                    persistElements(kind);
                }
                updateClearButton(kind);
            });
            statusObserver.observe(elements.status, { childList: true, characterData: true, subtree: true });
        }

        const overlayObserver = new MutationObserver(() => {
            if (!elements.overlay.classList.contains('is-visible')) return;
            window.requestAnimationFrame(() => restoreElements(kind));
        });
        overlayObserver.observe(elements.overlay, { attributes: true, attributeFilter: ['class'] });
    }

    function clearVisibleFieldsForTarget(target) {
        const normalizedTarget = normalizeTarget(target);
        ['branch', 'sync'].forEach(kind => {
            if (normalizeTarget(targetForKind(kind)) !== normalizedTarget) return;
            const elements = getOverlayElements(kind);
            setFields(elements, '', '', { emitInput: true });
            if (elements.status) {
                elements.status.textContent = '';
                elements.status.classList.remove('is-error');
            }
            updateClearButton(kind);
        });
    }

    function parseRequestPayload(init, input) {
        let body = init?.body;
        if (body == null && typeof Request !== 'undefined' && input instanceof Request) {
            return null;
        }
        if (typeof body !== 'string') return null;
        try {
            const parsed = JSON.parse(body);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function getRequestUrl(input) {
        if (typeof input === 'string') return input;
        if (input instanceof URL) return input.href;
        if (typeof Request !== 'undefined' && input instanceof Request) return input.url;
        return String(input || '');
    }

    function getRequestMethod(init, input) {
        const method = init?.method
            || (typeof Request !== 'undefined' && input instanceof Request ? input.method : 'GET');
        return String(method || 'GET').toUpperCase();
    }

    function pathnameForRequest(input) {
        try {
            return new URL(getRequestUrl(input), window.location.href).pathname;
        } catch (error) {
            return '';
        }
    }

    function installFetchLifecycleHook() {
        if (window.fetch?.__codexGitUiEnhanced) return;
        const originalFetch = window.fetch.bind(window);
        const enhancedFetch = async (input, init) => {
            const path = pathnameForRequest(input);
            const method = getRequestMethod(init, input);
            const payload = parseRequestPayload(init, input);
            const response = await originalFetch(input, init);

            if (response.ok && method === 'POST' && path.endsWith('/api/codex/git/commit')) {
                const target = normalizeTarget(payload?.repo_target || getBranchTarget());
                clearDraft(target);
                clearVisibleFieldsForTarget(target);
            }

            if (
                response.ok
                && method === 'POST'
                && (
                    path.endsWith('/api/codex/git/sync')
                    || path.endsWith(BRANCH_SWITCH_ENDPOINT)
                )
            ) {
                window.setTimeout(() => {
                    if (document.getElementById('codex-sync-overlay')?.classList.contains('is-visible')) {
                        void loadRemoteBranches({ preserveSelection: true });
                    }
                }, 0);
            }
            return response;
        };
        enhancedFetch.__codexGitUiEnhanced = true;
        enhancedFetch.__codexOriginalFetch = originalFetch;
        window.fetch = enhancedFetch;
    }

    function createBranchSwitcher() {
        const tools = document.querySelector('#codex-sync-overlay .sync-overlay-tools');
        if (!tools || document.getElementById('codex-sync-overlay-remote-branch')) return;

        const wrapper = document.createElement('div');
        wrapper.className = 'sync-branch-switcher';

        const select = document.createElement('select');
        select.id = 'codex-sync-overlay-remote-branch';
        select.className = 'sync-branch-select';
        select.setAttribute('aria-label', 'Remote branch');
        select.title = 'Switch remote branch';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Remote branch 선택';
        select.appendChild(placeholder);

        const switchButton = document.createElement('button');
        switchButton.type = 'button';
        switchButton.id = 'codex-sync-overlay-switch-branch';
        switchButton.className = 'btn secondary sync-branch-switch-btn';
        switchButton.textContent = 'Switch';
        switchButton.disabled = true;

        const status = document.createElement('span');
        status.id = 'codex-sync-overlay-branch-status';
        status.className = 'sync-branch-switch-status';
        status.setAttribute('aria-live', 'polite');

        select.addEventListener('change', () => {
            switchButton.disabled = remoteBranchSwitchInFlight || !select.value;
        });
        switchButton.addEventListener('click', () => void switchSelectedRemoteBranch());

        wrapper.append(select, switchButton, status);
        tools.appendChild(wrapper);
    }

    function getBranchSwitcherElements() {
        return {
            select: document.getElementById('codex-sync-overlay-remote-branch'),
            switchButton: document.getElementById('codex-sync-overlay-switch-branch'),
            status: document.getElementById('codex-sync-overlay-branch-status'),
        };
    }

    function setBranchSwitcherStatus(message = '', isError = false) {
        const { status } = getBranchSwitcherElements();
        if (!status) return;
        status.textContent = String(message || '');
        status.classList.toggle('is-error', Boolean(isError));
    }

    async function readJsonResponse(response) {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(data?.error || `HTTP ${response.status}`);
            error.payload = data;
            throw error;
        }
        return data;
    }

    async function loadRemoteBranches({ fetch = false, preserveSelection = false } = {}) {
        createBranchSwitcher();
        const elements = getBranchSwitcherElements();
        if (!elements.select) return;
        const requestId = ++remoteBranchLoadSerial;
        const target = getSyncTarget();
        const previousRef = preserveSelection
            ? elements.select.selectedOptions?.[0]?.dataset?.ref || ''
            : '';
        elements.select.disabled = true;
        if (elements.switchButton) elements.switchButton.disabled = true;
        setBranchSwitcherStatus(fetch ? '원격 브랜치 fetch 중...' : '원격 브랜치 불러오는 중...');
        try {
            const params = new URLSearchParams({
                repo_target: target,
                fetch: fetch ? '1' : '0',
            });
            const response = await window.fetch(`${BRANCH_LIST_ENDPOINT}?${params.toString()}`, {
                cache: 'no-store',
            });
            const result = await readJsonResponse(response);
            if (requestId !== remoteBranchLoadSerial || target !== getSyncTarget()) return;

            const branches = Array.isArray(result?.remote_branches) ? result.remote_branches : [];
            elements.select.innerHTML = '';
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = branches.length ? 'Remote branch 선택' : '원격 브랜치 없음';
            elements.select.appendChild(placeholder);

            let preferredIndex = 0;
            branches.forEach((entry, index) => {
                const option = document.createElement('option');
                option.value = `${entry.remote || ''}/${entry.branch || ''}`;
                option.dataset.remote = String(entry.remote || '');
                option.dataset.branch = String(entry.branch || '');
                option.dataset.ref = String(entry.ref || option.value);
                const localSuffix = entry.local_branch ? ` → ${entry.local_branch}` : '';
                const currentSuffix = entry.checked_out ? ' (current)' : '';
                option.textContent = `${entry.ref || option.value}${localSuffix}${currentSuffix}`;
                if (entry.checked_out || (previousRef && entry.ref === previousRef)) {
                    preferredIndex = index + 1;
                }
                elements.select.appendChild(option);
            });
            if (preferredIndex > 0) elements.select.selectedIndex = preferredIndex;
            elements.select.disabled = branches.length === 0;
            if (elements.switchButton) {
                const selected = elements.select.selectedOptions?.[0];
                const selectedCurrent = Boolean(
                    selected
                    && branches.find(item => item.ref === selected.dataset?.ref)?.checked_out
                );
                elements.switchButton.disabled = remoteBranchSwitchInFlight || !elements.select.value || selectedCurrent;
            }
            const dirtySuffix = result?.dirty ? ` · 작업 트리 변경 ${result.changed_files_count || 0}개` : '';
            setBranchSwitcherStatus(
                `${result.current_branch || '브랜치 없음'} · ${branches.length} remote branches${dirtySuffix}`
            );
        } catch (error) {
            if (requestId !== remoteBranchLoadSerial) return;
            elements.select.disabled = true;
            if (elements.switchButton) elements.switchButton.disabled = true;
            setBranchSwitcherStatus(error?.message || '원격 브랜치를 불러오지 못했습니다.', true);
        }
    }

    async function switchSelectedRemoteBranch() {
        const elements = getBranchSwitcherElements();
        const option = elements.select?.selectedOptions?.[0];
        const remote = String(option?.dataset?.remote || '').trim();
        const branch = String(option?.dataset?.branch || '').trim();
        if (!remote || !branch || remoteBranchSwitchInFlight) return;

        remoteBranchSwitchInFlight = true;
        elements.select.disabled = true;
        if (elements.switchButton) elements.switchButton.disabled = true;
        setBranchSwitcherStatus(`${remote}/${branch} 전환 중...`);
        try {
            const response = await window.fetch(BRANCH_SWITCH_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    repo_target: getSyncTarget(),
                    remote,
                    branch,
                    fetch: true,
                }),
            });
            const result = await readJsonResponse(response);
            notify(
                result.already_current
                    ? `${remote}/${branch} · 이미 현재 브랜치입니다.`
                    : `${remote}/${branch} 브랜치로 전환했습니다.`,
                'success',
                2800
            );
            try {
                if (typeof refreshGitSyncOverlayHistory === 'function') {
                    void refreshGitSyncOverlayHistory({ force: true });
                }
                if (typeof refreshGitBranchStatus === 'function') {
                    void refreshGitBranchStatus({ force: true, updateOverlay: false });
                }
            } catch (error) {
                void error;
            }
            await loadRemoteBranches({ preserveSelection: false });
        } catch (error) {
            setBranchSwitcherStatus(error?.message || '브랜치 전환에 실패했습니다.', true);
            notify(error?.message || '브랜치 전환에 실패했습니다.', 'error', 5200);
        } finally {
            remoteBranchSwitchInFlight = false;
            const current = getBranchSwitcherElements();
            if (current.select) current.select.disabled = current.select.options.length <= 1;
            if (current.switchButton) current.switchButton.disabled = !current.select?.value;
        }
    }

    function installSyncTargetHandling() {
        lastSyncTarget = getSyncTarget();
        document.querySelectorAll('#codex-sync-overlay .sync-overlay-target[data-repo-target]').forEach(button => {
            button.addEventListener('click', () => {
                const previousTarget = lastSyncTarget || getSyncTarget();
                persistElements('sync', previousTarget);
                window.setTimeout(() => {
                    lastSyncTarget = getSyncTarget();
                    restoreElements('sync', lastSyncTarget, { clearIfMissing: true });
                    void loadRemoteBranches({ preserveSelection: false });
                }, 0);
            }, true);
        });
    }

    function installSyncOverlayRemoteBranchRefresh() {
        const overlay = document.getElementById('codex-sync-overlay');
        if (!overlay) return;
        const observer = new MutationObserver(() => {
            if (!overlay.classList.contains('is-visible')) return;
            lastSyncTarget = getSyncTarget();
            window.requestAnimationFrame(() => void loadRemoteBranches({ preserveSelection: true }));
        });
        observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });

        const fetchButton = document.getElementById('codex-sync-overlay-fetch');
        if (fetchButton) {
            fetchButton.addEventListener('click', () => {
                window.setTimeout(() => void loadRemoteBranches({ preserveSelection: true }), 400);
            });
        }
    }

    function classifySyncMetaPart(text) {
        const value = String(text || '').replace(/^\s*·\s*/, '').trim();
        if (/^HEAD 대비 ahead\b/.test(value)) return 'is-divergence';
        if (/^작업 트리 변경\b/.test(value)) return 'is-changes';
        if (/^현재 브랜치:/.test(value)) return 'is-branch';
        if (/^오류:/.test(value)) return 'is-warning';
        if (/^요청\s/.test(value)) return 'is-fallback';
        return 'is-repository';
    }

    function enhanceSyncMeta() {
        const meta = document.getElementById('codex-sync-overlay-meta');
        if (!meta) return;
        const text = String(meta.textContent || '').trim();
        if (!text || text === meta.dataset.gitEnhancedSource) return;
        if (!text.includes(' · ')) return;
        const parts = text.split(/\s+·\s+/).map(part => part.trim()).filter(Boolean);
        if (parts.length < 2) return;

        meta.dataset.gitEnhancedSource = text;
        meta.classList.add('git-sync-meta-enhanced');
        const fragment = document.createDocumentFragment();
        parts.forEach((part, index) => {
            const span = document.createElement('span');
            span.className = `git-sync-meta-part ${classifySyncMetaPart(part)}`;
            span.textContent = index === 0 ? part : `· ${part}`;
            fragment.appendChild(span);
        });
        meta.replaceChildren(fragment);
    }

    function installSyncMetaEnhancement() {
        const meta = document.getElementById('codex-sync-overlay-meta');
        if (!meta) return;
        enhanceSyncMeta();
        const observer = new MutationObserver(() => enhanceSyncMeta());
        observer.observe(meta, { childList: true, characterData: true, subtree: true });
    }

    function initialize() {
        installFetchLifecycleHook();
        installDraftPersistence('branch');
        installDraftPersistence('sync');
        createBranchSwitcher();
        installSyncTargetHandling();
        installSyncOverlayRemoteBranchRefresh();
        installSyncMetaEnhancement();

        restoreElements('branch', getBranchTarget(), { clearIfMissing: false });
        restoreElements('sync', getSyncTarget(), { clearIfMissing: false });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize, { once: true });
    } else {
        initialize();
    }
})();
