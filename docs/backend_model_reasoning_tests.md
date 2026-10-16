# 백엔드 모델/reasoning 실행 검사

`scripts/test_backend_model_reasoning.ps1`이 PowerShell 진입점이며 같은 디렉터리의 Python 파일이 검사를 수행한다. PowerShell 5.1/7 및 Python 3.9 이상을 대상으로 작성했다. HTTP 검사는 Python 표준 라이브러리만 사용한다. 서버를 시작하거나 재시작하지 않는다.

```powershell
# 먼저 모델 카탈로그와 예상 호출 수 확인 (설정 변경/모델 호출 없음)
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000 -ListOnly

# 기본: Claude/OpenCode 대표 모델의 기본 reasoning, 총 최대 2회
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000

# 해당 백엔드의 모든 모델별 지원 reasoning 조합
.\scripts\test_backend_model_reasoning.ps1 -Backend claude,opencode -All -TimeoutSeconds 300

# 특정 모델/effort 선택, 실패 시 로컬 직접 실행과 비교
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -Model '실제-카탈로그-모델-ID' -Reasoning low,high -Direct failed

# 동기 API 경로
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -Mode sync

# 작업 경로 확인 + 한글/공백 파일명 첨부 읽기 (백엔드별 대표 조합)
.\scripts\test_backend_model_reasoning.ps1 -ContextChecks -ExpectedWorkspace 'C:\작업 폴더\workspace'

# 각각 추가 호출 발생. worktree는 실제 테스트용 worktree를 생성한다.
.\scripts\test_backend_model_reasoning.ps1 -Backend claude -WorktreeCheck -QueueCheck

# 강제 종료/서버 연결 장애로 복원이 실패했을 때
.\scripts\test_backend_model_reasoning.ps1 -BaseUrl http://127.0.0.1:5000 -RestoreSettings '결과폴더\restore-settings.json'
```

`-BaseUrl`은 실제 서버 주소/포트로 지정한다. 기본 주소는 예시 기본값이다. `-Python 'C:\path\python.exe'`, `-OutputDirectory 'C:\test-results\new-run'`을 사용할 수 있다. 출력 폴더는 새 경로여야 한다. PowerShell 없이도 `python3 scripts/test_backend_model_reasoning.py --help`로 동일 옵션을 사용한다.

기본 테스트 대상은 `claude`, `opencode`이며 `dtgpt`(Codex)는 제외한다. `-All`과 큐 검사 후보에도 같은 기본 대상이 적용된다. Codex를 테스트하려면 `-Backend codex` 또는 `-Backend dtgpt`를 명시해야 한다. Python 직접 실행에도 같은 기본값을 적용한다.

테스트 한 건당 기본 타임아웃은 90초이며 스트림·동기 API 검사와 CLI 직접 비교 실행에 적용한다. `-TimeoutSeconds`(Python: `--timeout`)로 변경할 수 있다. 설정 조회 등 개별 HTTP 요청과 큐 정리 대기는 최대 30초이며, 정리 작업 때문에 전체 소요 시간은 테스트 타임아웃보다 길어질 수 있다.

모델은 `/api/codex/settings`의 `model_catalogs_by_agent_backend`에서 수집한다. `codex`는 내부 ID `dtgpt`로 변환한다. `-All`은 모델별 reasoning 목록을 사용하며, 기본 실행은 백엔드별 현재 모델 또는 첫 모델의 기본 reasoning을 선택한다. OpenCode는 reasoning을 전달하지 않는 현재 구현에 맞춰 기본 실행만 검사한다. 명시한 미지원 모델/reasoning은 `UNSUPPORTED`이며 성공으로 계산하지 않는다. 모델 필터는 선택한 각 백엔드에 적용하므로, 백엔드마다 모델 ID가 다르면 따로 실행한다.

