# 사내 Windows Claude CLI 실행 재현 및 디버깅

이 문서는 Codex Workbench에서 에이전트 백엔드를 `Claude`로 선택했을 때의
실행 조건을 PowerShell에서 최대한 동일하게 재현하기 위한 절차다.

API Key 값은 문서나 스크립트에 기록하지 않는다. 이 절차에서 사용자가
설정할 환경변수 이름은 **`DTGPT_API_KEY`** 이다.

## 1. Workbench가 실제로 실행하는 방식

사내 실행 스크립트는 기본적으로 다음 값을 사용한다.

| 항목 | 값 |
| --- | --- |
| Claude CLI | `$HOME\.local\bin\claude.exe`, `$HOME\.local\bin\claude.cmd`, `PATH`의 `claude.cmd`, `claude.exe`, `claude` 순으로 탐색 |
| Health URL | `https://cloud.dtgpt.samsungds.net/llm/health` |
| Claude API base URL | `https://cloud.dtgpt.samsungds.net/llm` |
| 모델 | Health 응답의 `openai_models`에서 선택한 모델 |
| 프롬프트 전달 | 명령행 인자가 아니라 UTF-8 stdin |
| 실시간 출력 | `--output-format stream-json --verbose` |
| 권한 | 사내 실행 스크립트 기본값은 `--dangerously-skip-permissions` |

실시간 채팅에서 만들어지는 명령의 형태는 다음과 같다.

```text
<claude 실행 파일> -p
  --model <Workbench에서 선택한 모델>
  [--effort <Workbench에서 선택한 reasoning effort>]
  --dangerously-skip-permissions
  [--max-turns <CODEX_CLAUDE_MAX_TURNS 값>]
  --output-format stream-json
  --verbose
```

위 명령은 보기 편하게 여러 줄로 표시했을 뿐 실제로는 하나의 프로세스로
실행된다. 프롬프트는 이 명령 뒤에 붙지 않고 프로세스의 stdin에 쓰인 뒤
stdin이 닫힌다.

Workbench는 Claude 프로세스를 시작하기 직전에 다음 환경을 구성한다.

```text
CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1
ANTHROPIC_BASE_URL=https://cloud.dtgpt.samsungds.net/llm
ANTHROPIC_AUTH_TOKEN=<DTGPT_API_KEY의 값>
ANTHROPIC_MODEL=<선택 모델>
ANTHROPIC_DEFAULT_OPUS_MODEL=<선택 모델>
ANTHROPIC_DEFAULT_SONNET_MODEL=<선택 모델>
ANTHROPIC_DEFAULT_HAIKU_MODEL=<선택 모델>
CLAUDE_CODE_SUBAGENT_MODEL=<선택 모델>
```

`ANTHROPIC_API_KEY`는 제거하며, Bedrock·Vertex 등의 provider 선택 환경변수도
제거한다. 이 때문에 터미널 재현 시에도 기존 Claude 설정의 영향을 제거하는
과정이 필요하다.

## 2. API Key와 Claude CLI 확인

현재 PowerShell 프로세스에만 API Key를 넣는다.

```powershell
$env:DTGPT_API_KEY = Read-Host "DTGPT API Key"
```

키 값 자체를 출력하지 말고 설정 여부만 확인한다.

```powershell
if ([string]::IsNullOrWhiteSpace($env:DTGPT_API_KEY)) {
    throw "DTGPT_API_KEY가 설정되지 않았습니다."
}
Write-Host "DTGPT_API_KEY is configured."
```

Workbench와 같은 우선순위로 Claude CLI를 찾고 버전을 확인한다.

```powershell
$ClaudeCandidates = @(
    (Join-Path $HOME ".local\bin\claude.exe"),
    (Join-Path $HOME ".local\bin\claude.cmd")
)

$ClaudeCli = $ClaudeCandidates |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $ClaudeCli) {
    $ClaudeCommand = Get-Command claude.cmd, claude.exe, claude `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($ClaudeCommand) {
        $ClaudeCli = $ClaudeCommand.Source
    }
}

if (-not $ClaudeCli) {
    throw "Claude CLI를 찾지 못했습니다."
}

