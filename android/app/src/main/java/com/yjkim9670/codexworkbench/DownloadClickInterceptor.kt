package com.yjkim9670.codexworkbench

import android.webkit.WebView
import org.json.JSONObject

object DownloadClickInterceptor {
    const val BRIDGE_NAME = "CodexDownloadBridge"

    fun install(webView: WebView, bridgeScheme: String) {
        val scheme = JSONObject.quote(bridgeScheme)
        val bridgeName = JSONObject.quote(BRIDGE_NAME)
        val script = """
            (function() {
              if (window.__codexDownloadInterceptorInstalled) return;
              window.__codexDownloadInterceptorInstalled = true;
              const bridgeScheme = $scheme;
              const bridgeName = $bridgeName;

              function resolveHref(value) {
                if (!value) return '';
                try { return new URL(value, document.baseURI).href; }
                catch (_) { return String(value); }
              }

              function signalDownload(href, name, mime) {
                const resolved = resolveHref(href);
                if (!resolved) return false;
                try {
                  const bridge = window[bridgeName];
                  if (bridge && typeof bridge.request === 'function') {
                    bridge.request(resolved, name || '', mime || '');
                    return true;
                  }
                } catch (_) {}
                const target = bridgeScheme + '://request?url=' + encodeURIComponent(resolved) +
                  '&name=' + encodeURIComponent(name || '') +
                  '&mime=' + encodeURIComponent(mime || '');
                try {
                  window.location.href = target;
                  return true;
                } catch (_) {
                  return false;
                }
              }

              function shouldCapture(anchor, href) {
                if (!href) return false;
                const lower = href.toLowerCase();
                return !!(anchor && anchor.hasAttribute && anchor.hasAttribute('download')) ||
                  lower.startsWith('blob:') || lower.startsWith('data:');
              }

              document.addEventListener('click', function(event) {
                const path = event.composedPath ? event.composedPath() : [];
                let anchor = null;
                for (const item of path) {
                  if (item && item.tagName && String(item.tagName).toLowerCase() === 'a') {
                    anchor = item;
                    break;
                  }
                }
                if (!anchor) {
                  let node = event.target;
                  if (node && node.nodeType !== 1) node = node.parentElement;
                  anchor = node && node.closest ? node.closest('a') : null;
                }
                if (!anchor) return;
                const href = resolveHref(anchor.href || anchor.getAttribute('href'));
                if (!shouldCapture(anchor, href)) return;
                event.preventDefault();
                event.stopImmediatePropagation();
                signalDownload(href, anchor.getAttribute('download') || '', anchor.type || '');
              }, true);

              if (window.HTMLAnchorElement && HTMLAnchorElement.prototype) {
                const nativeAnchorClick = HTMLAnchorElement.prototype.click;
                HTMLAnchorElement.prototype.click = function() {
                  const href = resolveHref(this.href || this.getAttribute('href'));
                  if (shouldCapture(this, href)) {
                    signalDownload(href, this.getAttribute('download') || '', this.type || '');
                    return;
                  }
                  return nativeAnchorClick.apply(this, arguments);
                };
              }

              const nativeOpen = window.open;
              window.open = function(url) {
                const href = resolveHref(typeof url === 'string' ? url : '');
                const lower = href.toLowerCase();
                if (lower.startsWith('blob:') || lower.startsWith('data:')) {
                  signalDownload(href, '', '');
                  return null;
                }
                return nativeOpen.apply(this, arguments);
              };
            })();
            null;
        """.trimIndent()
        webView.evaluateJavascript(script, null)
    }
}