검사는 순차 실행한다. 기존 활성 스트림이 있으면 실행을 중단한다. 테스트 중 같은 설정을 사용하는 UI/다른 클라이언트에서 새 작업이나 설정 변경을 하지 않는다. 일반 모드에서는 설정 세 항목(`agent_backend`, `model`, `reasoning_effort`)만 변경하고 `finally`에서 복원 및 재조회 검증한다. API의 빈 설정 표현에 맞춰 백업의 null은 빈 문자열로 복원한다. 프로세스 강제 종료나 서버 장애 시 복구 파일로 다시 복원한다. 다중 사용자 모드에서 설정 변경은 관리자 권한이 필요하다. 인증이 필요하면 현재 셸의 `WORKBENCH_TEST_COOKIE` 또는 `WORKBENCH_TEST_AUTHORIZATION` 환경변수로 전달한다. 인증값은 인자/결과에 저장하지 않는다. 암호화만 허용하는 서버 구성은 이 클라이언트의 지원 범위 밖이다.

스트림 모드는 UI처럼 POST로 실행을 시작한 뒤 GET으로 `done`/`saved`를 폴링한다. 고유 문자열이 최종 저장된 assistant 메시지에 있는지, 시작/종료/저장 메타데이터가 요청과 일치하는지 확인한다. assistant 메시지는 ID로 찾아 user 프롬프트의 문자열을 성공으로 오인하지 않는다. 모델이 반환한 자기소개를 모델 식별 증거로 사용하지 않는다. 일반 실패 후 다음 조합을 계속 실행한다. 타임아웃 시 해당 테스트 스트림만 중단하고 종료/저장을 확인한다. 중단을 확인하지 못하거나 동기 요청의 완료 여부가 불분명하면 다음 조합을 실행하지 않는다. 동기 HTTP 연결을 끊어도 서버 작업은 자동 취소되지 않으므로 결과의 session ID로 상태를 확인한다.

`-ContextChecks`는 실제 서버 작업 경로와 첨부 텍스트 읽기를 검사한다. 예상 작업 경로와 첨부 내부 토큰을 프롬프트에 직접 넣지 않는다. 한글/공백 경로의 cwd 동작도 확인하려면 실제 서버 workspace가 그러한 경로인 환경에서 실행한다. API가 임의 cwd 변경을 지원하지 않으므로 스크립트가 서버 cwd를 변경하지 않는다. `-WorktreeCheck`는 생성된 경로와 모델이 확인한 cwd를 비교한다. `-QueueCheck`는 첫 작업 실행 중 두 번째 메시지를 큐에 넣고 다른 지원 설정으로 변경하여 큐 등록 당시 설정이 유지되는지 검사한다. 지원 조합이 하나뿐이거나 첫 응답이 너무 빨라 큐에 들어가지 못한 경우 검증 불충분으로 FAIL 처리한다. 큐 검사는 동기 모드에서도 스트림으로 수행하며 두 번 호출한다.

`-Direct off|failed|all`은 추가 모델 호출 옵션이다. 실행한 PC에 저장소의 Python 의존성과 CLI/인증/환경변수가 있어야 한다. Workbench 서버와 다른 PC에서 실행하면 직접 비교는 해당 PC 환경을 검사하므로 동일 환경의 재현이 아니다. Codex/Claude는 기존 `_build_agent_command`를, OpenCode는 `_prepare_agent_execution`과 `_execute_opencode_prompt`를 재사용한다. 직접 실행은 입력 인자/API payload 생성 경로를 재사용했다는 증거이며 원격 모델의 내부 reasoning 사용까지 증명하지 않는다. 직접 실행 성공은 Workbench 실패를 PASS로 바꾸지 않는다. 타임아웃은 로컬 프로세스 트리를 종료하며 OpenCode 원격 세션은 별도 정리가 필요할 수 있다.

결과 폴더에는 `results.json`, UTF-8 BOM `results.csv`, 민감한 응답 본문을 제외한 `diagnostics.jsonl`, `summary.json`, `restore-settings.json`이 생성된다. 결과는 세션 ID와 worktree 정보를 포함한다. 재검토할 수 있도록 테스트 세션·첨부·worktree는 보존한다. 확인 후 Workbench UI/API로 정리한다. 종료 코드: 0 전체 성공, 1 실패/미지원/타임아웃/복원 실패, 2 실행 자체 오류, 130 사용자 중단. `-ListOnly`는 조회가 성공하면 미지원 항목이 있어도 0이다.

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
