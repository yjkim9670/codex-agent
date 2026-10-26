# codex-workbench

Codex Workbench server for coding-agent chat sessions (Codex, Claude, and OpenCode), workspace files, terminal sessions, Git sync, and usage monitoring.

## Requirements
- Python 3.14.x for the macOS/Linux launchers and agent children. The Windows company launcher and its agent children support Python 3.10+.
- The selected agent CLI available on PATH: Codex (`codex` / `codex.cmd`), Claude (`claude`), or OpenCode (`opencode`). Backend-specific setup and command options still apply.

Set `CODEX_CLI_BIN=/absolute/path/to/codex` when the CLI is installed outside
`PATH`. Launchers prefer standalone installs under `.local/bin` and npm prefix
paths before falling back to the macOS Codex app bundle, which can lag behind
standalone CLI releases.

Conversation context and selection records: [agent-context.md](docs/agent-context.md).

## Setup
```bash
source ./activate_venv.sh
```

`activate_venv.sh` validates Python 3.14.x and exports it as `CODEX_PYTHON_BIN`, `PYTHON_BIN`, and `PYTHON`. The launcher places that executable first on `PATH`, including for `codex exec` children.

On Windows, `run_codex_chat_server_company.ps1` exports the actual Python executable selected by `py`/`python` to these variables. Children reuse that installation. Without an explicit setting, children also check the running server's `sys.executable` before searching other installations. An explicit Python setting must point to a compatible executable (not a command such as `py -3`). Failed runtime checks report the candidate and failure reason; each version probe has a five-second timeout.

## Run
```bash
python run_codex_chat_server.py
```

The server listens on `http://localhost:3000`.

Run with a custom port:
```bash
python run_codex_chat_server.py --port 3100
```

Or with the helper script:
```bash
./run_codex_chat_server.sh --port 3100
```

The helper launcher also uses `../.venv`.

## Android Development on MacBook

For the canonical MacBook + Codex workflow, Android build/release procedure,
GitHub Actions handoff, and stable signing/update policy, read:

- [`android/MACBOOK_CODEX_WORKFLOW.md`](android/MACBOOK_CODEX_WORKFLOW.md)
- [`android/RELEASE_SIGNING.md`](android/RELEASE_SIGNING.md)
- [`android/NAVIGATION.md`](android/NAVIGATION.md)

The MacBook is the runtime host for Workbench services. The Android app remains
a thin native/WebView client and may be built either locally on the MacBook or
through the repository's `Android APK` GitHub Actions workflow.

## Team mode

The composer menu offers `Work / Plan / Plan+ / Sec / Team`. Shift+Tab toggles
only `Work ↔ Plan`; Plan+, Sec and Team return to Work. Sec directly executes
with the secondary model. Team currently supports only the Codex backend.
Set a secondary model in execution settings before using it.
The main model analyzes the request, up to four secondary workers run sequentially,
and the main model verifies the actual changes and finishes the request.
Secondary model settings remain available for Sub jobs and commit messages.

See [Team execution](docs/team-mode.md) for state, cancellation, and recovery details.

## Codex CLI Stability Options
Workbench serializes mutable, interactive `codex exec` runs per workspace by
default. Read-only subjobs and structured reports can still run in parallel.
The workspace gate uses `.agent_state/codex_interactive_exec.lock`, so two
Workbench server processes aimed at the same workspace do not run interactive
agents at the same time.

For temporary debugging only, set `CODEX_CLI_EXEC_LOCK=1` to serialize every
`codex exec` child process, including read-only jobs, with a user-level lock
file. This can reduce CLI event-stream queue pressure, but it also makes all
Workbench instances that share the same lock wait for one another. The older
`CODEX_CLI_SERIALIZE_EXEC` variable is ignored by current server code.

If the provider is slow to produce a final response after retries, increase
`CODEX_STREAM_FINAL_RESPONSE_TIMEOUT_SECONDS` from the default.

## Codex CLI Self Protection
Set `CODEX_CLI_SELF_PROTECT=1` to run only the Codex CLI child process with
Workbench/agent paths mounted read-only. Other Workbench APIs remain unchanged.

On Linux this uses `bwrap`. Linux hosts must have bubblewrap installed or
available on `PATH`; otherwise Codex CLI startup fails fast. On non-Linux hosts
the flag is ignored with a warning because bubblewrap is Linux-only.

By default it protects this Workbench checkout and an adjacent `codex_agent`
directory when present. Add comma-separated extra paths with
`CODEX_CLI_PROTECTED_PATHS=/path/to/codex_agent,/path/to/other`. Set
`CODEX_CLI_SELF_PROTECT_GIT_RW=1` to keep those protections but re-bind
protected `.git` directories read-write for Codex CLI git operations.

## Git Sync Script
`z00_sync_git.py` is included for branch sync/mirror workflows.

Run:
```bash
python z00_sync_git.py
```

Protection rules are read from `sync_protect.list`.

