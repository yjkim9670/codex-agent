# 프롬프트 입력 지연 진단

## 코드 점검 결과

- 프롬프트 `input` 이벤트는 서버 호출이나 draft의 localStorage 저장을 하지 않는다. 입력 자체가 느린 현상과 Submit 이후 서버 응답이 느린 현상은 따로 기록한다.
- 기존에는 매 입력마다 `syncActiveSessionControls → renderRunningJobsMonitor → collectRunningJobs`가 실행됐다. 전체 세션을 순회하고, 실행 중 작업의 제목을 세션 목록에서 찾고, 목록 DOM을 다시 만들었다. Windows에서는 추가된 요소를 `MutationObserver → applyWeight → getComputedStyle`로 검사하므로 이 비용도 이어질 수 있었다.
- 입력 이벤트에서는 작업 목록 갱신을 생략하도록 수정했다. 작업 상태 변경과 기존 1초 타이머에서는 계속 갱신한다. 동일한 Send/Queue/Stop 보조 라벨을 반복 생성하지 않으며, 데스크톱 입력에서 모바일 viewport 갱신도 예약하지 않는다.
- 추가 후보: `renderMessages`는 세션을 열 때 전체 메시지와 Markdown을 렌더링한다. `updateStreamEntry`는 출력이 도착하면 누적 응답 텍스트를 교체하고 스크롤 치수를 읽는다. Windows 글꼴 관찰자는 동적으로 추가된 요소들의 computed style을 검사한다. 이들은 긴 대화/응답에서 확인할 후보이며, 사내 환경의 원인으로 확정한 것은 아니다. 스트리밍 중에는 전체 Markdown 파싱 대신 텍스트를 표시한다.

## Windows Chrome/Edge에서 재현 조건 좁히기

같은 짧은 문장을 10~20초 입력하고 아래 조건을 한 번에 하나씩 바꿔 비교한다. 프롬프트를 전송할 필요는 없다.

| 비교 | 차이가 날 때 의심할 영역 |
| --- | --- |
| 짧은 새 세션 / 대화가 많은 세션 | 메시지 DOM 규모, 레이아웃, 메모리 |
| 작업이 없는 상태 / 응답을 수신하는 상태 | 스트림 화면 갱신과 백그라운드 작업 |
| 영문 / 한글 조합 입력 | IME, 조합 이벤트, 맞춤법/입력 보조 기능 |
| 일반 창 / 확장 기능이 허용되지 않은 InPrivate·시크릿 창 | 확장 기능 영향. 기업 정책으로 강제된 기능은 남을 수 있음 |
| 파일 프리뷰를 닫은 상태 / 연 상태 | 함께 표시하는 문서와 렌더링 부하 |
| 새로고침 직후 / 장시간 사용 후 | DOM·메모리 누적, 브라우저 프로세스 부하 |

변경 전후에는 같은 PC, 브라우저, 세션, 실행 중 작업 조건을 사용한다. 시크릿 창은 로그인/설정 차이가 있으므로 결과만으로 원인을 확정하지 않는다.

## Performance 기록으로 실제 병목 찾기

1. F12 → **Performance**. 실사용 지연을 먼저 측정할 때 CPU·네트워크 throttling은 사용하지 않는다.
2. 녹화를 시작하고 프롬프트에 입력해 지연을 재현한 뒤 10~20초 안에 정지한다.
3. 지연 구간을 선택하고 **Main**, **Call tree**, **Bottom-up**에서 오래 걸린 호출을 확인한다. 특히 다음 이름을 검색한다.
   - `syncActiveSessionControls`, `renderRunningJobsMonitor`, `collectRunningJobs`
   - `MutationObserver`, `applyWeight`, `getComputedStyle`
   - `renderMessages`, `renderMarkdown`, `updateStreamEntry`, `setMarkdownContent`
4. 긴 JavaScript 실행은 해당 호출 경로를, `Recalculate Style`·`Layout` 비중이 크면 화면/스타일 갱신을 우선 점검한다. Main에 큰 작업이 없고 한글에서만 지연되면 IME와 OS/브라우저 입력 보조 기능을 비교한다. 이것도 확정 진단은 아니다.
5. **Network**는 Submit 이후 지연 또는 백그라운드 응답과의 상관관계를 볼 때 확인한다. 긴 요청 시간만으로 타이핑 지연의 원인이라고 판단하지 않는다.
6. 브라우저 작업 관리자(Chrome/Edge: Shift+Esc)와 Windows 작업 관리자에서 해당 탭·브라우저·다른 프로세스의 CPU/메모리 사용량을 같은 시점에 확인한다.

공식 안내: [Chrome DevTools Performance 사용법](https://developer.chrome.com/docs/devtools/performance).

## 선택: 30초 동안 긴 메인 스레드 작업만 집계

DevTools Console에서 다음 코드를 실행하고 페이지에 돌아와 입력한다. Performance API가 지원되는 브라우저에서 50ms 이상 작업의 개수와 시간을 집계한다. 입력 내용은 읽거나 저장하지 않으며 서버로 전송하지 않는다. 실행 결과가 없다고 입력 지연이 없다는 뜻은 아니다. Performance 녹화가 더 정확한 호출 경로를 제공한다.

```js
(() => {
  if (!PerformanceObserver.supportedEntryTypes?.includes('longtask')) {
    console.info('이 브라우저는 longtask 관찰을 지원하지 않습니다. Performance 녹화를 사용하세요.');
    return;
  }
  const rows = [];
  const collect = entries => entries.forEach(e => rows.push({
    startMs: Math.round(e.startTime), durationMs: Math.round(e.duration)
  }));
  const observer = new PerformanceObserver(list => collect(list.getEntries()));
  observer.observe({ type: 'longtask', buffered: false });
  console.info('30초 동안 입력해 보세요. 이후 결과를 출력합니다.');
  setTimeout(() => {
    collect(observer.takeRecords());
    observer.disconnect();
    console.table(rows);
    console.info('긴 작업 수:', rows.length,
      '최대 ms:', rows.reduce((max, row) => Math.max(max, row.durationMs), 0));
  }, 30000);
})();
```

진단 메모에는 발생 시각, 브라우저 버전, 한글/영문 여부, 세션의 대략적인 메시지 수, 실행 중 작업 수, 지연 지속 시간, 가장 오래 걸린 함수 이름/시간을 적으면 된다. Performance 내보내기에는 화면·URL 등 사내 정보가 포함될 수 있으므로 사내 공유 기준에 맞춰 취급한다.

## 검증 범위

`tests/test_prompt_input_performance.cjs`는 실제 입력 리스너와 제어/작업 목록 함수를 Chromium에 로드해 입력 1,000회에서 작업 수집과 목록 교체가 생략되는지 검사한다. Send/Queue/Stop 전환, remote 입력 잠금/해제, 모바일 viewport 갱신 유지도 확인한다. macOS Chromium에서 실행하며 Windows의 OS 글꼴 렌더링·IME나 사내 보안 프로그램은 재현하지 않는다. 실제 지연 시간 개선 비율을 측정하는 벤치마크는 아니다.
