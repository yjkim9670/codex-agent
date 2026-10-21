# CLI 실행 대기와 Claude 환경

Claude는 Codex 홈, 확장, 모델 캐시, queued memories 복사와 Python 버전 검사를
실행하지 않는다. Codex/DTGPT와 OpenCode의 기존 backend 선택은 유지한다.

## Claude 터미널 설정 유지

기본값은 기존 사내 gateway 방식이다. 개인 터미널에서 사용하는 Claude 로그인,
API key, endpoint, opus/sonnet/haiku/subagent 매핑을 그대로 사용하려면 서버를
실행하는 **같은 Windows 사용자와 셸**에서 다음 환경변수를 설정한 후 실행한다.

```powershell
$env:CODEX_CLAUDE_ENV_MODE = "native"
.\run_codex_chat_server_company.ps1
```

native 모드에서는 사내 health URL이나 `CODEX_CLAUDE_BASE_URL`로 endpoint를
유도하지 않고, 회사 키를 주입하지 않는다. 런처도 기존 Anthropic 인증변수를
지우지 않는다. 로컬 Claude 설정의 모델 목록과 modelOverrides를 사용한다.
Workbench에 명시적으로 선택한 모델·effort가 있으면 해당 CLI 옵션은 전달되므로,
터미널과 비교할 때는 같은 모델·effort를 선택한다. 기본 모델·effort를 Workbench
설정에서 자동 상속하는 동작은 native 모드에서 생략한다. 키는 로그에 입력하지 않는다.

기존 사내 gateway로 돌아가려면 `CODEX_CLAUDE_ENV_MODE`를 제거하거나 `company`로 설정한다.
환경변수 변경은 사용자가 서버를 재시작한 뒤 적용된다.

## 대기 제한과 진단

| 환경변수 | 기본값(초) | 적용 대상 |
| --- | ---: | --- |
| `CODEX_CLI_GATE_TIMEOUT_SECONDS` | 1800 | CLI 실행 잠금 대기, Windows 포함 |
| `CODEX_CLI_STDIN_TIMEOUT_SECONDS` | 60 | 스트리밍 프롬프트 전송 |
| `CODEX_CLI_PROGRESS_TIMEOUT_SECONDS` | 600 | 실행 중 출력·이벤트가 없는 스트리밍 작업 |
| `CODEX_CLI_EXEC_TIMEOUT_SECONDS` | 3600 | CLI 전체 실행, 동기 호출 포함 |

양수 초 단위로 조정할 수 있다. stdout/stderr reader를 stdin writer보다 먼저
시작하고, 입력 전송 중에도 취소·시간 제한을 확인한다. 부분 응답은 Claude의
`--include-partial-messages`와 `stream_event` 텍스트 delta로 표시한다.
옵션은 [Claude CLI 공식 문서](https://code.claude.com/docs/en/cli-reference)를 따른다.

현재 작업의 `diagnostic_phase`와 저장 메시지의 `finalize_reason`으로
`stdin_timeout`, `progress_timeout`, `execution_timeout` 제한 원인을 확인한다. 잠금 대기 초과는
`execution_gate_timeout`으로 저장된다. 제한 초과 시 자식 프로세스를 종료하고
실행 잠금을 해제한다. 기존 프로세스 종료 후 최종 응답 제한도 유지한다.

OpenCode의 전체/진행 정체 제한은 유지하되, 정상 진행 이벤트가 들어오는 동안에는
주기적인 전체 메시지 복구 조회를 생략한다. 이벤트가 정체되거나 연결이 끊기면
복구 조회를 수행한다.

문맥 선택 감사 기록 전체는 세션 메타데이터에 유지한다. backend로 보낼 때는
중복 memory 본문과 선택 세부 기록을 hash·누락 범위 참조로 줄인다. Source-linked
Context Notes와 선택된 대화 본문은 유지한다. 세션 저장은 공백 없는 JSON으로
원자적으로 교체한다. 저장 구조 자체는 여전히 전체 JSON 교체이다.
추가했던 저장 시간 INFO 로그는 2026-10-22 제거했다.

macOS에서 실제 자식 프로세스를 이용한 입출력·시간 제한과 모의 Windows 잠금으로
검증한다. 사내 Windows gateway의 실제 지연·인증 성공 여부는 해당 환경에서
재시작 후 비교해야 한다.

## 성능 진단 수집 제거

2026-10-22 상시 타임라인·작업별 계측·Claude 디버그 파일 수집과 타임 보고서
추가 저장을 제거했다. 기존 타임 로그는 열람할 수 있으며 새 응답에는 생성하지 않는다.
조사 결과·관측 한계·제거 범위는 [조사 기록](timing-comparison.md)에 남겼다.
서버 재시작은 사용자가 직접 수행한다.
