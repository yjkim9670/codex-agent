# codex_agent 독립 앱 분리 및 Vercel + Tailscale 1차 구현 계획

- 작성일: 2026-04-13
- 기준 범위: `/home/dinya/codex_agent`
- 이번 문서의 목적: `codex_agent`를 별도 웹앱으로 분리해 `Vercel`에 올리되, 백엔드는 내 로컬 PC에서 계속 실행하고 `Tailscale`로만 접근 가능한 1차 구조를 확정한다.
- 이번 단계의 접근 정책: 외부 공개가 아니라 `Tailscale` 사용자 전용 내부 운영
- 다음 단계의 방향: 운영 안정화 후 보안 강화와 인증 추가를 거쳐 외부 공개 구조로 전환

## 0. 진행 현황 (업데이트: 2026-04-14)

| 단계 | 상태 | 비고 |
|---|---|---|
| 단계 1. 백엔드 최소 분리 준비 | `[x] 완료` | CORS/env 기반, API-only 모드, runtime info, files/git API 토글 반영 |
| 단계 2. 프론트 앱 신설 | `[x] 완료` | `apps/codex-agent-web` 생성 및 기존 UI 자산 이관 완료 |
| 단계 3. 프론트 초기 진입 데이터 정리 | `[x] 완료` | `runtime/info` 기반 bootstrap 초기화 적용 완료 |
| 단계 4. 로컬 PC 백엔드 운영 준비 | `[x] 완료` | env 템플릿, 실행 스크립트, `systemd --user` 서비스 템플릿 반영 |
| 단계 5. Tailscale 네트워크 구성 | `[x] 완료` | expose/verify 스크립트와 운영 문서 반영 완료 |
| 단계 6. Vercel 배포 준비 | `[x] 완료` | Vercel 프로젝트 연결 및 preview 배포 확인 (`codex-agent-web.vercel.app`) |
| 단계 7. 통합 테스트 | `[x] 완료` | `tailscale serve`를 `127.0.0.1:6000`으로 재지정 후 `gbook.wind-mintaka.ts.net` 스모크 테스트 통과 |
| 단계 8. 1차 운영 안전장치 | `[~] 진행중` | CORS/기능 제한 정책과 운영 secret/env 고정 완료, ACL 최종 고정만 남음 |
| 단계 9. 외부 공개 전환 2차 보안 | `[ ] 대기` | 인증/권한/공개 게이트웨이 설계 및 구현 필요 |
| 단계 10. 리스크 대응 운영화 | `[ ] 대기` | 다운타임/로그/운영 정책 문서화 고도화 필요 |
| 단계 11. 계획 문서 삭제 | `[ ] 대기` | 운영 문서 이관 완료 후 본 문서/폴더 삭제 |

## 1. 최종 판단

이번 1차 방안은 구현 가능하다. 다만 구조는 아래처럼 고정해야 한다.

| 구분 | 1차 결정 |
|---|---|
| 프론트엔드 | `Vercel`에 별도 웹앱으로 배포 |
| 백엔드 | 현재 `codex_agent` Flask 서버를 로컬 PC에서 계속 실행 |
| 백엔드 접근 방식 | `Tailscale`로 노출한 HTTPS 주소를 브라우저가 직접 호출 |
| 사용자 범위 | `Tailscale`에 접속 가능한 사용자만 사용 |
| 이번 단계에서 하지 않을 것 | 로컬 백엔드를 `Vercel Functions`가 직접 프록시하도록 구성 |
| 외부 공개 시점 | 이후 보안 강화 단계에서 별도 공개 게이트웨이 또는 공개 백엔드로 전환 |

핵심 이유는 `Vercel`이 기본적으로 내 개인 `tailnet` 안에 들어와 있지 않기 때문이다. 따라서 1차에서 `Vercel`은 UI를 배포하고, 실제 API 호출은 `Tailscale`이 설치된 사용자 브라우저가 로컬 PC 백엔드로 직접 보내는 형태가 가장 현실적이다.

## 2. 현재 코드 기준 제약

아래 제약 때문에 백엔드를 그대로 `Vercel`에 올리는 방식은 맞지 않는다.

