# Workbench Chat 운영 안내

개인 Codex 계정으로 영어 번역·영문 교정·웹 검색·일반 대화를 제공하는 독립 Flask 앱이다. 기존 작업 서버를 import하지 않는다. 별도 API key나 DTGPT를 사용하지 않는다.

## 실행과 등록

- Proc Manager job: `Workbench Chat - conversation server`
- 로컬 주소: `http://127.0.0.1:3101`. 외부 브라우저는 기존 인증 게이트웨이의 **HTTPS Chat 링크**를 사용한다. 기존 `http://dinya.wind-mintaka.ts.net:3101` 직접 접속은 암호화 API를 사용할 수 없어 전송이 차단된다.
- Tailscale 내부 Chat 주소: `https://dinya.wind-mintaka.ts.net:3102/`. 2026-10-30 `tailscale serve --bg --https=3102 http://127.0.0.1:3101`로 등록했다. 3101의 기존 서버와 다른 포트의 Serve/Funnel 설정은 유지하며, 3102는 Funnel로 공개하지 않는다. 해제 명령은 `tailscale serve --https=3102 off`다. Proc Manager는 Tailscale 도메인·IP로 접속하면 Chat 열기 링크를 이 HTTPS 주소로 연결한다. 로컬 HTTP 접속과 외부 HTTPS 대시보드의 Funnel 링크는 기존 동작을 유지한다. Proc Manager 코드 변경 후에는 사용자가 Proc Manager를 재시작해야 반영된다.
- 같은 날 Chromium으로 HTTP의 `isSecureContext=false`·Web Crypto 미제공과 HTTPS의 암호화 연결·모델 8개·대화 3개 로딩을 확인했다. 캐시된 이전 HTML에 계정/사용량 접기 요소가 없어도 `responsiveSidebar()`가 초기화를 중단하지 않도록 호환 처리했다. 실제 모델 생성 요청과 운영 서버 재시작은 수행하지 않았다.
- 등록 payload: `ops/workbench-chat.job.json`; 실제 확인 기록: `ops/workbench-chat.registration.json`
- 등록 결과: **idx 16 / STOPPED / PID 없음**, 기존 16개 job의 설정·상태·PID는 최초 snapshot과 동일하다.
- 외부 접속용 등록 payload는 `--host 0.0.0.0 --allowed-host dinya.wind-mintaka.ts.net --allowed-network 100.64.0.0/10`을 지정한다. `open_url`은 로컬 기준으로 두고 Proc Manager의 공통 링크 정책을 사용한다. HTTP 대시보드는 현재 접속 호스트의 3101 포트로, HTTPS 대시보드는 기존 Funnel 링크가 있으면 그 링크로 연다. 대시보드의 **Codex Workbench 그룹 마지막·보라색 표시**는 유지한다.
- **최초 시작·재시작은 사용자 수행.** 등록은 start/restart API를 호출하지 않는다. `auto_start: true`는 다음 Proc Manager 자동 시작 때 함께 실행하려는 설정이다. `restart_on_exit: false`다.
- 옵션 없이 실행하면 기존대로 loopback 전용이다. 외부 접속은 명시한 호스트와 클라이언트 CIDR을 모두 만족해야 한다. 허용 CIDR에 속하는 IP 리터럴 주소도 Host로 허용한다. 현재 payload는 Tailscale 클라이언트만 추가 허용하며 LAN·공인 인터넷 직접 요청은 차단한다. `X-Forwarded-For`로 접속 권한을 부여하지 않는다. 기존 same-origin·CSRF 검사를 유지한다. 공용 Funnel을 새로 등록하거나 인증 설정을 변경하지 않는다.
- 명령: `bash run_conversation_server.sh --host 127.0.0.1 --port 3101`
- Python 3.11 이상, Flask와 cryptography가 필요하다 (`requirements.txt`). 등록 job은 검증한 `/opt/homebrew/bin/python3.14`를 지정한다.
- Proc Manager가 `HOME=/Users/dinya/works`로 실행해도 launcher는 OS 로그인 홈의 Python 사용자 패키지를 찾는다. macOS framework Python은 `~/Library/Python/<version>`을 `PYTHONUSERBASE`로 설정하며, 명시적으로 지정한 `PYTHONUSERBASE`는 유지한다. `PYTHONPATH`를 Workbench에서 상속받지 않아도 동작한다.
- Codex CLI **0.160.0**의 실제 전송 도구를 검증했다. 다른 버전에서는 모델 실행을 차단한다. CLI 업그레이드 시 `RUN_CODEX_CHAT_NATIVE_TESTS=1 ... -m pytest tests/test_conversation_provider.py -q`로 도구 격리를 재검증하고 버전 제한을 갱신한다. App Server는 버전별 동작 차이가 있으므로 알 수 없는 버전에 자동으로 권한을 열지 않는다.
- 기존 Workbench의 **Dev Codex Workbench job**도 사용자가 재시작하면 새 사용량 앱 필터·명시적 Chat outbox 수집 코드가 적용된다. 다른 체크아웃에는 소스를 동기화하지 않았다.

## 저장과 계정

기본 데이터는 `.agent_state/conversation/`이다. `CHAT_DATA_DIR`로 명시적으로 바꿀 수 있으며 수집기의 같은 환경에도 동일한 값을 설정해야 한다. 데이터 디렉터리는 0700, DB·세션 비밀·인증 snapshot은 0600이다. 실행 중 백업은 SQLite backup API를 쓰거나 사용자가 정지한 뒤 DB/WAL을 일관되게 보관한다.

