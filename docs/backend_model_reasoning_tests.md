# 백엔드 모델/reasoning 실행 검사

## 기본 실행: 작업 상태와 무관한 세션 없는 검사 (2026-10-22)

기본 모드는 이제 `direct`다. 서버의 `/api/codex/settings`를 한 번 조회해 모델
카탈로그를 얻고, 이 PC에서 CLI/provider를 직접 실행한다. 활성 스트림 조회나
중단, 공용 설정 변경·복원, Workbench 채팅 세션 생성은 하지 않는다. 따라서
Workbench에서 다른 작업이 실행 중이어도 테스트할 수 있고 채팅 목록에 테스트
세션이 쌓이지 않는다. 모델 호출 비용과 로컬 CLI/provider 자원 사용은 발생한다.

```powershell
# 기존 기본 명령 그대로: OpenCode → Claude, Workbench 세션 생성 없음
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000
# 모든 모델/reasoning 조합
.\scripts\test_backend_model_reasoning.ps1 -All
```

```bash
python3 scripts/test_backend_model_reasoning.py --base-url http://127.0.0.1:5000 --all
```

서버는 카탈로그 조회용으로 접속 가능해야 한다. 모델 실행에는 **테스트를 실행하는
PC의** CLI·Python 의존성·인증·게이트웨이 환경이 쓰인다. 원격 서버의 저장 키가
클라이언트로 전달되지는 않는다. 사내 환경에서는 아래의 직접 실행용 키 설정을
따른다. 기본 모드에서는 서버 Key Pool을 HTTP 실행 요청으로 예약하지 않는다.
원격 서버와 다른 PC에서 실행하면 해당 PC의 실행 환경을 검사한다.

진행 표시, 실행별 타임아웃, 키 순환, stdout/stderr 진단, `case-NNN.jsonl`과
JSON/CSV 보고서는 유지한다. 기본 모드에는 세션 ID와 설정 복구 파일이 없다.
`summary.json`에 `mode=direct`, `workbench_settings_changed=false`,
`workbench_sessions_created=0`을 기록한다. Ctrl+C 시 로컬 자식 프로세스 트리를
종료한다. OpenCode provider 자체 세션은 Workbench 채팅 세션과 별개다.

기존 HTTP 통합 검사가 필요하면 `-Mode stream` 또는 `-Mode sync`를 명시한다
(Python: `--mode stream|sync`). 이 모드는 여전히 실제 Workbench 세션을 생성하고
공용 설정을 변경하므로 서버가 유휴 상태여야 한다. 아래의 기존 HTTP 예제에는
`-Mode stream`을 추가해야 한다. Context/Worktree/Queue 검사와 추가 비교용
`-Direct failed|all`도 HTTP 모드에서만 허용한다. 기본 모드는 CLI 인자와 응답을
검증하며 HTTP 큐·첨부·저장 경로를 검증하지 않는다. 기존 테스트 세션은 삭제하지
않는다. 스크립트 변경이므로 Workbench 서버 재시작은 필요 없다.


직접 실행의 Claude/Codex reasoning 검증은 실제 CLI 생성기가 사용하는 모델별
보정 함수를 적용한 예상값과 비교한다. 지원하지 않는 값의 기본값 대체나
`--effort` 생략은 보정 결과와 일치하면 통과한다. 실제 인자가 보정 결과와
다르면 CLI를 실행하지 않고 `failure_phase=cli_argument_validation`으로 실패한다.
`results.json`과 `case-NNN.jsonl`의 완료 기록에는 `cli_validation`의
`requested`(요청값), `expected`(보정 후 예상값), `actual`(실제 인자값),
`matches`를 저장한다. 이 기록은 CLI 실행 전에 flush하므로 시간 초과나
프로세스 실행 오류에도 수집되며, 전체 명령줄이나 환경변수는 포함하지 않는다.

## 키 설정과 명시적 HTTP 통합 모드 상세 (2026-10-22)

명시적 HTTP 검사(`stream`/`sync`)는 실제 Workbench API를 사용한다. 사내 Windows/Linux의
서버 설정 화면에 등록된 Key Pool을 실행 요청마다 예약·순환하며, 큐 작업도 등록 시
예약한 키를 유지한다. 클라이언트 셸의 환경변수는 이미 실행 중인 서버에 전달되지 않는다.
OpenCode는 Workbench와 동일하게 자체 provider 인증을 사용한다.

