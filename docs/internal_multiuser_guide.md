# Codex Workbench 사내 다중 사용자 운영 가이드

이 문서는 고정 IP로 사용자를 식별하는 사내 배포용 안내입니다. 외부 배포는 기본값인 `standalone` 모드를 계속 사용하며, 이 기능은 활성화되지 않습니다.

## 1. 운영 구조

```text
고정 IP 사용자 → Codex Workbench
                  ├─ 공용 RTL Knowledge: revision별 읽기 전용 원본
                  ├─ 관리자 Key 풀: Windows DPAPI로 암호화된 공용 API Key
                  └─ 개인 영역: workspace / 채팅 / 첨부 / 사용량
```

개인 영역은 `<CODEX_INTERNAL_DATA_DIR>/users/ip-<SHA-256(IP) 앞 24자리>/` 아래에 저장됩니다. username은 화면에 표시되는 이름이며 변경해도 개인 폴더, 대화, API Key, 사용량 이력은 같은 IP 해시 경로를 계속 사용합니다. 첫 접속 시 username 설정 창이 열리고, 이후에는 상단의 username 버튼에서 수정할 수 있습니다. 공용 RTL 원본은 `<CODEX_INTERNAL_DATA_DIR>/organization/shared-knowledge/` 아래에만 저장됩니다. 사용자에게 보이는 `shared` File Preview 루트는 읽기 전용입니다. Agent backend, 모델, effort, speed mode, browser verification 등의 실행 설정은 `<CODEX_INTERNAL_DATA_DIR>/organization/codex_settings.json`에 조직 공통으로 저장됩니다.

## 2. 서버 설정과 시작

Windows 사내 서버에서는 전용 PowerShell 스크립트로 시작하는 것을 권장합니다. 최초 실행 시 사용자 맵이 없으면 관리자 `12.80.214.204 → dinya`를 자동으로 생성합니다.
별도 `-InternalDataDir`를 지정하지 않으면 데이터는 Workbench 폴더의 한 단계 위에 있는 `internal-workbench-data`에 생성됩니다.

```powershell
.\run_codex_chat_server_internal_multiuser.ps1
# 선택: 기본 데이터 경로 대신 별도 보호 볼륨을 사용
.\run_codex_chat_server_internal_multiuser.ps1 -InternalDataDir 'D:\CodexWorkbench\internal-state'
```

스크립트는 다음 환경 변수를 설정한 뒤 기존 회사망 실행기를 호출합니다. Linux 등 다른 환경에서는 아래 환경 변수를 직접 지정하고 Flask 서버를 재시작합니다.

```sh
export CODEX_WORKBENCH_MODE=internal-multiuser
export CODEX_INTERNAL_DATA_DIR=/srv/codex-workbench/internal-state
export CODEX_INTERNAL_USER_MAP_PATH=/srv/codex-workbench/internal-state/user_map.json
# 선택: 공용 지식 저장 위치를 별도 볼륨으로 둘 때만 지정
export CODEX_SHARED_KNOWLEDGE_DIR=/srv/codex-workbench/internal-state/organization/shared-knowledge
```

`CODEX_INTERNAL_DATA_DIR`는 서비스 계정만 읽고 쓸 수 있게 권한을 제한합니다. 이 위치에는 암호화된 API Key 풀과 사용자 대화가 들어가므로 백업 매체도 같은 수준으로 보호해야 합니다.

리버스 프록시 뒤에서 운영하면 프록시 IP만 신뢰하도록 지정합니다. 지정하지 않으면 Flask가 직접 연결한 IP만 사용합니다.

```sh
export CODEX_TRUSTED_PROXY_CIDRS=10.0.0.10/32
```

프록시가 아닌 사용자가 `X-Forwarded-For`를 넣어도 신뢰되지 않습니다. Flask 포트는 프록시 또는 사내망에서만 접근하게 방화벽으로 제한하십시오.

## 3. 최초 사용자 등록

최초에는 아래 파일을 만들고 서버를 시작합니다. Windows 전용 시작 스크립트를 사용하면 동일한 내용의 초기 파일을 자동으로 만듭니다. 최소 한 명의 `admin`이 필요합니다.

```json
{
  "version": 1,
  "users": [
    { "ip": "12.80.214.204", "username": "dinya", "role": "admin" },
    { "ip": "10.20.0.12", "username": "alice", "role": "maintainer" },
    { "ip": "10.20.0.13", "username": "bob", "role": "member" }
  ]
}
```

역할은 다음과 같습니다.

