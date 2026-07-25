# Codex Exec 토큰 효율화 구현 계획

## 1. 목적

Codex Workbench가 실행하는 `codex exec`의 결과 품질과 검증 수준은 유지하면서, 한 작업 안에서 반복되는 모델 호출과 도구 출력 누적으로 인한 불필요한 토큰 소비를 줄인다.

이 계획은 다음 원칙을 따른다.

- 모델의 reasoning effort를 낮추지 않는다.
- 필요한 코드 탐색, 구현, 관련 테스트, 최종 회귀 검증을 생략하지 않는다.
- 도구 호출 횟수에 강제 상한을 두지 않는다.
- 실패 로그를 무조건 잘라 원인 분석을 방해하지 않는다.
- 동일한 결과를 더 적은 왕복과 더 작은 중간 출력으로 만드는 데 집중한다.

## 1.1 검토 결론

이 방안은 현재 구조에서 구현 가능하다. `codex exec` 호출 방식을 바꾸지 않고 구조화 프롬프트에 조건부 overlay를 추가할 수 있고, 기존 JSON event와 usage 정보를 이용해 전후 차이도 측정할 수 있다.

다만 prompt 지침만으로 도구 사용 패턴을 바꾸는 방식은 확률적 최적화다. 현재 기준 실행에서 관찰한 40% 이상의 감소가 재현된다고 구현 전에 보장할 수는 없다. 특히 모델 또는 기본 Codex 지침에 이미 유사한 실행 규칙이 포함된 경우에는 overlay의 추가 효과가 작을 수 있다. 따라서 이 변경은 다음과 같이 판단한다.

- 기술적 구현 가능성: 높음
- 기존 실행 경로를 보존한 안전한 롤백 가능성: 높음
- 품질 유지 가능성: 중간 이상, 단 조건 판정과 회귀 검증 필요
- 목표 수치 달성 확실성: 미확정, A/B benchmark로 검증 필요

또한 현재 코드에서는 Plan mode와 subjob guardrail이 `build_codex_prompt()` 호출 **후**에 추가된다. 따라서 `_compose_structured_prompt()`가 prompt 문구만 보고 실행 모드를 추론하게 만들면 적용 제외를 완전히 보장할 수 없다. 실행 종류를 명시적 인자로 전달하는 구조가 우선이고, 텍스트 기반 감지는 작업 의도 판정에만 제한해야 한다.

## 2. 분석 기준과 병목

분석 대상 실행의 기준값은 다음과 같다.

| 항목 | 기준값 |
|---|---:|
| 전체 실행 시간 | 14분 5.111초 |
| 도구 호출 | 82회 |
| 모델 응답·추론 구간 | 83회 |
| 도구 자체 실행 시간 합계 | 5.717초 |
| 누적 input tokens | 11,133,605 |
| cached input tokens | 10,898,688 |
| 마지막 모델 호출 컨텍스트 | 190,546 tokens |
| reasoning output | 8,459 tokens |

도구 실행 시간은 전체의 약 0.68%였다. 주된 병목은 테스트나 셸 명령의 실행 속도가 아니라, 작은 탐색과 확인을 위해 모델과 도구가 82회 왕복하면서 이전 컨텍스트와 도구 결과를 계속 다시 입력한 데 있다.

Workbench가 처음 전달한 구조화 프롬프트는 약 11,597자였고 `CODEX_CONTEXT_MAX_CHARS` 기본값도 12,000자다. 따라서 초기 대화 이력보다 단일 `codex exec` 실행 중 누적된 도구 결과와 반복 모델 호출을 먼저 개선해야 한다.

## 3. 현재 구현의 변경 지점

현재 관련 구현은 다음 위치에 있다.

| 역할 | 파일·함수 |
|---|---|
| 대화 이력과 현재 요청 조합 | `codex-web-app/services/codex_chat.py::build_codex_prompt()` |
| 구조화 프롬프트와 overlay 조합 | `codex-web-app/services/codex_chat.py::_compose_structured_prompt()` |
| 실행 모드별 prompt 생성 호출부 | `codex-web-app/services/codex_chat.py::_start_next_queued_codex_stream_locked()`, `start_codex_subjob_for_session()` 및 직접 실행 호출부 |
| `codex exec` 명령 구성 | `codex-web-app/services/codex_chat.py::_build_codex_command()` |
| 초기 컨텍스트 한도 | `codex-web-app/config.py::CODEX_CONTEXT_MAX_CHARS` |
| 프롬프트·실행 회귀 테스트 | `tests/test_codex_chat_streams.py` |
| 운영 옵션 설명 | `README.md` |