`-Direct` / `--direct`의 로컬 CLI 비교에 별도 키 풀을 쓰려면 현재 테스트 셸에 JSON
배열을 설정한다. Claude/Codex 직접 실행마다 등록 순서로 순환하고 새 스크립트 실행에서
첫 키로 돌아온다. OpenCode 실행은 이 순서를 소비하지 않는다. 실패 시 자동 재시도는 없다.

```powershell
$env:WORKBENCH_TEST_API_KEYS = '["key-1","key-2"]'
# 단일 키 대안 (명시적 테스트 풀이 없을 때 기존 자격 증명 우선순위의 fallback)
$env:DTGPT_API_KEY = "single-key"
```

```bash
export WORKBENCH_TEST_API_KEYS='["key-1","key-2"]'
export DTGPT_API_KEY="single-key"
```

둘 다 없으면 위 설정 예시를 터미널에 출력한다. HTTP 검사는 서버 저장 키만으로도
실행할 수 있으므로 환경변수가 없다는 이유로 중단하지 않는다. 잘못된 JSON 풀은
키 내용을 출력하지 않고 실행 오류로 처리한다. 값은 인자나 보고서에 기록하지 않으며
진단 본문에 나타난 개별 풀 키도 마스킹한다.

직접 비교는 현재 PC의 실행 환경이므로 **서버와 같은 Windows/Linux 사내 환경**에서
실행해야 한다. 명시적 테스트 풀은 `CODEX_COMPANY_MODE=1`인 Windows/Linux에서만
적용하며 Claude `native` 모드와 함께 사용하면 오류를 반환한다. 명시적 풀이 없으면
실제 서비스의 저장 Key Pool → 기존 자격 증명 resolver를 그대로 사용한다.
서버와 같은 저장 경로·게이트웨이·CLI·모델 환경변수를 준비해야 하며, 테스트 도구가
사내 서버 실행 스크립트를 호출하거나 그 기본값을 자동으로 주입하지는 않는다.
Windows 실행기는 기본 HTTPS cloud 게이트웨이, Linux 실행기는 기본 HTTP 사내
게이트웨이를 지정하므로 서로 같은 주소라고 가정하면 안 된다.

코드 대조에서 기존 직접 비교가 CLI 인자만 재사용하고 자식 프로세스 환경 구성을
누락한 것을 확인했다. 이제 `_build_agent_exec_env`와 `_apply_agent_backend_exec_env`도
재사용하여 예약 키를 Codex에 전달하고 Claude의 `ANTHROPIC_AUTH_TOKEN`, 게이트웨이 및
선택 모델 환경을 실제 스트림 실행과 같은 순서로 구성한다. 직접 비교는 여전히 간단한
echo CLI 호출이며 HTTP 큐·스트림 저장·관리자 인증까지 재현하는 검사는 아니다.
실제 사내망 연결과 Windows/Linux CLI 실행 검증은 해당 환경에서 수행해야 한다.

`scripts/test_backend_model_reasoning.ps1`이 PowerShell 진입점이며 같은 디렉터리의 Python 파일이 검사를 수행한다. PowerShell 5.1/7 및 Python 3.9 이상을 대상으로 작성했다. HTTP 검사는 Python 표준 라이브러리만 사용한다. 서버를 시작하거나 재시작하지 않는다.

```powershell
# 먼저 모델 카탈로그와 예상 호출 수 확인 (설정 변경/모델 호출 없음)
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000 -ListOnly

# 기본: Claude/OpenCode 대표 모델의 기본 reasoning, 총 최대 2회
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000

# 해당 백엔드의 모든 모델별 지원 reasoning 조합
.\scripts\test_backend_model_reasoning.ps1 -Backend opencode,claude -All -TimeoutSeconds 300

# 특정 모델/effort 선택, 실패 시 로컬 직접 실행과 비교
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -Model '실제-카탈로그-모델-ID' -Reasoning low,high -Mode stream -Direct failed

# 동기 API 경로
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -Mode sync

# 작업 경로 확인 + 한글/공백 파일명 첨부 읽기 (백엔드별 대표 조합)
.\scripts\test_backend_model_reasoning.ps1 -Mode stream -ContextChecks -ExpectedWorkspace 'C:\작업 폴더\workspace'

# 각각 추가 호출 발생. worktree는 실제 테스트용 worktree를 생성한다.
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -Mode stream -WorktreeCheck -QueueCheck

# 강제 종료/서버 연결 장애로 복원이 실패했을 때
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000 -RestoreSettings '결과폴더\restore-settings.json'
```