Write-Host "Claude CLI: $ClaudeCli"
& $ClaudeCli --version
& $ClaudeCli --help
```

`--help` 결과에 이 문서에서 사용하는 `-p`, `--model`, `--output-format`,
`--verbose`, `--dangerously-skip-permissions` 옵션이 있는지 확인한다.
Workbench에서 reasoning effort를 사용 중이라면 `--effort` 지원 여부도
확인한다. 특정 Claude CLI 버전이 `--effort`를 지원하지 않으면 해당 옵션을
포함한 실행은 모델 호출 전에 즉시 실패한다.

## 3. Health에서 실제 모델 목록 확인

```powershell
$HealthUrl = "https://cloud.dtgpt.samsungds.net/llm/health"
$Health = Invoke-RestMethod -Uri $HealthUrl -Method Get

$Models = @(
    $Health.openai_models |
    Where-Object {
        $_ -and $_ -notmatch "(?i)embedding|embed|reranker|bge"
    }
)

if ($Models.Count -eq 0) {
    throw "Health 응답에서 테스트할 chat 모델을 찾지 못했습니다."
}

$Models | ForEach-Object { Write-Host "  $_" }
```

Workbench는 이 `openai_models` 목록을 Codex와 Claude 백엔드에 공통으로
사용한다. Health에는 표시되지만 Claude 호환 endpoint가 처리하지 못하는
모델이 있을 수 있으므로, 문제가 발생한 모델명을 아래 `$Model`에 그대로
지정해 각각 확인한다.

```powershell
$Model = $Models[0]
# 예: $Model = "Qwen3.6-27B"
Write-Host "Test model: $Model"
```

## 4. Workbench와 같은 Claude 환경 구성

아래 설정은 현재 PowerShell 프로세스에만 적용된다.

```powershell
$env:CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST = "1"

@(
    "CLAUDE_CODE_USE_ANTHROPIC_AWS",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_MANTLE",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_API_KEY"
) | ForEach-Object {
    [Environment]::SetEnvironmentVariable($_, $null, "Process")
}

$env:ANTHROPIC_BASE_URL = "https://cloud.dtgpt.samsungds.net/llm"
$env:ANTHROPIC_AUTH_TOKEN = $env:DTGPT_API_KEY
$env:ANTHROPIC_MODEL = $Model
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = $Model
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = $Model
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = $Model
$env:CLAUDE_CODE_SUBAGENT_MODEL = $Model
```

## 5. HTML 문서 생성 테스트

테스트는 빈 폴더에서 실행하는 것이 좋다. 다음 프롬프트는 실제 파일 쓰기와
최종 응답을 함께 확인한다.

```powershell
$TestDir = Join-Path $PWD "claude-workbench-debug"
New-Item -ItemType Directory -Path $TestDir -Force | Out-Null
Set-Location $TestDir

$Prompt = @'
현재 작업 폴더에 company_claude_test.html 파일을 만들어줘.
외부 라이브러리나 외부 리소스를 사용하지 않는 단일 HTML5 문서여야 해.
한국어로 "사내 Claude CLI 연결 테스트" 제목, 연결 상태를 설명하는 카드 3개,
현재 시간을 표시하는 작은 JavaScript 기능을 포함해줘.
시맨틱 HTML과 반응형 CSS를 사용하고, 작업이 끝나면 생성한 파일명과 구현 내용을 짧게 답변해줘.
'@
```

### 5.1 먼저 단순 JSON 모드 확인

실시간 event parsing을 제외한 Claude 호출 자체가 정상인지 먼저 확인한다.

```powershell
$JsonArgs = @(
    "-p",
    "--model", $Model,
    "--dangerously-skip-permissions",
    "--output-format", "json"
)

$Prompt | & $ClaudeCli @JsonArgs 1> "claude-json.stdout.json" 2> "claude-json.stderr.log"
$JsonExitCode = $LASTEXITCODE

Write-Host "Exit code: $JsonExitCode"
Write-Host "stdout: $(Join-Path $PWD 'claude-json.stdout.json')"
Write-Host "stderr: $(Join-Path $PWD 'claude-json.stderr.log')"
Test-Path ".\company_claude_test.html"
```

이 단계가 실패하면 Workbench의 실시간 렌더링 문제가 아니라 Claude CLI,
gateway, 인증, 모델 호환성 또는 파일 권한 문제다.

### 5.2 Workbench 실시간 모드와 동일하게 확인

```powershell
Remove-Item ".\company_claude_test.html" -ErrorAction SilentlyContinue

$StreamArgs = @(
    "-p",
    "--model", $Model,
    "--dangerously-skip-permissions",
    "--output-format", "stream-json",
    "--verbose"
)

