# Design Specification

## Scope

이 문서는 `mac-local-llm-infographic`의 현재 화면 디자인만 정의한다. 제품 선택, 가격 판단, 수치 해석, 결론 문구 같은 콘텐츠 결정은 포함하지 않는다.

## Direction

- 모바일 우선의 단일 페이지 인포그래픽
- 광고형 랜딩보다 판단 가능한 정보 밀도와 구조적 가독성을 우선
- 화려한 장식보다 경계선, 간격, 타이포 계층으로 구획을 만든다
- 숫자와 비교 정보를 빠르게 훑을 수 있는 편집형 UI를 유지한다
- 전체 톤은 차분하고 업무용에 가깝게 유지한다

## Visual System

### Typography

- 기본 폰트: `IBM Plex Sans KR`, `IBM Plex Sans`, `ui-sans-serif`, `system-ui`, `sans-serif`
- 모노 폰트: `IBM Plex Mono`, `ui-monospace`, `monospace`
- `h1`은 `clamp(2.4rem, 11vw, 5.4rem)`로 크게 잡고 줄간격은 매우 타이트하게 유지한다
- 섹션 타이틀은 `clamp(1.55rem, 7vw, 2.8rem)` 범위로 운용한다
- 본문은 15px에서 17px 체감 밀도를 유지하고 line-height는 약 `1.55`에서 `1.6`으로 둔다
- 라벨, 킥커, 표 머리글, 보조 메타는 모노 폰트와 uppercase로 구조감을 만든다

### Color Tokens

- Background: `#f4f4f4`
- Surface: `#ffffff`
- Surface alt: `#f4f4f4`
- Surface muted: `#e8e8e8`
- Text primary: `#161616`
- Text secondary: `#525252`
- Text tertiary: `#6f6f6f`
- Border: `#c6c6c6`
- Accent: `#0f62fe`
- Accent tint: `#d0e2ff`
- Dark panel start: `#262626`
- Dark panel end: `#161616`

### Surface Style

- 기본 카드는 흰 배경과 얇은 회색 보더를 사용한다
- 그림자는 약하게만 사용한다: `0 18px 40px rgba(22, 22, 22, 0.06)`
- 강조 카드는 연한 blue tint와 blue border로만 구분한다
- 과한 글로우, 블러, 유리 효과는 사용하지 않는다

## Layout

### Page Frame

- 전체 폭은 `min(100% - 24px, 1248px)`를 기본으로 한다
- 상단 여백은 작게 시작하고, 하단은 safe area를 고려해 확보한다
- 페이지는 여러 개의 독립 section card가 수직으로 쌓이는 구조를 사용한다

### Section Rhythm

- 주요 카드 간 간격은 `16px`
- 카드 내부 패딩은 모바일 `18px` 또는 `22px`, 큰 화면 `28px`
- 둥근 모서리는 `16px`와 `20px`를 기본 반경으로 사용한다

## Information Architecture

현재 화면의 구조는 아래 순서를 유지한다.

1. 큰 제목과 요약 지표를 담는 hero panel
2. 시나리오를 전환하는 selector block
3. 기준별 차이를 읽는 comparison grid
4. 숫자 지표를 나열하는 metrics section
5. 선택지를 훑는 candidate card grid
6. 판단 문장을 짧게 정리한 decision tile section
7. 운영 규칙과 전환 메모를 나란히 놓는 dual grid
8. 어두운 톤의 final summary panel
9. 출처와 메타 정보를 담는 footer link area

## Component Rules

### Hero Panel

- 첫 화면은 2단 구조를 기본으로 설계하되 모바일에서는 1열로 접는다
- 좌측은 큰 제목, 설명, 요약 태그로 구성한다
- 우측은 1차 강조 타일과 숫자 타일 묶음을 둔다
- hero 태그는 pill 형태로 처리하고 자동 줄바꿈을 허용한다

### Summary Tile

- 강조 타일은 연한 blue gradient를 사용한다
- 상단에 작은 kicker, 중앙에 큰 제목, 하단에 요약 정보 line을 둔다
- 하단 분리선으로 요약 정보 영역을 구분한다