`-BaseUrl`은 실제 서버 주소/포트로 지정한다. 기본 주소는 예시 기본값이다. `-Python 'C:\path\python.exe'`, `-OutputDirectory 'C:\test-results\new-run'`을 사용할 수 있다. 출력 폴더는 새 경로여야 한다. PowerShell 없이도 `python3 scripts/test_backend_model_reasoning.py --help`로 동일 옵션을 사용한다.

기본 테스트는 `opencode` → `claude` 순서로 실행하며 `dtgpt`(Codex)는 제외한다. `-All`과 큐 검사 후보에도 같은 기본 순서가 적용된다. Codex를 테스트하려면 `-Backend codex` 또는 `-Backend dtgpt`를 명시해야 한다. Python 직접 실행에도 같은 기본값을 적용한다. `-Backend`를 명시하면 지정한 순서대로 실행한다.

테스트 한 건당 기본 타임아웃은 90초이며 스트림·동기 API 검사와 CLI 직접 비교 실행에 적용한다. `-TimeoutSeconds`(Python: `--timeout`)로 변경할 수 있다. 설정 조회 등 개별 HTTP 요청과 큐 정리 대기는 최대 30초이며, 정리 작업 때문에 전체 소요 시간은 테스트 타임아웃보다 길어질 수 있다.

실행 중에는 현재 검사 순번/전체 건수, 백엔드·모델·reasoning·검사 종류, 실행 단계, 세션/스트림 ID와 경과 시간(`elapsed`)을 1초마다 새 줄로 출력한다. 단계가 바뀔 때도 즉시 출력하며, 동기 HTTP 응답이나 직접 실행을 기다리는 동안에도 시간이 갱신된다. `submitting`은 요청 전송/응답 대기, `submitted`는 스트림 ID 수신, `waiting-response`는 스트림 완료 대기, `verifying`는 저장 결과 검사, `stopping-stream`/`cleaning-queue`는 정리를 뜻한다. 큐 검사는 `queued`/`waiting-queue` 및 발견된 큐 스트림 ID를, 직접 비교는 `scenario=…/direct`를 표시한다. 경과 시간은 해당 검사 준비부터 정리까지이며 직접 비교는 별도로 계산한다. 완료 줄에는 상태와 최종 소요 시간을 표시한다. PowerShell 진입점은 Python을 버퍼링 없이 실행하며, 프롬프트와 응답 본문은 진행 로그에 출력하지 않는다.

```text
[1/2] backend=claude model=claude-a reasoning=low scenario=echo phase=waiting-response session=123 stream=456 elapsed=12.0s timeout=90s
```

모델은 `/api/codex/settings`의 `model_catalogs_by_agent_backend`에서 수집한다. `codex`는 내부 ID `dtgpt`로 변환한다. `-All`은 모델별 reasoning 목록을 사용하며, 기본 실행은 백엔드별 현재 모델 또는 첫 모델의 기본 reasoning을 선택한다. OpenCode는 reasoning을 전달하지 않는 현재 구현에 맞춰 기본 실행만 검사한다. 명시한 미지원 모델/reasoning은 `UNSUPPORTED`이며 성공으로 계산하지 않는다. 모델 필터는 선택한 각 백엔드에 적용하므로, 백엔드마다 모델 ID가 다르면 따로 실행한다.

HTTP 통합 검사는 순차 실행한다. 이 모드에서는 기존 활성 스트림이 있으면 실행을 중단한다. 테스트 중 같은 설정을 사용하는 UI/다른 클라이언트에서 새 작업이나 설정 변경을 하지 않는다. 일반 모드에서는 설정 세 항목(`agent_backend`, `model`, `reasoning_effort`)만 변경하고 `finally`에서 복원 및 재조회 검증한다. API의 빈 설정 표현에 맞춰 백업의 null은 빈 문자열로 복원한다. 프로세스 강제 종료나 서버 장애 시 복구 파일로 다시 복원한다. 다중 사용자 모드에서 설정 변경은 관리자 권한이 필요하다. 인증이 필요하면 현재 셸의 `WORKBENCH_TEST_COOKIE` 또는 `WORKBENCH_TEST_AUTHORIZATION` 환경변수로 전달한다. 인증값은 인자/결과에 저장하지 않는다. 암호화만 허용하는 서버 구성은 이 클라이언트의 지원 범위 밖이다.