$Prompt | & $ClaudeCli @StreamArgs 1> "claude-stream.stdout.ndjson" 2> "claude-stream.stderr.log"
$StreamExitCode = $LASTEXITCODE

Write-Host "Exit code: $StreamExitCode"
Write-Host "stdout: $(Join-Path $PWD 'claude-stream.stdout.ndjson')"
Write-Host "stderr: $(Join-Path $PWD 'claude-stream.stderr.log')"
Test-Path ".\company_claude_test.html"
```

Workbench에서 reasoning effort를 선택한 실행까지 재현하려면 Claude CLI의
`--help`에서 지원을 확인한 후 `$StreamArgs`의 `--model` 다음에 다음 두
항목을 추가한다.

```powershell
"--effort", "high"
```

`CODEX_CLAUDE_MAX_TURNS`를 Workbench 실행 전에 설정했다면 다음도 추가한다.

```powershell
"--max-turns", $env:CODEX_CLAUDE_MAX_TURNS
```

## 6. 구조화된 도구 결과로 422 재현 및 우회 검증

Gateway가 문자열형 `tool_result.content`를 거부하는 환경에서는 기본 `Write`,
`Edit`, `Bash` 도구를 사용한 파일 생성 뒤 HTTP 422가 발생할 수 있다.
테스트 스크립트의 기본값인 `StructuredMcp` 모드는 모든 내장 도구를 끄고,
격리된 모델 결과 폴더의 `company_claude_test.html` 하나만 쓸 수 있는 MCP
도구를 노출한다.

MCP 도구는 성공과 실패 모두 다음과 같은 content-block 배열을 반환한다.

```json
{
  "content": [
    {
      "type": "text",
      "text": "File created successfully: company_claude_test.html"
    }
  ],
  "isError": false
}
```

먼저 기존에 422가 발생한 모델 하나만 순차 실행한다.

```powershell
$env:DTGPT_API_KEY = Read-Host "DTGPT API Key"
.\test_claude_all_models_windows.ps1 `
    -Models "<422가 발생한 정확한 모델명>" `
    -MaxParallelModels 1 `
    -ToolResultMode StructuredMcp `
    -EnableApiDebug `
    -OutputRoot "C:\temp\claude-structured-mcp-check"
```

모델명은 `/health`가 반환한 이름과 정확히 일치해야 한다. 쉼표로 여러 모델을
지정할 수도 있다.

```powershell
.\test_claude_all_models_windows.ps1 `
    -Models "model-a","model-b" `
    -MaxParallelModels 1 `
    -ToolResultMode StructuredMcp `
    -OutputRoot "C:\temp\claude-structured-mcp-two-models"
```

비교군은 같은 모델과 프롬프트에 `Builtin` 모드를 사용한다. 이 모드는 MCP
helper를 로드하지 않고 기존 Claude 내장 파일 도구를 그대로 사용한다.

```powershell
.\test_claude_all_models_windows.ps1 `
    -Models "<422가 발생한 정확한 모델명>" `
    -MaxParallelModels 1 `
    -ToolResultMode Builtin `
    -OutputRoot "C:\temp\claude-builtin-control"
```

`StructuredMcp` 성공 기준은 다음과 같다.

- `mcp-helper.debug.jsonl`에 `file_written` event 존재
- `company_claude_test.html` 생성
- `api_422_errors`가 `0`
- `result_seen`이 `True`
- `response.raw.txt`에 최종 답변 존재
- `overall_status`가 `passed`

`-EnableApiDebug`를 지정하면 `claude-api.debug.log`도 저장한다. MCP helper
로그에는 HTML 본문이나 API key를 남기지 않고 method, 파일 경로, 출력 byte
수와 오류 요약만 기록한다.

helper는 절대 경로, 하위 경로, `..`, 다른 파일명, 비문자열/빈 content,
5 MiB를 초과하는 content와 HTML 문서가 아닌 content를 거부한다. 따라서 이
모드는 Gateway 전체 트래픽을 중계하지 않으며 모델별 API stream의 지연이나
NDJSON buffering을 추가하지 않는다.

## 7. 모든 모델을 high effort 실시간 모드로 일괄 테스트