| 항목 | 현재 코드 근거 | 의미 |
|---|---|---|
| 워크스페이스 의존 | `run_codex_chat_server.py:20-27` | 기본적으로 부모 워크스페이스를 직접 잡아 사용 |
| 로컬 파일 저장 | `codex_agent/config.py:14-67` | 세션, 설정, 사용량 파일을 워크스페이스와 `~/.codex`에 저장 |
| 로컬 CLI 실행 | `codex_agent/services/codex_chat.py:2910-2932` | 응답 생성이 `subprocess` 기반 `codex` 실행에 의존 |
| 메모리 상태 보관 | `codex_agent/state.py:1-6` | 스트림 상태가 프로세스 메모리에 있음 |
| CORS 제한 | `codex_agent/codex_app.py:16-20`, `80-89` | 현재는 `localhost:4000`만 허용 |
| 프론트 상대경로 API 호출 | `codex_agent/static/js/app.js` 여러 위치 | 프론트를 분리하면 API base URL 주입이 필요 |
| 민감한 관리 API 포함 | `codex_agent/blueprints/codex_chat.py:641-688` | 파일 조회, raw 파일, git 액션까지 노출됨 |

## 3. 1차 목표와 비목표

| 구분 | 내용 |
|---|---|
| 목표 1 | 현재 UI를 별도 앱으로 분리해 `Vercel`에서 서비스 |
| 목표 2 | 백엔드는 내 로컬 PC에서 유지하며 `codex`, Git, 파일시스템 접근 계속 사용 |
| 목표 3 | `Tailscale` 사용자만 접근 가능한 내부 운영 체계 확보 |
| 목표 4 | 이후 외부 공개를 고려해 프론트/백엔드 경계를 먼저 분리 |
| 비목표 1 | 이번 단계에서 완전 공개 서비스 만들기 |
| 비목표 2 | 이번 단계에서 멀티 인스턴스 확장, 무상태 스트리밍 구조로 재작성 |
| 비목표 3 | 이번 단계에서 관리자/일반사용자 권한 체계를 완성 |

## 4. 1차 목표 아키텍처

| 레이어 | 구성 | 설명 |
|---|---|---|
| 웹 배포 | `Vercel` | 정적 자산과 프론트 앱 제공 |
| API 호출 | 사용자 브라우저 -> `https://<local-pc>.<tailnet>.ts.net` | 브라우저가 `Tailscale` HTTPS 주소로 직접 호출 |
| 백엔드 런타임 | 로컬 PC의 Flask 서버 | `codex exec`, 세션 파일, Git, workspace 접근 유지 |
| 네트워크 보호 | `Tailscale Serve` 또는 tailnet HTTPS | `Tailscale` 사용자만 접속 가능 |
| 저장소 | 로컬 PC 디스크 | 기존 워크스페이스와 `~/.codex` 유지 |

요청 흐름은 아래와 같다.

1. 사용자가 `Vercel` 도메인으로 프론트 앱에 접속한다.
2. 브라우저가 환경변수로 주입된 `Tailscale` 백엔드 URL로 API 요청을 보낸다.
3. `Tailscale` 네트워크에 올라온 로컬 PC의 Flask 서버가 요청을 처리한다.
4. Flask 서버가 로컬 워크스페이스와 `codex` CLI를 이용해 응답을 생성한다.
5. 응답이 다시 브라우저로 돌아오고, 프론트가 이를 렌더링한다.

## 5. 왜 1차에서 Vercel 프록시를 주 경로로 쓰지 않는가

| 항목 | 판단 |
|---|---|
| `Vercel`이 tailnet 내부 주소로 직접 접근 | 부적합 |
| 사용자 브라우저가 tailnet 주소로 직접 접근 | 적합 |
| 이후 외부 공개 시 `Vercel` rewrite/proxy 도입 | 적합 |

정리하면, 이번 1차는 `Vercel = UI 배포`, `Tailscale = API 접근 제어`로 나누는 편이 맞다. 이후 외부 공개 단계에서만 공개 가능한 백엔드 주소와 프록시를 붙인다.

## 6. 권장 폴더 구조

1차는 같은 Git 저장소 안에서 배포 단위를 먼저 분리하는 방식이 가장 안전하다.

| 경로 | 역할 |
|---|---|
| `/home/dinya/codex_agent/codex_agent` | 기존 Flask 백엔드 패키지 유지 |
| `/home/dinya/codex_agent/run_codex_chat_server.py` | 백엔드 실행 진입점 유지 |
| `/home/dinya/codex_agent/apps/codex-agent-web` | 새로 분리할 `Vercel` 프론트 앱 |
| `/home/dinya/codex_agent/vercel_tailscale_split_plan` | 이번 계획 문서 폴더 |