`_build_codex_command()`는 큰 프롬프트를 stdin으로 전달하며, 일반 실행에서는 기존 `codex exec --json` 경로를 사용한다. 이 구조는 유지한다.

## 4. 구현 범위

### 4.1 실행 효율 overlay 추가

로컬 코드 구현·수정 요청에만 짧은 실행 효율 지침을 추가한다. 이 지침은 `_compose_structured_prompt()`에서 별도 section으로 조합하되, 적용 여부를 판단하는 데 필요한 실행 모드는 상위 호출부에서 명시적으로 전달한다.

권장 상수와 함수는 다음과 같다.

- `_EXEC_EFFICIENCY_PROMPT_SUFFIX`
- `_looks_like_local_code_task(prompt_text, recent_blocks=None)`
- `_should_include_exec_efficiency_overlay(prompt_text, recent_blocks=None, execution_context=None)`

`execution_context`는 최소한 `plan_mode`, `question_only`, `subjob`, `structured_report_preset`, `worktree_mode`를 구분할 수 있는 내부 값으로 한다. boolean 인자를 여러 개 늘어놓기보다 작은 dataclass, typed dict 또는 명시적 enum/문자열 정책으로 정규화한다. 외부 API payload를 그대로 신뢰하지 않고 서버가 결정한 실행 정책에서 생성한다.

overlay에는 다음 행동을 명시한다.

1. 시작할 때 변경 기능, 예상 파일, 테스트, 완료 조건을 한 번에 정리한다.
2. 관련 키워드는 하나의 `rg` 호출에 묶고, 파일 전체가 아닌 필요한 함수 주변만 읽는다.
3. 서로 독립적인 제한 범위 조회는 가능한 경우 한 번의 도구 호출로 실행한다.
4. 이미 읽은 코드는 다시 출력하지 않고 변경 후 `git diff`로 확인한다.
5. `apply_patch`는 기능 단위로 묶되 서로 다른 책임까지 거대한 한 패치로 합치지 않는다.
6. 검증은 문법 또는 정적 검사, 직접 관련 테스트, 관련 테스트 묶음, 전체 회귀 순으로 한 번씩 확대한다.
7. 성공한 동일 테스트를 근거 없이 반복하지 않는다.
8. 큰 로그, JSONL, HTML은 원문 전체 대신 `rg`, `jq`, 요약 명령으로 먼저 집계한다.
9. 명령 출력은 필요한 범위로 제한하되 실패 원인과 traceback은 보존한다.
10. 예상 밖의 증거가 나오면 호출 횟수보다 정확성을 우선하고 탐색 범위를 넓힐 수 있다.

overlay 자체가 길어져 매 turn의 고정 input을 늘리지 않도록 공백과 중복 문장을 제거한 뒤 토큰 수를 기록한다. 기존 시스템 지침과 의미가 같은 항목은 benchmark에서 기여도가 없으면 삭제한다.

실제 prompt literal은 저장소의 스크립트 작성 규칙에 맞춰 영어로 작성한다. 초안은 다음과 같다.

```text
## Efficient Local Code Execution
- Preserve correctness, requested scope, and verification depth while minimizing redundant model/tool round trips.
- Before editing, identify the likely files, symbols, tests, and completion criteria from one bounded repository scan.
- Combine related searches into one `rg` call and read only the relevant function or class ranges. Do not repeatedly print whole files.
- Group independent bounded inspections into one tool call when practical.
- After a section has been inspected, review subsequent changes with targeted `git diff` output instead of rereading the full source.
- Apply patches by coherent feature unit, avoiding both one-line patch churn and unrelated mega-patches.
- Verify progressively: syntax/static checks, directly affected tests, related test scope, then one final full regression when warranted.
- Do not rerun an unchanged passing check without new evidence.
- Summarize large logs and structured files before opening raw excerpts. Keep failure details and tracebacks visible.
- These are efficiency preferences, not hard limits. Expand inspection or testing whenever correctness requires it.
```

### 4.2 overlay 적용 조건 제한

모든 요청에 지침을 넣으면 초기 프롬프트만 커지고 비코딩 작업에 불필요한 영향을 줄 수 있다. 다음 조건을 만족하는 구현 요청에만 적용한다.