워크스페이스 루트의 `test_claude_all_models_windows.ps1`을 사용한다. 긴 실행
코드는 이 문서에 중복하지 않으며, 스크립트가 Workbench와 같은 `stream-json`,
`verbose`, `high effort` 인자와 Workbench 첫 채팅의 구조화된 stdin 프롬프트로
`/health`의 모든 chat 모델을 지정한 병렬도 안에서 실행한다. 기본값은
`StructuredMcp`, 병렬도는 `1`이다. 구조화 프롬프트의 실행 환경,
브라우저 검증, 응답 규칙 같은 보조 지시는 영어와 한글을 같은 내용으로 함께
전달한다. `Recent Transcript`와 `Current User Request` 안의 실제 사용자
요청은 일반 한글 채팅처럼 한글로만 전달한다. 동일한 최근 대화·현재 요청·
Windows 실행 환경·응답 규칙 절이 포함되므로, 단순
프롬프트에서는 성공하지만 Workbench에서는 발생하는
`API Error: Content block is not a text block` 문제를 모델별로 재현할 수 있다.

```powershell
Set-Location <스크립트가 있는 워크스페이스>
$env:DTGPT_API_KEY = Read-Host "DTGPT API Key"
.\test_claude_all_models_windows.ps1
```

단일 모델 검증이 끝난 뒤 전체 모델을 적정 병렬도로 실행한다.

```powershell
.\test_claude_all_models_windows.ps1 `
    -MaxParallelModels 4 `
    -ToolResultMode StructuredMcp `
    -OutputRoot "C:\temp\claude-all-models-structured"
```

출력 위치를 직접 지정하거나 Workbench의 최대 turn 수까지 재현할 수 있다.

```powershell
$env:DTGPT_API_KEY = Read-Host "DTGPT API Key"
$env:CODEX_CLAUDE_MAX_TURNS = "20"
.\test_claude_all_models_windows.ps1 `
    -OutputRoot "C:\temp\claude-model-check"
```

이전처럼 구조화하지 않은 테스트 프롬프트만 Claude CLI에 직접 보내 비교하려면
`-DirectPrompt`를 사용한다.

```powershell
.\test_claude_all_models_windows.ps1 `
    -DirectPrompt `
    -OutputRoot "C:\temp\claude-model-check-direct"
```

기본 실행과 `-DirectPrompt` 실행의 `summary.csv`를 비교하면 Workbench 프롬프트
구조가 특정 모델의 오류 발생 조건인지 분리할 수 있다.

스크립트는 Windows PowerShell의 네이티브 리디렉션 인코딩 차이를 피하도록
stdout과 stderr를 UTF-8로 직접 읽는다. 모델이 실행되는 동안 원본 NDJSON과
다음의 읽기 쉬운 파일도 함께 갱신된다.

- `stream.pretty.log`: 각 JSON event를 들여쓰기하고 event 경계를 표시한 로그
- `events.summary.tsv`: event 번호, 시각, type, subtype, 오류 여부만 모은 표
- `response.live.formatted.txt`: Workbench 채팅버블과 같은 누적 규칙으로
  실행 중 계속 갱신되는 읽기 쉬운 답변
- `response.raw.txt`: 모델이 반환한 최종 답변 원문
- `response.formatted.txt`: 긴 줄을 120자 기준으로 줄바꿈한 최종 답변
- `diagnostics.txt`: 실행 모드, 종료 코드, event/텍스트 후보 수, NDJSON 크기,
  도구 결과 모드, 422 오류 수, 응답 추출 경로와 산출물 상태
- `mcp.config.json`: 모델 폴더에만 적용되는 임시 MCP 설정
- `mcp-helper.debug.jsonl`: MCP 초기화·호출·파일 생성 진단
- `claude-api.debug.log`: `-EnableApiDebug`를 지정했을 때의 Claude CLI 로그

`exit-code.txt`의 `-1`은 Claude CLI가 반환한 실제 종료 코드가 아니라, 이전
버전 스크립트가 프로세스 종료 코드를 읽기 전에 출력 수집 예외가 발생했을 때
남기던 초기값이었다. 현재 스크립트는 출력 정리 중 오류가 발생해도 실행 중인
Claude CLI와 stdout/stderr가 완전히 종료될 때까지 기다린다. 따라서 high
effort 모델이 마지막 화면 출력 뒤에도 HTML을 작성 중이면 완료될 때까지 해당
모델 작업을 유지한다. 실제 종료 코드를 읽을 수 없는 시작 실패 등의 경우에는
오해하기 쉬운 `-1` 대신 `unavailable`을 기록하고, 원인은
`diagnostics.txt`와 `stream.stderr.log`의
`PowerShell collector diagnostics` 절에 남긴다.

