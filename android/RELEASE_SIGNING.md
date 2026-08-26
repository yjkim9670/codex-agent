# Stable Android APK signing and in-place updates

Android only installs a new APK over an existing app when all of the following remain true:

1. `applicationId` is unchanged (`com.yjkim9670.codexworkbench`).
2. The new APK is signed by the same app-signing certificate.
3. `versionCode` is greater than the installed version.

This project uses one long-lived release-signing key for installable builds. Never commit the `.jks` file, its Base64 representation, or its password to this public repository.

## One-time keystore creation

Create the signing key on a trusted machine with JDK 17+:

```bash
keytool -genkeypair \
  -v \
  -storetype JKS \
  -keystore codex-workbench-release.jks \
  -alias codex-workbench \
  -keyalg RSA \
  -keysize 4096 \
  -validity 36500
```

Use one strong password for both the keystore and private key. Keep the keystore backed up in at least two secure locations. Losing this private key means future APKs cannot update the existing sideloaded installation.

## GitHub Actions secrets

The workflow intentionally fixes the key alias to `codex-workbench` and reuses the keystore password as the key password. Only two repository secrets are required:

- `ANDROID_KEYSTORE_BASE64`: Base64-encoded contents of `codex-workbench-release.jks`
- `ANDROID_KEYSTORE_PASSWORD`: keystore/private-key password

In GitHub, open:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Generate the Base64 value without line wrapping:

### PowerShell

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("codex-workbench-release.jks")) | Set-Clipboard
```

### Linux/macOS

```bash
base64 < codex-workbench-release.jks | tr -d '\n'
```

## CI behavior

Every Android CI run builds a debug APK only for compile validation. It is uploaded as:

`codex-workbench-android-debug-validation-only`

Do not use that artifact as the long-lived installed app. GitHub-hosted debug signing identities are not the stable update identity for this project.

When both signing secrets exist, the workflow also:

1. reconstructs the keystore only inside the ephemeral runner,
2. validates the fixed `codex-workbench` alias,
3. builds `assembleRelease`,
4. verifies the APK signature with `apksigner`,
5. records the signing-certificate information in the workflow summary, and
6. uploads `codex-workbench-android-release` with 90-day artifact retention.

Only `codex-workbench-android-release` should be used for normal device installation after migration.

## One-time migration from old debug builds

Previously installed CI debug APKs may have a different certificate from the stable release key. Android cannot replace an installed package when the certificates differ, even if the package name is identical and the version number is newer.

Therefore the first migration to the stable release certificate can require exactly one uninstall of the old debug-signed app. After the stable release APK is installed, subsequent `codex-workbench-android-release` APKs update it in place as long as:

- the same release keystore is preserved,
- the package name remains unchanged, and
- the CI `versionCode` continues to increase.

Do not rotate the signing key casually.

## Certificate verification

To inspect the release certificate locally:

```bash
apksigner verify --verbose --print-certs app-release.apk
```

Record the SHA-256 certificate digest from the first stable release and compare it whenever the signing setup changes. A different certificate digest means Android will treat the APK as a different signing identity and refuse an in-place update.