- 수정·구현·리팩터·버그 수정·테스트 추가 등 변경 의도가 있다.
- 코드, 설정, 테스트, 스크립트, 웹 UI 등 저장소 파일 작업을 뜻하는 단서가 있다.
- 현재 요청이 단순 설명, 상태 보고, 로그 분석, 번역, 문서 요약만을 요구하지 않는다.

짧은 후속 요청인 `적용해줘`, `계획대로 수정해줘`는 최근 1~2개 메시지의 문맥을 함께 검사한다. 기존 browser verification 감지 방식과 같은 패턴을 재사용할 수 있다.

판정은 다음 우선순위로 처리한다.

1. 서버가 알고 있는 실행 정책으로 강제 제외한다: Plan mode, read-only/ephemeral, subjob, structured report.
2. 이미지·스프레드시트 등 전용 workflow가 주 작업이면 제외한다.
3. 현재 요청에서 명시적인 변경 의도를 판정한다.
4. 현재 요청이 짧고 모호할 때만 최근 사용자 메시지의 변경 문맥을 보조적으로 사용한다.

최근 문맥에는 assistant/error 메시지도 포함될 수 있으므로, 가능하면 원본 message role을 유지한 구조를 판정 함수에 넘기고 사용자 메시지만 의도 판정에 사용한다. 이미 문자열로 직렬화된 `recent_blocks`만 사용할 경우 `<message role="user">` 범위 외의 지시문은 trigger 근거로 삼지 않는다.

부정 키워드만으로 Plan mode를 추정하지 않는다. 예를 들어 “계획 문서를 업데이트해줘”는 실제 파일 변경 작업이고, “구현하지 말고 계획만 알려줘”는 read-only 요청이다. 모호한 자연어 분류는 false positive보다 false negative를 우선해 기존 동작을 보존한다.

다음 요청에는 기본적으로 적용하지 않는다.

- Plan mode 또는 사용자가 명시적으로 계획만 요청한 경우
- read-only subjob
- 일반 질의응답과 코드 설명
- 이미지 생성이나 스프레드시트 생성처럼 별도 전용 overlay가 작업 절차를 지배하는 경우
- 단순 Git 상태 조회나 결과 보고

Plan mode guardrail과 충돌하지 않도록 plan-only 판정이 실행 효율 overlay보다 우선해야 한다.

browser verification overlay는 로컬 UI 구현 작업에서 함께 적용할 수 있다. 이때 양쪽에 중복된 “성공한 검증을 반복하지 않는다” 등의 문구는 한 곳만 남겨 prompt 증가를 막는다. 전용 overlay가 있다고 무조건 제외하지 말고, 전용 workflow가 주 작업인지 또는 일반 코드 변경의 검증 수단인지 구분한다.

### 4.3 출력 누적 최소화 지침

Workbench가 Codex 내부의 개별 tool result를 직접 축약하면 중요한 정보가 사라질 수 있으므로, 1차 구현에서는 event stream이나 원본 tool result를 사후 변조하지 않는다. 대신 Codex가 처음부터 제한된 출력을 요청하도록 유도한다.

권장 패턴은 다음과 같다.

- 검색: 여러 키워드를 하나의 `rg -n` 정규식으로 조회
- 파일 조회: 함수 주변의 명시적 line range만 출력
- 테스트: `pytest -q`와 직접 관련 node id부터 실행
- diff: `git diff --stat` 후 변경 파일별 targeted diff 확인
- 로그: 이벤트 종류·시간·토큰·호출 수를 집계한 뒤 이상 구간만 조회

출력 바이트 수를 Workbench에서 일괄 절단하는 기능은 1차 범위에서 제외한다. 향후 추가할 경우에도 원본 로그 파일은 보존하고 모델 입력용 요약본과 분리해야 한다.

### 4.4 단계적 검증 정책

검증 수준은 유지하되 중간 반복을 줄인다.

1. 변경 모듈의 문법·정적 검사
2. 새로 추가하거나 직접 영향받은 테스트
3. 실패한 테스트만 수정 후 재실행
4. 관련 테스트 파일 또는 기능 묶음
5. 최종 전체 회귀 테스트 1회
6. `git diff --check`
7. 저장소 규칙상 필요한 별도 validator

전체 회귀 테스트가 필요한 작업에서는 반드시 마지막에 실행한다. 다만 같은 코드 상태에서 성공한 전체 회귀를 다시 실행하지 않는다.

### 4.5 metadata와 문서 작업 분리

