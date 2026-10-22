# 사내 API Key Pool

사내 Windows·Linux 배포(`CODEX_COMPANY_MODE=1`)의 일반 모드 및
`internal-multiuser` 모드에서 여러 키를 영구 저장할 수 있습니다.
일반 macOS 배포의 기존 단일 키 동작은 유지됩니다.

## 등록과 실행

일반 사내 모드에서는 서버의 기존 `CODEX_COMPANY_ADMIN_PASSWORD` 또는
`CODEX_COMPANY_ADMIN_TOKEN`으로 설정 화면의 **인증 관리**에 로그인한 뒤
**Key Pool 열기**를 선택합니다. 각 키의 이름과 값을 추가하고 **Key Pool 저장**을
누르면 다음 요청부터 등록 순서대로 순환합니다. 이름 변경·삭제도 저장해야 적용됩니다.
다중 사용자 모드에서는 기존 IP 기반 관리자만 조직 키 풀을 관리합니다.
키 등록 요청은 기존 ECDH/AES-GCM 암호화 전송을 사용합니다.

Claude와 Codex가 사용하는 공유 사내 자격 증명입니다. 상태 조회, 키 목록 조회,
연결 테스트는 순환 순서를 변경하지 않습니다. 실행에 예약한 키는 해당 실행에서
재사용합니다. 자동 오류 재시도나 실패 시 다른 키로 전환하는 기능은 추가하지 않습니다.
일반 모드에서 풀이 비어 있으면 기존 메모리 키 → Windows DPAPI 단일 키 →
`DTGPT_API_KEY` 환경변수 순으로 선택합니다. 다중 사용자 모드는 빈 풀일 때
환경변수로 대체하지 않습니다. 손상된 풀은 환경변수로 우회하지 않습니다.

## 저장 위치

일반 모드의 풀은 `CODEX_STORAGE_DIR/credentials/`, 다중 사용자 모드는
`CODEX_INTERNAL_DATA_DIR/organization/credentials/`에 저장합니다.

- Windows: `api_key_pool.dpapi`, 현재 Windows 계정의 DPAPI로 암호화.
- Linux: `api_key_pool.fernet`, Fernet 인증 암호화. 별도 `api_key_pool.key`는
  서비스 계정만 읽는 권한 600으로 생성하며 풀 파일도 600으로 저장.
  Linux의 보호 경계는 서비스 계정의 파일 접근 권한입니다. 백업·복구 시 암호화
  파일과 키 파일을 함께 보관하고, 다른 사용자에게 디렉터리 접근을 허용하지 마세요.

기존 Windows 조직 풀의 경로와 형식은 호환됩니다. API 응답과 선택 감사 로그에는
실제 키 대신 식별자·이름·마스킹된 미리보기 및 사용량만 제공합니다.

## OpenCode 응답

OpenCode 자체 provider 인증은 그대로 사용합니다. 수정 이후의 스트리밍 응답과
복구 응답은 `text` 부분만 챗 버블에 반영합니다. `reasoning`은 상세 이벤트와
`[OpenCode reasoning]` 상세 로그에 보존합니다. 기존 저장 대화는 변환하지 않습니다.
