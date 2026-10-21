# 로컬·사내 환경 타임로그 비교

사내 모드(`CODEX_COMPANY_MODE=1`)에서는 자동으로 상세 계측합니다. 로컬에서는 서버 시작 시 `CODEX_TIMING_ENABLED=1`을 설정하면 동일한 보고서를 수집합니다. 예: `CODEX_TIMING_ENABLED=1 ./run_codex_chat_server.sh`. 실행 중인 서버의 환경 설정을 바꾸려면 서버 재시작이 필요합니다. 새 요청부터 적용되며 이전 기록은 재계산하지 않습니다.

답변 하단 **타임 로그 보기**에서 환경 정보, 비교용 구간, CLI 보고 정보, 최근 시각, 저장 작업 집계를 확인합니다. 로그는 기본적으로 닫혀 있으며 메시지와 함께 저장됩니다. 서버 로그에도 `Company process timing` JSON으로 출력됩니다. 보고서의 `schema_version: 2`와 `spans[].name`을 기준으로 두 환경의 같은 구간을 비교할 수 있습니다.

같은 backend·model·effort·프롬프트 크기·첨부 조건으로 여러 번 실행하고, 캐시 토큰과 세션 저장 파일 크기도 함께 확인하세요. 모델 캐시와 동시 작업에 따라 결과가 달라질 수 있습니다. 환경 정보에는 OS, Python, CPU 개수, 저장 파일 크기, 프록시 설정 여부가 포함됩니다. 프록시 주소·호스트 이름·환경 변수 원문은 수집하지 않습니다. 별도의 네트워크 요청이나 CLI 버전 조회 프로세스도 추가하지 않습니다.

| 오래 걸리는 구간 | 확인할 범위 |
| --- | --- |
| 문맥 준비 / 실행 환경·명령 구성 | 실행 문맥, 계정 설정, 파일 접근. 작업별 집계에서 세부 함수 시간을 확인 |
| 실행 잠금 대기 | 동시 실행 및 실행 제한 |
| 프로세스 생성 | 운영체제의 프로세스 시작, 실행 래퍼 |
| 프로세스 생성 → 첫 표준 출력 / Claude 초기화 | CLI 시작과 초기화. 첫 출력은 서버 응답을 뜻하지 않음 |
| Claude 초기화 → 메시지 시작 | CLI 내부 준비 및 요청 대기. hook·재시도 이벤트 종류와 발생 간격을 함께 확인 |
| Claude 메시지 시작 → 결과 이벤트 | CLI 응답 처리 구간. 네트워크·서버·모델 각각의 시간으로 분해할 수 없음 |
| Claude 결과 이벤트 → 프로세스 종료 관측 | 결과 수신 후 CLI 종료 및 Workbench 폴링 관측 지연 |
| 프로세스 종료 관측 → 출력 스레드 대기 완료 | stdout/stderr 스레드 join 대기. 제한 시간 후에도 스레드가 살아 있을 수 있음 |
| 출력 스레드 대기 완료 → CLI 처리 종료 | 출력 파일·이미지 등 결과 처리 |
| 답변 저장 / 저장 후 후처리 | 세션 저장, 사용량 기록 등. 저장 집계와 비교 |

구간과 작업 집계는 서로 겹치므로 합산하지 마세요. 누락 구간은 경계가 관측되지 않은 경우이며 0ms가 아닙니다. OpenCode는 세션 생성·이벤트 연결·첫 이벤트 대기를 별도로 표시합니다. CLI 전용 구간은 OpenCode에 적용되지 않습니다.

구간은 단조 시계로 계산하며 주요 경계는 최근 64개 시각 목록에서 사라져도 유지합니다. `cli.event_observations`의 `first_ms`, `last_ms`, `max_gap_ms`는 첫 CLI 이벤트를 기준으로 한 종류별 관측값입니다. 이벤트 페이로드나 hook 이름은 저장하지 않습니다. 같은 종류 이벤트가 오래 끊긴 사실만 보여주며 해당 시간의 원인을 확정하지는 않습니다.

저장된 요약은 요약 자체의 저장과 후속 큐 시작 이전까지의 스냅샷입니다. 브라우저↔Workbench 전송 시간 및 CLI 내부 DNS/TLS/인증/서버 큐/추론 시간은 이 로그만으로 개별 측정하지 않습니다.

## Claude 초기화 전 지연 진단

