# MacBook + Codex Android Build and Deployment Workflow

This document is the operating plan for developing Codex Workbench on a MacBook, asking Codex to make changes from a local clone, and producing update-safe Android APKs.

## 1. Canonical repository and branch

- Repository: `yjkim9670/codex-agent`
- Canonical branch: `main`
- Do not use or recreate `master`.
- Before starting work, sync the local checkout to the current remote `main`.
- Keep feature work based on the current `main` unless a task explicitly requires a temporary branch.
- Do not delete branches unless explicitly requested.

Recommended local setup:

```bash
git clone https://github.com/yjkim9670/codex-agent.git
cd codex-agent
git checkout main
git pull --ff-only origin main
```

For an existing clone:

```bash
cd /path/to/codex-agent
git checkout main
git pull --ff-only origin main
```

Before modifying anything, Codex should inspect:

```bash
git status --short --branch
git log --oneline -10
git branch -a
```

Do not overwrite unrelated local changes. If the checkout is dirty, inspect and preserve the user's work before editing.

## 2. Runtime architecture

The MacBook is the runtime host. The Android application is a thin client.

```text
MacBook
  ├─ Codex Workbench servers
  ├─ Process Dashboard
  ├─ Tailscale / Funnel exposure
  └─ source checkout and Codex CLI
          │
          │ HTTPS / Tailscale
          ▼
Android app
  └─ native shell + WebView
```

The Android app must not move server-side business logic into the APK without a specific reason. Preserve the current thin-client architecture.

Current service selection and navigation behavior is documented in `android/NAVIGATION.md`.

## 3. MacBook server workflow

The main Workbench server can be prepared and started from the repository root:

```bash
source ./activate_venv.sh
python run_codex_chat_server.py
```

Default endpoint:

```text
http://localhost:3000
```

A custom port can be used when needed:

```bash
python run_codex_chat_server.py --port 3100
```

or:

```bash
./run_codex_chat_server.sh --port 3100
```

The MacBook can continue to host the runtime servers regardless of whether the APK is built locally or by GitHub Actions.

## 4. Preferred Android development workflow with Codex

After cloning or pulling the repository on the MacBook, a suitable request to Codex is:

> Read `android/MACBOOK_CODEX_WORKFLOW.md`, `android/RELEASE_SIGNING.md`, and `android/NAVIGATION.md`. Inspect the current `main` source before changing anything. Implement the requested Android change, preserve the thin-client/server architecture and existing navigation behavior unless the task changes it, build and validate the app, review the diff, and report the resulting commit and APK path. Do not expose or commit signing secrets.

For each Android task, Codex should follow this sequence:

1. Confirm the checkout is current and inspect uncommitted changes.
2. Read the actual Android source instead of relying on old assumptions.
3. Make the smallest coherent change.
4. Keep `applicationId` stable: `com.yjkim9670.codexworkbench`.
5. Increment the user-visible app version for feature/fix releases when appropriate.
6. Keep Android User-Agent version strings synchronized with the app version.
7. Build the debug APK for compile/runtime validation.
8. Build a signed release APK when stable signing material is available.
9. Verify the release signature.
10. Review `git diff` and `git status` before committing.
11. Commit with a clear message and push to `main` when that is the requested workflow.
12. Check GitHub Actions after an Android-related push.

Avoid broad startup/lifecycle refactors unless required. Existing crash recovery and server-selection-root navigation should remain intact unless the requested change explicitly modifies them.

## 5. Android toolchain

The repository CI currently standardizes on:

- JDK 17
- Gradle 8.13
- compile SDK 36
- target SDK 36
- min SDK 26

A local Mac build should use compatible versions.

### Debug validation build

From the repository root:

```bash
gradle -p android :app:assembleDebug --stacktrace
```

Output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

This debug APK is for validation. It is **not** the long-lived installation artifact because debug signing is not the stable update identity.

## 6. Stable release signing

In-place Android updates require all of the following:

1. the same `applicationId`,
2. the same signing certificate,
3. a greater `versionCode` than the installed build.

The permanent release keystore is private material and must never be committed to this repository.