### Metric Tiles

- 동일한 높이감의 카드로 반복 배치한다
- 아이콘, 라벨, 큰 숫자, 짧은 설명 순서를 유지한다
- 모바일에서는 1열 또는 2열, 넓은 화면에서는 다열 확장을 허용한다

### Scenario Selector

- 선택 UI는 세로 탭 리스트를 기본으로 한다
- 활성 상태는 파란 배경과 흰 텍스트로만 명확히 구분한다
- 선택된 탭의 상세 설명 카드는 오른쪽 또는 아래에 붙인다

### Comparison Grid

- 데스크톱에서는 표처럼 읽히는 4열 grid를 사용한다
- 모바일에서는 각 row를 카드처럼 분해하고 셀 앞에 라벨을 붙인다
- 판단 셀은 accent blue로 강조한다
- 가로 스크롤은 허용하지 않는다

### Candidate Cards

- 모든 후보 카드는 동일한 리듬으로 정렬한다
- 상단에는 badge와 선택 상태 표식을 둔다
- 가장 중요한 숫자는 가장 강한 계층으로 보이게 한다
- 보조 스펙은 한 단계 낮은 색으로 처리한다
- 하단 메모 영역은 상단과 border로 분리한다
- 강조 카드는 tint만 다르게 하고 과한 배지 사용은 피한다

### Decision Tiles

- 긴 문단보다 짧은 판단 문장 위주로 정리한다
- 각 타일은 독립 카드처럼 보이되 지나치게 무겁지 않게 유지한다

### Dual Grid

- 두 개의 compact section을 같은 밀도로 배치한다
- 모바일에서는 세로 스택, 중간 이상 화면에서는 2열로 전환한다

### Final Panel

- 마지막 요약 영역만 어두운 테마를 사용해 앞선 카드들과 대비시킨다
- 검은색 면 위에 약한 반투명 카드들을 올린다
- 여기서도 정보 밀도를 유지하고 장식성은 최소화한다

### Footer Links

- 출처 링크는 pill 버튼 스타일로 처리한다
- 모바일에서는 전체 너비 버튼처럼 보이게 확장한다
- 메타 텍스트는 모노 폰트로 작게 정리한다

## Responsive Rules

### Base

- 기본 기준 폭은 모바일 우선이다
- 320px 이상에서 무리 없이 읽혀야 한다
- 390px 전후 화면에서 가장 자연스럽게 보이도록 조정한다

### `min-width: 720px`

- hero panel을 2열로 확장한다
- scenario block을 탭 영역과 상세 영역의 2열로 바꾼다
- candidate, reason, dual, final 영역의 다열 배치를 시작한다

### `min-width: 940px`

- section padding을 더 늘린다
- comparison grid를 완전한 표 구조로 바꾼다
- metrics grid와 candidate grid를 3열로 확장한다
- decision tile도 3열로 정리한다

### `max-width: 939px`

- comparison grid는 표 대신 stacked row 패턴을 사용한다
- 각 셀 앞의 작은 label로 열 의미를 보완한다

### `max-width: 719px`

- 작은 숫자 카드와 규칙 카드들은 1열 우선으로 정리한다
- footer 링크는 전폭 버튼으로 바꾼다

## Interaction Style

- 모션은 최소화한다
- 상태 변화는 색상, 보더, 배경 전환으로 해결한다
- 버튼과 링크는 크기보다 명확한 대비와 정렬로 클릭 가능성을 만든다
- sticky UI는 사용하지 않는다

## Content Presentation Rules

- 숫자 정보는 카드 단위로 나눠 빠르게 스캔되게 한다
- 긴 설명보다 비교, 차이, 판단 문장을 우선한다
- 제목은 결론형으로, 본문은 근거형으로 작성한다
- 장식용 이미지 없이도 페이지가 충분히 완성되어 보여야 한다

## Avoid

- 제품 사진 중심의 대형 hero
- 과한 gradient 사용
- 유리 효과와 과한 blur
- 모바일 가로 스크롤
- 설명 없이 많은 배지와 스티커성 강조
- 넓은 여백으로 정보 밀도를 떨어뜨리는 구성
