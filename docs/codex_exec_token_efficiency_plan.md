# Codex Exec 토큰 효율화 구현 계획

## 1. 목적

Codex Workbench가 실행하는 `codex exec`의 결과 품질과 검증 수준은 유지하면서, 한 작업 안에서 반복되는 모델 호출과 도구 출력 누적으로 인한 불필요한 토큰 소비를 줄인다.

이 계획은 다음 원칙을 따른다.

- 모델의 reasoning effort를 낮추지 않는다.
- 필요한 코드 탐색, 구현, 관련 테스트, 최종 회귀 검증을 생략하지 않는다.
- 도구 호출 횟수에 강제 상한을 두지 않는다.
- 실패 로그를 무조건 잘라 원인 분석을 방해하지 않는다.
- 동일한 결과를 더 적은 왕복과 더 작은 중간 출력으로 만드는 데 집중한다.

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
| `codex exec` 명령 구성 | `codex-web-app/services/codex_chat.py::_build_codex_command()` |
| 초기 컨텍스트 한도 | `codex-web-app/config.py::CODEX_CONTEXT_MAX_CHARS` |
| 프롬프트·실행 회귀 테스트 | `tests/test_codex_chat_streams.py` |
| 운영 옵션 설명 | `README.md` |

`_build_codex_command()`는 큰 프롬프트를 stdin으로 전달하며, 일반 실행에서는 기존 `codex exec --json` 경로를 사용한다. 이 구조는 유지한다.

## 4. 구현 범위

### 4.1 실행 효율 overlay 추가

로컬 코드 구현·수정 요청에만 짧은 실행 효율 지침을 추가한다. 이 지침은 `_compose_structured_prompt()`에서 별도 section으로 조합한다.

권장 상수와 함수는 다음과 같다.

- `_EXEC_EFFICIENCY_PROMPT_SUFFIX`
- `_looks_like_local_code_task(prompt_text, recent_blocks=None)`
- `_should_include_exec_efficiency_overlay(prompt_text, recent_blocks=None)`

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

다음 요청에는 기본적으로 적용하지 않는다.

- Plan mode 또는 사용자가 명시적으로 계획만 요청한 경우
- read-only subjob
- 일반 질의응답과 코드 설명
- 이미지 생성이나 스프레드시트 생성처럼 별도 전용 overlay가 작업 절차를 지배하는 경우
- 단순 Git 상태 조회나 결과 보고

Plan mode guardrail과 충돌하지 않도록 plan-only 판정이 실행 효율 overlay보다 우선해야 한다.

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

## 5. 설정과 롤아웃

초기에는 환경 변수 기반으로 켜고 끌 수 있는 fail-open 옵션을 둔다.

권장 이름:

```text
CODEX_EXEC_EFFICIENCY_OVERLAY=1
```

동작 원칙은 다음과 같다.

- 기본값은 활성화한다.
- 값이 유효하지 않으면 기존 실행 경로를 유지하고 경고만 남긴다.
- 비활성화하면 효율 overlay만 제거하며, 기존 history 구성과 `codex exec` 명령은 바꾸지 않는다.
- UI 설정은 효과가 검증된 뒤 필요할 때 추가한다.

`CODEX_CONTEXT_MAX_CHARS`를 단순히 낮추는 것은 핵심 해결책으로 사용하지 않는다. 이 값은 초기 대화 문맥만 제한하며, 단일 실행 중 누적되는 도구 결과를 직접 제어하지 못한다.

## 6. 구현 순서

### Phase 1. 기준선 고정

- 분석 대상 rollout에서 기준 지표를 재현하는 집계 스크립트 또는 테스트 helper를 준비한다.
- 대표 작업 3종을 benchmark fixture로 정한다.
  - 여러 파일을 수정하고 전체 회귀가 필요한 구현 작업
  - 짧은 후속 구현 요청
  - read-only 분석 또는 plan-only 요청
- 각 fixture의 기대 결과, 변경 파일, 필수 테스트를 기록한다.

### Phase 2. prompt overlay 구현

- `codex_chat.py`에 효율 overlay 상수와 감지 함수를 추가한다.
- `_compose_structured_prompt()`에서 적용 조건을 만족할 때만 section을 삽입한다.
- Plan mode, subjob, imagegen, spreadsheet, browser verification overlay와의 우선순위를 명시적으로 처리한다.
- 설정 비활성화 시 현재 prompt 결과가 유지되도록 한다.