| 역할 | 권한 |
| --- | --- |
| `admin` | IP 사용자 맵 관리, 공용 RTL revision 등록, 조직 공통 Agent/Model/Effort 설정 및 API Key 풀 관리, 일반 사용자 기능 |
| `maintainer` | 공용 RTL revision 등록, 일반 사용자 기능 |
| `member` | 공용 RTL 조회·개인 workspace 복사·대화 |

등록되지 않은 IP의 모든 요청은 `403`으로 거부됩니다. 관리자는 `GET`/`PUT /api/codex/internal/users`로 사용자 맵을 갱신할 수 있습니다. IP가 NAT로 공유되면 이 방식만으로는 개인 식별이 불가능하므로 사용자마다 고정 IP를 배정해야 합니다.

## 4. 관리자 API Key 풀과 요청별 자동 배정

내부 모드에서는 일반 사용자가 API Key를 입력하거나 볼 수 없습니다. `admin`으로 접속하면 설정 패널에 **Internal API Key Pool**과 **Key Pool 열기** 버튼이 표시됩니다. 새 오버레이 창에서 Key 이름과 실제 값을 추가하고 **Key Pool 저장**을 누릅니다. Key 값은 전송 시 암호화되며 저장 후에는 다시 화면·API 응답에 표시되지 않습니다.

HTTPS 관리자 화면을 사용할 수 없는 경우에는 서버 콘솔에서 `Manage-CodexWorkbenchApiKeyPool.ps1`을 실행해 Key Pool을 관리할 수 있습니다. **반드시 Workbench 서버를 실행하는 동일한 Windows 계정**으로 실행해야 DPAPI로 기존 풀을 복호화할 수 있습니다. 실제 Key는 안전한 입력 프롬프트에서만 받아 화면이나 PowerShell 이력에 표시하지 않습니다.

```powershell
# Workbench 폴더에서 실행 (기본 데이터 경로: ..\internal-workbench-data)
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action Add -Label 'team-a'
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action List
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action Remove -Id '<List에서 확인한 Id>'

# 서버를 다른 내부 데이터 경로로 시작했다면 같은 경로를 지정
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action List -InternalDataDir 'D:\CodexWorkbench\internal-state'
```

이 스크립트는 웹 서버 재시작 없이 풀 파일을 갱신합니다. 다만 이미 시작된 실행은 시작 시 선택한 Key를 계속 사용하고, 이후 새 Codex/Claude 실행부터 변경된 풀을 사용합니다.

각 Codex/Claude 실행 요청이 시작될 때 서버는 등록된 Key를 라운드로빈(순환)으로 하나 선택합니다. 선택된 Key는 해당 요청의 종료까지 고정되며, 다음 요청은 다음 Key를 사용합니다. Key별 자동 선택 횟수와 마지막 선택 시각은 관리자 패널에서 확인할 수 있습니다. Key 풀은 `<CODEX_INTERNAL_DATA_DIR>/organization/credentials/api_key_pool.dpapi`에 Windows DPAPI로 암호화되어 저장되고, 선택 감사 로그는 같은 폴더의 `api_key_selection_audit.jsonl`에 Key ID·IP 해시 사용자 ID·시각만 기록됩니다. 사용자 개인 영역이나 브라우저 저장소에는 Key가 기록되지 않으며, 풀에 Key가 없으면 회사 API Key가 주입되지 않고 서버 환경변수 Key도 우회 경로로 사용되지 않습니다.

API 공급자 측 rate limit·사용량 한도는 Key 단위로 공유됩니다. 선택 횟수는 배정 횟수이며 실제 토큰 사용량과는 다를 수 있으므로, 기존 Usage Panel의 메시지별 토큰 사용량과 함께 확인하십시오.

## 4-1. 조직 공통 Usage & Model 설정

내부 모드에서는 `admin`만 Agent Backend, Claude/Codex model, effort, plan mode model/effort, speed mode, browser verification을 수정할 수 있습니다. 일반 사용자는 같은 현재값을 읽기 전용으로 보며, 관리자도 상단의 **일반 사용자** 화면 전환을 선택하면 동일한 읽기 전용 화면을 봅니다. 서버도 일반 사용자의 `PATCH /api/codex/settings`를 `403`으로 거부합니다.

관리자가 저장한 값은 조직 공통 설정 파일에 저장되고, 모든 사용자의 다음 Codex/Claude 요청에 적용됩니다. 실행 중인 요청은 시작 시 확정된 설정을 계속 사용합니다.

## 4-2. API Key 입력 시 HTTPS 필요

`이 브라우저 연결에서는 API Key 암호화 전송을 사용할 수 없습니다. HTTPS로 접속하세요.`는 Workbench 오류가 아니라, `http://<사내-IP>:3300`처럼 보안 컨텍스트가 아닌 주소에서 브라우저가 Web Crypto API를 차단해서 발생합니다. API Key는 HTTPS 종료를 제공하는 사내 reverse proxy(IIS, nginx, Caddy 등) 뒤에서 접속하십시오.

