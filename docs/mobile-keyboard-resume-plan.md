# 삼성 인터넷 복귀 후 프롬프트 키보드 가림: 분석 및 개선 계획

작성일: 2026-11-07. 키보드 문제는 계획만 수립하며, 해당 JS 동작은 이번에 변경하지 않는다.

## 증상 및 확정 범위

사용자 관찰: 모바일 삼성 인터넷에서 다른 작업 후 Workbench로 복귀해 프롬프트를 선택하면, 간헐적으로 입력창이 충분히 올라오지 않아 키보드에 가려진다. 브라우저를 완전히 종료한 뒤 다시 열면 정상화된다. 실제 삼성 인터넷의 장애 상태는 아직 재현·측정하지 않았으므로 아래 원인은 가설이다.

## 코드에서 확인한 사실

- `codex-web-app/static/js/app.js`의 `setupMobileViewportBehavior()`는 visualViewport의 resize/scroll, window resize, 입력창 focus/blur/input 등을 통해 화면 상태를 갱신한다. 페이지 복귀를 위한 pageshow/visibilitychange/window focus 동기화는 없다. pagehide는 파일 보기 상태 저장에만 연결되어 있다.
- `lastStableMobileViewportHeight/Width`와 `lastAppliedMobileViewportHeight/Top/PromptLift`는 페이지 메모리에 유지된다. 브라우저 프로세스를 다시 열면 이 값들이 새로 초기화되는 점은 사용자 증상과 부합하지만 원인 확정 근거는 아니다.
- `rememberPromptFocusBaseline()`는 pointerdown/touchstart/mousedown 시점의 높이를 기준값으로 직접 저장한다. 복귀 직후 브라우저 측정값이 과도 상태라면 잘못된 기준 높이를 저장할 여지가 있다. 일반 갱신 경로의 `shouldRememberStableMobileViewportHeight()` 보호와도 차이가 있다.
- 커버 화면은 키보드 전 높이를 유지하고 `applyMobilePromptLift()`로 폼을 이동한다. 내부 Fold 화면은 visualViewport 높이와 offsetTop에 맞춰 셸을 줄이는 별도 경로다.
- `getPromptViewportBottom()`는 app의 좌표를 보고 offsetTop 적용 여부를 판단하고, `applyMobilePromptLift()`는 기존 이동량을 되돌려 미이동 폼 위치를 추정한다. 페이지 복귀 시 문서 스크롤·팬·저장된 이동량의 상태가 어긋나면 이 계산도 영향을 받을 수 있다.

키보드는 layout viewport와 별개로 visual viewport를 줄일 수 있고, offsetTop은 두 좌표계 사이의 차이다. 따라서 innerHeight만으로 장애를 설명하거나 offsetTop을 일괄 가산하는 수정은 피한다. 참고: [MDN VisualViewport](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport), [offsetTop](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport/offsetTop).

## 우선순위가 높은 원인 가설

1. 숨김/복귀 후 이벤트 누락 또는 지연으로 과거 기준 높이·이동량이 남고, 재포커스 없이 복귀하면 focus 재동기화도 실행되지 않는다.
2. 복귀 직후 과도 상태의 높이가 기준값으로 저장되어 키보드 감지 또는 셸 높이 보존이 틀어진다.
3. 주소 표시줄·브라우저 팬·문서 스크롤과 CSS zoom이 결합해 가시 하단 좌표 또는 이동 상한이 실제 입력창 위치와 달라진다.

삼성 인터넷 고유 버그나 특정 버전의 결함으로 단정하지 않는다. 현재 코드와 사용자 관찰로는 가설 간 우선순위만 정할 수 있다.

## 구현 단계 (후속 작업)

1. **재현 상태 측정:** opt-in 디버그 모드에 한해 이벤트명/시간, visibilityState, pageshow.persisted, activeElement의 ID, innerHeight/Width, visualViewport height/width/offsetTop/scale, scrollY, app·폼의 rect, UI scale, 화면 모드, 기준 높이·이동량·키보드 판정을 제한된 메모리 버퍼에 기록한다. 프롬프트 내용과 음성은 기록하지 않는다.
2. **복귀 동기화 통합:** pageshow, visible로의 visibilitychange, window focus를 하나의 중복 방지 스케줄러에 연결한다. 복귀 즉시와 다음 프레임, 짧은 후속 시점(예: 120/300/700ms)에 측정한다. 연속 측정이 안정되면 종료하고 숨김 시 타이머를 해제한다. 탭 이동과 다른 앱 복귀, BFCache 복귀를 모두 확인한다.
3. **상태 회복:** 복귀 시 기존 이동량을 그대로 계산에 재사용하기 전에 DOM과 일치하는지 확인하고, 높이 적용→키보드 판정→레이아웃 반영→폼 위치 재측정 순서를 통일한다. 키보드가 열린 상태를 기준 높이로 저장하지 않는다. 입력창 터치 경로에도 안정값 저장 보호를 적용한다. 회전·접기/펼치기로 폭이 바뀐 기준값은 무효화한다. 측정 불안정 시 유효한 기존 기준을 유지한다.
4. **최소 보정:** 측정 결과로 좌표계와 이동 상한 문제 여부를 판단한다. 필요할 때만 커버 화면에서 가시 하단과 폼 하단을 재비교해 제한된 추가 보정을 한다. 내부 Fold의 셸 축소 경로는 별도로 검증한다. 상시 polling, UA별 고정 키보드 높이, 무조건 blur/focus, 강제 재로드는 사용하지 않는다.

## 검증 및 완료 기준

- 자동화: 늦게 도착하는 viewport 이벤트, 복귀 후 focus 유지/해제, offsetTop 0/양수, innerHeight 동시 축소/유지, 오래된 기준값, 반복 복귀·회전에서 최종 폼 위치와 상태 회복을 검증한다. 이벤트 수·타이머 상한도 확인한다.
- 삼성 인터넷 실기기: 브라우저/OS/키보드 버전과 화면 모드를 기록한 뒤 다른 탭 왕복, 앱 왕복, 화면 잠금 후 복귀, 뒤로/앞으로 복원, 주소창 접기/펼치기, 접기/펼치기 및 회전을 각각 반복한다. 빈 초안과 긴 초안, 포커스 유지 상태를 포함한다.
- 완료: viewport 안정 후 입력 가능한 영역과 버튼이 키보드 위에 있고, 글/선택 영역/스크롤이 보존되며, 강제 재시작 없이 반복 복귀해도 회복한다. 키보드 닫힘 뒤 원래 레이아웃으로 돌아오고 pinch zoom·데스크톱·터미널 입력에 회귀가 없어야 한다.
- Chromium 자동화는 실제 삼성 인터넷의 키보드/절전/프로세스 복원을 대신하지 못하므로 최종 원인 확정과 승인에는 실기기 결과를 사용한다.

## 이번에 구현한 별도 수정

모바일(599px 이하) 프롬프트는 오른쪽에 두 버튼의 폭과 간격을 포함한 82px을 확보한다. 더보기 버튼의 왼쪽 끝은 우측에서 74px 지점이므로 텍스트와 8px 이상 분리된다. 이 여백은 textarea의 모든 줄에 적용되어 중간/끝으로 스크롤해도 겹치지 않는다. 하단 여백은 10px로 복원한다. 키보드 감지·이동 계산은 수정하지 않는다.