### Phase 3. 단위·회귀 테스트

`tests/test_codex_chat_streams.py`에 최소한 다음 사례를 추가한다.

- 명시적 코드 구현 요청에는 overlay가 포함된다.
- 일반 설명 요청에는 포함되지 않는다.
- plan-only 요청에는 포함되지 않는다.
- 짧은 후속 구현 요청은 최근 문맥을 통해 감지된다.
- 설정을 끄면 포함되지 않는다.
- browser verification 등 기존 overlay가 그대로 유지된다.
- 최종 구조화 prompt가 `CODEX_CONTEXT_MAX_CHARS`를 넘을 때 기존 trimming 정책이 깨지지 않는다.
- `_build_codex_command()`의 stdin 전달과 기존 인자가 바뀌지 않는다.

### Phase 4. 실사용 비교

- 동일 repository snapshot과 동일 사용자 요청으로 overlay on/off 실행을 비교한다.
- 결과 diff, 테스트 결과, 최종 답변의 요구사항 충족 여부를 먼저 비교한다.
- 품질이 동등한 실행에 대해서만 tool call, 모델 turn, token, elapsed time을 비교한다.
- 한 사례의 우연한 개선이 아니라 3회 이상 반복한 중앙값을 사용한다.

### Phase 5. 문서화와 기본 활성화

- `README.md`의 Codex CLI 옵션에 환경 변수와 동작 범위를 추가한다.
- benchmark 결과와 알려진 한계를 이 문서에 갱신한다.
- 회귀가 없고 목표치를 만족하면 기본 활성화를 유지한다.

## 7. 합격 기준

### 품질 기준

다음 조건은 반드시 모두 만족해야 한다.

- 사용자 요구사항과 완료 조건이 overlay 미적용 실행과 동일하게 충족된다.
- 변경 diff에 기능 누락이나 불필요한 범위 확장이 없다.
- 직접 관련 테스트와 기존 전체 회귀 결과가 동일하다.
- 오류가 발생한 경우 최종 답변에 원인과 미검증 범위가 누락되지 않는다.
- Plan mode와 read-only subjob의 비변경 보장이 유지된다.

### 효율 목표

대표적인 다중 파일 구현 작업의 3회 중앙값을 기준으로 다음을 목표로 한다.

- 도구 호출 및 모델 응답 구간 수 40% 이상 감소
- 누적 input tokens 40% 이상 감소
- 최종 모델 컨텍스트 크기 30% 이상 감소
- 전체 elapsed time 20% 이상 감소

목표 수치는 품질 기준을 통과한 실행에만 인정한다. 품질이 낮아졌다면 토큰 감소 폭과 관계없이 실패로 판단한다.

## 8. 제외 사항

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

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| 요청 분류 실패로 overlay가 빠짐 | 최근 메시지 문맥을 사용하고, 빠져도 기존 동작을 유지하는 fail-open 구조 적용 |
| overlay가 지나치게 강해 필요한 탐색을 억제 | hard limit이 아님을 명시하고 정확성 우선 문구 포함 |
| prompt 자체가 길어짐 | overlay를 짧고 고정된 section으로 유지하고 중복 지침 제거 |
| 로그 제한 때문에 실패 원인이 사라짐 | 성공 출력만 축약하고 실패 traceback과 stderr는 보존 |
| 테스트 순서 변경으로 회귀 누락 | 최종 전체 회귀 조건과 repository validator를 완료 조건에 포함 |
| 기존 전용 overlay와 충돌 | 적용 우선순위와 조합 테스트 추가 |

## 10. 완료 산출물

구현 완료 시 다음 산출물이 있어야 한다.

- `codex_chat.py`의 실행 효율 overlay 및 적용 조건
- `config.py`의 on/off 설정
- `test_codex_chat_streams.py`의 prompt 조합·회귀 테스트
- `README.md` 운영 옵션 설명
- overlay on/off benchmark 결과
- 품질 기준과 효율 목표의 통과 여부 기록

이 계획의 핵심 완료 조건은 단순 토큰 감소가 아니라, 동일한 요구사항과 테스트 결과를 유지한 상태에서 불필요한 모델·도구 왕복이 감소했음을 측정값으로 입증하는 것이다.
