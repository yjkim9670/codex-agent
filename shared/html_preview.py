"""Shared opaque-origin HTML preview policy for Workbench and Chat."""
import re

HTML_MAX_BYTES = 64 * 1024 * 1024
HTML_PREVIEW_CSP = (
    "sandbox allow-scripts allow-forms; base-uri 'none'; "
    "object-src 'none'; frame-ancestors 'self'"
)

_HTML_PREVIEW_STORAGE_COMPAT = b'''<script data-codex-workbench-preview-compat="web-storage">
(() => {
    const createMemoryStorage = () => {
        const values = new Map();
        return {
            get length() { return values.size; },
            key(index) { return Array.from(values.keys())[Number(index)] ?? null; },
            getItem(key) {
                const normalized = String(key);
                return values.has(normalized) ? values.get(normalized) : null;
            },
            setItem(key, value) { values.set(String(key), String(value)); },
            removeItem(key) { values.delete(String(key)); },
            clear() { values.clear(); }
        };
    };
    for (const name of ['localStorage', 'sessionStorage']) {
        try {
            void window[name];
        } catch (_error) {
            try {
                Object.defineProperty(window, name, {
                    configurable: true,
                    enumerable: true,
                    value: createMemoryStorage()
                });
            } catch (_defineError) {
                // Keep the browser's native sandbox behavior when replacement is unavailable.
            }
        }
    }
})();
</script>'''


def inject_html_preview_storage_compat(content):
    """Add a preview-only in-memory Web Storage fallback before page scripts."""
    if not isinstance(content, bytes) or not content:
        return content
    if content.startswith((b'\xff\xfe', b'\xfe\xff', b'\x00\x00\xfe\xff', b'\xff\xfe\x00\x00')):
        return content

    first_script = re.search(br'<script(?:\s|>)', content, flags=re.IGNORECASE)
    head = re.search(br'<head(?:\s[^>]*)?>', content, flags=re.IGNORECASE)
    charset = re.search(
        br'<meta\s+[^>]*(?:charset\s*=|http-equiv\s*=\s*["\']?content-type)[^>]*>',
        content,
        flags=re.IGNORECASE,
    )
    if charset and (not first_script or charset.start() < first_script.start()):
        insert_at = charset.end()
    elif head and (not first_script or head.start() < first_script.start()):
        insert_at = head.end()
    else:
        doctype = re.match(br'(?:\xef\xbb\xbf)?\s*<!doctype\s+html[^>]*>', content, flags=re.IGNORECASE)
        insert_at = doctype.end() if doctype else (3 if content.startswith(b'\xef\xbb\xbf') else 0)
    return content[:insert_at] + _HTML_PREVIEW_STORAGE_COMPAT + content[insert_at:]