`CODEX_COMPANY_MODE=1`이면 Claude 초기화 진단이 기본 활성화되어 새 Claude
스트리밍 작업마다 `--debug-file`을 지정합니다. 사외에서는 기본 비활성화입니다.
`CODEX_CLAUDE_STARTUP_DIAGNOSTICS`가 미설정이거나 빈 값이면 사내 모드 설정을
따르고, 명시적으로 `1`을 지정하면 활성화, `0`을 지정하면 사내에서도 비활성화합니다.
진단을 켜면 타임 로그도 활성화됩니다. 서버는 사용자가 직접 재시작합니다.
Codex/OpenCode 명령이나 프로젝트 설정 파일은 변경하지 않습니다.

원본은 기존 CLI 출력 디렉터리 아래
`claude-startup/<log_id>/claude.debug.log`에 남습니다. 실제 절대 경로는 해당
응답 상세 로그의 `Claude exec input` 인자에서 확인합니다. 타임 로그의
`cli.startup_debug`에는 파일 식별자, 최대 4 MiB 스캔의 상태, 고정 분류별
개수와 가장 긴 기록 간격 10개만 저장합니다. 원문·URL·인증값·훅 이름은
요약에 복사하지 않습니다. 분류는 문자열 기반 추정이며, 긴 간격 앞뒤의
분류가 지연 원인을 증명하지는 않습니다. 타임스탬프 형식이 다르면
`timestamped_lines`가 0일 수 있습니다.
`file_bytes`는 원본 디버그 파일의 크기이고 `summary_scan_ms`는 종료 후
요약 스캔에 실제로 소요된 시간입니다. 이 시간에는 CLI의 디버그 쓰기 비용은
포함되지 않습니다.

원본 CLI 디버그 파일에는 민감한 내용이 들어갈 수 있습니다. 원본을 그대로
공유하지 마세요. POSIX에서는 작업 폴더/파일에 0700/0600을 요청하고 Windows는
저장 위치의 ACL을 따릅니다. 원본 크기는 제한하지 않으며 자동 삭제하지 않으므로
진단을 마친 뒤 옵션을 끄고 필요 없는 작업별 폴더를 정리합니다.

진단 작업에서는 stdout/stderr를 청크로 읽되 기존 줄 단위 이벤트 파서로
전달합니다. UTF-8 분할, CRLF, 개행 없는 마지막 줄을 처리합니다.
`stdout_reader_started`, `first_stdout_byte`, `first_stdout_line`을 구분하고
기존 `first_stdout`은 첫 줄 관측이라는 의미를 유지합니다.

- `first_stdout_byte_wait`: 프로세스 생성 반환 → 첫 바이트 관측
- `stdout_line_buffer_wait`: 첫 바이트 관측 → 첫 줄 관측
- `stdout_reader_start`: 프로세스 생성 반환 → stdout 리더 시작

관측 시각에는 스레드 스케줄링과 계측 처리 시간이 포함됩니다. 실제 자식
프로세스의 write 시각을 직접 재는 값은 아닙니다. 일반 실행은 기존
`readline()` 경로를 유지합니다.

## 조건별 비교 실행

`scripts/compare_claude_startup.py`는 Python 표준 라이브러리만 사용하는
Windows/macOS 공용 도구입니다. Workbench 밖에서 실행하며 현재 셸의 인증·
프록시 환경을 상속합니다. Workbench의 자식 환경 변환은 자동 적용하지
않으므로 같은 인증과 endpoint를 준비해야 합니다. 사내에서는 기존 설정에
맞춰 `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`과 모델 매핑을 확인하세요.
키를 argv나 JSON 파일에 넣지 않습니다.

기준 argv를 UTF-8 JSON 배열 `claude-command.json`으로 준비합니다. 아래 모델과
effort는 실제 작업에 맞게 교체하고, 실행 파일은 같은 절대 경로를 사용합니다.
실제 작업에서 지정한 권한·turn 제한 등도 동일하게 맞춥니다. stdin은
`prompt.txt`의 바이트를 그대로 보냅니다. Workbench와 비교하려면 실행 환경
절까지 포함한 실제 구조화 프롬프트를 사용합니다.

```json
["C:\\path\\to\\claude.exe", "-p", "--model", "sonnet", "--effort", "high", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
```

PowerShell 예시입니다. 출력은 새 폴더여야 하고 빈 작업 폴더는 프로젝트 및
그 상위 경로 밖의 비어 있는 로컬 경로를 지정합니다.

```powershell
python .\scripts\compare_claude_startup.py `
  --command-file C:\temp\claude-command.json `
  --prompt-file C:\temp\prompt.txt `
  --cwd C:\work\project `
  --empty-cwd C:\temp\claude-empty-workdir `
  --output C:\temp\claude-startup-comparison-01 `
  --repeats 3 --timeout 180
```