## GUI
- `http://localhost:<port>/` serves the chat UI.
- `http://localhost:<port>/health` returns JSON status.

## File Download And Mail Limits
- File preview downloads are limited by `CODEX_FILE_MAX_SINGLE_DOWNLOAD_BYTES`
  for one file and `CODEX_FILE_MAX_ARCHIVE_DOWNLOAD_BYTES` for multi-file or
  folder zip downloads. Defaults are 64MB and 128MB; each can be raised up to
  512MB.
- Mail delivery uses `CODEX_MAIL_MAX_ARCHIVE_BYTES` for the generated zip
  attachment. The default is 20MB and the application cap is 128MB, but the
  SMTP provider can still reject attachments below that value.
- These limits exist because the current download and mail paths build the
  response/archive in server memory before the browser or SMTP server receives
  it. Going beyond these caps should use a streaming download or temporary-file
  archive flow instead of only raising environment variables.

## Tailscale Code Server Access
The deployment split artifacts were removed. The remaining remote-access helper is:

- `deploy/tailscale/expose_code_server.sh`

Expose `code-server` on the tailnet:

```bash
./deploy/tailscale/expose_code_server.sh 8080
curl -I https://<machine>.<tailnet>.ts.net:8080/
```

If `serve config denied` appears:

```bash
sudo tailscale set --operator=$USER
```

Keep `8080` reserved for `code-server`. A successful remote check typically returns `302` with `location: ./login`.

## Codex Token Monitoring
- Codex usage tracks prompt/response tokens separately (`input_tokens`, `output_tokens`) plus `cached_input_tokens`. The UI displays uncached input (`input_tokens - cached_input_tokens`), cached input, and output separately.
- Aggregated counters are stored at `<repo>/workspace/.agent_state/codex_token_usage.json` (default parent-workspace mode).
- `GET /api/codex/usage` returns both rate-limit info and `token_usage` summary (`today`, `all_time`, `recent_days`).

## Browser Verification

The model settings card exposes `Auto`, `Browser`, and `Off` verification modes.
`Auto` adds browser instructions only for UI-changing requests, `Browser` always
adds them, and `Off` omits them. The injected instruction points to one stable
runner invocation:

```bash
python3.14 scripts/verify_browser_ui.py --url http://127.0.0.1:3100 --selector body
```

The runner invokes the project-local pinned Playwright CLI once with headless Chromium and a
temporary profile. It checks HTTP status, the requested DOM selector, console
errors, and page errors. Screenshots and artifacts are retained only when the
check fails. Use an unused local port and leave active Workbench processes
running during verification.

Install the pinned browser runtime once after cloning or updating this folder:

```bash
npm install
npm run playwright:install
```

### 자동 사용량 대시보드

화면 설정의 **사용량 통계 열기**에서 새 탭으로 열거나 `/usage`에서 확인합니다. 기본 조건은 최근 30일,
medium, 활성 계정, 전체 환경입니다. Apple 스타일과 로컬 IBM Plex Sans KR을
사용하며 5시간/주간 차감 비교, 날짜별 토큰/한도 그래프, 상세 표, 수집 상태와
계정 조회값 차이를 제공합니다. 그래프 데이터는 표로도 열람할 수 있습니다.

서버 시작 시 수집하고 이후 5분마다, 실행 기록 저장 후에도 재대조합니다.
기존 계정 한도 조회 주기를 유지하며 화면은 1분마다 갱신됩니다. 여러 서버는
계정별 파일 잠금을 공유합니다. 수집 결과는 공용 계정 디렉터리의
`codex_usage_collection.json`에 저장하고 한국시간 90일 범위로 유지합니다.
원장/세션 DB/실행 JSONL 원본은 변경하지 않습니다.

기본 탐색 범위는 로그인 사용자의 `~/works`, 기존 원장에 기록된 환경 경로,
등록 계정의 Codex 홈입니다. 추가 탐색 루트는 `CODEX_USAGE_DISCOVERY_ROOTS`로
지정합니다(여러 경로는 OS의 경로 구분자 사용, macOS/Linux에서는 `:`).
현재 계정과 동일한 provider account ID가 확인된 Codex 홈만 수집합니다.
내부 다중 사용자 모드는 각 사용자의 활성 컨텍스트/작업 경로로 제한합니다.
다른 PC/클라우드 기록은 수집하지 않습니다.

100만 토큰당 차감은 **검증 구간의 차감 합계(%p) / 검증 토큰 합계 × 100만**입니다.
공식 환산율이 아닌 관측 추정치이며, 서로 다른 모델/effort, 동시 실행, 리셋,
미완성 그룹, 관측 누락은 제외합니다. 표본이 3개 미만이면 관측 부족으로 표시합니다.
전체 effort를 선택하면 모델/effort 조합을 나누어 표시합니다. 필터 밖의 실행도
동시 실행 검증에 포함합니다. 기존 CLI도 `--effort medium`과
`--environment <workspace_path>` 필터를 지원합니다.