원본인 `stream.stdout.ndjson`은 한 줄 한 event 형식을 그대로 보존한다. 따라서
사람이 읽을 때는 `stream.pretty.log` 또는 `response.live.formatted.txt`를 보고,
파서 재현이 필요할 때만 원본 NDJSON을 사용한다.

실행 중에는 별도 PowerShell 창에서 다음처럼 정리된 답변을 확인할 수 있다.

```powershell
Get-Content `
    ".\claude-all-models-<실행시각>\<모델폴더>\response.live.formatted.txt" `
    -Wait -Encoding UTF8
```

결과 폴더의 구조는 다음과 같다.

```text
claude-all-models-20260725-153000/
  summary.csv
  summary.json
  summary.report.txt
  01-Model-A/
    company_claude_test.html
    stream.stdout.ndjson
    stream.pretty.log
    events.summary.tsv
    stream.stderr.log
    response.live.formatted.txt
    response.raw.txt
    response.formatted.txt
    diagnostics.txt
    exit-code.txt
    command.txt
    model.txt
    prompt.txt
  02-Model-B/
    ...
```

각 모델이 끝날 때마다 루트의 `summary.csv`, `summary.json`,
`summary.report.txt`가 즉시 갱신된다. `summary.report.txt`는 상태별 모델 수와
핵심 판정 열을 사람이 읽기 쉬운 고정 폭 표로 함께 보여준다.
통합 결과에서 다음 필드를 먼저 비교한다.

| 필드 | 의미 |
|---|---|
| `overall_status` | `passed`, `artifact_created_response_empty`, `failed_api_content_block`, `failed_exit` 등 종합 판정 |
| `evaluation` | 종합 판정을 사람이 바로 이해할 수 있도록 풀어 쓴 원인/결과 |
| `execution_mode` | 기본값은 `workbench_first_turn`, `-DirectPrompt` 사용 시 `direct` |
| `tool_result_mode` | `StructuredMcp` 또는 비교군인 `Builtin` |
| `api_422_errors` | stderr/NDJSON에서 발견한 HTTP 422 또는 `string_type` 오류 수 |
| `ndjson_bytes` | 원본 NDJSON 크기. response가 비었지만 이벤트가 실제 생성됐는지 판별 |
| `pretty_log_bytes` | 종료 후 재구성된 pretty 로그 크기 |
| `derived_log_status` | `rebuilt`, `empty_with_ndjson`, `rebuild_failed` 등 파생 로그 재구성 상태 |
| `result_seen` | Claude CLI의 `result` event 수신 여부 |
| `text_candidates` | Workbench와 같은 중첩 content/delta 규칙으로 추출한 텍스트 후보 수 |
| `response_source` | 최종 response를 찾은 위치 (`result`, `message.content`, `content`, `delta` 등) |
| `response_status` | 텍스트 추출 성공 또는 HTML만 생성되고 response가 빈 상태를 구분 |
| `response_chars` | 최종 response의 문자 수 |
| `content_block_api_errors` | stdout NDJSON, 오류 event, stderr 전체에서 문제 문구가 발견된 횟수 |
| `html_created`, `html_bytes` | 요청한 HTML 산출물의 생성 여부와 파일 크기 |

`artifact_created_response_empty`는 HTML 작업은 성공했지만 Claude CLI가 최종
텍스트를 반환하지 않았거나 파싱 가능한 텍스트 event가 없었다는 뜻이다.
`failed_api_content_block`은 종료 코드나 HTML 생성 여부와 관계없이
`Content block is not a text block` 문구가 한 번 이상 검출된 경우다.
`failed_log_derivation`은 NDJSON 데이터가 있는데도 pretty 로그가 비어 있는
수집기/재구성 실패를 뜻한다.

`exit_code`, `collector_errors`, `invalid_json_lines`, `html_created`,
`response_status`, `content_block_api_errors`를 비교한 뒤 실패한 모델 폴더의
`diagnostics.txt`, `stream.stderr.log`, `stream.pretty.log` 순서로
확인한다. API Key는 어느 결과 파일에도 기록하지 않는다.

`stream.stdout.ndjson`은 파생 로그의 원본(source of truth)이다. 스크립트는 실행
중에 pretty 로그와 response를 갱신하고, Claude CLI가 종료된 뒤 원본 NDJSON
전체를 다시 파싱하여 다음 파일을 재구성한다.

