# 음성 전사 수정 검증 및 코드 리뷰

검증일: 2026-11-07. 대상: macOS의 canonical Workbench 음성 서비스, API, 녹음·삽입 UI와 기존 Android 권한 변경 코드.

## 수정한 발견 사항

| 중요도 | 발견 | 조치 및 근거 |
| --- | --- | --- |
| 높음 | 실행 중인 3004 서버의 `/api/codex/voice`가 비활성화 오류를 반환했다. 환경변수 미설정 시 기본 비활성화이며 `.env.example`은 실행 설정으로 읽히지 않는다. | 서버 전용 `.local/voice/config.json`을 읽도록 추가했다. 명시적 환경변수가 우선한다. 로컬 설정 및 모델을 준비했고 임시 서버의 상태 응답은 `error: null`이다. |
| 높음 | 길이 메타데이터가 없는 MediaRecorder WebM에 `float(N/A)`를 적용하면 정상 녹음도 실패한다. | 제한된 WAV 변환 후 PCM 길이를 검사한다. 메타데이터 없는 WebM, fragmented MP4/AAC, 초과 길이 테스트를 통과했다. |
| 높음 | 취소 중인 상태 조회의 응답 또는 이전 녹음의 비동기 종료 이벤트가 새 결과/마이크 상태를 변경할 수 있다. | 응답 수신 뒤 generation을 재검사하고 콜백을 해당 recorder에 고정했다. 이전 이벤트는 상태 변경 전에 무시한다. 페이지 종료 시에도 generation을 무효화한다. 브라우저에서 취소 후 새 녹음 중 늦은 응답을 반환하는 사례를 검증했다. |
| 보통 | 설정 확인과 worker 실행 사이에 환경 또는 모델 설정이 달라질 수 있다. | 검증된 도구와 모델 절대 경로를 작업별로 전달한다. 실행 중 설정 변경에도 기존 모델을 유지하는 테스트를 추가했다. |
| 보통 | 전사 결과 응답에 명시적 캐시 금지가 없었다. | 음성 API 응답에 `Cache-Control: no-store`를 추가하고 테스트했다. |

변환 입력에는 `file,pipe` 프로토콜만 허용해 오디오 처리 중 네트워크 프로토콜 접근을 차단한다. 기존 크기 제한, 세션 소유권 및 동일 출처 검사, 동시 작업 제한, 프로세스 시간 제한과 임시 파일 정리는 유지했다.

## 검증 결과

- `python3.14 -m pytest tests/test_voice_transcription.py tests/test_frontend_resource_payloads.py -q`: **22 passed**. 설정 우선순위, 잘못된 설정, 실행 파일 누락, WebM/MP4 디코딩, 길이/크기 제한, 소유권, 취소 중 동시 요청, timeout 후 프로세스 회수, 임시 파일 정리, API 업로드·조회·삭제를 포함한다.
- `CODEX_VERIFY_VOICE=1 python3.14 scripts/verify_browser_ui.py --url http://127.0.0.1:38941/ --selector '#voice-start'`: **1 passed (12.7s)**. 응답·DOM·콘솔 검사, 기존 초안 보존과 수동 삽입, 늦은 취소 응답 무시, 마이크 트랙 종료를 확인했다. 실제 Chromium MediaRecorder로 만든 약 1초 무음 WebM을 실제 ffmpeg 및 로컬 whisper 모델로 처리해 완료 UI까지 확인했다. 원래 사용자 녹음이나 마이크는 사용하지 않았다. 무음 테스트는 한국어 인식 정확도를 증명하지 않는다.
- `node --check`(음성 JS와 브라우저 테스트), `python3.14 -m py_compile`(서비스·blueprint·임시 서버), `git diff --check`: 통과.
- 추가 검사 `tests/test_internal_multiuser.py`: **6 passed, 2 failed**. 공유 지식 쓰기가 예상 403 대신 400을 반환하고, 기존 사용자 폴더 이관 후 `keep.txt` 조회가 실패한다. 두 실패를 음성 라우트와 응답 hook이 없는 **HEAD의 blueprint 코드로 메모리에서 교체한 비교 실행**에서도 동일하게 재현했다. 음성 수정과 분리된 기존 실패이며 이번 변경에서 수정하지 않았다.

## 다중 사용자 기존 실패 후속 수정 (2026-11-07)

위의 실패 2건을 재현한 뒤 다음과 같이 수정했다.

- 공유 지식 쓰기 검사는 평문 요청이라 읽기 전용 검사 전에 `encrypted_file_write_required`(400)로 거부되고 있었다. 실제 브라우저와 같은 ECDH/AES-GCM 세션으로 요청하도록 테스트를 수정했다. 암호화된 전체 쓰기와 patch가 모두 `read_only_root`(403)로 거부되고 원본이 유지됨을 확인한다. 평문 요청은 계속 400으로 거부하며 서버의 암호화 정책을 완화하지 않았다.
- 사용량 수집기가 첫 HTTP 요청 전에 IP 해시 저장소를 생성하면 기존 이름 기반 폴더 이관을 건너뛰는 경합이 있었다. 공통 `prepare_user_storage`를 HTTP 요청, 사용량 수집기, 사용량 스케줄러가 사용자 저장소에 접근하기 전에 호출한다. 같은 프로세스의 이관은 lock으로 직렬화하고, 다른 프로세스가 같은 rename을 완료한 경우도 허용한다.
- 수집기 완료 후 첫 페이지 조회를 수행하도록 회귀 테스트를 고정했다. 스케줄러의 계정 조회 전 이관, 동시 호출, workspace·대화·키 파일 보존, username 변경 후 파일 조회도 검사한다. 이미 IP 해시 폴더가 존재하면 덮어쓰거나 병합하지 않고 기존 폴더를 모두 유지한다.

