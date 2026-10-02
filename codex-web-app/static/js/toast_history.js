/* Every displayed toast is retained in this origin's IndexedDB. */
(() => {
    const PAGE_SIZE = 50;
    const list = document.getElementById('toast-history-list');
    const status = document.getElementById('toast-history-status');
    const toneSelect = document.getElementById('toast-history-tone');
    const more = document.getElementById('toast-history-more');
    let lastKey = null;
    let generation = 0;
    let storageError = '';
    let pending = Promise.resolve();
    const database = new Promise((resolve, reject) => {
        const request = indexedDB.open('codex-workbench-toast-history', 1);
        request.onupgradeneeded = () => request.result.createObjectStore('toasts', { keyPath: 'id', autoIncrement: true });
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error('다른 탭이 알림 저장소를 사용 중입니다.'));
    });
    const reportError = error => {
        storageError = `알림 이력을 저장하거나 조회하지 못했습니다: ${error?.message || error}`;
        if (status) status.textContent = storageError;
    };
    // Handle startup failures even if no toast has appeared yet.
    database.catch(reportError);
    async function transaction(mode, callback) {
        const db = await database;
        return new Promise((resolve, reject) => {
            const tx = db.transaction('toasts', mode);
            let result;
            tx.oncomplete = () => resolve(result);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error('알림 저장 작업 취소'));
            callback(tx.objectStore('toasts'), value => { result = value; });
        });
    }
    const label = tone => ({ error: '오류', success: '완료', warning: '주의', default: '안내' }[tone] || tone);
    function matches(entry) {
        return !toneSelect?.value || entry.tone === toneSelect.value;
    }
    async function render(reset = true) {
        if (!list) return;
        const current = ++generation;
        const after = reset ? null : lastKey;
        try {
            await pending;
            const entries = await transaction('readonly', (store, done) => {
                const results = [];
                const request = store.openCursor(after === null ? undefined : IDBKeyRange.upperBound(after, true), 'prev');
                request.onsuccess = () => {
                    const cursor = request.result;
                    if (!cursor || results.length > PAGE_SIZE) { done(results); return; }
                    if (matches(cursor.value)) results.push(cursor.value);
                    cursor.continue();
                };
            });
            if (current !== generation) return;
            if (reset) list.replaceChildren();
            entries.slice(0, PAGE_SIZE).forEach(entry => {
                const item = document.createElement('li');
                const meta = document.createElement('div');
                meta.className = 'toast-history-meta';
                meta.textContent = `${new Date(entry.created_at).toLocaleString()} · ${label(entry.tone)}`;
                const message = document.createElement('div');
                message.className = 'toast-history-message';
                message.textContent = entry.message;
                item.append(meta, message);
                list.append(item);
                lastKey = entry.id;
            });
            if (more) more.hidden = entries.length <= PAGE_SIZE;
            status.textContent = storageError || (list.children.length ? `${list.children.length}개 표시 · 최신 알림부터` : '기록된 알림이 없습니다.');
        } catch (error) { reportError(error); }
    }
    window.workbenchToastHistory = {
        record(message, tone = 'default') {
            // A serialized write chain keeps ordering stable and survives individual write failures.
            pending = pending.then(() => transaction('readwrite', store => {
                store.add({ message: String(message), tone, created_at: new Date().toISOString(), page: location.pathname });
            })).catch(reportError);
            pending.then(() => {
                if (document.getElementById('toast-history-overlay')?.classList.contains('is-visible')) void render();
            });
        },
        refresh: () => render(),
        ready: () => pending
    };
    more?.addEventListener('click', () => void render(false));
    toneSelect?.addEventListener('change', () => void render());
    document.getElementById('toast-history-export')?.addEventListener('click', async () => {
        try {
            await pending;
            const entries = await transaction('readonly', (store, done) => {
                const request = store.getAll();
                request.onsuccess = () => done(request.result);
            });
            const url = URL.createObjectURL(new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' }));
            const link = document.createElement('a');
            link.href = url;
            link.download = `workbench-toast-history-${new Date().toISOString().slice(0, 10)}.json`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { reportError(error); }
    });
    const overlay = document.getElementById('toast-history-overlay');
    const settings = document.getElementById('codex-ui-settings-overlay');
    const openButton = document.getElementById('toast-history-open');
    const closeButton = document.getElementById('toast-history-close');
    function close() {
        overlay?.classList.remove('is-visible');
        overlay?.setAttribute('aria-hidden', 'true');
        if (settings) {
            settings.inert = false;
            settings.setAttribute('aria-hidden', String(!settings.classList.contains('is-visible')));
        }
        openButton?.focus();
    }
    openButton?.addEventListener('click', () => {
        overlay?.classList.add('is-visible');
        overlay?.setAttribute('aria-hidden', 'false');
        closeButton?.focus();
        if (settings) { settings.inert = true; settings.setAttribute('aria-hidden', 'true'); }
        void render();
    });
    closeButton?.addEventListener('click', close);
    document.getElementById('toast-history-done')?.addEventListener('click', close);
    overlay?.addEventListener('click', event => {
        if (event.target.dataset.action === 'close') close();
    });
    document.addEventListener('keydown', event => {
        if (!overlay?.classList.contains('is-visible')) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopImmediatePropagation();
            close();
        } else if (event.key === 'Tab') {
            const controls = [...overlay.querySelectorAll('button, select')].filter(el => !el.hidden && !el.disabled);
            const first = controls[0], last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
    }, true);
})();