스트림 모드는 UI처럼 POST로 실행을 시작한 뒤 GET으로 `done`/`saved`를 폴링한다. 고유 문자열이 최종 저장된 assistant 메시지에 있는지, 시작/종료/저장 메타데이터가 요청과 일치하는지 확인한다. assistant 메시지는 ID로 찾아 user 프롬프트의 문자열을 성공으로 오인하지 않는다. 모델이 반환한 자기소개를 모델 식별 증거로 사용하지 않는다. 일반 실패 후 다음 조합을 계속 실행한다. 타임아웃 시 해당 테스트 스트림만 중단하고 종료/저장을 확인한다. 중단을 확인하지 못하거나 동기 요청의 완료 여부가 불분명하면 다음 조합을 실행하지 않는다. 동기 HTTP 연결을 끊어도 서버 작업은 자동 취소되지 않으므로 결과의 session ID로 상태를 확인한다.

`-ContextChecks`는 실제 서버 작업 경로와 첨부 텍스트 읽기를 검사한다. 예상 작업 경로와 첨부 내부 토큰을 프롬프트에 직접 넣지 않는다. 한글/공백 경로의 cwd 동작도 확인하려면 실제 서버 workspace가 그러한 경로인 환경에서 실행한다. API가 임의 cwd 변경을 지원하지 않으므로 스크립트가 서버 cwd를 변경하지 않는다. `-WorktreeCheck`는 생성된 경로와 모델이 확인한 cwd를 비교한다. `-QueueCheck`는 첫 작업 실행 중 두 번째 메시지를 큐에 넣고 다른 지원 설정으로 변경하여 큐 등록 당시 설정이 유지되는지 검사한다. 지원 조합이 하나뿐이거나 첫 응답이 너무 빨라 큐에 들어가지 못한 경우 검증 불충분으로 FAIL 처리한다. 큐 검사는 동기 모드에서도 스트림으로 수행하며 두 번 호출한다.

`-Direct off|failed|all`은 추가 모델 호출 옵션이다. 실행한 PC에 저장소의 Python 의존성과 CLI/인증/환경변수가 있어야 한다. Workbench 서버와 다른 PC에서 실행하면 직접 비교는 해당 PC 환경을 검사하므로 동일 환경의 재현이 아니다. Codex/Claude는 기존 `_build_agent_command`를, OpenCode는 `_prepare_agent_execution`과 `_execute_opencode_prompt`를 재사용한다. 직접 실행은 입력 인자/API payload 생성 경로를 재사용했다는 증거이며 원격 모델의 내부 reasoning 사용까지 증명하지 않는다. 직접 실행 성공은 Workbench 실패를 PASS로 바꾸지 않는다. 타임아웃은 로컬 프로세스 트리를 종료하며 OpenCode 원격 세션은 별도 정리가 필요할 수 있다.

결과 폴더에는 `results.json`, UTF-8 BOM `results.csv`, 상세 진단을 포함한 `diagnostics.jsonl`, `summary.json`, `restore-settings.json`이 생성된다. HTTP 통합 결과는 세션 ID와 worktree 정보를 포함한다. 재검토할 수 있도록 테스트 세션·첨부·worktree는 보존한다. 확인 후 Workbench UI/API로 정리한다. 종료 코드: 0 전체 성공, 1 실패/미지원/타임아웃/복원 실패, 2 실행 자체 오류, 130 사용자 중단. `-ListOnly`는 조회가 성공하면 미지원 항목이 있어도 0이다.

