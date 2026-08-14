# Codex Workbench Android Client

The Android client is a thin native shell around the existing Codex Workbench web UI. Codex CLI, workspace files, terminal sessions, Git operations, and credentials remain on the Workbench host.

## Architecture

```text
Android APK
  -> native connection screen
  -> /health check
  -> Android WebView
  -> HTTPS or HTTP
  -> Codex Workbench Flask server
  -> Codex CLI / workspace / Git / terminal
```

The preferred network path is HTTPS over Tailscale. Plain HTTP is intentionally allowed for local development, but the app displays a warning before connecting.

## Requirements

- Android 8.0 (API 26) or later
- Workbench server reachable from the Android device
- Workbench `/health` endpoint returning the `codex-workbench` service status

## Build

The project uses:

- Android Gradle Plugin 8.11.1
- Kotlin 2.1.20
- Gradle 8.13
- JDK 17
- compileSdk / targetSdk 36
- minSdk 26

Build a debug APK from the repository root:

```bash
gradle -p android :app:assembleDebug
```

Output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

GitHub Actions also builds and uploads the debug APK artifact for Android-related pushes, pull requests, and manual workflow runs.

## First connection

1. Start Codex Workbench on the host machine.
2. Make the server reachable from the Android device, preferably through a Tailscale HTTPS URL.
3. Launch the APK.
4. Enter the server base URL, for example `https://workbench.example.ts.net`.
5. Tap **연결**.
6. The app calls `<server>/health` before opening the WebView.

The last successful server URL is saved in Android SharedPreferences.

## Android integrations

The v1 client includes:

- JavaScript and DOM storage for the existing Workbench UI
- first-party cookies for Workbench sessions
- same-origin navigation inside WebView
- external HTTP(S), `mailto:`, and `tel:` links opened outside the WebView
- Android document picker for `<input type="file">`
- DownloadManager integration with Workbench session cookies
- reload and server-switch controls
- WebView history-aware Android back behavior
- safe browsing enabled
- no automatic HTTP Basic credential submission
- no SSL error bypass

Downloads are saved into the app-specific external Downloads directory, so the app does not request broad storage permission.

## Security notes

Do not embed OpenAI, GitHub, SMTP, or other server credentials in the APK. Keep them on the Workbench host.

Use HTTPS for normal use. Plain HTTP support exists only to make local/LAN testing possible and should not be used across untrusted networks.

The WebView does not expose an `addJavascriptInterface` bridge. This keeps the existing web application isolated from native Android APIs except for explicit file chooser and download handling.

## Next improvements

Potential follow-up work:

- signed release APK / AAB pipeline
- adaptive launcher icon and splash screen
- completion notifications
- Android share-to-Workbench intent
- biometric app lock
- tablet/foldable layout tuning
- explicit offline/reconnect overlay