| 데이터 | 용도 |
| --- | --- |
| `conversations.sqlite3` | 대화·메시지·설정·attempt·재전송 이벤트·출처·사용량 outbox |
| `codex_home/<account>/<provider identity hash>/` | 계정별 Codex 실행 DB·rollout·채팅 전용 모델 카탈로그 |
| `empty_workspace/` | 저장소 작업을 하지 않는 빈 실행 경로 |
| `session.key`, `server.lock` | 독립 cookie 서명·데이터 경로 단일 서버 보장 |

macOS 실제 로그인 홈의 `.codex-workbench/codex_accounts.json`을 읽어 기존 개인 계정을 표시한다. `HOME`이 작업 프로세스에서 바뀌어 있어도 로그인 홈으로 해석한다. 별도 계정 registry를 지정할 때는 기존 `CODEX_WORKBENCH_SHARED_ACCOUNT_STATE_DIR`를 사용할 수 있다.

기존 인증의 access/id token 및 `last_refresh`만 전용 home에 snapshot으로 보관한다. **refresh token은 복사하지 않고 원본 인증·설정을 수정하지 않는다.** 기존 Workbench/CLI가 유일한 인증 갱신 주체다. 계정 만료 시 기존 로그인에서 갱신한 뒤 Chat의 ‘연결·모델 새로고침’을 누른다. 모델 조회 결과에는 비밀을 반환하지 않는다. 현재 추가 등록 계정 2개는 로그인 정보가 없어 실제 복수 계정 전환 호출은 검증하지 못했다. 계정 identity별 home 분리·미로그인 실패 처리는 테스트했다.

## 대화·검색 동작

대화 생성·제목 검색·제목 변경·삭제, Markdown·복사, 재시도, 중단을 지원한다. 재시도는 마지막 메시지의 새 attempt이며 기존 답변·사용량을 덮어쓰지 않는다. 한 대화에는 활성 요청 하나, 전체에는 모델 요청 두 개를 허용한다.

요청마다 새 provider thread를 만들어 완료된 대화 문맥을 한 번 전달한다. 이전 thread에 전체 이력을 중복 삽입하지 않는다. 이 방식은 검색/모델/계정 변경 시 도구·문맥 격리를 단순화한다. 로컬 DB가 대화의 원본이다. 180,000자를 초과하는 전달 문맥은 생략하지 않고 새 대화를 안내한다. 자동 요약·장문 분할은 제공하지 않는다. 긴 대화는 새 대화로 전환한다.

번역은 대상 언어·톤·결과 형식을 선택하며 검색이 기본 꺼진다. 검색은 자동/켜기/끄기로 제공한다. 켜기는 실제 검색을 지시하며 검색 이벤트가 없는 완료 응답은 실패로 표시한다. 실시간 검색 이벤트로 진행 상태와 출처명·URL·검색 시각을 저장한다. 게시일이 없으면 만들어 넣지 않는다. 검색 기능 오류에는 메시지와 재시도, 검색 끄기 선택을 제공하며 다른 backend로 전환하지 않는다.

이벤트는 SQLite에 저장하고 SSE event ID로 재연결한다. 화면 이동 시 이전 스트림은 닫으며 응답은 서버에서 보존한다. 재실행 시 미완료 attempt를 interrupted로 복구한다. SIGTERM 시 앱이 생성한 Codex 자식만 정리한다. 실행 중인 다른 Workbench/Proc Manager는 건드리지 않는다.

영어 번역·교정·검색 중심의 채팅 전용 지침과 수정한 모델 메타데이터를 사용한다. shell·apply_patch·파일 보기·MCP·앱·플러그인·skills·코드 실행·에이전트 위임을 제거했다. ultra 추론은 자동 위임을 동반하므로 노출하지 않는다. 현재 실제 CLI 전송 요청에는 `chat_artifact`만 제공하고, 검색을 켜면 `web.run`을 추가한다. 모델의 셸·패치·임의 파일 도구는 제공하지 않는다. read-only sandbox를 도구 격리의 대체물로 사용하지 않는다.

## UI·접속 보호

360/768/1440px 반응형 대화 UI, 모바일 이력 drawer, 네이티브 설정 dialog, 기존 로컬 font asset 8종과 즉시 적용·저장, 80~110% 배율을 제공한다. `codex-ui-font`는 포트별 localStorage에 독립 저장한다. 파일 preview·파일 업로드·저장소 패널은 없다.

데스크톱 Enter 전송/Shift+Enter 줄바꿈, IME 조합 보호, 모바일 Enter 줄바꿈, 초안 보존, 위로 읽는 동안 자동 스크롤 억제를 적용했다. Markdown은 기존 pinned marked/DOMPurify로 정화한다. 링크는 http(s)만 허용한다. Host/Origin 검증·독립 session cookie·CSRF·CSP와 loopback 접근 제한을 적용했다.

## 공통 사용량 수집

Chat은 자신의 SQLite outbox만 갱신한다. 기존 Workbench 수집기가 원장/rollout/outbox를 병합해 공통 계정별 수집 cache를 단독으로 갱신한다. 기존 discovery roots는 보존하고 Chat home을 추가한다. 수집은 기본 최대 5분 cache를 사용한다.