저장소 규칙에 따라 일반 구현 중 metadata Markdown 전체를 탐색하지 않는다. 즉시 갱신 조건이나 사용자 요청이 없다면 영향 범위만 최종 응답에 기록하고 daily sync로 넘긴다.

이 정책은 문서 누락을 허용하는 것이 아니라, 구현 도중 광범위한 문서 재검색과 버전 기록 수정을 자동으로 수행해 토큰을 소비하는 일을 막기 위한 것이다.

### 4.6 관측 지표 추가

최적화 효과를 재현 가능하게 비교하려면 각 `codex exec` 완료 시 다음 지표를 집계할 수 있어야 한다.

- 전체 elapsed time
- 모델 응답 구간 수
- command execution 및 MCP tool call 수
- 도구별 실행 시간 합계
- input, cached input, uncached input, output, reasoning tokens
- 최대 또는 마지막 모델 컨텍스트 크기
- 성공·실패·사용자 취소 상태
- 실행 효율 overlay 적용 여부

기존 세션 JSONL과 token usage 데이터를 우선 재사용한다. 원본 prompt나 민감한 명령 전체를 새 telemetry에 복제하지 않는다.

1차 구현에서는 서버 로그에 구조화된 요약을 남기고, UI 그래프나 별도 대시보드 추가는 후속 범위로 분리한다.

지표의 정의와 집계 단위를 구현 전에 고정한다.

- 한 benchmark sample은 하나의 `codex exec` process/turn으로 식별한다.
- `input_tokens`는 CLI의 `turn.completed.usage` 값을 사용하고, `uncached_input_tokens = max(0, input_tokens - cached_input_tokens)`를 별도로 계산한다.
- event 수와 모델 응답 구간 수를 같은 값으로 취급하지 않는다. 모델 구간을 event stream에서 직접 식별할 수 없으면 `unknown`으로 남기고 추정치를 공식 지표로 사용하지 않는다.
- tool call은 `item.started`가 아니라 완료된 item의 안정된 ID로 중복 제거하며 command execution과 MCP를 구분한다.
- 컨텍스트 크기가 event schema에서 직접 제공되지 않으면 “마지막 컨텍스트”로 명명하지 않고, 해당 값의 원본 필드와 계산식을 기록한다.
- elapsed time은 queue wait, CLI runtime, finalize lag를 분리하고 효율 비교의 주 지표는 CLI runtime으로 한다.
- 취소, timeout, event stream lag/drop이 있는 sample은 실패로 보존하되 성능 중앙값에서는 별도 집계한다.

가능하면 새 영구 ledger를 먼저 만들지 않고 실행 종료 시 단일 구조화 로그를 남긴다. benchmark helper가 stdout/event 원본에서 같은 요약을 재생성할 수 있어야 하며, session ID, prompt hash, repository commit, 설정 조합만 기록하고 prompt/명령 원문과 도구 출력은 복제하지 않는다.

## 5. 설정과 롤아웃

초기에는 환경 변수 기반으로 켜고 끌 수 있는 fail-open 옵션을 둔다.

권장 이름:

```text
CODEX_EXEC_EFFICIENCY_OVERLAY=1
```

동작 원칙은 다음과 같다.

- benchmark와 canary 단계의 기본값은 비활성화하고, 합격 기준을 통과한 릴리스에서 활성화한다.
- 값이 유효하지 않으면 overlay를 적용하지 않는 기존 실행 경로를 유지하고 경고만 남긴다.
- 비활성화하면 효율 overlay만 제거하며, 기존 history 구성과 `codex exec` 명령은 바꾸지 않는다.
- UI 설정은 효과가 검증된 뒤 필요할 때 추가한다.
- 실행 시작 시 결정한 on/off 값을 해당 stream에 고정해, 실행 중 환경이나 설정 변화로 측정군이 바뀌지 않게 한다.

`CODEX_CONTEXT_MAX_CHARS`를 단순히 낮추는 것은 핵심 해결책으로 사용하지 않는다. 이 값은 초기 대화 문맥만 제한하며, 단일 실행 중 누적되는 도구 결과를 직접 제어하지 못한다.

## 6. 구현 순서

### Phase 1. 기준선 고정

- 분석 대상 rollout에서 기준 지표를 재현하는 read-only 집계 스크립트 또는 테스트 helper를 준비한다.
- 현재 event schema에서 직접 측정 가능한 값과 추정값을 구분하고, 82회/83회 및 마지막 컨텍스트 190,546 tokens의 산출식을 문서화한다.
- 대표 작업 3종을 benchmark fixture로 정한다.
  - 여러 파일을 수정하고 전체 회귀가 필요한 구현 작업
  - 짧은 후속 구현 요청
  - read-only 분석 또는 plan-only 요청