- Workbench는 계속 `127.0.0.1:3300` 또는 사내 방화벽으로 제한된 3300 포트에서 실행합니다.
- reverse proxy에 사내 CA가 발급한 인증서를 설치하고 `https://workbench.<사내도메인>`으로 TLS를 종료한 뒤, 해당 포트로 프록시합니다.
- proxy는 `X-Forwarded-Proto: https`와 실제 클라이언트 IP가 담긴 `X-Forwarded-For`를 전달하고, `CODEX_TRUSTED_PROXY_CIDRS`에는 proxy IP/CIDR만 설정합니다.
- HTTPS를 쓰면 서버 시작 환경에 `CODEX_SESSION_COOKIE_SECURE=true`도 설정합니다.
- 인증서 경고를 무시하거나 HTTP 예외를 열어 API Key를 입력하지 마십시오. `localhost`에서 서버 본인이 입력하는 경우만 브라우저의 보안 컨텍스트 예외가 적용될 수 있습니다.

## 5. 공용 RTL Knowledge 등록 (admin/maintainer)

공용 지식은 불변 revision으로 올립니다. 지원 파일은 Verilog/SystemVerilog/VHDL (`.v`, `.vh`, `.sv`, `.svh`, `.vhd`, `.vhdl`)와 Markdown (`.md`, `.markdown`)입니다. revision ID는 소문자 영문·숫자·`.`, `_`, `-`만 사용합니다.

```sh
curl -X POST http://workbench.internal/api/codex/shared-knowledge/revisions \
  -F revision_id=uart-r1 \
  -F title='UART baseline r1' \
  -F description='2026-08-12 signoff snapshot' \
  -F files=@rtl/uart_tx.sv \
  -F files=@docs/uart.md
```

업로드 뒤 서버는 원본, SHA-256 manifest, 모듈 이름·Markdown heading 인덱스를 함께 저장합니다. 같은 revision ID는 덮어쓸 수 없습니다. 변경이 필요하면 새 revision을 만드십시오.

조회 API는 다음과 같습니다.

```text
GET  /api/codex/shared-knowledge/revisions
GET  /api/codex/shared-knowledge/revisions/<revision-id>
POST /api/codex/shared-knowledge/revisions/<revision-id>/import
```

## 6. 분석과 개인 작업

사용자는 File Preview에서 `shared` 루트로 공용 revision과 `manifest.json`, `index.json`, `source/`를 읽을 수 있습니다. 공용 루트는 편집·업로드·삭제할 수 없습니다.

분석 전에 revision을 개인 workspace로 복사하려면 import API를 호출합니다. 복사본은 다음 위치에 생깁니다.

```text
workspace/.codex-knowledge/<revision-id>/
```

이 경로는 개인 영역이므로 분석 중 파일을 변경해도 공용 원본은 바뀌지 않습니다. 채팅 요청 JSON에 `knowledge_revision`을 넣으면 Workbench가 해당 revision을 개인 workspace에 준비하고, Codex에게 분석 근거 경로와 파일·모듈 근거 표기 지침을 전달합니다.

```json
{
  "prompt": "uart_tx의 reset 처리와 CDC 위험을 검토해줘.",
  "knowledge_revision": "uart-r1"
}
```

대화 메시지에는 선택한 revision ID가 함께 기록되므로 후속 이력 분석에서 답변 근거 버전을 확인할 수 있습니다.

## 7. 운영 점검·백업

- `organization/audit-log.jsonl`에는 공용 revision 생성·개인 workspace import의 사용자/IP/시간을 기록합니다.
- 개인 채팅, 첨부, 사용량은 사용자별 경로를 통째로 백업하되 다른 사용자에게 복원하지 않습니다. API Key 풀은 `organization/credentials`를 별도로 서비스 계정 전용으로 백업합니다.
- 공용 지식은 revision 디렉터리를 삭제·수정하지 말고 새 revision을 추가하는 방식으로 운영합니다.
- 서버 업데이트 전에는 `user_map.json`, `organization/shared-knowledge`, 각 사용자 `.agent_state`를 백업하고, 테스트 IP로 `403` 차단과 사용자 간 채팅·파일 격리를 확인합니다.

## 8. 외부 환경과의 차이

외부 환경에서는 `CODEX_WORKBENCH_MODE`를 설정하지 않거나 `standalone`으로 둡니다. 이때 기존 단일 workspace, 채팅, File Preview, API Key 동작은 바뀌지 않으며 `shared-knowledge` API는 `404`를 반환합니다.
