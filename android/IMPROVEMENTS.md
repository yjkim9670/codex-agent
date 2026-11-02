# Android 1.2.0 implementation and handoff

All source changes are confined to the canonical `codex_workbench` checkout. No Git sync, active server restart, Proc Manager configuration change, or new signing identity is performed.

| Requested item | Implemented behavior | Remaining verification / user input |
| --- | --- | --- |
| 1. Chat mode | Task / Chat selector; the existing conversation server supplies history, models, reasoning, search, stop and retry. Chat uses HTTPS on both networks. | Physical device login and real account request. |
| 2. Fold / tablet | Responsive connection-screen padding; retained Activity/WebView during fold changes; keyboard insets; bounded tablet composer; existing narrow-screen sheets/drawer. | Physical fold / keyboard test. |
| 3. Connection / resume | Network-return retry after connection failure; actionable HTTP/auth errors; renderer crash recovery; selected connection restoration; chat draft, scroll and active response refresh; work-session restoration. | Real network handover and device process termination. |
| 4. Completion notifications | Monitor starts while the work page is open; ignores historical completions; detects tasks completed between polls; explicit completion and queue-drain checks; cancellation and duplicate suppression; notification opens its work session; Android service timeout handling. | Physical device notification permissions and background restrictions. Chat's encrypted attempt transport is not monitored by this Workbench-stream service. |
| 5. Downloads / popups | One shared HTTP/data/blob download controller; HTTP progress notifications; same-origin redirects only; destination and failure feedback; origin-bound top-frame message bridge; other sites open in the external browser. | Device Downloads/MediaStore and blob handling. Android 8/9 use app-specific Downloads as before. |
| 6. Reading / input | Native font and line-height controls; chat line-height preference; Markdown heading/list/quote/code rhythm; horizontal code scrolling; existing copy and new-content controls; per-conversation draft and reading position. | User preference selection. |
| 7. Release / maintenance | Gradle 8.13 Wrapper with distribution checksum; local signing-properties support and signing gate; version 1.2.0; CI unit tests, lint and release compilation; regression tests and documentation. | Existing release keystore and passwords, or explicit decision to create a new identity. |

## Connection policy and addresses

The app exposes only **Tailscale** and **Cloudflare**. Legacy `FUNNEL` preferences resolve to Cloudflare. The previous bundled Cloudflare override is cleared on upgrade; deliberate custom overrides remain editable in App Settings.

Confirmed from local runtime state on 2026-11-02:

- Cloudflare root: `https://strategy-lawrence-runs-places.trycloudflare.com`
- Workbench paths: `/tg/`, `/finance-codex/`, `/local/`, `/constraint/`, `/dev/`
- Dashboard: `/`
- Chat: `/workbench-chat-conversation-server/`, confirmed by the running Proc Manager `/api/open_funnel` candidate list.
- Tailscale workbenches: `http://dinya.wind-mintaka.ts.net:3000/` through `:3004/`
- Tailscale dashboard: `http://dinya.wind-mintaka.ts.net:18000/`
- Tailscale chat: `https://dinya.wind-mintaka.ts.net:3102/` (Serve to local HTTP 3101).

Cloudflare login pages remain on the selected Cloudflare origin. HTTPS Tailnet port 443 (the old Funnel entry), unrelated hosts and obsolete Cloudflare hosts are not app page destinations. Cleartext traffic is permitted only for the configured Tailnet hostname. External source links open in the user's external browser. This is an Android-client policy; the server's separately operated Funnel listener is not disabled.

Quick Tunnel addresses change whenever their tunnel is recreated. Use App Settings → Quick Tunnel address to replace the root; no rebuild is required. The local current address is published in `/Users/dinya/works/.config/proc_manager/quick_tunnel_url.txt`. No discovery API token is embedded in the APK.

## Build and release

```sh
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
ANDROID_HOME=/opt/homebrew/share/android-commandlinetools \
./android/gradlew -p android :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleRelease
```

`versionCode = 1_200_000 + ANDROID_VERSION_CODE` (default offset 0). CI uses its increasing run number as the offset. A local build intended to replace a CI build must supply a larger offset than the installed build. Increment the base for a subsequent release series. `versionName` is `1.2.0`.

For signing, copy `keystore.properties.example` to ignored `keystore.properties`, fill in the existing key's details and restrict the file to its owner. Alternatively, set `ANDROID_SIGNING_PROPERTIES` to an existing private properties file. Explicit signing environment variables take priority. Use `:app:requireReleaseSigning :app:assembleRelease` before distributing the release. Without signing material, `assembleRelease` deliberately produces an **unsigned**, noninstallable validation artifact.

The official [Android WebViewCompat reference](https://developer.android.com/reference/androidx/webkit/WebViewCompat#addWebMessageListener(android.webkit.WebView,java.lang.String,java.util.Set%3Cjava.lang.String%3E,androidx.webkit.WebViewCompat.WebMessageListener)) documents the origin rules used by the download message listener. Devices without `WEB_MESSAGE_LISTENER` retain normal HTTP downloads but require a current Android System WebView for blob transfers.

## Applying web changes

Existing long-running servers are left running. After the user syncs changes to the server checkout, restart the **Workbench Chat / conversation server** and the Workbench instances that should receive session-link restoration. The APK includes native behavior; web CSS/JS is delivered by those servers. Existing cached chat templates are tolerated while awaiting restart.


## Local validation results

- Android unit tests: 10 passed (connection policy, legacy mode migration, chat endpoints, historical/fast/queued/cancelled completions).
- `lintDebug`, debug APK and release APK builds: passed. No release signing key is configured; the signing gate correctly rejects distribution without it.
- Session notification/resume logic: 6 production-JavaScript cases passed, including missing sessions and disabled browser storage.
- Python conversation regression tests: 39 passed (backend, transport, external links, launcher).
- Deterministic browser runner: passed against a temporary loopback fixture at 360/768/1440/1920px, including encrypted API/SSE/poll recovery, cancellation, Markdown/XSS, sidebar/dialog behavior, keyboard/fold sizing, and saved draft/scroll/line-height restoration.
- No Android device or AVD was attached/configured; APK installation, hardware keyboard/fold behavior, background notification delivery and native download integration remain device checks.

Browser command used after the fixture was ready:

```sh
CODEX_VERIFY_CONVERSATION=1 CODEX_VERIFY_CONVERSATION_SIDEBAR=1 python3.14 scripts/verify_browser_ui.py --url http://127.0.0.1:56165 --selector '#composer' --timeout-ms 120000
```

The temporary fixture is stopped after verification. Existing production servers remain running.