프론트 앱은 `Vite + Vanilla JS`를 우선 권장한다. 현재 UI가 서버 템플릿과 단일 대형 JS 파일 중심이라, `React`로 바로 재작성하는 것보다 추출 난이도가 낮고 배포도 단순하다.

## 7. 구현 단계 상세 계획

### 단계 0. 작업 전 정리

| 항목 | 해야 할 일 | 완료 기준 |
|---|---|---|
| 브랜치 정리 | 작업 브랜치 생성 | 분리 작업이 기존 운영 코드와 섞이지 않음 |
| 기능 목록 고정 | 세션, 메시지, 스트림, 파일, git 기능 목록 정리 | 프론트 추출 범위가 명확함 |
| 사용자 범위 확인 | 이번 1차 사용자들이 모두 `Tailscale` 접속 가능함을 확인 | 운영 대상이 명확함 |

### 단계 1. 백엔드 최소 분리 준비

| 항목 | 해야 할 일 | 수정 예상 파일 |
|---|---|---|
| CORS 환경변수화 | 허용 Origin을 환경변수로 읽도록 변경 | `codex_agent/codex_app.py` |
| API 전용 모드 준비 | 서버 템플릿 렌더링 의존을 줄이고 `/health`와 `/api/*`만으로도 운영 가능하게 정리 | `codex_agent/codex_app.py` |
| 서버 식별 정보 정리 | 프론트가 필요로 하는 초기 상태를 API로 내려줄지 검토 | `codex_agent/blueprints/codex_chat.py` 또는 신규 route |
| 민감 API 검토 | `files`/`git` 기능을 1차에서 그대로 열지, 관리자 전용으로 둘지 결정 | `codex_agent/blueprints/codex_chat.py` |

이 단계의 핵심은 “현재 Flask 서버가 프론트 템플릿 없이도 독립 API 서버로 동작하는 상태”를 만드는 것이다.

### 단계 2. 프론트 앱 신설

| 항목 | 해야 할 일 | 산출물 |
|---|---|---|
| 앱 생성 | `apps/codex-agent-web` 초기화 | `package.json`, `vite.config.*`, `src/*` |
| UI 자산 이동 | 현재 템플릿과 정적 자산에서 필요한 것만 추출 | HTML, CSS, JS 자산 |
| API 베이스 분리 | 상대경로 `/api/...` 호출을 `VITE_CODEX_API_BASE_URL` 기반으로 변경 | 프론트 환경변수 구조 |
| 배포 환경 분리 | `local`, `preview`, `production` 환경별 API URL 전략 정의 | `.env.example` 또는 문서 |

이 단계에서 가장 중요한 리팩터링 포인트는 `app.js` 안의 상대경로 호출을 모두 치환하는 것이다.

예상 환경변수:

| 변수명 | 예시 | 용도 |
|---|---|---|
| `VITE_CODEX_API_BASE_URL` | `https://my-pc.my-tailnet.ts.net` | 브라우저가 호출할 백엔드 기본 URL |
| `VITE_APP_ENV_NAME` | `private-tailnet` | UI에 현재 운영 모드 표시 |

### 단계 3. 프론트 초기 진입 데이터 정리

| 항목 | 해야 할 일 | 이유 |
|---|---|---|
| 서버 렌더링 제거 | 현재 템플릿에서 서버가 주입하는 값 정리 | `Vercel` 정적 앱으로 옮기기 위함 |
| 초기 상태 API화 | 모델 목록, reasoning 옵션, 브랜치명, workspace 정보가 필요한지 재검토 | 프론트 독립 실행 보장 |
| 최소 초기화 설계 | 첫 렌더는 정적으로 하고 필요한 값은 앱 로드시 API 호출 | 배포 복잡도 감소 |

권장 방향은 “템플릿 주입값 최소화 + 앱 시작 시 API fetch”다.

### 단계 4. 로컬 PC 백엔드 운영 준비