- provider account identity + thread + turn으로 정확히 결합한다. 반복 수집은 합산을 반복하지 않는다.
- 실시간 누적 사용량은 attempt별 최신값으로 교체하고, 최종 rollout이 있으면 토큰 구성과 모델 구간을 원본으로 교체한다.
- cache input과 reasoning output을 total에 다시 더하지 않는다.
- 대화 삭제 후에도 본문이 없는 최소 사용량 회계와 Codex rollout은 남는다. 대화 삭제가 rollout 삭제를 뜻하지 않는다.
- 중단 직후 provider가 usage를 전혀 반환하지 않을 수 있다. 이때 outbox에는 `usage_pending: true`로 매핑만 보존하고 화면에 **사용량 집계 대기**를 표시한다. 알 수 없는 사용량을 확정 0으로 표시하지 않는다. 수집 진단 `chat_pending_attempts`에서 확인할 수 있다.
- 사용량 화면의 `전체 앱 / Workbench / Chat / 미분류` 필터는 기존 환경 필터와 독립적이다. 앱을 확인할 수 없는 과거 rollout도 전체 합계에 남는다.
- 계정 사용 한도 snapshot과 Chat 토큰 합계는 별개다. Chat dialog는 관측 토큰·대기 건수를 표시하며 기존 대시보드에서 전체 계정/모델/일별 분석을 확인한다.

## 검증 기록 (2026-10-28)

- 기동 오류 수정: Proc Manager job 16 로그의 `ModuleNotFoundError: No module named 'flask'`를 `PYTHONPATH` 없이 변경된 HOME으로 재현했다. launcher 수정 후 같은 환경에서 임시 데이터·33101 포트로 실제 기동, `/health` 및 지정 Chromium runner의 `#composer` 검증을 통과했다. 운영 job은 시작·재시작하지 않았다.
- launcher 포함 Chat Python 테스트 11개 통과, native provider 테스트 1개는 기존 opt-in 조건으로 건너뛰었다. Proc Manager 분류·로컬 URL·기존 인증 관련 테스트 39개 통과. 대시보드는 읽기 전용 임시 fixture의 Chromium 검증에서 그룹·마지막 배치·보라색·로컬 링크·그룹 필터·콘솔 오류 없음까지 통과했다.

- 관련 Python 검증 **32개 통과**. Flask/SQLite·권한·중복 POST·SSE 재연결·취소·재시도·삭제 후 회계·재시작 복구·앱 필터·기존 수집 회귀 및 실제 CLI 전송 도구 검증: `tests/test_conversation_*.py`, `tests/test_usage_dashboard.py`, `tests/test_model_usage_analysis.py`, `tests/test_usage_reconciliation.py`.
- 실제 개인 계정·GPT-6.1-Sol low: 영어 번역 312 tokens, 실시간 검색 20,868 tokens, 합계 21,180 tokens. 공통 수집기에서 최종 rollout과 정확히 일치하고 재수집 후 중복 없음. 검증 대화 본문은 삭제했으며 회계는 보존했다.
- 실제 GPT-6-Luna high의 모델·추론 반영과 응답 중단도 검증했다. 빠른 중단 시 provider가 사용량을 반환하지 않는 경우를 확인해 집계 대기로 처리한다.
- Chromium 360/768/1440px: 글꼴 8종 실제 로딩, IME, 전송, Markdown/XSS, 초안·설정 복원, drawer·접근성 초점, 가로 넘침 없음.
- 기존 `test_codex_chat_streams.py`: 337 통과, 24 실패. 변경 전 HEAD를 별도 디렉터리에서 검증해 동일한 실패 24개를 확인했다. 오래된 날짜 fixture 및 subprocess Python 버전 probe mock 관련 기존 문제이며 이번 변경에서 새로 발생한 실패는 없다.
- 운영 Chat 서버·기존 서버·Proc Manager의 시작/종료/재시작 API는 호출하지 않았다. 모델 검증용 Codex 자식 프로세스와 로컬 요청 캡처용 임시 서버는 테스트 종료 시 정리했다.

## 외부 링크 수정 적용

- Workbench 소스 변경과 외부 접속용 payload는 이 체크아웃에만 작성한다.
- 사용자 승인 후 `/Users/dinya/works/proc_manager_web.py`의 Chat 전용 로컬 주소 고정 예외 두 곳과 `/Users/dinya/works/test_proc_manager_chat.py`의 기대값을 수정했다. `ops/proc-manager-chat-external.patch`와 `ops/proc-manager-chat-external-tests.patch`는 적용 내역 참고용이며 재적용하지 않는다.
- 패치 적용과 Chat job 명령 갱신 후 사용자가 **Proc Manager Web**, **Workbench Chat - conversation server**를 재시작해야 반영된다. `ops/workbench-chat.registration.json`은 이전 등록 시점의 기록이며 현재 프로세스 상태로 해석하지 않는다.

