# Workbench 실행 설정과 알림 이력

Usage & Model에는 사용량, 실행 계정, 메인·플랜·세컨더리 모델 및 effort 선택을 둡니다. 모델 선택 후 패널의 적용 버튼을 누릅니다. Speed mode 선택은 제거되었으며, 기존 Fast 저장값과 CLI 설정을 포함해 새 Codex 실행은 Standard(`service_tier="default"`)로 고정됩니다. 과거 사용량 이벤트는 그대로 보존합니다.

워크벤치 설정에서 Browser verification, 계정 관리, Codex CLI 버전, 경량 작업 상태·이력, 블로그 상황판, Usage 추이 그래프, 해당 모드의 인증 관리를 확인합니다. Browser verification 변경은 ‘실행 설정 저장’으로 적용합니다. Usage 통계는 기존처럼 새 탭에서 엽니다.

입력창의 실행 모드 버튼을 클릭하거나 입력창·모드 버튼에서 Shift+Tab을 누르면 `Work → Plan → Secondary → Plan+ → Work` 순서로 전환합니다. 모바일 추가 메뉴도 같은 상태를 공유합니다. Work은 메인 모델로 일반 실행, Plan은 플랜 모델로 계획만 작성, Secondary는 세컨더리 모델로 일반 실행합니다. Plan+는 플랜 모델로 계획을 작성한 뒤 메인 모델로 실행합니다. 세컨더리의 모델·effort를 비워두면 메인 설정을 각각 상속합니다. 서버 큐는 제출 시점의 역할과 모델·effort를 저장합니다. 기존 큐는 실행 시 기존 호환 경로로 설정을 결정합니다. Sub job과 Usage keepalive는 세컨더리를 사용하며, 커밋 메시지 생성은 전용 설정이 있으면 이를 우선하고 없으면 세컨더리·메인 순으로 상속합니다. 커밋 메시지 설정의 ‘세컨더리 상속 선택’은 전용 설정을 지웁니다. 실행 메시지와 사용량 이벤트에 `model_role`을 기록합니다.

설정의 ‘알림 이력’은 표시된 일시·종류·문구를 브라우저 IndexedDB에 자동 기록합니다. 영구 토스트도 포함하며, 자동 건수 제한은 없습니다. 최신 50건부터 표시하고 검색, 종류 필터, 이전 알림 더 보기, 전체 JSON 내보내기, 명시적 전체 삭제를 지원합니다. 기록은 새로고침 후에도 유지됩니다. 브라우저·접속 origin별로 분리되며, 다른 기기와 자동 공유하지 않습니다. 브라우저 저장 공간 삭제·시크릿 모드 종료 시 사라질 수 있습니다. 저장 오류는 이력 영역에 표시합니다. 적용 이전에 사라진 토스트는 복원하지 않습니다.

검증: 역할 설정 저장·상속, 서버 큐 선택 보존, 커밋 모델 우선순위, Standard 고정의 Python 테스트와 `CODEX_VERIFY_WORKBENCH_CONTROLS=1 CODEX_VERIFY_DIALOG_LAYOUT=1 python3.14 scripts/verify_browser_ui.py --url <URL> --selector '#codex-ui-settings-open'`로 알림 보존·검색·필터·페이지 조회·내보내기 및 낮은 화면 레이아웃을 검사할 수 있습니다.