| 조건 | 기준 대비 변경 |
| --- | --- |
| `baseline` | 디버그 없는 원래 명령 |
| `baseline_debug` | `--debug-file`만 추가: 디버그 로깅 부담 비교 |
| `no_mcp` | debug 기준 + `--strict-mcp-config --mcp-config <빈 설정>` |
| `user_settings` | debug 기준 + `--setting-sources user` |
| `no_commands` | debug 기준 + `--disable-slash-commands` |
| `empty_cwd` | debug 기준 + 프로젝트 밖 빈 폴더에서 실행 |

각 조건은 한 가지씩만 바꿉니다. 원인 비교는 **`baseline_debug`**와 비교하고,
디버그 부담은 **`baseline` 대 `baseline_debug`**로 비교합니다. 이 옵션들이
모든 관리 설정·훅·플러그인을 비활성화하는 것은 아닙니다. CLI 버전에 따라
옵션이 거부되면 해당 실행은 실패로 남으며 성공 중앙값에서 제외합니다.
공식 옵션 설명: [Claude CLI reference](https://code.claude.com/docs/en/cli-reference).

첫 회차는 조건별 워밍업으로 별도 기록하고, 이후 3~5회씩 순차 실행합니다.
회차마다 조건 순서를 뒤집어 기준이 항상 먼저 실행되는 편향을 줄입니다.
캐시·네트워크·서비스 부하 차이는 여전히 남습니다. 3회 기준 총 24번의 실제
모델 요청이 발생하므로 파일 수정·도구 호출을 요구하지 않는 진단용 프롬프트를
권장합니다. 빈 폴더 비교도 같은 프롬프트·환경·모델·effort를 사용합니다.

실행 중 현재 조건·수행시간을 터미널에 표시하고 각 실행 후 `results.json`,
`results.csv`를 갱신합니다. JSON에는 워밍업 표시, 종료 코드, 시작 실패·
타임아웃·수집 실패, 첫 바이트·첫 줄·init·result·완료 시각과 성공한 측정의
중앙값·최솟값·최댓값이 있습니다. 상태가 실패이면 개별 폴더의 `stderr.log`를
확인합니다. `stdout.log`, `stderr.log`, `claude.debug.log`는 원본 진단 자료이며
자동으로 공유하거나 채팅에 넣지 않습니다. 이 도구 자체는 Workbench의
세션 저장 비용을 측정하지 않습니다.

## 로깅 부담 해석

부담은 0이 아닙니다. 코드에서 확인되는 추가 작업은 다음과 같습니다.

| 모드 | 작업마다 추가되는 비용 |
| --- | --- |
| 사외 기본 | 상세 계측 없음. 기존 lifecycle 시각·INFO 로그와 stdout/stderr 상세 보관 비용은 있음 |
| 사내 진단 해제(`CODEX_CLAUDE_STARTUP_DIAGNOSTICS=0`) / 사외 `CODEX_TIMING_ENABLED=1` | 줄별 UTF-8 바이트 계산·잠금, Claude 이벤트별 카운터·시각·usage 집계, 함수별 시간 집계, 보고서 복사·직렬화·로그 출력, 완료 보고서용 세션 갱신 |
| 사내 기본 / `CODEX_CLAUDE_STARTUP_DIAGNOSTICS=1` | 위 상세 계측 + CLI 디버그 파일 쓰기, 청크 디코딩·추가 경계 시각, 종료 후 최대 4 MiB 디버그 스캔 |

이벤트/집계 종류와 시각 목록은 제한하지만 기존 stdout/stderr 문자열과
세션 파일의 크기는 별개입니다. 긴 stderr는 원본과 표시용 문자열에 보관되어
메모리와 저장량을 늘릴 수 있습니다. 세션 갱신은 전체 세션 저장소 읽기·쓰기
경로를 사용하므로 파일 크기와 디스크 속도에 민감합니다. Windows 백신·
네트워크 드라이브·동시 작업·로그 핸들러 출력 지연이 있으면 비용이 더 커질
수 있습니다. 기본 상세 계측 자체는 새 네트워크 요청이나 모델 요청을
추가하지 않습니다. 별도 사용량 갱신은 기존 작업이며 로깅 비용과 구분합니다.

이 코드 검토만으로 작업당 몇 ms 또는 몇 %인지 확정할 수 없습니다.
사내 모드에는 계측이 자동 적용되므로 `CODEX_TIMING_ENABLED=0`만으로 끌 수
없습니다. 동일 장비의 별도 시험 프로세스에서 상세 계측을 켜고 끄는 대조가
필요합니다. 실제 사내 Windows의 지연은 이 macOS 검증으로 측정한 값이
아닙니다. 저장 집계 시간은 I/O 지연을 찾는 근거이지만 계측 자체의 CPU 비용을
의미하지 않으며, 구간과 저장 집계를 합산하지 않습니다.