The repository ignores local signing material under `android/.signing/`, plus `*.jks` and `*.keystore` files.

See `android/RELEASE_SIGNING.md` for the canonical signing procedure.

### Local release build on the MacBook

Keep the keystore outside the repository, for example:

```text
~/private/codex-signing/codex-workbench-release.jks
```

Set the required environment variables in the shell without committing them:

```bash
export ANDROID_KEYSTORE_FILE="$HOME/private/codex-signing/codex-workbench-release.jks"
export ANDROID_KEYSTORE_PASSWORD='YOUR_PRIVATE_PASSWORD'
export ANDROID_KEY_ALIAS='codex-workbench'
export ANDROID_KEY_PASSWORD="$ANDROID_KEYSTORE_PASSWORD"
```

Then build:

```bash
gradle -p android :app:assembleRelease --stacktrace
```

Output:

```text
android/app/build/outputs/apk/release/app-release.apk
```

Verify the signature before distributing the APK. Example when `apksigner` is available on `PATH`:

```bash
apksigner verify --verbose --print-certs \
  android/app/build/outputs/apk/release/app-release.apk
```

Never paste the keystore password into tracked files, source code, issue bodies, commits, or logs.

## 7. GitHub Actions build

Workflow:

```text
.github/workflows/android-apk.yml
```

Android-related pushes and manual workflow dispatches can build the app.

Artifacts are intentionally separated:

```text
codex-workbench-android-debug-validation-only
    compile/validation artifact only

codex-workbench-android-release
    stable signed installation/update artifact
```

The release artifact is created only when these repository Actions secrets are configured:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`

The workflow fixes the alias to:

```text
codex-workbench
```

It reconstructs the JKS only inside the ephemeral runner, builds `assembleRelease`, verifies it using `apksigner`, and uploads the signed release APK.

Use `codex-workbench-android-release` for normal device installation after stable signing has been established.

## 8. First migration and later updates

An already-installed old debug build may use a different signing certificate. Android will refuse an update signed by a different certificate even when the package name and version are correct.

Therefore:

- Moving from an old debug-signed installation to the permanent stable release may require one final uninstall/reinstall.
- After the stable release is installed, preserve the same release JKS permanently.
- All later release APKs signed with that JKS and a higher `versionCode` should update the installed app in place.
- Losing or replacing the key breaks that update chain.

Back up the permanent JKS securely in at least two private locations.

## 9. Security / app protection policy

Do not attempt to evade, disable, disguise, or bypass security-product detection.

For security scanners or Samsung/Android app-protection systems, reduce false positives through normal software-distribution practices:

- use a stable release signing identity,
- use release builds for installation,
- keep permissions minimal,
- avoid unnecessary packers, dynamic code loading, or suspicious obfuscation,
- keep package identity and signing certificate stable,
- use standard HTTPS/Tailscale connectivity,
- verify APK signatures and provenance.

Security-product evasion is not part of this project plan.

## 10. Source-control completion checklist

Before a task is considered complete, verify:

```bash
git status --short --branch
git diff --check
git log --oneline -5
```

For Android source changes, also verify at least the debug build:

```bash
gradle -p android :app:assembleDebug --stacktrace
```

If stable signing material is available, additionally build and verify the release APK.

After pushing Android changes, confirm the `Android APK` GitHub Actions workflow succeeds. A validation-only debug artifact is not a substitute for the stable release artifact when the task is to produce an installable/updateable production APK.

## 11. Expected handoff report from Codex

At the end of a MacBook Codex task, report:

- branch and final commit SHA,
- files changed and behavioral summary,
- version name / version code if changed,
- local build command and result,
- release signing verification result when applicable,
- resulting APK path,
- GitHub Actions run/result if pushed,
- any manual step still required.

Do not claim a release artifact exists when signing material was unavailable.

## 12. Related documents

- `README.md` — Workbench server setup and runtime information
- `android/NAVIGATION.md` — Android server-selection and Back behavior
- `android/RELEASE_SIGNING.md` — stable APK signing and update-chain details
- `.github/workflows/android-apk.yml` — canonical CI build implementation