| 항목 | 해야 할 일 | 완료 기준 |
|---|---|---|
| 실행 계정 고정 | 항상 같은 사용자 계정으로 실행 | `~/.codex`와 workspace 권한 문제 방지 |
| 프로세스 관리 | `systemd --user`, `pm2`, `supervisor` 중 하나로 백엔드 상시 실행 | 재부팅 후 자동 복구 가능 |
| 로그 위치 고정 | stdout/stderr 로그 파일 경로 지정 | 장애 분석 가능 |
| 환경변수 파일 분리 | 실행 스크립트와 운영 환경변수 분리 | 재현성과 운영 안정성 확보 |

권장 최소 운영 변수:

| 변수명 | 설명 |
|---|---|
| `CODEX_WORKSPACE_DIR` | 실제 작업 workspace 루트 |
| `CODEX_STORAGE_SUBDIR` | 세션/설정 파일 저장 위치 |
| `CODEX_CHAT_SECRET_KEY` | Flask secret 교체 |
| `CODEX_ALLOWED_ORIGINS` | `Vercel` 도메인과 개발용 origin 목록 |
| `CODEX_SKIP_GIT_REPO_CHECK` | 필요 시 기존 동작 유지 |

### 단계 5. Tailscale 네트워크 구성

| 항목 | 해야 할 일 | 완료 기준 |
|---|---|---|
| 로컬 PC Tailscale 가입 | 로컬 PC를 tailnet에 연결 | `tailscale status`에서 정상 확인 |
| MagicDNS/HTTPS 확인 | `*.ts.net` 주소와 인증서 사용 가능 여부 확인 | 브라우저 HTTPS 접속 가능 |
| 서비스 노출 | Flask `127.0.0.1:6000` 또는 지정 포트를 `tailscale serve`로 노출 | tailnet 사용자만 접속 가능 |
| 접근 정책 제한 | 1차 사용자만 접근 가능하도록 ACL 또는 공유 정책 정리 | 무분별한 tailnet 접근 차단 |

이 단계에서 중요한 점은 `public` 노출이 아니라 `tailnet 내부` 노출이라는 것이다.

### 단계 6. Vercel 배포

| 항목 | 해야 할 일 | 완료 기준 |
|---|---|---|
| Git 연결 | 프론트 앱 디렉터리를 `Vercel` 프로젝트로 연결 | 프리뷰 배포 가능 |
| 환경변수 입력 | `VITE_CODEX_API_BASE_URL`에 `Tailscale` HTTPS 주소 설정 | 프론트가 올바른 API 주소 호출 |
| 커스텀 도메인 선택 | 필요 시 별도 도메인 연결 | 사용자 접근 주소 고정 |
| 캐시/빌드 검증 | 새 배포 후 API 대상 URL 반영 확인 | 잘못된 백엔드 URL 잔존 없음 |

주의할 점은 이번 1차에서 `Vercel`이 백엔드를 대신 호출하지 않는다는 점이다. `Vercel`은 프론트를 배포할 뿐이고, API 호출은 사용자의 브라우저에서 직접 발생한다.

### 단계 7. 통합 테스트

| 테스트 | 기대 결과 |
|---|---|
| 내 PC에서 `Vercel` 프론트 접속 + API 호출 | 정상 동작 |
| 다른 `Tailscale` 사용자 PC에서 `Vercel` 프론트 접속 + API 호출 | 정상 동작 |
| `Tailscale` 미접속 PC에서 `Vercel` 프론트 접속 | 화면은 열리더라도 API 호출 실패 |
| 세션 생성/메시지 전송/스트림 조회 | 모두 정상 동작 |
| Git/File 브라우저 기능 | 정책대로 허용 또는 차단 |
| 백엔드 재시작 후 세션 지속성 | 저장 파일 기준으로 복구 가능 |

이 테스트로 “이번 1차 구조는 내부 사용자 전용”이라는 점이 명확해져야 한다.

진행 메모 (2026-04-14):

- `deploy/tailscale/verify_tailscale_backend.sh`를 세션 생성/삭제, 스트림 조회, 기능 비활성화(403) 체크까지 확장했다.
- 로컬 임시 백엔드(`127.0.0.1:3300`) 기준 스모크 테스트 통과를 먼저 확인했다.
- 이후 `tailscale serve` 대상을 `127.0.0.1:6000`으로 재지정했고, `https://gbook.wind-mintaka.ts.net` 대상 스모크 테스트와 CORS(`https://codex-agent-web.vercel.app`) 검증이 모두 통과했다.
- `code-server`는 `deploy/tailscale/expose_code_server.sh`로 `https://gbook.wind-mintaka.ts.net:8080 -> http://127.0.0.1:8080` 매핑을 별도로 유지한다.
- `tailscale serve`를 사용할 때 `VITE_CODEX_API_BASE_URL`은 `https://<machine>.<tailnet>.ts.net` 형태(포트 미포함)로 유지한다.

