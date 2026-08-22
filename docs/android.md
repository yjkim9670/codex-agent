# 코덱스 워크벤치 Android

Android 앱은 기존 Codex Workbench 서버를 그대로 사용하는 thin client입니다. Codex CLI, workspace, Git, terminal 및 인증 정보는 Workbench host에 유지되고 Android에서는 WebView와 모바일 기능만 담당합니다.

## Workbench connection modes

앱 시작 후 5개 Codex Workbench 또는 `Mac Process Dashboard`를 선택합니다. 기본 선택은 Common TG입니다. 접속 방식은 `Funnel`과 `Tailscale 내부 접속` 두 가지이며, 기본값은 기존과 동일한 Funnel입니다.

| Service | Funnel | Tailscale direct |
|---|---|---|
| Common TG Codex Workbench | `https://dinya.wind-mintaka.ts.net/tg/` | `http://dinya.wind-mintaka.ts.net:3000/` |
| Finance Codex Workbench | `https://dinya.wind-mintaka.ts.net/finance-codex/` | `http://dinya.wind-mintaka.ts.net:3001/` |
| Local Codex Workbench | `https://dinya.wind-mintaka.ts.net/local/` | `http://dinya.wind-mintaka.ts.net:3002/` |
| Constraint Codex Workbench | `https://dinya.wind-mintaka.ts.net/constraint/` | `http://dinya.wind-mintaka.ts.net:3003/` |
| Dev Codex Workbench | `https://dinya.wind-mintaka.ts.net/dev/` | `http://dinya.wind-mintaka.ts.net:3004/` |
| Mac Process Dashboard | `https://dinya.wind-mintaka.ts.net/` | `http://dinya.wind-mintaka.ts.net:18000/` |

Funnel은 외부에서 접근할 수 있고, Tailscale 모드는 Android 기기가 tailnet에 연결된 상태에서 MagicDNS host와 각 서비스 포트로 직접 접근합니다. 선택한 접속 방식은 SharedPreferences에 저장되고 다음 실행에도 유지됩니다.

선택된 URL은 WebView뿐 아니라 same-origin 판정, 인증 cookie, DownloadManager에 동일하게 사용합니다. Codex Workbench에서는 background completion monitor API에도 같은 URL을 사용합니다. 따라서 Funnel과 Tailscale 주소가 한 세션에서 섞이지 않습니다. Tailscale direct 연결이 실패하면 앱은 자동으로 Funnel로 전환하지 않고 Tailscale 연결 상태를 확인하거나 Funnel 모드로 전환하라는 안내를 표시합니다.

`Mac Process Dashboard`는 일반 관리 페이지로 취급하며 Codex 전용 `/api/codex/streams` polling, 세션 완료 알림, Work Mode 활성화, prompt safe-area CSS injection 대상에서 제외합니다.

앱은 OpenAI/GitHub/Workbench 비밀키를 APK에 포함하지 않습니다.

## Mobile defaults

- 상태바, display cutout, navigation/gesture 영역에 Android `WindowInsets` 기반 safe area를 적용합니다.
- WebView text zoom 기본값은 85%입니다.
- 설정에서 text zoom을 60~125%, 5% 단위로 변경할 수 있습니다.
- text zoom 설정은 저장되며 현재 열린 WebView에도 즉시 적용됩니다.
- 설정에서 `85%로 초기화`할 수 있습니다.
- Codex Workbench 페이지 로딩 후 `codex-work-mode-toggle`을 찾아 작업모드를 기본으로 활성화합니다.
- 파일 선택은 Android document picker를 사용합니다.
- 다운로드는 Android DownloadManager를 사용합니다.
- 서버 선택 화면에서 `Mac Process Dashboard`는 최상단 `시스템 대시보드` 그룹에 별도로 표시하고, 5개 Codex Workbench는 그 아래 `Codex Workbench` 그룹에 표시합니다.
- Mac Process Dashboard의 `target="_blank"` / `window.open()` 요청은 외부 브라우저로 보내지 않고 앱 내부 `DashboardBrowserActivity`의 독립 WebView 인스턴스로 엽니다. 각 인스턴스는 자체 뒤로가기/새로고침/닫기와 추가 popup 생성을 지원합니다. Codex Workbench WebView의 기존 popup 정책은 변경하지 않습니다.

## Native UI

네이티브 UI는 별도 font binary 없이 Android `sans-serif` 계열을 사용하고, 밝은 canvas / rounded card / primary action 구조를 사용합니다. 앱 이름은 `코덱스 워크벤치`입니다.