- `python3.14 -m pytest tests/test_internal_multiuser.py tests/test_voice_transcription.py tests/test_frontend_resource_payloads.py tests/test_usage_dashboard.py tests/test_usage_recovery.py -q`: **69 passed**. 이 중 다중 사용자 테스트는 **11 passed**이며 기존 실패는 모두 해소됐다.
- `python3.14 -m pytest tests/test_codex_file_browser.py -q -k 'encrypted_write_route or plain_write_route'`: **5 passed, 125 deselected**. 암호화 쓰기, binary v3 patch, 평문 차단 및 명시적 trusted HTTP fallback을 확인했다.
- `git diff --check`: 통과. 수정 코드와 호출 경로를 검토했다. 이번 후속 수정에는 UI 변경이 없어 브라우저 검증은 재실행하지 않았다. 실행 중인 서버를 재시작하지 않았다.

## 로컬 준비와 적용

`.local/voice/`에 설정 및 `ggml-large-v3-turbo-q5_0.bin` 복사본을 준비했다. 다른 프로젝트의 원본 파일을 수정하지 않았고 복사본과 원본의 SHA-256 일치를 확인했다.

SHA-256: `394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2`.

`.local/`은 Git 추적 대상이 아니다. 모델이나 PC별 도구 경로를 다른 checkout의 기본값으로 추가하지 않았다. 기존 3004 서버는 재시작하지 않았으며, 적용하려면 사용자가 **canonical Workbench Chat 서버(3004)를 재시작하고 페이지를 새로고침**해야 한다. 다른 Workbench checkout은 수정하지 않았다.

## 확인하지 않은 범위

Galaxy Chrome/Android WebView의 실제 마이크 권한과 녹음, 한국어 발화 정확도, 모바일 백그라운드 전환은 실기기 검증이 필요하다. Android 변경은 권한·origin 검사 및 요청 취소/화면 종료 정리 코드를 정적으로 검토했다. APK 빌드나 기기 테스트는 실행하지 않았다. 다중 서버 프로세스의 공유 큐 및 OS 수준 메모리/CPU 제한은 기존 구현 범위 밖이다.


## 음성 요청 출처 차단 후속 수정 (2026-11-07)

- 보고된 메시지는 전사 모델 실행 전 음성 POST의 출처 검사에서 반환된다. 기존 코드는 브라우저 `Origin`의 host·port를 Flask `request.host`와 직접 비교하므로, 프록시가 내부 Host로 바꾸는 환경에서 정상 녹음도 거부한다. 실제 사용 중인 프록시의 전달 헤더는 확인하지 않았으며, 이 주소 불일치 조건을 별도 테스트로 재현했다.
- 음성 API에 전용 세션 CSRF 토큰을 도입했다. 설정 GET에서 토큰을 발급하고 업로드 및 모든 취소·정리 DELETE가 `X-Codex-CSRF-Token`을 전송한다. 서버는 세션 토큰을 상수 시간 비교하고 `Sec-Fetch-Site: cross-site`도 거부한다. `Origin`이나 임의 `X-Forwarded-Host` 신뢰에 의존하지 않는다. 기존 회사 자격증명용 출처 검사는 변경하지 않았다.
- 토큰은 세션 내 반복 조회 시 유지하며 설정 응답은 계속 `no-store`다. 음성 작업의 사용자·세션 소유권 검사도 유지한다. 토큰 누락, 오류, 다른 세션, 비정상 문자, cross-site, 위조 전달 헤더 요청이 작업 생성·취소 전에 403으로 거부되는지 검증했다.
- `python3.14 -m pytest tests/test_internal_multiuser.py tests/test_voice_transcription.py tests/test_frontend_resource_payloads.py -q`: **42 passed**.
- `CODEX_VERIFY_VOICE_PROXY=1 python3.14 tests/serve_voice_fixture.py --host 127.0.0.1 --port 38941`로 격리된 임시 서버를 구동했다. 음성 API에만 내부 Host를 주입해 브라우저 Origin과 불일치하도록 설정했다. `CODEX_VERIFY_VOICE=1 python3.14 scripts/verify_browser_ui.py --url http://127.0.0.1:38941/ --selector '#voice-start'`: **1 passed (8.2s)**. 실제 Chromium MediaRecorder의 생성 무음 WebM → CSRF 포함 업로드(202) → 실제 ffmpeg·로컬 모델 → 완료 UI, 수동 삽입, 취소와 늦은 응답 무시, 마이크 트랙 종료를 검증했다. 실제 사용자의 오디오는 사용하지 않았다.
- JS 구문 검사, Python 컴파일, `git diff --check` 통과. Android 실기기 및 실제 HTTPS 프록시 통합 검증은 수행하지 않았다. 운영 3004 서버는 재시작하지 않았다. 적용 전 현재 탭의 녹음을 다운로드해 보관한 후, 사용자가 3004 서버를 재시작하고 페이지를 새로고침해야 한다.