### 단계 8. 1차 운영 안전장치

외부 공개 전이라도 최소한 아래는 먼저 적용하는 편이 좋다.

| 항목 | 조치 |
|---|---|
| CORS 제한 | `Vercel` 본 도메인과 프리뷰 도메인만 허용 |
| Secret 교체 | 기본 `SECRET_KEY` 사용 금지 |
| 로그 마스킹 | 프롬프트와 토큰 사용 로그가 과도하게 남지 않도록 확인 |
| 사용자 제한 | `Tailscale` ACL 또는 기기 공유 대상을 최소화 |
| 기능 제한 | 신뢰되지 않은 사용자에게 `files/raw`, `git/push` 같은 기능 비활성화 검토 |

진행 메모 (2026-04-14):

- `deploy/codex-backend.env`를 실제 운영값으로 생성하고 `CODEX_CHAT_SECRET_KEY`를 랜덤 값으로 고정했다.
- `proc_manager_jobs.json`에 `10) Local Codex Backend - Vercel API (6000)` 잡을 추가해 proc manager에서 백엔드 상시 실행/재시작이 가능해졌다.
- `proc_manager`의 전체 순차실행은 `auto_start`가 아니라 `sequential=true`인 모든 작업을 대상으로 실행하도록 수정했다.

### 단계 9. 외부 공개 전환을 위한 2차 보안 강화 백로그

이 단계는 이번 구현 범위는 아니지만, 외부 공개 전에 반드시 별도 작업으로 진행한다.

| 항목 | 왜 필요한가 | 권장 방향 |
|---|---|---|
| 인증 추가 | 지금 구조는 사실상 네트워크 신뢰에 의존 | 앱 로그인 또는 SSO 추가 |
| 권한 분리 | 일반 사용자에게 파일/Git 전체 권한은 위험 | 관리자/일반 사용자 role 분리 |
| 공개 백엔드 진입점 | `Vercel`에서 private tailnet API를 대신 호출할 수 없음 | 공개 백엔드 또는 공개 게이트웨이 도입 |
| API 토큰 검증 | 브라우저만 믿는 구조는 부족 | 서버 간 인증 또는 세션 인증 추가 |
| Rate limiting | 외부 공개 시 남용 위험 | reverse proxy 또는 앱 레벨 제한 |
| 감사 로그 | 누가 어떤 작업을 했는지 필요 | 명령/파일/Git 액션 감사 로그 추가 |
| 스트림 상태 구조 개선 | 메모리 단일 프로세스 의존 | Redis 또는 영속 큐 검토 |

외부 공개 시점에는 아래 둘 중 하나로 갈 가능성이 높다.

| 후보 | 설명 |
|---|---|
| 공개 백엔드 별도 이전 | 로컬 PC가 아니라 클라우드 VM/컨테이너로 백엔드 이동 |
| 공개 게이트웨이 추가 | 로컬 백엔드는 유지하되 공개 가능한 보호 계층을 하나 더 둠 |

## 8. 실제 구현 순서 제안

| 순서 | 작업 | 선행 조건 | 결과 | 상태 |
|---|---|---|---|---|
| 1 | 백엔드 CORS/환경변수 정리 | 없음 | 외부 프론트 연결 가능 | `[x]` |
| 2 | 서버 템플릿 의존 제거 | 1 | API 서버 독립성 확보 | `[x]` |
| 3 | `apps/codex-agent-web` 생성 | 2 | 프론트 분리 시작 | `[x]` |
| 4 | 프론트 자산 이관 및 API base URL 적용 | 3 | `Vercel` 배포 가능한 앱 확보 | `[x]` |
| 5 | 로컬 PC에 백엔드 상시 실행 구성 | 1 | 운영 준비 완료 | `[x]` |
| 6 | `Tailscale` HTTPS 주소로 백엔드 노출 | 5 | tailnet 전용 API 주소 확보 | `[x]` |
| 7 | `Vercel`에 프론트 배포 | 4, 6 | 분리 배포 완료 | `[x]` |
| 8 | 실제 사용자 테스트 | 7 | 1차 운영 가능 여부 확정 | `[x]` |
| 9 | 민감 기능 제한 여부 확정 | 8 | 내부 운영 보안선 확보 | `[~]` |
| 10 | 외부 공개 백로그 생성 | 8 | 2차 작업 준비 | `[ ]` |
| 11 | 운영 문서 반영 후 본 문서 삭제 | 10 | 임시 계획 문서 정리 완료 | `[ ]` |

