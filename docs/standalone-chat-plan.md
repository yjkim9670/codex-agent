# 독립 채팅 서비스 계획

작성·갱신일: 2026-10-28. 상태: **구현·검증 및 Proc Manager 등록 완료 (idx 16, STOPPED, PID 없음)**. 현재 구현·실행·검증 상세는 [운영 안내](standalone-chat.md)를 기준으로 한다. 아래 본문은 최초 설계와 결정 근거를 보존한 계획 기록이며, ‘아직 생성하지 않음/계획만’ 문구는 최초 계획 당시 상태다. 실행 중인 서버의 시작·종료·재시작은 사용자 수행이다.

구현 파일은 `conversation-app/`, `shared/chat_accounts.py`, `run_conversation_server.py/.sh`, `ops/workbench-chat.job.json`이다. 별도 DB·계정별 Codex home, 개인 계정·런타임 모델/추론 선택, 번역/교정/검색, SSE·복구·중단, 글꼴 8종, 공통 사용량 수집·앱 필터를 구현했다. 실제 모델 번역·검색·중단과 격리된 Chromium 화면을 검증했다. 실제 CLI 전송 도구는 검색 끄기 0개, 켜기 web.run만 노출됐다.

실제 구현의 조정 사항: 요청별 새 provider thread에 완료 문맥을 한 번 전달하며 자동 요약은 하지 않는다. 접속은 loopback 전용이다. 인증 갱신은 기존 로그인만 담당하고 Chat은 refresh token 없이 접속 snapshot을 읽는다. Codex CLI는 격리 검증한 0.160.0으로 제한한다. 중단 직후 사용량 미반환은 확정 0 대신 집계 대기로 남긴다. 기존 스트림 테스트 실패 24개는 변경 전 HEAD에서도 동일하게 재현됐다.

## 1. 목표와 이번 결정

영어 번역·영문 교정, 웹 검색·자료 조사, 일반 질의응답에 사용하는 메시지 중심 앱을 별도 프로세스·별도 포트로 만든다. 기존 사외용 Workbench처럼 개인 Codex 계정과 사용 가능한 GPT/Codex 모델을 선택한다. 사내 DTGPT나 회사 관리자 고정 모델 정책을 신규 서비스의 기본으로 삼지 않는다. 현재 작업의 실행 backend가 `dtgpt`라는 사실과 신규 서비스의 제품 설정을 구분한다.

기존 계획의 직접 대화 API 우선 제안은 **기존 사외용 Codex 연결·계정·모델 선택 흐름을 재사용하는 방향**으로 변경한다. 검색은 후속 기능에서 초기 필수 기능으로 올린다. 별도 OpenAI API key나 별도 API 과금 계약을 초기 버전의 필수 조건으로 추가하지 않는다. ChatGPT와 유사한 대화 UX가 목표이며, ChatGPT 제품의 대화 기록·메모리와 동기화하는 기능은 포함하지 않는다.

| 항목 | 기존 Workbench | 신규 Workbench Chat |
| --- | --- | --- |
| 역할 | 저장소·파일·터미널·에이전트 작업 | 번역·검색·일반 대화 |
| 실행 | 기존 서버 유지 | 독립 Flask 진입점 + 채팅 전용 Codex adapter |
| 포트 | 현재 job별 포트 유지 | 3101 제안, 구현 시 사용 여부 확인 |
| 모델 | 기존 설정 유지 | 사외용 Codex 계정에서 사용 가능한 모델·추론 강도 선택 |
| 저장 | 기존 작업 세션·설정 | 독립 대화 DB·환경설정·로그·Codex 실행 home |
| 사용량 | 기존 수집·대시보드 | 동일 수집 체계에 포함, 앱별 구분 가능 |
| 파일 관련 UI | 현재 기능 유지 | 파일 트리·preview·업로드·편집 UI 제외 |
| 프로세스 관리 | 기존 job 유지 | 같은 Proc Manager Web에 독립 job 등록 예정 |
| 운영 전환 | 사용자 수행 | 구현 후 등록까지만, 최초 시작·재시작은 사용자 수행 |

이번 수정은 이 문서에 한정한다. 신규 서비스 구현이나 실제 job 등록은 향후 구현 단계에 해당한다. 모든 Workbench 소스·테스트·목업·운영 설정 산출물은 `/Users/dinya/works/dev_workspace/codex_workbench/` 안에 둔다. 다른 체크아웃과 Proc Manager 소스는 읽기 전용 참고자료다.

## 2. 확인한 기존 구조와 재사용 범위

2026-10-28 로컬 파일을 읽어 확인한 내용이다. 실제 구현 시 다시 검증한다.

