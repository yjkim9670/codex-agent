# OpenCode Server 백엔드 (Windows)

Workbench는 `opencode run`을 채팅마다 실행하지 않고, 이미 실행 중인
`opencode serve`에 로컬 HTTP와 SSE로 연결한다. Codemate 인증은 OpenCode의
기존 `auth.json`과 provider 설정이 처리하며 Workbench에 API 키를 넣지 않는다.

## 실행

Workbench와 같은 Windows 사용자 계정의 PowerShell에서 OpenCode를 한 번 실행한다.
추가된 실행 스크립트는 `PATH`와 일반적인 npm 설치 경로에서 OpenCode를 찾아,
이미 사용 중인 포트는 시작 전에 알려 준다.

```powershell
.\run_opencode_server.ps1
```

기본값은 로컬 전용 `127.0.0.1:4096`이다. 다른 포트를 쓸 때는 Workbench의
`CODEX_OPENCODE_SERVER_URL`도 같은 주소로 맞춘다.

```powershell
.\run_opencode_server.ps1 -Port 4097
```

다른 PowerShell 창에서 연결과 provider를 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:4096/global/health
Invoke-RestMethod "http://127.0.0.1:4096/provider?directory=$([uri]::EscapeDataString((Get-Location).Path))" |
    ConvertTo-Json -Depth 20
```

`codemate`와 `CodeLLMPro`가 보이면 Workbench 실행 환경을 설정한다.

```powershell
$env:CODEX_AGENT_BACKEND_OPTIONS = "dtgpt,claude,opencode"
$env:CODEX_OPENCODE_SERVER_URL = "http://127.0.0.1:4096"
$env:CODEX_OPENCODE_MODEL = "codemate/CodeLLMPro" # 서버가 일시적으로 조회되지 않을 때의 선택 목록 fallback
.\run_codex_chat_server_company.ps1
```

Workbench 설정에서 Backend를 `OpenCode`로 선택한다. 모델 목록은 서버의
`/provider` 응답에서 갱신되며, 모델을 선택하면 `provider/model` 형태로
OpenCode에 전달된다.

## 동작과 중지

각 Workbench 응답은 임시 OpenCode 세션 하나를 만들고, 전체 Workbench 문맥을
전송한 뒤 `/event` SSE를 화면 스트림으로 변환한다. 응답 완료 후 Workbench는
해당 세션만 끝내며 `opencode serve`는 계속 실행된다. Workbench의 중지 버튼은
그 임시 세션에 `abort`를 요청한다.

`OpenCode Server에 연결할 수 없습니다` 오류가 나오면 서버가 같은 사용자로
실행 중인지와 `CODEX_OPENCODE_SERVER_URL` 포트가 일치하는지 먼저 확인한다.