- 이전 검증: 서버·launcher·패치 회귀 테스트 11개 통과. 임시 Flask 서버(33109)의 실제 채팅 화면과 패치에서 추출한 링크 함수를 지정 Chromium runner로 검증했다.
- 승인 후 적용 검증: Proc Manager 분류·인증 테스트 39개와 설치된 소스를 읽는 외부 링크 회귀 테스트 2개 통과. 임시 서버에서 실제 링크 함수로 생성한 링크를 지정 Chromium runner로 한 번 검증해 로컬·외부 도메인·Tailscale IP·HTTPS 기본 링크·HTTPS Funnel 링크 선택을 확인했다. 임시 서버는 정리했으며 운영 프로세스는 재시작하지 않았다.
- Chat job 16의 명령은 지원 API(`PUT /api/tasks/16`)로 외부 접속용 payload와 일치하도록 갱신했다. 갱신 전후 RUNNING/PID 25915가 유지됐으며 다른 job의 명령·URL·플래그·상태·PID도 동일했다. 시작·정지·재시작 API는 호출하지 않았다.

## 경로형 Funnel / Cloudflare 게이트웨이

- `/apps/<slug>/` 또는 `/chat/` 등 하위 경로에서 열어도 API와 SSE URL은 실제 로드된 `static/js/chat.js`의 앱 루트를 기준으로 생성한다. HTML의 정적 리소스와 CSS의 글꼴도 상대 경로를 사용한다. 루트 `/api/...`로 빠져 게이트웨이 포털 HTML(HTTP 200)을 받던 문제를 수정했다. CSP에 차단되는 게이트웨이 인라인 스크립트에 의존하지 않는다.
- 로컬 프록시가 TLS를 종료하고 Host를 루프백으로 변경하면, 루프백 소켓 요청에 한해 `X-Forwarded-Host`와 `X-Forwarded-Proto`로 외부 Origin을 확인한다. 실제 소켓·Host 허용 규칙과 세션 CSRF 검사는 유지하며, 원격 소켓의 전달 헤더는 Origin 허용에 사용하지 않는다.
- 이 동작은 기존 Proc Manager 인증 게이트웨이를 경유하는 구성을 위한 것이다. Chat 3101 포트로 터널을 직접 연결하는 경우에는 별도로 접근 인증을 제공하고 `--allowed-host`에 실제 공개 호스트를 지정해야 한다. 이 수정은 공개 호스트나 네트워크를 자동 허용하지 않는다.
- 검증: Python 회귀 16개 통과, 실제 CLI opt-in 테스트 1개 제외. 임시 경로형 게이트웨이와 가짜 Codex provider에서 지정 Chromium runner 1회로 계정·모델·추론·글꼴·설정 저장·메시지 전송·SSE 표시를 확인했다. 운영 로컬 API는 계정 3개(인증 1개), 해당 계정의 모델 8개를 반환했다. 실제 외부 인증 세션에서는 검증하지 않았다.
- 반영하려면 사용자가 **Workbench Chat - conversation server**를 재시작하고 외부 페이지를 새로고침한다. Proc Manager 변경이나 재시작은 필요하지 않다.


## Cloudflare 전송·UUID·산출물 제한 보완 (2026-10-28)