| 근거 파일 | 확인 내용 | 설계에 반영할 사항 |
| --- | --- | --- |
| `codex-web-app/config.py` | `standalone` / `internal-multiuser` 구분, backend별 모델 카탈로그 | 사외용 `standalone` 의미에 맞춰 Codex 목록·추론 옵션 사용 |
| `codex-web-app/services/codex_chat.py` | 계정 저장 문맥, 모델 선택, Codex App Server 호출 코드 | 인증 해석·모델 정규화 등을 부작용 없는 공통 모듈로 추출; 거대한 작업 서비스 전체 import 금지 |
| `codex-web-app/services/usage_dashboard.py` | Codex home 탐색, state DB·rollout 수집, 계정 일치 확인, 이벤트 병합 | 새 home을 명시적 수집원으로 연결하고 account/thread/turn 식별자 보존 |
| `codex-web-app/services/model_usage_analysis.py`, `usage_reconciliation.py` | 모델별 분석과 계정 관측치 정합성 처리 | 기존 합계·필터·정합성 보고에 채팅 사용량 포함 |
| `codex-web-app/templates/index.html`, `static/js/app.js`, `static/css/app.css` | 글꼴 8종, 즉시 적용·localStorage 저장, UI 배율 | 동일한 선택지·글꼴 자산·fallback과 설정 UX 재사용 |
| `/Users/dinya/works/proc_manager_web.py` | `POST /api/tasks` → `add_task()` → 설정 저장; 등록 함수에는 시작 호출 없음 | 구현 완료 후 지원 API/UI로 등록만 수행하는 절차 설계 |
| `/Users/dinya/works/proc_manager_jobs.json` | 최상위 `jobs` 배열, 기존 Dev Workbench job은 3004 사용 | 기존 job 유지, 신규 job 1개 추가; 실행 중인 manager의 설정 파일 직접 편집 회피 |

프로젝트 지침이 가리키는 `design.md`는 현재 체크아웃에서 발견하지 못했다. UI는 `AGENTS.md`에 명시된 IBM Carbon 스타일과 기존 자산을 기준으로 계획한다.

## 3. 주요 사용자 흐름

### 영어 번역·교정

1. 새 대화에서 `영어 번역` 바로가기를 누르면 입력창에 번역 목적을 안내하고 검색은 끈다.
2. 원문을 붙여 넣고 대상 언어(기본 영어), 톤(자연스럽게/업무용/간결하게), 결과 형식(번역만/번역+설명)을 선택한다.
3. 기본 답변은 바로 복사할 수 있는 번역문을 먼저 제시한다. 문단·목록·고유명사·숫자·단위를 보존한다.
4. `조금 더 공손하게`, `더 짧게`, `원문 의미를 유지해줘` 등의 후속 메시지는 같은 대화 문맥에서 처리한다. 번역문 복사와 전체 답변 복사를 구분한다.
5. 원문 내 지시문은 번역 대상 텍스트로 다룬다. 장문 한도 초과 시 분할 안내를 제공하고 몰래 뒷부분을 생략하지 않는다.

영문 교정은 교정문 우선·변경 이유 선택 표시로 제공한다. 번역 프리셋이 검색을 자동 실행하거나 저장소 작업을 시작하지 않도록 한다.

### 검색·자료 조사

1. `웹 검색` 바로가기는 검색 `켜기`와 함께 질문 입력에 초점을 준다. 사용자가 검색을 명시하면 실제 검색 가능한 설정으로 실행한다.
2. 검색 설정은 `자동 / 켜기 / 끄기`로 제공한다. 자동은 시의성 있는 일반 질문에 검색을 허용하며 번역·교정 프리셋에서는 기본적으로 끈다.
3. `검색 중 → 자료 확인 중 → 답변 작성 중`을 실제 이벤트가 있을 때 표시한다. 도구 호출의 원문 로그 대신 짧은 진행 상태를 보여준다.
4. 답변에는 관련 문장 옆 출처 링크와 하단 출처 목록을 제공한다. 출처명·URL·검색 시각, 제공되는 경우 게시일을 저장한다. 검색 시각을 게시일로 대체하지 않는다.
5. 실패·지원 불가·결과 없음은 구분한다. 검색하지 못한 답변을 검색 완료처럼 표시하지 않으며, 검색 재시도 또는 검색 없이 답변받기를 사용자가 선택한다.
6. 검색 언어와 답변 언어를 구분한다. 영문 자료를 조사한 뒤 한국어로 요약하거나 번역하도록 요청할 수 있다.

웹 페이지는 조사 자료로만 취급한다. 검색 결과의 지시문이 앱 설정·계정·도구 권한을 바꾸지 않게 한다. 검색 결과에서 온 HTML은 실행하지 않고 출처 링크는 안전한 http(s) URL만 표시한다.

### 일반 대화와 공통 동작

새 대화, 목록 검색, 제목 변경·삭제, 여러 턴 문맥, Markdown·코드 블록·복사, 스트리밍, 중단, 재시도를 제공한다. 대화 제목은 우선 첫 메시지에서 로컬 생성해 불필요한 모델 호출을 줄인다. 향후 모델로 제목·요약을 만들면 해당 사용량도 수집한다.