각 검사에는 `case-001.jsonl` 형태의 실시간 추적 파일도 생성된다. HTTP 시작/완료와 소요 시간, HTTP 오류 코드와 오류 본문, 검사 단계, 스트림 상태를 즉시 기록하므로 테스트가 중간에 종료돼도 앞선 기록을 확인할 수 있다. `at`은 서버 타임라인과 대조할 수 있는 Unix 밀리초이며 `elapsed`는 검사 시작 이후 초 단위 시간이다. `stream_diagnostics`에는 스트림의 stdout(`output`), stderr/서버 오류(`error`), 이벤트와 종료 정보가 변경될 때마다 남는다. `persisted_message`에는 검증한 assistant 메시지가, `exception`에는 실패 예외와 traceback이 남는다. HTTP 오류 본문은 최대 64 KiB를 읽는다.

실패 시 정리 전에 스트림과 테스트 세션을 추가 조회해 `results.json`의 `failure_stream_diagnostics`, `failure_assistant_messages`, `exception_traceback`에 저장한다. 추가 조회가 실패해도 원래 실패와 설정 복원 절차를 유지한다. 정리 후 상태는 `last_stream_diagnostics`로 구분한다. 직접 비교(`-Direct`)도 CLI stdout/stderr와 종료 코드를 결과의 `direct`에 저장하며, worker 오류와 타임아웃에도 수집 가능한 출력을 남긴다.

본문 필드는 각각 마지막 16,384자를 보존하고 생략 표시를 붙인다. 인증 환경변수, 이름에 TOKEN/SECRET/PASSWORD/API_KEY가 포함된 환경변수의 값, 일반적인 Bearer/인증 헤더/키 표현은 저장 전에 마스킹한다. 요청 프롬프트, 전체 세션, user 메시지, 전체 설정/환경변수/헤더는 저장하지 않는다. 다만 모델 출력이나 HTTP 오류 본문에 포함된 임의의 개인정보까지 자동 제거되는 것은 아니므로 공유 전 본문을 확인한다. 원인 분석을 요청할 때는 **`results.json`과 실패 항목의 `trace_file`에 지정된 `case-NNN.jsonl`**을 함께 전달하면 된다. `results.csv`만으로는 상세 원인을 확인할 수 없다. 기존 실행 명령을 그대로 사용하면 추가 진단이 기본 수집되며 테스트 스크립트만 변경했으므로 서버 재시작은 필요 없다.

메타데이터 검사는 저장 메시지의 최상위 `response_*` 필드를 읽으며 중첩 `metadata` 표현도 지원한다. 스트림 조회의 백엔드는 `agent_backend`도 허용한다. `metadata_check` 추적 이벤트에는 검증 위치(`source`)와 예상/실제 백엔드·모델·reasoning만 기록한다. `results.json`의 `metadata_source`로 시작 응답, 완료 스트림, 저장 메시지 중 어느 단계에서 불일치가 발생했는지 구분할 수 있다. 서버는 reasoning만 전달된 요청에서도 선택 모델을 별도로 복사해 스트림에 `claude-default`/`codex-default`가 잘못 기록되는 것을 방지한다.

`results.json`에는 `stream_id`, `trace_file`, `failure_phase`, 중단 전 `failure_stream_snapshot`, 정리 후까지 포함한 `last_stream_snapshot`이 추가된다. `done=false`이면 실행 단계와 프로세스·출력 상태를, `done=true`이면 `saved`, `persistence_complete`, `persistence_failed`를 함께 확인한다. 기존 `saved`는 실제 저장 작업이 끝나기 전에도 설정될 수 있으므로 저장 완료 여부는 `persistence_complete`로 구분한다. 서버 업데이트 전에는 새 필드가 없거나 단계가 `unknown`일 수 있다.

2026-10-22 서버의 `Agent lifecycle` INFO 로그와 `diagnostic_timeline` 수집은
제거했다. API에는 현재 작업 단계인 `diagnostic_phase`만 남는다. 서버의
worker/OpenCode 예외 처리, traceback과 저장 완료/실패 상태는 유지한다.
위 테스트 도구의 추적 파일은 도구를 명시적으로 실행할 때만 수집하며 서버의
상시 로깅이 아니다. 이전 타임 로그의 조사 결과는
[진단 로깅 제거 기록](timing-comparison.md)을 참고한다.
변경 적용을 위한 서버 재시작은 사용자가 직접 수행한다.

모의 서버 검증:

```text
python3 -m pytest tests/test_backend_model_reasoning_runner.py -q
```

PowerShell 설치 환경의 구문 검사:

```powershell
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\scripts\test_backend_model_reasoning.ps1), [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { $parseErrors; exit 1 }
```
