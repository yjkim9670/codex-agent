package com.yjkim9670.codexworkbench

import android.webkit.WebView
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject
import java.util.Collections
import java.util.WeakHashMap

object DownloadClickInterceptor {
    const val BRIDGE_NAME = "CodexDownloadBridge"

    private val documentStartRegistered = Collections.synchronizedMap(WeakHashMap<WebView, Boolean>())

    fun install(webView: WebView, bridgeScheme: String) {
        val script = buildScript(bridgeScheme)
        val firstDocumentStartRegistration = registerDocumentStart(webView, script)

        // Cover the currently visible top-level document as a fallback. The document-start
        // registration below covers every frame on the next navigation, including iframes.
        webView.evaluateJavascript(script, null)

        // V2 originally installs this helper from onPageCommitVisible/onPageFinished, which is
        // too late for scripts that create download APIs during initial page startup. Reload once
        // after registering the document-start script so the very next document is instrumented
        // before any page JavaScript runs. The WeakHashMap prevents a reload loop.
        if (firstDocumentStartRegistration) {
            webView.post {
                if (webView.url?.startsWith("http") == true) {
                    webView.reload()
                }
            }
        }
    }

    private fun registerDocumentStart(webView: WebView, script: String): Boolean {
        if (documentStartRegistered.containsKey(webView)) return false
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) return false

        return runCatching {
            WebViewCompat.addDocumentStartJavaScript(webView, script, setOf("*"))
            documentStartRegistered[webView] = true
            true
        }.getOrDefault(false)
    }

    private fun buildScript(bridgeScheme: String): String {
        val scheme = JSONObject.quote(bridgeScheme)
        val bridgeName = JSONObject.quote(BRIDGE_NAME)
        return """
            (function() {
              if (window.__codexDownloadInterceptorInstalled) return;
              window.__codexDownloadInterceptorInstalled = true;
              const bridgeScheme = $scheme;
              const bridgeName = $bridgeName;

              function bridge() {
                try { return window[bridgeName] || null; }
                catch (_) { return null; }
              }

              function resolveHref(value) {
                if (!value) return '';
                try { return new URL(value, document.baseURI).href; }
                catch (_) { return String(value); }
              }

              function isDownloadLikeUrl(href) {
                if (!href) return false;
                const lower = href.toLowerCase();
                if (lower.startsWith('blob:') || lower.startsWith('data:')) return true;
                if (!lower.startsWith('http://') && !lower.startsWith('https://')) return false;
                try {
                  const url = new URL(href, document.baseURI);
                  const path = url.pathname.toLowerCase();
                  const query = url.search.toLowerCase();
                  if (/(^|\/)download(s)?(\/|$)/.test(path) || /(^|\/)export(\/|$)/.test(path)) return true;
                  if (/(^|[?&])(download|export|attachment)=/.test(query)) return true;
                  return /\.(zip|7z|tar|gz|tgz|pdf|csv|tsv|xlsx?|docx?|pptx?|txt|md|json|xml|yaml|yml|log|bin|apk|png|jpe?g|webp|gif|mp3|wav|m4a|mp4|mov|webm)(?:$|[?#])/.test(lower);
                } catch (_) {
                  return false;
                }
              }

              function signalDownload(href, name, mime) {
                const resolved = resolveHref(href);
                if (!resolved) return false;
                try {
                  const targetBridge = bridge();
                  if (targetBridge && typeof targetBridge.request === 'function') {
                    targetBridge.request(resolved, name || '', mime || '');
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
                return !!(anchor && anchor.hasAttribute && anchor.hasAttribute('download')) ||
                  isDownloadLikeUrl(href);
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
                if (isDownloadLikeUrl(href)) {
                  signalDownload(href, '', '');
                  return null;
                }
                return nativeOpen.apply(this, arguments);
              };

              // File System Access API is not consistently implemented by Android WebView.
              // Expose a small compatible save-file handle before application JavaScript runs.
              // On close, convert the accumulated data to a data URL and route it through the
              // same Android bridge. This covers apps that never create an <a download> element.
              window.showSaveFilePicker = async function(options) {
                const opts = options || {};
                const suggestedName = String(opts.suggestedName || 'download.bin');
                let declaredMime = '';
                try {
                  const types = Array.isArray(opts.types) ? opts.types : [];
                  const accept = types[0] && types[0].accept ? types[0].accept : null;
                  if (accept) declaredMime = Object.keys(accept)[0] || '';
                } catch (_) {}

                return {
                  kind: 'file',
                  name: suggestedName,
                  async createWritable() {
                    const parts = [];
                    return {
                      async write(value) {
                        let data = value;
                        if (data && typeof data === 'object' && data.type === 'write' && 'data' in data) {
                          data = data.data;
                        }
                        if (data && typeof data === 'object' && data.type === 'truncate') return;
                        if (data && typeof data === 'object' && data.type === 'seek') return;
                        parts.push(data);
                      },
                      async seek() {},
                      async truncate() {},
                      async abort() { parts.length = 0; },
                      async close() {
                        const blob = new Blob(parts, { type: declaredMime || 'application/octet-stream' });
                        await new Promise(function(resolve, reject) {
                          const reader = new FileReader();
                          reader.onload = function() {
                            signalDownload(String(reader.result || ''), suggestedName, blob.type || declaredMime);
                            resolve();
                          };
                          reader.onerror = function() { reject(reader.error || new Error('save conversion failed')); };
                          reader.readAsDataURL(blob);
                        });
                      }
                    };
                  }
                };
              };

              if (navigator && typeof navigator.msSaveBlob === 'function') {
                const nativeMsSaveBlob = navigator.msSaveBlob.bind(navigator);
                navigator.msSaveBlob = function(blob, name) {
                  try {
                    const reader = new FileReader();
                    reader.onload = function() { signalDownload(String(reader.result || ''), name || '', blob.type || ''); };
                    reader.readAsDataURL(blob);
                    return true;
                  } catch (_) {
                    return nativeMsSaveBlob(blob, name);
                  }
                };
              }
            })();
            null;
        """.trimIndent()
    }
}
