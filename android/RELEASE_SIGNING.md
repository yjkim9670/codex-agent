# Stable Android APK signing and in-place updates

Android only installs a new APK over an existing app when all of the following remain true:

1. `applicationId` is unchanged (`com.yjkim9670.codexworkbench`).
2. The new APK is signed by the same app-signing certificate.
3. `versionCode` is greater than the installed version.

This project now supports a stable release-signing key through GitHub Actions secrets. Never commit the `.jks` file or its passwords to this public repository.

## One-time keystore creation

Run this on a trusted local machine with JDK 17+ installed:

```bash
keytool -genkeypair \
  -v \
  -keystore codex-workbench-release.jks \
  -alias codex-workbench \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10950
```

Use strong passwords and keep the keystore backed up in at least two secure locations. Losing this private key means future APKs cannot update the existing sideloaded installation.

## GitHub Actions secrets

In the GitHub repository, open:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Add these four secrets:

- `ANDROID_KEYSTORE_BASE64`: Base64-encoded contents of `codex-workbench-release.jks`
- `ANDROID_KEYSTORE_PASSWORD`: keystore password
- `ANDROID_KEY_ALIAS`: `codex-workbench` (or the alias chosen above)
- `ANDROID_KEY_PASSWORD`: private-key password

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

Every Android CI run still builds a debug APK for compile validation.

When all four signing secrets exist, the workflow also:

1. reconstructs the keystore only inside the ephemeral runner,
2. builds `assembleRelease`,
3. verifies the APK signature with `apksigner`, and
4. uploads artifact `codex-workbench-android-release`.

Only the `codex-workbench-android-release` artifact should be used for the long-lived installed app.

## One-time migration from old debug builds

Existing v1.1.3 and earlier APKs were CI debug builds. Their signing certificate is not guaranteed to match the new stable release certificate.

Therefore the first stable release APK may require one final uninstall of the old debug build before installation. After the stable release is installed, subsequent release APKs can update it in place as long as the same signing key is preserved and `versionCode` keeps increasing.

Do not rotate the signing key casually. Android compares the installed certificate to the update certificate before allowing an in-place update.