- `stream.pretty.log`: `hook_progress`를 포함한 system/hook/assistant/result 전체 이벤트
- `events.summary.tsv`: 이벤트 타입, subtype, 오류 여부와 답변 텍스트 추출 위치
- `response.live.formatted.txt`: `message.content`, `content`, `delta`,
  `result`를 Workbench 채팅버블과 같은 방식으로 누적한 실시간 답변. 누적
  메시지는 새 suffix만 추가하고 독립 메시지는 전체를 추가하며, JSON으로
  파싱되지 않는 stdout 줄도 Workbench처럼 그대로 추가. 중첩된
  `assistant.message.content[]`의 `type: "thinking"` 블록은 `thinking` 값을,
  `type: "text"` 블록은 `text` 값을 배열 순서대로 함께 기록
- `response.raw.txt`: 마지막 Claude 답변 후보 원문
- `response.formatted.txt`: 읽기 좋게 줄바꿈한 최종 답변

따라서 이벤트 하나의 로그 직렬화나 텍스트 추출에서 예외가 발생해도 이후
stdout이 NDJSON에만 기록된 채 끝나지 않는다. gateway가 JSON 객체 하나를 여러
줄로 출력하는 경우도 종료 후 재구성 단계에서 합쳐서 파싱한다.

> 스크립트는 모델 수만큼 요청을 동시에 시작한다. 실행 전 사내 gateway의
> 동시 요청 제한과 사용량 정책을 확인한다.

## 8. 로그를 안전하게 확인하는 방법

실시간 모드의 stdout은 일반 답변이 아니라 줄 단위 JSON 이벤트다.
stderr와 섞지 말고 별도 파일로 확인해야 어떤 데이터가 채팅 버블로
유입되는지 판단할 수 있다.

```powershell
Write-Host "stdout lines: $((Get-Content .\claude-stream.stdout.ndjson).Count)"
Write-Host "stderr lines: $((Get-Content .\claude-stream.stderr.log).Count)"

Get-Content .\claude-stream.stderr.log

Get-Content .\claude-stream.stdout.ndjson | ForEach-Object {
    try {
        $Event = $_ | ConvertFrom-Json -ErrorAction Stop
        [pscustomobject]@{
            type = $Event.type
            subtype = $Event.subtype
            is_error = $Event.is_error
            session_id = $Event.session_id
        }
    }
    catch {
        [pscustomobject]@{
            type = "INVALID_JSON"
            subtype = $null
            is_error = $true
            session_id = $null
        }
    }
} | Format-Table -AutoSize
```

API Key가 포함될 가능성이 있는 전체 환경 덤프나 원본 요청 헤더는 공유하지
않는다. 공유가 필요한 진단 자료는 다음으로 제한한다.

- `claude --version`
- 사용한 모델명
- 실제 인자 목록(키 제외)
- 종료 코드
- `claude-stream.stderr.log`
- stdout 이벤트의 `type`, `subtype`, `is_error` 요약
- `INVALID_JSON` 발생 줄의 키를 제거한 내용

## 9. 결과 판별

| 결과 | 우선 확인할 원인 |
| --- | --- |
| JSON 모드부터 실패 | API Key, base URL, Claude CLI 버전, 선택 모델의 Claude 호환성 |
| JSON은 성공하고 stream-json만 실패 | gateway streaming 응답 또는 Claude CLI의 stream event 처리 |
| 터미널은 성공하고 Workbench만 실패 | Workbench가 선택한 모델·effort 차이, 실행 작업 폴더, stdout event parser |
| 종료 코드 0인데 채팅에 과도한 내용 표시 | stdout의 JSON event 중 답변 외 필드가 text로 해석되는지 확인 |
| stderr 내용이 채팅 버블에 표시 | 같은 내용이 `CLI stderr` 상세 로그에도 있는지 확인하고 stderr 필터 대상 검토 |
| 특정 모델만 실패 | Health 노출 모델과 Claude 호환 endpoint 지원 모델의 불일치 가능성 |
| `unknown option --effort` | Claude CLI 버전이 effort 옵션을 지원하지 않음 |
| 인증 또는 401/403 | `DTGPT_API_KEY` 설정 여부와 `ANTHROPIC_AUTH_TOKEN` 매핑 확인 |

Workbench 안에서 실제 명령과 프롬프트는 해당 응답의 상세 로그에 있는
`Claude exec input` 절에서, 원본 stderr는 `CLI stderr` 절에서 확인할 수
있다. 단, 보안을 위해 환경변수 값은 이 상세 로그에 기록되지 않는다.