모델·추론 강도·계정 변경은 다음 요청부터 적용한다. 응답마다 실제 사용 계정 식별자·모델·추론 강도와 검색 여부를 기록한다. 생성 중에는 해당 요청의 설정을 고정한다. 재시도는 새 attempt로 남기고 기존 답변과 사용량을 덮어쓰지 않는다. 대화 이동이나 새로고침 후에도 생성 결과가 다른 대화에 섞이지 않아야 한다.

## 4. Codex 연결과 실행 격리

채팅 서버가 관리하는 전용 Codex App Server adapter를 우선 검토한다. 기존 작업 서버의 실행 큐·Team·Git·파일 preview·작업 프롬프트를 거치지 않는다. 앱 프로세스가 관리하는 Codex 자식 프로세스는 채팅 job에 종속시키고 종료·중단도 해당 프로세스에만 적용한다.

공식 App Server 문서는 thread/turn 기반 대화, 응답 이벤트, `model/list`, `thread/tokenUsage/updated`를 설명한다. 이를 연결 후보로 삼되 설치된 Codex 버전의 스키마와 실제 계정 지원을 확인한 뒤 사용한다. [OpenAI Docs — App Server](https://learn.chatgpt.com/docs/app-server)

- **모델 목록:** 사외용 Codex 계정에서 런타임 모델 목록을 조회하고 기존 정규화 로직을 재사용한다. 특정 GPT 이름·권한·가격을 문서에 고정하지 않는다. 추론 강도는 선택 모델이 지원하는 값만 노출한다. 계정 미로그인·목록 조회 실패·모델 접근 불가는 별도 상태로 표시한다.
- **인증:** 기존 개인 계정 인증을 서버에서 재사용하되 새 실행 home에서 안전하게 사용하는 방법을 검증한다. 공유 인증 원본을 덮어쓰거나 브라우저로 인증 파일을 전송하지 않는다. home 분리 시 갱신 토큰 충돌·계정 전환·세션 재연결을 검증한다.
- **대화 문맥:** 로컬 DB는 화면 이력·attempt·설정의 원본이며 Codex thread는 실행 문맥이다. `conversation_id ↔ account_id ↔ thread_id/turn_id`를 저장한다. 계정 변경은 새 thread로 안전하게 이어 붙이되 필요한 대화 문맥만 재전송한다. 활성 thread에 전체 이력을 매번 중복 입력하지 않는다.
- **지침:** 채팅 전용 지침은 번역·질의응답·출처 기반 검색에 집중한다. 실제 저장소를 cwd로 사용하지 않는다. 전용 빈 작업 경로를 사용하고 사용자 전역·상위 AGENTS.md, skills, plugins, MCP 및 작업 지침이 자동 주입되지 않는 설정을 검증한다.
- **도구:** 검색만 허용하고 shell·파일 읽기/쓰기·Git·코드 실행·작업 큐·자동 에이전트를 비활성화한다. read-only sandbox만으로 파일 읽기까지 차단된다고 가정하지 않는다. 실제 노출 도구·로드된 지침·권한을 확인한다. 지원 버전에서 통제할 수 없다면 운영 전환을 보류하고 adapter 대안을 재설계한다.
- **검색:** 자동/켜기에는 지원되는 실시간 검색 설정을 연결하고 끄기는 검색 도구를 비활성화한다. 개인 Codex 인증으로 검색·출처를 실제 반환하는지 반드시 검증한다. 지원 불가 시 DTGPT나 별도 유료 API로 자동 전환하지 않는다.
- **복구:** 한 대화에는 활성 응답 1개만 허용한다. 다른 대화의 동시 요청은 제한하고 계정 한도 오류에는 대기·재시도를 안내한다. 중단은 해당 turn에만 적용하며 다른 Workbench의 Codex 프로세스는 건드리지 않는다.

공식 검색 문서는 실시간 검색 설정과 도구 가용성 조건을 설명한다. 검색 허용은 로컬 명령의 네트워크 권한과 별개이므로 검색만 허용하는 구성을 검증한다. [OpenAI Docs — Web search](https://learn.chatgpt.com/docs/web-search)

직접 Responses API를 기본 연결로 삼았던 이전 제안은 철회한다. 향후 사용자가 별도 API 연결을 요청하면 인증·과금·사용량 출처를 구분한 별도 adapter로 검토한다.

## 5. 서버·API·데이터 구성

아래 파일은 아직 만들지 않았다.

```text
codex_workbench/
  run_conversation_server.py
  run_conversation_server.sh
  conversation-app/
    server.py
    services/conversations.py
    services/codex_provider.py
    services/usage_export.py
    templates/index.html
    static/js/chat.js
    static/css/chat.css
  shared/                         # 검증 후 부작용 없는 공통 기능만 추출
  ops/workbench-chat.job.json      # Proc Manager 등록 payload 제안
  docs/standalone-chat-plan.md
  tests/                          # 채팅 및 기존 수집 호환 검증
  .agent_state/conversation/      # 실행 데이터, Git 제외
    conversations.sqlite3
    settings.json
    codex_home/
    empty_workspace/
    logs/
```

실제 데이터 경로는 명시적 `CHAT_DATA_DIR`로 확정하고 `HOME`을 변경해 우회하지 않는다. 별도 home에는 대화 실행 데이터와 필요한 최소 설정만 둔다. 기존 Workbench 작업 세션·환경설정은 신규 서비스가 쓰지 않는다. UI 글꼴 자산은 별도 서버에서도 제공되도록 제한된 공통 static 경로나 복사 빌드로 연결한다.

| API 제안 | 역할 |
| --- | --- |
| `GET /health` | 앱 상태·DB 준비 상태, 매번 모델 API 호출 금지 |
| `GET /api/models`, `GET /api/accounts` | 선택 가능한 모델·추론 옵션·계정 상태, 인증 비밀 제외 |
| `GET/PATCH /api/settings` | 채팅 전용 기본 계정·모델·추론·검색 설정 |
| `GET/POST /api/conversations` | 대화 목록·새 대화 |
| `PATCH/DELETE /api/conversations/<id>` | 제목 변경·삭제 |
| `GET /api/conversations/<id>/messages` | 답변·출처·attempt·생성 상태 조회 |
| `POST /api/conversations/<id>/messages` | request ID와 설정 snapshot으로 attempt 생성 |
| `GET /api/attempts/<id>/events` | event ID 기반 SSE·재접속·중복 제거 |
| `POST /api/attempts/<id>/cancel` | 해당 turn 생성 중단 |
| `GET /api/usage/summary` | 동일 수집 체계의 채팅 요약·최종 수집 시각 |

DB에는 conversation, message, attempt, provider thread/turn 매핑, citations, stream events, usage outbox를 둔다. attempt는 queued/streaming/completed/cancelled/failed/interrupted를 구분한다. request ID는 중복 전송을 막는다. 상태와 outbox를 같은 트랜잭션으로 저장해 수집 누락을 방지한다. 재시작 후 미완료 응답은 interrupted로 복구하고 최종 사용량이 뒤늦게 오면 상태와 별개로 반영한다.

대화 삭제 시 메시지·출처·이벤트 및 대응 Codex thread의 삭제/보관 정책을 적용한다. 단, 이미 발생한 사용량의 최소 회계 레코드는 유지하고 메시지 본문을 수집 데이터에 복제하지 않는다. 로컬 DB 삭제만으로 Codex rollout까지 지워졌다고 표시하지 않는다. 문맥 축약 시 화면에 알리고, 요약 호출도 사용량에 포함한다.

별도 서버 session·cookie 이름과 키를 사용한다. cookie는 포트만으로 격리되지 않는다. 개인 사용 모드에 사내 사용자 관리 UI를 추가하지 않되 기존 사외용 접속 보호 정책은 따른다. 변경 요청의 origin/CSRF, 접근 제어, Markdown sanitization을 적용한다. 기본 개발 bind는 loopback으로 두고 기존 tailnet 등 원격 접속은 검증된 접속 정책과 함께 설정한다.

## 6. 사용량: 기존 집계에 반드시 포함

채팅 화면 내부 숫자만 따로 쌓는 것으로 완료하지 않는다. 기존 사용량 수집·대시보드의 계정별·모델별·일별 합계와 정합성 보고에 새 채팅을 포함한다. 채팅 프로세스 종료나 대화 삭제 후에도 사용 이력이 남아야 한다.

### 수집 경로와 소유권

1. 전용 `codex_home`을 기존 수집기의 명시적 탐색 대상으로 연결한다. `CODEX_USAGE_DISCOVERY_ROOTS`를 사용할 경우 기존 대상들을 보존하고 새 경로를 추가한다. 원본 코드상 탐색 옵션은 기본 탐색 roots를 대체하므로 새 경로 하나로 덮어쓰지 않는다. 기존 계정 home 수집도 회귀 검증한다.
2. 계정 인증 identity와 실행 thread/turn을 매핑한다. 공통 이벤트에는 `application=workbench-chat`, `account_id`, provider account identity, `thread_id`, `turn_id`, `attempt_id`, model, reasoning effort, UTC 시각, workspace path, token 항목, 상태를 보존한다. `application` 등 신규 필드는 수집기·분석기의 스키마 확장 제안이다.
3. 실시간 provider 사용량은 채팅 DB outbox에 저장하고 **기존 수집 프로세스가 단독으로 병합·공통 집계 파일을 갱신**한다. 두 앱이 같은 JSON ledger를 각각 read-modify-write하지 않는다. 기존 앱이 꺼져 있으면 채팅 outbox에 보관하고 공통 집계는 다음 수집 때 반영한다.
4. Codex rollout을 최종 정합성 근거로 삼고, 실시간 이벤트는 잠정치로 표시한다. 계정+thread+turn을 공통 키로 매핑해 rollout 수집 시 교체·보정한다. 서로 다른 `event_id`만 붙여 동일 토큰을 두 번 더하지 않는다. 한 turn의 여러 모델 구간은 구분해 합산한다.
5. 기존 `merge_events()`의 ledger/rollout 매칭 계약에 맞춰 adapter를 설계한다. 모호한 매핑·사용량 누락은 진단으로 분리하고 임의 시간·토큰 유사성만으로 다른 채팅의 기록과 합치지 않는다.

### 수치와 화면 표시

- input, cached input, output, total 및 제공되는 reasoning token을 원본 의미대로 저장한다. cached input은 input의 부분 집합이며 reasoning도 provider 정의에 따라 output에 포함될 수 있으므로 중복 가산하지 않는다.
- 누적 usage 이벤트는 이전 관측 대비 차분으로 처리한다. 재접속·이벤트 재전송·수집 반복은 멱등성을 보장한다. 중단·실패한 요청도 실제 사용된 토큰을 기록한다. 미확정은 0으로 확정하지 않고 `집계 대기`로 표시한다.
- 검색 호출 횟수·실패·지연은 별도 운영 지표다. provider가 제공하지 않는 검색 비용을 임의 토큰으로 환산하지 않는다. 구독 사용 한도를 API의 달러 비용처럼 표시하지 않는다.
- 기존 전체 합계에는 자동 포함하고 `전체 / Workbench / Chat` 필터를 추가한다. 기존 환경 필터는 workspace 의미를 유지한다. 과거 이벤트 중 앱을 확정할 수 없는 기록은 `미분류`로 두되 전체 합계에서 제외하지 않는다.
- Chat 상단에는 현재 계정·한도 snapshot 시각·집계 시각을 간단히 표시하고 상세 보기는 기존 대시보드 또는 동일 분석 결과를 보여주는 화면으로 연결한다. 한도 관측치와 채팅 토큰 합계는 구분한다.

완료 기준: 같은 계정의 Workbench 1회 + Chat 번역 1회 + Chat 검색 1회의 최종 원본 사용량 합계가 공통 대시보드에 누락·중복 없이 나타난다. 재수집·취소·재시도·모델 변경·계정 변경·대화 삭제·프로세스 재시작 후에도 합계가 유지된다.

## 7. UI/UX 구현안

### 화면 구조

IBM Carbon 계열의 차분한 중립 배경, 선 중심 구획, 파란 primary 버튼, 4/8px 간격 체계를 사용한다. 기본 글꼴은 IBM Plex Sans KR이다. 큰 장식 카드·그라데이션보다 읽기 쉬운 대화 본문을 중심에 둔다.

```text
┌──────────────────────┬───────────────────────────────────────────────┐
│ Workbench Chat       │ 대화 제목               사용량 · 화면 설정    │
│ + 새 대화            ├───────────────────────────────────────────────┤
│ 대화 검색            │ 사용자: 이 문장을 자연스러운 영어로…         │
│ 오늘                 │                                               │
│  회의 일정 번역      │ 답변: 번역문 / 검색 요약                      │
│  검색한 주제         │ [번역문 복사] [전체 복사] [재시도]             │
│ 이전                 │ 검색인 경우 문장 옆 인용 및 [출처 목록]       │
│  …                   │                                               │
│                      ├───────────────────────────────────────────────┤
│ 계정 · 연결 상태     │ [대화] [영어 번역] [웹 검색]                   │
│                      │ [Codex 모델 ▾] [추론 ▾] [검색: 자동 ▾]        │
│                      │ 메시지 입력…                         [전송]   │
└──────────────────────┴───────────────────────────────────────────────┘
```

- **Desktop(1024px 이상):** 256px 대화 sidebar, 가변 본문, 최대 800px 메시지 읽기 폭. 입력창과 모델 선택은 대화 하단에 고정한다.
- **Tablet/fold(600–1023px):** sidebar 접기와 overlay 목록, 대화 단일 열. 파일 패널을 위한 분할 공간을 두지 않는다.
- **Mobile(599px 이하):** 전체 폭 대화, drawer 이력, 설정 bottom sheet. 조작부는 줄바꿈하며 가로 스크롤을 만들지 않는다. 안전 영역·가상 키보드·동적 viewport 높이에 대응한다.
- **빈 대화:** `영어로 번역`, `영문 교정`, `웹에서 찾아 요약`, `일반 질문` 바로가기와 짧은 입력 예시를 보여준다. 바로가기 선택만으로 요청을 보내지 않는다.
- **응답:** 일반 Markdown 본문을 우선하고 복사·재시도는 답변 아래 둔다. 검색 출처는 본문 인용과 펼칠 수 있는 목록으로 제공하며 별도 웹/파일 preview 패널은 만들지 않는다.
- **입력:** 데스크톱 Enter 전송·Shift+Enter 줄바꿈, IME 조합 중 Enter 전송 방지. 모바일은 Enter 줄바꿈·명시적 전송 버튼을 기본으로 한다. 생성 중 전송은 중단 버튼으로 바뀐다.
- **스크롤:** 답변 하단을 보고 있을 때만 자동 따라가기, 위로 읽는 중에는 `새 내용` 버튼 제공. 전송 실패 시 초안을 보존한다.
- **접근성:** 버튼·드롭다운 label, 명확한 focus, 키보드 조작, drawer/modal focus 복원, 최소 44px 조작 영역, 진행 상태의 제한적 live announcement를 제공한다. 토큰마다 스크린리더 알림을 내보내지 않는다.

### 폰트 설정은 기존과 동일

| 값 | 표시 이름 |
| --- | --- |
| `ibm-plex` | IBM Plex Sans KR (기본) |
| `suit` | SUIT Variable |
| `nanum-square` | NanumSquare Neo |
| `wanted-sans` | Wanted Sans |
| `line-seed-kr` | LINE Seed Sans KR |
| `goorm-sans` | Goorm Sans |
| `paperlogy` | 페이퍼로지 (Paperlogy) |
| `nexon-lv2-gothic` | Nexon Lv2 Gothic |

동일한 로컬 font asset·weight·한글/영문 fallback을 제공하고 설정 변경 즉시 목록·답변·입력창에 적용한다. 기존과 같이 브라우저에 저장하고 다시 열어도 유지한다. 글꼴 자산이 로드되지 않을 때는 대체 글꼴로 읽을 수 있어야 한다.

포트가 다르면 localStorage origin도 다르므로 기존 `codex-ui-font` 값이 자동 공유된다고 가정하지 않는다. 새 앱의 같은 키에 독립 저장하는 것을 기본으로 하며 기존 Workbench 설정에는 쓰지 않는다. 초기 자동 동기화는 범위에서 제외한다. UI 배율도 기존 80–110%, 5% 단위, 기본 90%·fold 내부 85%와 화면별 보존 UX를 재사용하되 파일 보기 설정은 제거한다.

### 상태별 필수 UX

| 상태 | 화면 동작 |
| --- | --- |
| 미로그인·계정 만료 | 계정 연결 안내, 입력 초안 보존 |
| 모델 목록 로딩·실패 | 상태 표시·재조회, 임의 모델로 자동 전환 금지 |
| 생성·검색 중 | 실제 단계 표시·중단 제공, 요청 설정 고정 |
| 검색 불가·실패 | 오류 이유와 검색 재시도/검색 없이 답변 선택 |
| 연결 끊김 | 재접속 상태와 마지막 이벤트부터 복구 |
| 취소·프로세스 중단 | 부분 응답에 중단 표시·새 attempt 재시도 |
| 사용량 미확정 | 집계 대기·최종 수집 시각 표시 |
| 문맥 한도 접근 | 축약 상태 또는 새 대화 안내, 원문 이력 보존 |

## 8. Proc Manager Web 등록 계획

사용자가 말한 루트 dinya의 관리 도구는 확인된 로컬 구조상 `/Users/dinya/works/proc_manager_web.py`와 `/Users/dinya/works/proc_manager_jobs.json`이다. 다른 위치의 별도 manager가 있다면 실제 구현 시 실행 중인 manager의 경로를 다시 확인한다.

신규 job 이름은 `Workbench Chat - conversation server`로 제안한다. Workbench 전용 동기화/상태 탐지 규칙과의 충돌도 등록 전 확인한다. 등록 payload 파일은 Workbench 안에 두고 관리 도구의 지원 API/UI로 등록한다. Proc Manager 코드 변경은 계획하지 않는다.

```json
{
  "name": "Workbench Chat - conversation server",
  "workdir": "/Users/dinya/works/dev_workspace/codex_workbench",
  "commands": [
    "export PYTHONUNBUFFERED=1",
    "export CHAT_DATA_DIR=/Users/dinya/works/dev_workspace/codex_workbench/.agent_state/conversation",
    "bash run_conversation_server.sh --host 127.0.0.1 --port 3101"
  ],
  "auto_start": true,
  "sequential": true,
  "restart_on_exit": false,
  "open_url": "http://127.0.0.1:3101"
}
```

이 예시는 loopback 기준이다. 기존처럼 tailnet 주소에서 직접 접속하려면 bind·접속 보호·`open_url`을 함께 조정한다. `0.0.0.0`으로 바꾸기만 해서 공개하지 않는다. Python·Codex 절대 경로와 최소 환경은 새 launcher에서 확인하고 기존 job의 `HOME` 재정의나 danger-full-access 설정을 복사하지 않는다. launcher는 실행 전 디렉터리·포트·의존성을 확인하고 자식 프로세스가 해당 job 수명에 종속되도록 한다.

`auto_start: true`는 사용자가 다음에 manager를 시작하거나 자동 시작 동작을 실행할 때 함께 구동하려는 목적이다. 현재 읽은 `add_task()`에는 즉시 시작 호출이 없어 등록과 시작을 분리할 수 있다. 다만 manager의 자동 시작 순서가 진행 중인지 등 실제 동작 상태는 등록 시점에 확인한다. 등록 순간 실행될 가능성이 있으면 먼저 `auto_start: false`로 등록하고 정지 상태에서 자동 시작 설정만 전환한다. `restart_on_exit: false`로 임의 재시작 루프도 막는다.

향후 구현 완료 후 등록 절차:

1. 포트 3101 충돌·launcher 준비·데이터 경로·기존 job 이름 중복을 확인한다. 같은 이름의 job이 있으면 중복 등록하지 않고 설정 차이를 검토한다.
2. 인증된 Proc Manager Web UI 또는 `POST /api/tasks`로 신규 job만 등록한다. API 인증 정보는 코드·문서·브라우저 저장소에 기록하지 않는다.
3. 반환된 job 식별자, 이름, working directory, 명령, open URL, 자동 시작 옵션을 다시 읽어 확인하고 **stopped, PID 없음**을 확인한다.
4. start/restart/start_all/web restart 등 실행 API를 호출하지 않는다. 기존 작업 job이나 manager 자체를 재시작하지 않는다.
5. 사용자에게 job 이름·주소·등록 상태를 전달한다. 최초 시작 및 필요한 서버 재시작은 사용자가 수행한다. 이후 자동 시작 시 기존 Workbench와 함께 올라오는지 확인한다.

현재 단계에는 실제 등록을 수행하지 않는다. 등록 후 사용자 시작 전에는 새 포트의 health 성공을 운영 완료 근거로 요구하지 않는다.

## 9. 구현 순서와 검증 기준

| 단계 | 산출물·작업 | 통과 조건 |
| --- | --- | --- |
| 1. 연결 검증 | 설치 버전 스키마·개인 계정·모델·검색·취소·권한 확인 | 번역·실제 검색·출처·사용량 확인, 저장소 지침·파일/명령 도구 미노출 |
| 2. 독립 실행 기반 | launcher·Flask·DB·provider adapter·접속 보호 | 별도 포트/PID/데이터, 기존 서버 import 부작용 없음 |
| 3. 대화 UX | responsive 대화·번역 옵션·검색·글꼴·SSE | 한국어 IME·모바일·설정 유지·초안 보존·출처 접근 검증 |
| 4. 공통 사용량 통합 | outbox·수집원·병합·앱 필터·정합성 | 정상·실패·취소·재시도의 원본 대비 합계 일치, 중복 수집 없음 |
| 5. 복구·회귀 | 단절·새로고침·프로세스 종료·계정/모델 전환 | 다른 대화 혼입 없음, 기존 Workbench 작업·설정·수집 유지 |
| 6. 등록만 수행 | Workbench 내 payload + Proc Manager 신규 job | stopped/PID 없음, 기존 job 불변, 사용자가 시작할 항목 안내 |
| 7. 사용자 시작 후 확인 | 동시 구동·health·실제 요청·사용량 | 두 앱 독립 동작과 공통 집계 확인; 재시작은 사용자 수행 |

검증에서는 번역 시 불필요한 검색 없음, 검색을 켠 요청의 실제 도구 호출과 출처 일치, 모델·추론 선택 반영, 폰트 8종·fallback, 360/768/1440px 화면, 중복 POST·SSE 재연결·취소 직후 대화 이동을 포함한다. 현재 작업에서는 테스트 서버나 모델 요청을 실행하지 않는다.

## 10. 문서 내 HTML 프로토타입 초안

계획문서만 변경한다는 범위에 맞춰 별도 `.html` 파일을 생성하지 않고 검토용 초안을 아래에 포함한다. 향후 `docs/standalone-chat-prototype.html`로 저장해 브라우저에서 열 수 있는 독립 HTML이다. 현재 브라우저 렌더링 검증이나 운영 기능 구현은 하지 않았다. 정적 예시이며 실제 모델·검색·사용량 API를 호출하지 않는다. 모델 드롭다운의 문구는 실제 모델명이 아닌 위치 표시다. 운영 폰트 8종·저장 동작은 7절 요구사항이며 이 작은 초안에는 포함하지 않는다.

```html
<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workbench Chat · 계획 목업</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f4f4;color:#161616;
font:16px/1.6 "IBM Plex Sans KR",system-ui,sans-serif}
button,select,textarea{font:inherit}button,select{min-height:44px;padding:8px 12px;
border:1px solid #8d8d8d;background:#fff;color:#161616;cursor:pointer}
button:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid #0f62fe;outline-offset:2px}
.shell{display:grid;grid-template-columns:256px 1fr;min-height:100dvh}
aside{background:#e8e8e8;border-right:1px solid #c6c6c6;padding:24px 16px}
aside button{display:block;width:100%;margin:12px 0;text-align:left}
main{display:flex;flex-direction:column;min-width:0}
header{padding:16px 24px;border-bottom:1px solid #c6c6c6;background:#fff}
.small{font-size:13px;color:#525252}.thread{width:min(100%,848px);margin:auto;padding:32px 24px;flex:1}
.user{padding:16px;background:#e0e0e0}.answer{margin-top:32px}
.composer{background:#fff;border-top:1px solid #c6c6c6;padding:16px 24px max(16px,env(safe-area-inset-bottom))}
.inner{max-width:800px;margin:auto}.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
textarea{display:block;width:100%;min-height:100px;padding:12px;border:1px solid #8d8d8d;resize:vertical}
.primary{background:#0f62fe;color:#fff;border-color:#0f62fe}.send{display:flex;justify-content:flex-end;margin-top:8px}
@media(max-width:1023px){.shell{grid-template-columns:1fr}aside{display:none}}
@media(max-width:599px){header,.composer{padding:12px}.thread{padding:20px 12px}}
</style>
<div class="shell">
<aside aria-label="대화 이력"><strong>Workbench Chat</strong><p class="small">검토용 정적 목업</p>
<button type="button">＋ 새 대화</button><p class="small">오늘</p>
<button type="button" aria-current="page">회의 일정 영어 번역</button>
<button type="button">검색한 주제</button><p class="small">Codex 계정 · 연결 상태 영역</p></aside>
<main>
<header><strong>회의 일정 영어 번역</strong><div class="small">계정 · 모델 · 사용량 · 화면 설정 영역</div></header>
<section class="thread" aria-label="메시지">
<div class="user">내일 회의를 오후 3시로 변경할 수 있을까요? 자연스러운 영어로 번역해줘.</div>
<article class="answer"><p class="small">Assistant · 선택한 Codex 모델</p>
<p>Would it be possible to move tomorrow’s meeting to 3 p.m.?</p>
<button type="button" id="copy">번역문 복사</button>
<p class="small" id="status" role="status">예시 응답 · 실제 모델을 호출하지 않았습니다.</p></article>
</section>
<div class="composer"><div class="inner">
<div class="row" aria-label="요청 바로가기"><button type="button" data-prompt="">일반 대화</button>
<button type="button" data-prompt="다음을 자연스러운 영어로 번역해줘: ">영어 번역</button>
<button type="button" data-prompt="웹에서 찾아 출처와 함께 요약해줘: ">웹 검색</button></div>
<div class="row"><select aria-label="모델"><option>사용 가능한 Codex 모델</option></select>
<select aria-label="추론 강도"><option>모델 기본 추론 강도</option></select>
<select aria-label="검색 설정" id="search"><option value="auto">검색: 자동</option>
<option value="on">검색: 켜기</option><option value="off">검색: 끄기</option></select></div>
<label for="message">메시지</label><textarea id="message" placeholder="원문을 붙여 넣거나 질문하세요"></textarea>
<div class="send"><button class="primary" type="button" id="send">전송 예시</button></div>
<p class="small">모델·검색·사용량·설정은 배치 예시입니다. 입력과 복사만 체험할 수 있습니다.</p>
</div></div>
</main></div>
<script>
const message=document.getElementById('message'),status=document.getElementById('status');
document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>{
message.value=button.dataset.prompt;
document.getElementById('search').value=button.textContent==='웹 검색'?'on':button.textContent==='영어 번역'?'off':'auto';
message.focus();}));
document.getElementById('send').addEventListener('click',()=>{status.textContent='정적 목업입니다. 입력 내용은 서버에 전송되지 않습니다.';});
document.getElementById('copy').addEventListener('click',async()=>{
try{await navigator.clipboard.writeText('Would it be possible to move tomorrow’s meeting to 3 p.m.?');status.textContent='번역문을 복사했습니다.';}
catch{status.textContent='브라우저에서 복사를 허용하지 않습니다. 위 번역문을 선택해 복사하세요.';}});
</script>
</html>
```

이 초안은 화면 위계와 읽기 폭을 검토하기 위한 것이다. 실제 구현에서는 모바일 이력 drawer, 폰트·배율 설정 sheet, 번역 옵션, 검색 출처·진행·오류 화면, 실제 스트리밍·접근성 검증을 7절 기준으로 추가한다.