- 각 fixture의 기대 결과, 변경 파일, 필수 테스트를 기록한다.
- overlay 자체의 문자·토큰 증가량을 기준선에 포함한다.

### Phase 2. prompt overlay 구현

- `codex_chat.py`에 효율 overlay 상수와 감지 함수를 추가한다.
- prompt 생성 호출부에서 정규화한 실행 정책을 전달하고 `_compose_structured_prompt()`에서 적용 조건을 만족할 때만 section을 삽입한다.
- Plan mode, question-only, structured report, subjob, imagegen, spreadsheet, browser verification overlay와의 우선순위를 명시적으로 처리한다.
- 설정 비활성화 시 현재 prompt 결과가 유지되도록 한다.
- 적용 여부와 판정 reason code를 stream metadata 또는 구조화 로그에 남긴다.

### Phase 3. 단위·회귀 테스트

`tests/test_codex_chat_streams.py`에 최소한 다음 사례를 추가한다.

- 명시적 코드 구현 요청에는 overlay가 포함된다.
- 일반 설명 요청에는 포함되지 않는다.
- plan-only 요청에는 포함되지 않는다.
- question-only, structured report 및 subjob에는 포함되지 않는다.
- 짧은 후속 구현 요청은 최근 문맥을 통해 감지된다.
- assistant/error 문구만으로는 후속 구현 요청으로 오인하지 않는다.
- “계획 문서 업데이트”와 “계획만 제시”를 구분한다.
- 설정을 끄면 포함되지 않는다.
- browser verification 등 기존 overlay가 그대로 유지된다.
- 최종 구조화 prompt가 `CODEX_CONTEXT_MAX_CHARS`를 넘을 때 기존 trimming 정책이 깨지지 않는다.
- `_build_codex_command()`의 stdin 전달과 기존 인자가 바뀌지 않는다.
- overlay 적용 여부가 trimming 재조합 중 바뀌지 않고, 잘린 prompt tail만 반환하는 최후 경로에서도 `Current User Request`와 `Response Rules`의 구조가 훼손되지 않는다.

마지막 항목은 기존 `structured_prompt[-max_chars:]` fallback 자체의 잠재 위험도 드러낼 수 있다. 이 최적화의 범위를 벗어난 기존 결함이면 별도 이슈로 기록하되, overlay 추가로 fallback 진입 빈도가 늘어나지 않는 것은 이번 변경의 합격 조건으로 둔다.

### Phase 4. 실사용 비교

- 동일 repository snapshot, 모델, reasoning effort, Codex CLI 버전, sandbox 및 설정으로 overlay on/off 실행을 비교한다.
- 결과 diff, 테스트 결과, 최종 답변의 요구사항 충족 여부를 먼저 비교한다.
- 품질이 동등한 실행에 대해서만 tool call, 모델 turn, token, elapsed time을 비교한다.
- 순서·캐시 편향을 줄이기 위해 on/off 실행 순서를 교차하거나 무작위화하고 각 실행을 깨끗한 worktree/snapshot에서 시작한다.
- fixture당 최소 3회, 가능하면 5회 이상 반복해 중앙값과 범위를 함께 기록한다.
- 같은 계정의 동시 실행, rate limit, event loss가 있는 표본은 표시하고 별도 집계한다.
- 품질 판정자는 가능하면 overlay 적용 여부와 토큰 결과를 보지 않은 상태에서 고정 rubric으로 diff와 테스트 결과를 평가한다.

### Phase 5. 문서화와 기본 활성화

- `README.md`의 Codex CLI 옵션에 환경 변수와 동작 범위를 추가한다.
- benchmark 결과와 알려진 한계를 이 문서에 갱신한다.
- 회귀가 없고 목표치를 만족하면 다음 릴리스에서 기본값을 활성화로 전환한다.

기본 활성화 후에도 reason code별 적용률, false positive 사례, 품질 회귀 및 토큰 중앙값을 짧은 canary 기간 동안 확인한다. 문제가 있으면 환경 변수 하나로 overlay만 즉시 비활성화하며 CLI 경로나 사용자 데이터는 변경하지 않는다.

## 7. 합격 기준

### 품질 기준

다음 조건은 반드시 모두 만족해야 한다.

