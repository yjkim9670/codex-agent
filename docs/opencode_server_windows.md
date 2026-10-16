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

## 사내 오류·대기 처리

안전장치는 사내에서 선택하는 `opencode` 백엔드에 적용된다. 외부 Codex CLI의
실행·시간 제한·종료 처리는 기존 동작을 유지한다.

- 해당 세션의 `session.error`는 완료 이벤트 없이도 실패로 종료한다.
- SSE 구독 연결 후 prompt를 한 번 제출한다. 실행 전 초기 idle과 다른 세션의
  오류, 세션 ID 없는 전역 알림은 현재 작업을 종료시키지 않는다.
- SSE 단절과 이벤트 누락 시 메시지·상태 조회로 결과를 회수한다. 조회가 실패해도
  prompt를 자동 재제출하지 않으며, 시간 제한 안에서 종료한다.
- heartbeat와 동일한 메시지의 반복 조회는 유효한 진행으로 계산하지 않는다.
- Workbench 종료 상태와 대기열 처리를 원격 세션 삭제보다 먼저 수행한다.
  결과 저장 실패는 스트림 오류와 서버 로그에 남기고 다음 요청을 처리한다.
- 성공한 세션은 별도 스레드에서 삭제한다. 실패·시간 초과·취소 세션은 abort를
  시도하고 삭제하지 않아 DB 오류 조사에 필요한 기록을 보존한다. 보존 세션은
  운영자가 원격 실행 종료를 확인한 뒤 정리한다.

| 환경 변수 | 기본값 | 의미 |
|---|---:|---|
| `CODEX_OPENCODE_RUN_TIMEOUT_SECONDS` | 3600 | 세션 생성부터 전체 실행 상한(초) |
| `CODEX_OPENCODE_PROGRESS_TIMEOUT_SECONDS` | 600 | 메시지·도구 상태의 변화 없이 기다리는 상한(초) |
| `CODEX_OPENCODE_CLEANUP_TIMEOUT_SECONDS` | 5 | abort·삭제·복구 조회의 HTTP timeout(초) |

장시간 도구 실행은 진행 이벤트가 없으면 정체로 판정될 수 있다. 사내 실행 시간에
맞춰 값을 조정하고 Workbench 서버를 다시 시작한다. 기존 SSE 읽기 timeout은
`CODEX_OPENCODE_EVENT_TIMEOUT_SECONDS`로 별도 유지한다.

로그의 `stream`(Workbench 요청 ID), `session`(OpenCode 세션 ID), `reason`을
사용해 제출·오류·종료를 연결한다. 외래키 오류 자체의 원인은 OpenCode 버전과
서버 원본 로그에서 부모 session/message 생성, part 저장, abort/delete 순서를
대조해야 한다. 이 패치는 외래키 제약이나 DB 내용을 변경하지 않는다.

복구에 사용하는 API는 [OpenCode 서버 문서](https://dev.opencode.ai/docs/server/)의
`GET /session/:id/message`와 `GET /session/status`다.

## 공통 실행 문맥과 백엔드 선택

Codex(DTGPT), Claude, OpenCode는 실행 직전에 최종 작업 경로, worktree 존재 여부,
첨부 파일과 공용 자료 경로를 같은 준비 함수에서 확인합니다. 대기열에는 제출 시점의
백엔드와 모델 설정을 저장하므로 설정을 바꿔도 이미 제출한 작업은 해당 백엔드로 실행됩니다.
기존 대기열 항목에 백엔드가 없으면 현재 설정을 사용하는 호환 동작을 유지합니다.

Workbench 서버 OS와 에이전트 도구의 OS·셸을 구분합니다. Windows만으로 PowerShell을
가정하지 않습니다. 운영 환경에서 실제 도구 셸을 확인한 경우에만 다음 환경 변수를
설정하세요. 이 변수들은 프롬프트 안내용이며 CLI 또는 OpenCode 서버의 셸을 변경하지 않습니다.

- `CODEX_WORKBENCH_CODEX_SHELL`: Codex/DTGPT 도구 셸 (예: `powershell.exe`, `pwsh`, `/bin/zsh`).
- `CODEX_WORKBENCH_CLAUDE_SHELL`: Claude 도구 셸.
- `CODEX_WORKBENCH_OPENCODE_SHELL`: OpenCode 서버의 도구 셸.
- `CODEX_WORKBENCH_OPENCODE_PLATFORM`: OpenCode 실행 호스트 플랫폼 (`win32`, `darwin`, `linux`). 미설정 시 `unknown`.

최종 경로·첨부 안내는 CLI 입력에 한 번만 추가됩니다. OpenCode에서는 실행 환경 안내를
[`system` 필드](https://dev.opencode.ai/docs/server/#messages)에, 사용자 요청과 역할별 대화 기록을
`parts`에 전달합니다. 세션 생성, 이벤트 구독, 프롬프트 제출, 상태 복구와 정리는 같은
`directory` 쿼리를 사용합니다. 동기 요청도 Codex CLI 대신 OpenCode API를 사용합니다.
Workbench와 OpenCode 서버는 전달된 작업·첨부·공용 경로에 접근할 수 있어야 합니다.
원격 서버의 경로 변환은 지원하지 않으며, 존재 확인은 Workbench의 파일 시스템 기준입니다.

대화 본문과 첨부 설명의 XML 태그는 이스케이프합니다. 본문에 `<message>`가 있어도
직렬화된 역할 경계를 만들 수 없지만, 이것만으로 모델의 지침 주입 방어를 보장하지는 않습니다.
셸 오류 시 부분 실행 여부를 확인하고 미완료 단계만 재시도하도록 안내합니다.
