# Workbench Chat 운영 안내

개인 Codex 계정으로 영어 번역·영문 교정·웹 검색·일반 대화를 제공하는 독립 Flask 앱이다. 기존 작업 서버를 import하지 않는다. 별도 API key나 DTGPT를 사용하지 않는다.

## 실행과 등록

- Proc Manager job: `Workbench Chat - conversation server`
- 주소: `http://127.0.0.1:3101`
- 등록 payload: `ops/workbench-chat.job.json`; 실제 확인 기록: `ops/workbench-chat.registration.json`
- 등록 결과: **idx 16 / STOPPED / PID 없음**, 기존 16개 job의 설정·상태·PID는 최초 snapshot과 동일하다.
- 등록 명령에는 `--host`를 두지 않고 launcher의 `127.0.0.1` 기본값을 사용한다. Proc Manager의 Chat 전용 분류는 loopback Open URL을 유지한다. 대시보드에서는 **Codex Workbench 그룹의 마지막 항목**에 보라색으로 표시한다. 이 Proc Manager 변경은 사용자가 Proc Manager Web을 재시작한 뒤 적용된다.
- **최초 시작·재시작은 사용자 수행.** 등록은 start/restart API를 호출하지 않는다. `auto_start: true`는 다음 Proc Manager 자동 시작 때 함께 실행하려는 설정이다. `restart_on_exit: false`다.
- 같은 PC의 브라우저 또는 사용자가 구성한 SSH 포트 전달로 접근한다. 이번 버전은 loopback 전용이며 LAN·tailnet 직접 bind를 제공하지 않는다.
- 명령: `bash run_conversation_server.sh --host 127.0.0.1 --port 3101`
- Python 3.11 이상, 설치된 Flask가 필요하다. 등록 job은 검증한 `/opt/homebrew/bin/python3.14`를 지정한다.
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

영어 번역·교정·검색 중심의 채팅 전용 지침과 수정한 모델 메타데이터를 사용한다. shell·apply_patch·파일 보기·MCP·앱·플러그인·skills·코드 실행·에이전트 위임을 제거했다. ultra 추론은 자동 위임을 동반하므로 노출하지 않는다. 실제 CLI 전송 요청 검증 결과 검색 끄기에는 도구 0개, 켜기에는 `web.run`만 있다. read-only sandbox를 도구 격리의 대체물로 사용하지 않는다.

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