세션 로그의 누적 토큰을 차분하여 실행별로 수집하고 thread/turn ID로 중복을
제거합니다. 원장과는 환경/모델/effort/토큰 구성/종료 시각의 고유 일치로
대조합니다. 모호하거나 서로 다른 토큰이 같은 시각에 기록된 경우는 추가
집계하지 않고 검토 필요량에 표시합니다. 로그가 없는 DB 누적값은 미배분
잔액으로 표시하며, 날짜별/모델별 통계와 차감률 분모에 임의로 넣지 않습니다.
계정 인증 미확인, 파싱 오류, 포크의 상속 토큰도 수집 상태에서 확인합니다.
계정 조회 차이는 필터와 무관하게 전체 환경/전체 effort의 수집 원장과 비교합니다.
기존 계정 조회 차이 추적 이력은 계속 유지됩니다.

코드 동기화 후 각 서버를 사용자가 재시작해야 자동 수집과 새 화면이 적용됩니다.
이 PC의 코드 수정 기준 경로는 `/Users/dinya/works/dev_workspace/codex_workbench/`이며,
다른 Workbench의 Git 동기화는 사용자가 진행합니다.

## TG Platform 문서 동기화

`/metadata-sync` 페이지에서 별도로 수동 문서 동기화를 실행할 수 있습니다.
자동·수동 경량작업은 블로그만 실행하며, TG Platform 문서 동기화는 포함하지 않습니다.
대시보드는 로컬 Paperlogy 글꼴을 사용합니다. 현재 수정 후보 영역에서는
마지막 성공 일일 배치의 HEAD 이후 커밋과 현재 작업 트리 변경, 오래된 번역을
기존 분석기로 조회합니다. feature별·과제별 후보 문서·선정 사유와 기타 범위 문서를 표시하며,
범위 선택 버튼으로 `feature:<이름>` 또는 `project:<과제명>` 수동 실행 입력을 채울 수 있습니다. 후보 조회는 모델·동기화 실행,
이력·상태 갱신 없이 수행하며 카탈로그 검증은 생략합니다. 실제 수정 여부는 실행 시 결정됩니다.
일일 launchd 배치와 Workbench 수동 실행의 최근 200건, 실행 결과, 수정 파일,
추가·삭제 줄 수, diff, 검증 로그, 작업 요약과 미반영 항목을 확인할 수 있습니다.
기존 로그에 diff가 없으면 상세 변경 기록이 없는 실행으로 표시합니다.
내부 다중 사용자 모드에서는 관리자만 공유 CommonTG 프로젝트에 접근합니다.

수동 실행은 `feature:vcd`, `design_tool:tg_sim_manager`, `project:HPA`처럼
좁은 범위를 지정합니다. Workbench는 기존 CommonTG
`git_actions/scripts/run_metadata_doc_sync.py --mode manual --scope <범위>`를
호출합니다. 일정 등록과 블로그 파이프라인 설정은 이 페이지에서 변경하지 않습니다.
기존 KST 자정 일일 배치는 동일한 실행기의 강화된 검증과 기록을 사용합니다.

CommonTG 실행기는 임시 Git worktree에 현재 로컬 변경을 복사해 작업합니다.
후보 문서 디렉터리의 메타데이터 Markdown만 반영하며, 버전 참조 변경,
레지스트리·코드 수정, 문서 삭제, 빈 문서, 카탈로그 검증 실패 또는 실행 중
원본 문서 충돌을 발견하면 반영을 차단합니다. 버전 검사는 보수적으로 동작하므로
새 버전 번호를 문서에 추가하는 작업도 별도 릴리스 작업으로 처리해야 합니다.
실행 기록은 CommonTG의 `.sync_runtime/codex_daily_doc_sync/runs/<실행 ID>/`에
저장됩니다. `run_metadata.json`에는 실제 diff와 검증 결과가 포함됩니다.

기본 CommonTG 경로는 `/Users/dinya/works/Sensor_Projects/CommonTG-Verification-Platform`입니다.
다른 서버에서는 `CODEX_COMMONTG_ROOT`로 저장소 경로를 지정하고 강화된 CommonTG
실행기도 함께 배포해야 합니다. 실행 권한과 Codex CLI 인증은 서버 계정을 사용합니다.
실행이 비정상 종료되어 `run.lock`이 남으면 기존 실행 종료 여부를 확인한 뒤 관리자가
잠금을 정리해야 합니다. 실행 중인 Workbench 서버는 자동 재시작하지 않습니다.
대시보드 API 요청은 캐시를 사용하지 않으며, HTML 오류·로그인 페이지를 받으면
JSON 파싱 오류 대신 HTTP 상태와 서버·접속 주소·권한 확인 안내를 표시합니다.
업데이트 후에는 해당 Workbench 서버를 재시작하고 대시보드를 새로고침해야 합니다.