서버 선택 화면에는 `Tailscale 내부 접속` 토글이 있으며, 각 서비스 card에 현재 선택된 방식의 실제 URL을 표시합니다. Workbench 또는 Dashboard toolbar에도 현재 `Funnel` 또는 `Tailscale` 모드를 표시합니다.

## v1.1.6 crash-safe recovery mode

일부 Galaxy 기기에서 앱 실행 직후 Activity가 종료되는 문제를 ADB 없이도 확인할 수 있도록 시작 구조를 단순화했습니다.

- AndroidManifest에서 custom `Application` 등록을 제거했습니다. 따라서 `MainActivity` 이전에 프로젝트 고유 startup 코드가 실행되지 않습니다.
- `MainActivity`는 가장 먼저 최소 root view를 만들고 이후 초기화 과정에서 예외가 발생하면 앱을 종료하지 않고 복구 화면으로 전환합니다.
- splash → Workbench 선택 화면 전환, WebView 생성, 설정 화면, background monitor lifecycle 호출을 각각 방어적으로 처리합니다.
- uncaught exception이 남는 경우 예외 class/message와 첫 번째 Workbench stack frame을 SharedPreferences에 짧게 기록합니다.
- 다음 실행에서 저장된 오류가 있으면 `코덱스 워크벤치 복구 모드` 화면을 열어 ADB 없이 오류 종류를 볼 수 있습니다.
- 복구 화면에서 `기본 설정으로 다시 시작` 또는 `저장된 앱 설정 초기화`를 선택할 수 있습니다.

이 기능은 logcat 전체 stack trace를 대체하지는 않지만, 특정 기기에서만 발생하는 startup crash를 사용자 화면에서 좁힐 수 있게 합니다.

## 작업 완료 알림

설정 화면에서 `작업 완료 알림`을 켜거나 끌 수 있습니다.

이 기능은 FCM 같은 외부 push 서버가 아니라 Android 로컬 foreground monitor 방식이며 Codex Workbench에서만 사용합니다. Mac Process Dashboard에서는 시작하지 않습니다.

1. 사용자가 Workbench에서 작업을 시작합니다.
2. 앱이 실제로 백그라운드로 전환될 때 현재 WebView 인증 쿠키를 메모리로만 foreground service에 전달합니다.
3. service는 현재 선택한 접속 방식의 `/api/codex/streams?include_done=1`을 5초 간격으로 확인합니다.
4. 실행 중이던 stream과 pending queue가 모두 끝나면 세션 제목을 포함한 `작업 완료` Android 알림을 시도합니다.
5. 완료되거나 실행 중인 작업이 확인되지 않으면 service는 자동 종료합니다.

foreground monitor 알림은 별도 minimum-importance silent channel을 사용하고 기존 `작업 완료를 확인하는 중` 문구는 표시하지 않습니다. 인증 쿠키는 앱 설정이나 파일에 별도로 저장하지 않습니다. Android 13 이상에서는 알림 권한이 필요합니다.

## Build

현재 Android client source fallback 버전은 `1.1.10` (`versionCode 12`)입니다. GitHub Actions에서는 run number를 versionCode로 사용해 자동 증가시킵니다.

- Android Gradle Plugin 8.11.1
- Kotlin 2.1.20
- Gradle 8.13
- JDK 17
- compileSdk / targetSdk 36
- minSdk 26

```bash
gradle -p android :app:assembleDebug
```

APK 출력 위치:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

GitHub Actions의 `Android APK` workflow도 동일한 debug APK를 artifact로 업로드합니다.

## Stable in-place updates

고정 release key를 GitHub Actions Secret으로 설정하면 같은 application ID와 같은 서명 인증서를 유지한 release APK를 만들 수 있습니다. 이후 versionCode가 증가하는 APK는 앱을 삭제하지 않고 기존 설치본 위에 업데이트할 수 있습니다.

필요한 secrets:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

자세한 설정은 `android/RELEASE_SIGNING.md`를 참고합니다.

## Security

- APK에 OpenAI/GitHub/Workbench credentials를 넣지 않습니다.
- WebView 인증 쿠키는 Android WebView가 관리합니다.
- background completion monitor에 넘기는 쿠키는 메모리로만 전달하며 별도 파일에 저장하지 않습니다.
- SSL 오류 우회 및 자동 HTTP Basic credential 제출을 사용하지 않습니다.
- `addJavascriptInterface` bridge를 사용하지 않습니다.
- Tailscale direct URL은 HTTP이지만 tailnet 내부 통신을 전제로 하며, 앱은 Tailscale VPN 자체를 우회하거나 자동 연결하지 않습니다.