- 사용자 요구사항과 완료 조건이 overlay 미적용 실행과 동일하게 충족된다.
- 변경 diff에 기능 누락이나 불필요한 범위 확장이 없다.
- 직접 관련 테스트와 기존 전체 회귀 결과가 동일하다.
- 오류가 발생한 경우 최종 답변에 원인과 미검증 범위가 누락되지 않는다.
- Plan mode와 read-only subjob의 비변경 보장이 유지된다.

### 효율 목표

아래 수치는 구현 전 보장값이 아니라 검증할 목표 가설이다. 대표적인 다중 파일 구현 작업의 반복 실행 중앙값을 기준으로 다음을 목표로 한다.

- 도구 호출 및 모델 응답 구간 수 40% 이상 감소
- 누적 input tokens 40% 이상 감소
- 최종 모델 컨텍스트 크기 30% 이상 감소
- 전체 elapsed time 20% 이상 감소

목표 수치는 품질 기준을 통과한 실행에만 인정한다. 품질이 낮아졌다면 토큰 감소 폭과 관계없이 실패로 판단한다.

릴리스 판단에는 total input과 함께 uncached input도 반드시 표시한다. cached input 감소만으로는 실제 비용·지연 개선을 과대평가할 수 있고, 반대로 캐시 적중률 변화가 overlay 효과를 가릴 수 있다. 한 지표의 큰 개선으로 다른 지표의 악화를 숨기지 않도록 fixture별 결과와 전체 중앙값을 모두 공개한다.

목표를 충족하지 못했을 때 임의로 기준을 낮추지 않는다. 품질은 유지되지만 효과가 작은 경우 기본값을 끈 채 실험 기능으로 유지하거나 overlay 문구를 축소·제거한다. prompt-only 방식이 반복적으로 효과가 없으면 원본 event stream을 변조하지 않는 범위에서 Codex CLI가 공식적으로 제공하는 출력 제한 또는 context 관리 기능을 별도 제안으로 검토한다.

## 8. 주요 위험과 대응

| 위험 | 대응 |
|---|---|
| 휴리스틱 오분류로 read-only 작업에 변경 지침 삽입 | 실행 정책 강제 제외, user role만 검사, false negative 우선 |
| overlay가 기존 지침과 중복되어 input만 증가 | overlay 토큰 수 기록, 항목별 축소 실험, 효과 없으면 기본 비활성 |
| 출력 제한 지침이 실패 원인을 가림 | traceback·실패 요약 보존을 품질 rubric과 테스트에 포함 |
| 도구 호출 감소가 탐색·검증 누락으로 이어짐 | 필수 artifact와 테스트를 fixture별 사전 정의 |
| A/B 결과가 캐시·동시 실행·모델 변동에 오염 | 실행 조건 고정, 순서 교차, 반복 중앙값과 범위 기록 |
| telemetry가 prompt나 명령 원문을 중복 저장 | ID/hash/집계값만 기록하고 기존 보존 정책 재사용 |
| 긴 overlay가 context trimming을 앞당김 | 고정 길이 예산, 경계 테스트, fallback 진입률 비교 |

## 9. 제외 사항

다음 변경은 이 계획의 1차 범위에 포함하지 않는다.

- reasoning effort 자동 하향
- 모델 자동 교체
- 전체 테스트 생략 또는 테스트 횟수 강제 제한
- 도구 호출 횟수 hard limit
- `codex exec` 세션을 중간에 임의로 분할하거나 `resume`으로 전환
- 원본 tool result 또는 rollout JSONL 삭제
- event stream의 실패 로그를 무조건 truncate
- 기존 App Server pilot이나 agent backend 구조 변경

이 항목들은 결과 품질, 재현성, 장애 분석 능력을 떨어뜨릴 가능성이 있으므로 별도 실험과 승인이 필요하다.

## 10. 완료 산출물

구현 완료 시 다음 산출물이 있어야 한다.

- `codex_chat.py`의 실행 효율 overlay 및 적용 조건
- `config.py`의 on/off 설정
- `test_codex_chat_streams.py`의 prompt 조합·회귀 테스트
- `README.md` 운영 옵션 설명
- overlay on/off benchmark 결과
- 품질 기준과 효율 목표의 통과 여부 기록

이 계획의 핵심 완료 조건은 단순 토큰 감소가 아니라, 동일한 요구사항과 테스트 결과를 유지한 상태에서 불필요한 모델·도구 왕복이 감소했음을 측정값으로 입증하는 것이다.