- 현재 `cloudflared`는 `127.0.0.1:19443`의 인증 게이트웨이를 사용한다. 게이트웨이가 내부 Host로 요청을 전달하므로 공개 Origin과 다를 수 있다. 게이트웨이 소스는 자체 전달 헤더를 추가하면서 기존 헤더도 통과시켜 중복 값이 발생할 수 있다. 운영 로그인 세션의 실제 실패 요청은 관측하지 못했으며, 이 조건을 회귀 테스트로 재현했다.
- loopback 프록시 요청은 브라우저가 설정한 `Sec-Fetch-Site: same-origin`과 **세션에 결합된 CSRF 토큰**을 함께 확인해 공개 Origin을 허용한다. 정확한 Host·실제 소켓 네트워크 검사는 계속 적용한다. 단일 정상 전달 헤더를 사용하는 기존 게이트웨이도 지원한다. 원격 소켓·cross-site 요청·토큰 누락은 허용하지 않는다. 게이트웨이 외부 소스는 수정하지 않았다.
- API의 403 응답은 `host_not_allowed`, `network_not_allowed`, `origin_mismatch`, `csrf_mismatch` 코드와 각 원인에 맞는 안내를 반환한다. 인증 게이트웨이를 우회하여 Chat 포트에 직접 연결하는 터널은 여전히 실제 공개 호스트를 `--allowed-host`에 명시해야 한다. 와일드카드 공개 호스트는 허용하지 않는다.
- HTTP LAN/Tailscale에서 `crypto.randomUUID`가 없으면 `crypto.getRandomValues`로 UUID v4를 생성한다. Web Crypto 전체가 없을 때에는 시간과 난수로 재전송 식별자를 만든다. 이 값은 인증·CSRF 비밀로 사용하지 않는다. JS 버전은 4로 갱신했다.
- 모델의 파일 작업은 서버가 처리하는 `chat_artifact` 도구로만 제공한다. 사용자 요청에 따른 UTF-8 텍스트 산출물의 생성·전체 내용 교체·읽기·삭제를 지원한다. 도구 하나당 파일 크기는 1 MiB까지다. 임의 코드 실행·셸·Git·저장소 수정·임의 로컬 파일 읽기는 허용하지 않는다.
- 산출물은 `/tmp/workbench-chat-*`의 권한 0700 전용 폴더, 파일은 0600으로 생성한다. 같은 계정·대화는 서버가 실행 중인 동안 동일 폴더를 사용한다. 대화 ID는 서버가 지정하고 클라이언트가 파일 경로/범위를 지정할 수 없다. 서버 재시작 후에는 새 폴더를 배정하며 기존 산출물은 지우지 않는다. `/tmp`이므로 OS의 임시 파일 정리 대상이다.
- 절대 경로, `..`, 심볼릭 링크, 하드링크, 특수 파일을 거부한다. 디렉터리 descriptor와 `O_NOFOLLOW`, 원자적 교체로 경로 확인 후 링크를 바꾸는 우회도 방어한다. `/tmp` 전체나 다른 대화의 폴더를 파일 도구에 개방하지 않는다. 대화 DB·인증 snapshot·사용량 등 앱 내부 상태는 기존 데이터 경로에서 서버가 관리하며 모델 도구로 접근할 수 없다.
- 도구 연결은 [OpenAI Docs의 App Server dynamic tools 프로토콜](https://learn.chatgpt.com/docs/app-server#dynamic-tool-calls-experimental)을 따르며 고정된 CLI 0.160.0으로 검증한다. 가짜 로컬 모델 응답으로 실제 도구 전송 목록과 JSON-RPC 파일 생성을 확인하므로 실제 계정 토큰·유료 모델 요청은 보내지 않는다.
- 반영: 사용자가 **Workbench Chat - conversation server**를 재시작한 다음 페이지를 새로고침한다. 이번 작업에서는 운영 서버·Proc Manager·터널을 재시작하지 않았다. 실제 Cloudflare 인증 브라우저 세션 검증은 별도로 남아 있다.

- 이번 검증: native CLI 도구 전송·실제 산출물 호출을 포함한 관련 Python 테스트 **36개 통과**, Chromium **360/768/1440px**에서 `randomUUID` 없는 상태의 전송·폰트·설정·XSS 회귀 통과. `git diff --check` 통과.


## Chat 사용량·화면 설정·자동 제목

- 계정 영역과 사용량 창에서 선택 계정의 5시간·주간 사용 비율, 남은 비율, 초기화 시각을 표시한다. `/api/usage/limits?account_id=…`는 격리된 App Server의 `account/rateLimits/read`를 사용하며, 토큰 누적 집계와 구분한다. 공식 프로토콜: https://learn.chatgpt.com/docs/app-server
- 창이 보이는 동안 60초마다 갱신하며 계정 전환, 답변 완료, 수동 새로고침에서도 갱신한다. 서버 캐시는 계정 및 provider identity별 60초이며, 강제 조회에도 10초 중복 요청 방지를 적용한다. 제공되지 않은 기간은 미제공, 실패한 조회는 오류로 표시한다. 서버 시각은 관측 시각이며 초기화 시각은 접속 기기의 현지 시간으로 표시한다.
- 화면 설정에서 시스템/라이트/다크를 선택하며 기존 글꼴·배율 설정과 함께 브라우저에 저장한다. 답변과 입력 영역은 데스크톱에서 최대 1440 CSS px까지 확장된다. 코드에는 로컬 D2Coding을 사용하고 코드 복사 버튼을 제공한다. 인용문은 선택한 UI 글꼴을 사용한다.
- 새 대화 첫 요청의 동일 모델 응답에 짧은 제목 메타데이터를 요청한다. 서버는 스트리밍 메타데이터를 답변에서 분리하여 제목으로 저장하므로 별도 제목 생성 호출이 없다. 제목이 누락되면 첫 프롬프트 일부를 임시 제목으로 유지한다. 직접 변경한 제목과 기존 대화 제목은 덮어쓰지 않는다. 빈 대화를 만드는 시점에는 제목을 추론할 내용이 없으므로 첫 전송 후 제목이 정해진다.
- 변경 없는 메시지의 DOM을 유지하며, 정제된 Markdown은 최대 24개·250,000자 입력 범위에서 캐시한다. 생성 중에는 텍스트를 표시하고 완료·취소 시 Markdown을 적용한다. HTML 정제와 HTTP(S) 링크 제한, 저장소 도구 차단 및 전용 `/tmp/workbench-chat-*` 산출물 제한은 유지된다.
- 적용은 **Workbench Chat - conversation server** 재시작과 브라우저 새로고침이 필요하다. 실행 중인 운영 작업은 자동 재시작하지 않는다.

## 브라우저 전송 암호화와 성능 개선 (2026-10-29)

기존 작업모드는 `codex-web-app/services/file_crypto.py`를 통한 ECDH/AES-GCM 경로를 제공했지만 독립 Chat의 JSON·SSE에는 적용되지 않았다. Chat은 독립 모듈 `conversation-app/services/transport.py`와 브라우저 `static/js/transport.js`로 다음 전송 보호를 강제한다. 기존 작업 서버를 import하지 않는다.

- 브라우저와 Chat 서버가 ECDH P-256으로 임시 키를 합의하고, HKDF-SHA256으로 요청·응답용 256비트 AES-GCM 키를 따로 만든다. 인증 태그는 128비트, IV는 암호학적 난수 96비트다. Web Crypto의 비동기 네이티브 연산을 사용하며 암호화 라이브러리/WASM을 브라우저에 추가하지 않는다.
- `/api/crypto-session`에는 공개키·salt·만료 시각만 오간다. 나머지 API 요청은 경로·검색어·본문을 모두 `/api/secure`의 암호문에 넣는다. 프롬프트·답변·제목·이력·계정·모델·설정·사용량·출처와 API 오류 응답도 암호화한다. 기존 평문 API 직접 호출은 428로 거부한다.
- 키는 서버의 프로세스 메모리와 브라우저 페이지 메모리에만 보관하며 쿠키/localStorage에 기록하지 않는다. 채널은 CSRF 세션에 결합하고 15분 만료, 요청 IV 재사용 차단, 요청·응답 키 분리, 응답의 요청 IV 결합 및 스트림 순서 검증을 적용한다. 서버는 채널 256개·브라우저 세션당 16개·채널당 요청 8,192개로 메모리를 제한한다. 만료는 디스패치 전에 거부하고 브라우저가 키를 갱신해 한 번 재시도한다.
- 암호화 SSE는 fetch 스트림으로 순차 복호화한다. 요청을 처리한 시점의 이력 스냅샷에 event cursor를 함께 반환해 이미 표시한 delta가 중복되지 않게 한다. 스트림이 끊기면 마지막 적용 cursor 이후부터 다시 연결한다. 정상 수신 중에는 전체 이력을 재조회하지 않고 현재 답변만 100ms 간격으로 갱신한다. 최종 상태·출처는 완료 시 한 번 다시 조회한다.
- 생성 중에는 단일 텍스트 노드에 추가하고 완료 시 Markdown을 처리한다. 완료된 DOM·코드 복사 버튼·펼친 출처는 유지하며 화면 밖 메시지는 `content-visibility`로 레이아웃·페인트 비용을 줄인다. 백그라운드 탭의 중간 렌더링을 생략하고 복귀 시 누적 내용을 반영한다. 초안 localStorage 저장은 400ms로 병합하고 페이지 이탈 시 flush한다.
- 이력 조회는 메시지별 별도 DB 연결 대신 한 연결에서 메시지와 attempt를 조회한다. 관련 색인을 추가하고 SSE는 최대 128개 이벤트씩 묶어 암호화한다. 정적 JS/CSS/글꼴은 private 1일 캐시, HTML·API·이벤트는 `no-store`다.

### 보호 범위와 접속 조건

외부 접속에는 HTTPS가 필요하다. Web Crypto를 사용할 수 없는 원격 HTTP 환경에서는 **평문 전송으로 우회하지 않고** 안내와 함께 전송을 막는다. `http://localhost`/`127.0.0.1`은 브라우저가 신뢰하는 로컬 개발 예외다. Tailscale HTTP 주소는 네트워크가 암호화되어도 브라우저의 secure context 조건을 충족하지 않는다. 기존 HTTPS 게이트웨이를 사용하며 이 변경은 게이트웨이·터널을 새로 등록하거나 수정하지 않는다.

이 보호는 **신뢰한 페이지 코드와 키 교환을 전제로**, 네트워크 패킷·TLS 종료 프록시 로그에 대화 본문이 평문으로 남지 않도록 하는 브라우저↔Chat 서버 구간의 추가 암호화다. 접속 호스트·트래픽 크기·시각·공개키 등의 메타데이터는 숨기지 않는다. HTTPS는 페이지와 키 교환의 상대를 인증하는 역할도 하므로 계속 필요하다.

사내 보안 장비가 신뢰 인증서를 사용해 페이지/스크립트나 ECDH 공개키를 능동적으로 바꾸거나, 관리 브라우저·확장 프로그램·단말 DLP·화면/키보드를 감시하면 이 구현으로 열람을 방지한다고 보장할 수 없다. 비밀 키의 사전 배포/독립 검증이 없는 웹 앱이므로 이런 환경에 대한 종단간 기밀성을 주장하지 않는다. Chat 서버와 모델 제공자는 처리할 평문을 보며, 기존 SQLite/rollout·산출물·브라우저 초안의 저장 암호화는 이번 변경 범위가 아니다. 기존 파일 권한은 유지한다.

공식 규격: [W3C Web Cryptography](https://www.w3.org/TR/webcrypto/), [W3C Secure Contexts](https://www.w3.org/TR/secure-contexts/).

재현 가능한 검증은 `python3.14 -m pytest tests/test_conversation_*.py -q`와 임시 fixture 서버 `python3.14 tests/serve_conversation_fixture.py --port 0`을 사용한다. 출력된 loopback URL에 대해 `CODEX_VERIFY_CONVERSATION=1 python3.14 scripts/verify_browser_ui.py --url <URL> --selector '#composer' --timeout-ms 120000`를 실행한다. fixture는 실제 계정·모델을 호출하지 않고 임시 DB를 사용한다. 종료 시 해당 임시 서버만 정리한다.

검증 결과: 관련 Python 테스트 **55개 통과·실제 모델 opt-in 1개 제외**. 지정 runner의 Chromium **360/768/1440/1920px**에서 실제 Web Crypto↔Python 암호화 왕복, SSE 끊김 복구·취소·중복 방지, 완료 DOM 유지, Markdown/XSS·코드 복사·8개 글꼴·다크모드·사용 한도 오류 복구와 Web Crypto 미제공 시 전송 차단을 통과했다. 브라우저 콘솔 오류는 없었다. 합성 부하(메시지 151개·약 60,000자 생성 중 답변)의 100회 갱신은 이 머신에서 91.7ms, 중간 Markdown 파싱 0회였다. 이는 특정 fixture의 동기 갱신 측정치이며 실제 회사 네트워크·모바일 기기의 지연이나 메모리 사용량을 보장하지 않는다. 실제 사내 인증 브라우저·TLS 검사 장비에서는 검증하지 않았다. 운영 서버·Proc Manager·터널은 재시작하지 않았다.

### 외부 HTTPS·프록시 재검증 (2026-10-29)

**모든 외부 접속 경로의 정상 동작을 확인한 것은 아니다.** HTTPS에서의 암호화 호환성과 터널의 SSE 전달 지원은 별도 조건이다.

- 읽기 전용으로 확인한 현재 구성: Tailscale Funnel의 443 포트와 `cloudflared tunnel --url http://127.0.0.1:19443`가 기존 인증 게이트웨이를 사용한다. 실제 두 HTTPS 주소에 GET을 보내 인증서 검증 성공과 HTTP 303 로그인 리다이렉트를 확인했다. 로그인 세션을 사용한 Chat API·모델 요청은 보내지 않았다. 이 머신에서의 접속이므로 사내망/별도 외부 단말에서의 도달성을 입증하지 않는다.
- 현재 Cloudflare는 `trycloudflare.com` Quick Tunnel이다. [공식 Quick Tunnel 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)에 **SSE 미지원**이 명시되어 있다. 현재 Chat은 암호화한 `POST /api/secure` 응답에도 `text/event-stream`을 사용하므로 AES 적용으로 이 제한이 없어지지 않는다. 스트림 버퍼링 시 실시간 표시·완료·취소 상태 반영이 지연되거나 끊길 수 있다. 현재 클라이언트에는 스트림 무응답 감지 후 JSON 폴링으로 전환하는 기능이 없다. Cloudflare 사용을 확정하려면 named tunnel에서 인증 후 스트리밍을 검증하거나, 암호화 JSON 이벤트 폴링 경로를 추가해야 한다. 이번 검증에서는 터널 변경이나 폴링 기능을 구현하지 않았다.
- [Funnel은 HTTPS로 로컬 서비스를 프록시한다](https://tailscale.com/docs/features/tailscale-funnel). 로컬 게이트웨이 소스에서도 응답 MIME에 따른 스트림 전달을 확인했지만, 실제 인증 후 Funnel 전체 경로의 스트리밍 성공으로 간주하지 않는다.
- 임시 loopback HTTPS fixture에서 TLS 종료 후 HTTP upstream의 Host 변경, 정상 전달 헤더와 Cloudflare식 중복 전달 헤더를 재현했다. `/`, `/chat/`, `/apps/workbench-chat/` 경로에서 지정 Chromium runner **1회**로 **360/768/1440/1920px** 검증을 통과했다. 실제 Web Crypto 키 교환·암호문 API/SSE·재연결·취소·Markdown·폰트·콘솔 검사를 포함한다. fixture의 임시 자체 서명 인증서에만 테스트용 인증서 오류 허용 옵션을 사용했다. 공개 인증서 체인 검증은 앞의 실제 HTTPS GET 결과와 구분한다. 실제 프록시 소켓/Cloudflare edge 자체를 fixture에 포함하지 않는다.
- 추가한 4개 프록시 조건 테스트는 암호화 키 교환과 실제 `/api/secure` 요청의 생성·복호화·CSRF 누락 차단·cross-site 차단을 확인한다. provider 완료 전에 첫 암호화 SSE 프레임을 읽어 앱의 스트림이 전체 응답을 버퍼링하지 않는지도 확인한다. 전체 관련 Python 테스트 **59개 통과·실제 모델 opt-in 1개 제외**.

재현 명령:

```sh
python3.14 -m pytest tests/test_conversation_*.py -q
python3.14 tests/serve_conversation_fixture.py --https-proxy --port 0
# 별도 터미널: 위 서버가 출력한 포트 사용
CODEX_VERIFY_CONVERSATION=1 CODEX_VERIFY_LOCAL_TLS=1 python3.14 scripts/verify_browser_ui.py \
  --url https://127.0.0.1:<PORT> --selector '#composer' --timeout-ms 120000
```

`CODEX_VERIFY_LOCAL_TLS=1`은 자체 서명 로컬 fixture 검증 전용이며 실제 외부 인증서 검증에 사용하지 않는다. 검증 후 임시 서버만 종료했다. 운영 서버·Proc Manager·Funnel·Cloudflare 설정과 프로세스는 변경하거나 재시작하지 않았다. 이번 추가 변경은 테스트·검증 설정·문서뿐이므로 이 검증 자체를 적용하기 위한 운영 재시작은 필요 없다.

### 임시 Cloudflare 주소용 암호화 JSON 폴링 (2026-10-29)

앞 절에서 남아 있던 JSON 폴링을 구현했다. `*.trycloudflare.com` 접속은 SSE를 시도하지 않고 처음부터 암호화 JSON 폴링을 사용한다. 특정 임시 호스트명은 저장하거나 고정하지 않는다. API 주소는 기존과 같이 현재 로드한 스크립트를 기준으로 계산하므로 주소 변경과 `/chat/`, `/apps/workbench-chat/` 같은 하위 경로를 지원한다. 새 주소에서는 게이트웨이에 다시 로그인해야 할 수 있고, 브라우저의 초안·선택 대화·화면 설정은 origin별 localStorage이므로 다른 주소로 자동 이전되지 않는다. 서버 DB의 대화 이력은 유지된다.

- 내부 조회 API는 `GET /api/attempts/<aid>/poll?after=<event_id>`다. 브라우저에서는 이 경로·cursor도 암호화해 `POST /api/secure`로 전송한다. 응답은 SSE가 아닌 유한한 JSON 암호문이며 대기 없이 저장된 이벤트 최대 128개와 `cursor`, `has_more`를 반환한다. 평문 직접 호출은 428로 차단하며 기존 세션·CSRF·호스트·네트워크 검사를 유지한다.
- 답변 생성 중 약 1초마다 마지막 적용 이벤트 이후만 조회한다. 밀린 이벤트가 더 있으면 즉시 다음 배치를 받는다. SSE와 같은 이벤트 적용 함수를 사용하고 이미 적용한 ID는 무시한다. `done` 이벤트로 완료·실패·취소·프로세스 복구 종료를 반영한 뒤 조회를 중단하고 최종 이력을 한 번 갱신한다.
- 다른 호스트에서는 SSE를 우선 사용한다. 연결 실패, 완료 이벤트 없는 연결 종료, 또는 연결/유효한 암호화 프레임 수신이 15초 동안 없으면 마지막 cursor부터 JSON 폴링으로 전환한다. 해당 구독이 끝날 때까지 폴링을 유지한다. 정상 SSE heartbeat는 기존 10초 간격이며 수신 타이머를 갱신한다.
- 폴링 요청도 15초 제한을 적용한다. 연속 오류는 재시도 대기를 1초에서 최대 10초까지 늘리고 성공하면 초기화한다. 대화 전환·페이지 이탈 시 진행 중 조회와 예약 대기를 취소한다. 암호화 세션은 기존 만료 갱신 절차를 사용하며 평문 fallback은 없다. 키 교환 요청에도 15초 제한을 적용했다.
- JS 캐시 버전을 갱신했다. 반영하려면 사용자가 **Workbench Chat - conversation server**를 재시작하고 브라우저를 새로고침한다. 폴링을 위해 새 job 등록이나 임시 도메인 고정 설정은 필요하지 않다. 운영 서버·Proc Manager·터널은 이번 작업에서 재시작하거나 변경하지 않았다.

검증: 관련 Python 테스트 **61개 통과·실제 모델 opt-in 1개 제외**. 새 테스트는 유휴 provider의 즉시 JSON 반환, 128개 배치 경계, 암호문 보호, cursor 재개, 중복 방지, 완료·취소·복구 이벤트, 잘못된 cursor·없는 attempt·평문 차단을 확인한다. 지정 Chromium runner를 임시 HTTPS fixture에 **1회** 실행해 **360/768/1440/1920px**에서 각각 SSE 중간 끊김, Quick Tunnel 폴링 선택, SSE 응답 헤더 무응답, 첫 프레임 이후 수신 중단을 검증했다. 폴링 전환 후 답변 완성과 취소, 기존 Markdown/글꼴/레이아웃 회귀 및 콘솔 검사를 통과했다. 두 개의 서로 다른 임시 호스트명에 대한 자동 폴링 선택과 비대상 호스트 구분도 확인했다. 실제 Cloudflare edge·게이트웨이 로그인 이후 경로는 이번 검증에 포함하지 않았다. 임시 테스트 서버는 검증 후 종료했다.


### 좁은 모바일 화면의 대화 중심 배치

- 599px 이하에서 상단은 대화 목록·제목·더 보기 한 줄로 표시한다. 제목 변경·삭제·사용량·화면 설정은 더 보기 대화상자에서 사용한다.
- 요청·모델·추론·검색 및 번역 언어·톤·형식은 요청 요약 버튼으로 여는 하단 대화상자로 옮긴다. 화면을 펼치면 같은 컨트롤을 원래 위치로 돌려 선택값과 초안을 보존한다. 패널은 화면 높이 안에서 별도로 스크롤한다.
- 모바일 입력창은 한 줄로 시작해 최대 120px 또는 가시 화면 높이의 25%까지 늘어난다. 생성 중에는 전송 위치에 중단 버튼을 표시한다. 모바일 배율은 별도로 저장하며 기본값은 100%다.
- 정상 암호화 연결 정보는 대화 목록의 계정 정보로 옮겼다. 오류·재연결은 본문 아래 상태 영역에 계속 표시하고, 완료·복사 알림은 3초 뒤 닫는다. 답변의 모델·추론·검색·토큰은 펼칠 수 있는 상세 정보로 제공한다.
- `visualViewport` 높이를 사용해 입력창을 배치한다. Chromium의 360×780 모사에서 상단 약 51px, 입력부 105px, 본문 약 624px를 확인했다. 높이 460px의 키보드 모사에서는 본문 약 304px를 확보했다. 실기기 키보드 검증은 포함하지 않는다.
- `tests/test_conversation_mobile_browser.cjs`는 본문 공간·번역 설정·입력창 높이·상세 접기·메뉴·키보드 모사·360→768→390px 전환을 검증하며 기존 conversation 브라우저 검증에 포함된다. 360/768/1440/1920px 기존 전송·중단·Markdown·폰트·암호화 회귀 검증도 통과했다.
- 반영하려면 사용자가 **Workbench Chat - conversation server**를 재시작한 다음 브라우저를 새로고침한다. 이번 작업에서는 운영 서버·Proc Manager·터널을 재시작하지 않았다.