## 9. 단계별 완료 판정 기준

| 단계 | 완료 판정 |
|---|---|
| 프론트 분리 | `Vercel` 배포 URL에서 UI가 정상 렌더링됨 |
| API 연결 | 브라우저가 `Tailscale` 백엔드 URL을 통해 세션 조회 가능 |
| 메시지 처리 | 메시지 전송과 스트림 조회가 정상 동작 |
| 운영 안정성 | 백엔드 재시작 후에도 세션 저장이 유지됨 |
| 내부 보안 | 비인가 인터넷 사용자는 API를 직접 사용할 수 없음 |
| 문서 정리 | 핵심 내용이 README 또는 운영 위키로 이관된 뒤 본 문서와 폴더 삭제 |

## 10. 리스크와 대응

| 리스크 | 설명 | 대응 |
|---|---|---|
| `Vercel` 프론트는 공개 URL | 누구나 화면은 열 수 있음 | API는 `Tailscale` 내부 주소만 사용, 필요 시 프론트에도 접근 제어 추가 |
| tailnet 미접속 사용자는 사용 불가 | 1차 구조의 의도된 제약 | 사용자 범위를 tailnet 사용자로 명확히 공지 |
| CORS 오설정 | 브라우저 요청 실패 가능 | 환경별 origin 목록을 분리 관리 |
| 로컬 PC 다운타임 | 백엔드가 개인 PC에 묶임 | 자동 재기동, UPS, 원격 접속 준비 |
| 파일/Git API 위험 | trusted user 전제가 깨지면 위험 | 외부 공개 전 반드시 권한/인증 추가 |

## 11. 이번 문서 삭제 계획

이 문서는 “분리 설계와 초기 실행 순서”를 정리하기 위한 임시 문서다. 구현이 완료되면 아래 순서로 정리한다.

| 순서 | 해야 할 일 |
|---|---|
| 1 | 최종 운영 절차를 `README` 또는 별도 운영 문서로 이관 |
| 2 | 실제 반영된 환경변수, 실행 방법, 장애 대응 절차만 남김 |
| 3 | `/home/dinya/codex_agent/vercel_tailscale_split_plan/implementation-plan.md` 삭제 |
| 4 | 폴더가 비어 있으면 `/home/dinya/codex_agent/vercel_tailscale_split_plan` 폴더도 삭제 |

권장 삭제 시점:

- `Vercel` 프론트가 운영 배포됨
- `Tailscale` 백엔드 접속 절차가 README 또는 운영 위키에 반영됨
- 외부 공개용 2차 보안 백로그가 별도 이슈나 문서로 이관됨

## 12. 참고 메모

| 참고 | 내용 |
|---|---|
| `Vercel` 1차 역할 | 프론트 배포 전용 |
| `Tailscale` 1차 역할 | 백엔드 접근 제어와 HTTPS 진입점 |
| 지금 당장 필요한 설계 원칙 | 프론트와 백엔드의 배포 단위를 먼저 분리 |
| 이후 공개 전 핵심 과제 | 인증, 권한, 감사 로그, 공개 게이트웨이 |

## 13. 외부 문서 참고

아래 문서는 이번 판단의 배경으로 참고할 수 있다.

| 문서 | 핵심 포인트 |
|---|---|
| Tailscale machine sharing 문서 | tailnet 외 사용자에게도 공유는 가능하지만, 기본 전제는 공유/접근 제어가 먼저라는 점 확인 |
| Vercel rewrites 문서 | 외부 공개 단계에서는 공개 가능한 API origin이 생기면 rewrite/proxy를 붙일 수 있음 |
| Vercel framework env vars 문서 | 프론트 환경변수 주입 방식 확인 |
