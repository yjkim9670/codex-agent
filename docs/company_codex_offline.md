# 사내망 Codex CLI 오프라인 설정 가이드

검토 기준일: 2026-05-24

이 문서는 외부 인터넷 접속이 불가능한 회사망에서 Codex CLI를 설치하고, 사내 DTGPT LLM API를 사용하도록 `config.toml`을 다시 구성하는 절차를 정리한다.

## 전제

- 회사망에서는 외부 인터넷 접속이 불가능하다.
- OA Windows 망에서는 WSL을 사용하지 않는다. 모든 작업은 PowerShell에서 수행한다.
- Windows OA 망에는 기존 Codex 사용 흔적인 `%USERPROFILE%\.codex` 폴더가 있으며, 이를 삭제하고 새로 셋업한다.
- Linux 폐쇄망은 `sudo` 권한과 외부 인터넷 접속이 없다고 가정한다.
- Codex Workbench는 LLM API를 직접 호출하지 않고 `codex exec`를 실행한다. 따라서 사내 LLM 연결은 Codex CLI의 user-level 설정인 `.codex/config.toml`에서 처리한다.

## 핵심 결론

현재 작업 환경의 Codex CLI `0.131.0` 기준으로 custom provider의 `wire_api = "chat"`은 더 이상 지원되지 않는다.

검증 결과:

```text
Error loading config.toml: `wire_api = "chat"` is no longer supported.
How to fix: set `wire_api = "responses"` in your provider config.
```

따라서 `config.toml`은 반드시 다음 방향으로 작성한다.

```toml
wire_api = "responses"
```

즉, 사내 LLM gateway가 OpenAI Responses API 호환 endpoint를 제공해야 한다. Codex CLI는 대략 다음 경로를 호출한다고 보면 된다.

```text
{base_url}/responses
```

사내 API가 `/v1/chat/completions`만 제공한다면 Codex CLI에서 바로 사용할 수 없다. 이 경우 다음 중 하나가 필요하다.

- 사내 gateway에서 `/llm/v1/responses` 호환 endpoint를 제공한다.
- 회사 내부망에 Responses API 요청을 Chat Completions 요청으로 변환하는 adapter를 둔다.
- `wire_api = "chat"`을 지원하는 과거 Codex CLI 버전을 별도로 검증해 고정한다. 단, 현재 기준 권장하지 않는다.

## 사내 API 주소

Health check URL:

| 망 | URL |
| --- | --- |
| OA Windows | `https://cloud.dtgpt.samsungds.net/llm/health` |
| Linux 폐쇄망 | `http://dtgpt.samsungds.net/llm/health` |

`config.toml`의 `base_url`에는 health URL을 넣지 않는다. API root만 넣는다.

| 망 | `base_url` 후보 |
| --- | --- |
| OA Windows | `https://cloud.dtgpt.samsungds.net/llm/v1` |
| Linux 폐쇄망 | `http://dtgpt.samsungds.net/llm/v1` |

## Windows OA 망 모델 순서

Workbench의 모델 목록은 코드 작업과 에이전트 작업 기준으로 아래 순서를 사용한다.

1. `Qwen3.6-27B`
2. `Gemma-4-31B-IT`

PowerShell 환경변수:

```powershell
$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
$env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
```

## Linux 폐쇄망 모델 순서

1. `DeepSeek-V4-Pro`
2. `Qwen3.5-397B-A17B-FP8`
3. `GLM4.7`
4. `OpenAI-GPT-OSS-120B`
5. `Gemma-4-31B-IT`

Bash 환경변수:

```bash
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"
export CODEX_CLI_MODEL_PROVIDER="dtgpt_linux"
```

## 반입해야 할 오프라인 파일

회사망에서는 `npm install`, `pip install`, `git clone`이 외부망으로 나가면 실패한다. 따라서 인터넷이 가능한 준비 장비나 사내 artifact 저장소에서 아래 파일을 미리 준비한 뒤 회사망으로 반입한다.

### Windows OA 망 필수 파일

예상 기준 경로:

```text
D:\Project_DBs\TG_Dev_2026\offline_codex
```

필수 구성:

```text
D:\Project_DBs\TG_Dev_2026\offline_codex\
  codex-version.txt
  npm-cache\
  node-v24.16.0-win-x64\
    node.exe
    npm.cmd
    npx.cmd
```

선택 구성:

```text
D:\Project_DBs\TG_Dev_2026\offline_codex\
  codex-agent-main.zip
  wheelhouse\
```

### Linux 폐쇄망 필수 파일

예상 기준 경로:

```text
$HOME/apps/offline_codex
```

필수 구성:

```text
codex_workbench-src.tgz
wheelhouse.tgz
node-v*-linux-x64.tar.xz
codex-node-linux-x64.tgz
```

## 오프라인 npm cache 준비

이 절은 회사망에서 실행하지 않는다. 외부 인터넷이 가능한 준비 장비에서 1회 실행한 뒤 결과물만 회사망으로 반입한다.

### Windows용 cache 준비

준비 장비가 Windows이면 PowerShell에서 실행한다.

```powershell
$BASE = "C:\temp\offline_codex"
$NPM_CACHE = "$BASE\npm-cache"
New-Item -ItemType Directory -Force $BASE, $NPM_CACHE | Out-Null

$CODEX_VER = (npm view @openai/codex version).Trim()
$CODEX_VER | Set-Content "$BASE\codex-version.txt" -Encoding ASCII

npm cache add "@openai/codex@$CODEX_VER" --cache "$NPM_CACHE"
npm cache add "@openai/codex@$CODEX_VER-win32-x64" --cache "$NPM_CACHE"

npm cache ls --cache "$NPM_CACHE" | Select-String "codex"
```

반입 대상:

```text
C:\temp\offline_codex\npm-cache\
C:\temp\offline_codex\codex-version.txt
```

### Linux용 Codex CLI bundle 준비

Linux 폐쇄망용은 폐쇄망과 같은 CPU architecture의 준비 장비에서 만드는 것이 안전하다.

```bash
BASE="$HOME/offline_codex_linux"
mkdir -p "$BASE"
cd "$BASE"

# Node.js tarball은 사내 승인 경로에서 받은 파일을 둔다.
tar -xf node-v*-linux-x64.tar.xz
NODE_DIR="$(find "$PWD" -maxdepth 1 -type d -name 'node-v*-linux-x64' | head -n 1)"
export PATH="$NODE_DIR/bin:$PATH"

npm install --global --prefix "$BASE/codex-node" @openai/codex
tar -czf codex-node-linux-x64.tgz -C "$BASE/codex-node" .
```

## Windows OA 망 설치

이 절은 WSL 없이 PowerShell만 사용한다.

### 1. 경로 변수 설정

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_CACHE = "$BASE\npm-cache"
$NPM_PREFIX = "$BASE\npm-global"

New-Item -ItemType Directory -Force $NPM_PREFIX | Out-Null
$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
```

### 2. Node.js 확인

```powershell
& "$NODE_HOME\node.exe" -v
& "$NODE_HOME\npm.cmd" -v
```

PowerShell에서는 `npm`보다 `npm.cmd`를 쓰는 편이 안전하다.

### 3. Codex CLI 오프라인 설치

```powershell
$CODEX_VER = (Get-Content "$BASE\codex-version.txt").Trim()

& "$NODE_HOME\npm.cmd" config set prefix "$NPM_PREFIX"

& "$NODE_HOME\npm.cmd" install -g `
  "@openai/codex@$CODEX_VER" `
  --offline `
  --include=optional `
  --cache "$NPM_CACHE" `
  --prefix "$NPM_PREFIX"

& "$NPM_PREFIX\codex.cmd" --version
```

`Missing optional dependency @openai/codex-win32-x64` 또는 `ENOTCACHED`가 발생하면 Windows용 binary package가 cache에 없는 것이다. 이 경우 cache를 다시 반입하거나 아래 명령으로 명시 설치한다.

```powershell
& "$NODE_HOME\npm.cmd" install -g `
  "@openai/codex@$CODEX_VER" `
  "@openai/codex-win32-x64@npm:@openai/codex@$CODEX_VER-win32-x64" `
  --offline `
  --include=optional `
  --cache "$NPM_CACHE" `
  --prefix "$NPM_PREFIX"
```

### 4. PATH 영구 등록

```powershell
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($UserPath -notlike "*$NODE_HOME*") {
  $UserPath = "$NODE_HOME;$UserPath"
}

if ($UserPath -notlike "*$NPM_PREFIX*") {
  $UserPath = "$NPM_PREFIX;$UserPath"
}

[Environment]::SetEnvironmentVariable("Path", $UserPath, "User")
```

새 PowerShell을 열고 확인한다.

```powershell
node.exe -v
npm.cmd -v
codex.cmd --version
```

## Windows OA 망 `.codex` 완전 재설정

기존 `%USERPROFILE%\.codex` 폴더를 그대로 삭제하고 새로 만든다. 이 작업은 기존 Codex 세션, auth, config를 삭제한다.

```powershell
$CODEX_DIR = Join-Path $env:USERPROFILE ".codex"

if (Test-Path $CODEX_DIR) {
  Remove-Item -Path $CODEX_DIR -Recurse -Force
}

New-Item -ItemType Directory -Force $CODEX_DIR | Out-Null
```

백업을 남기고 싶으면 삭제 대신 rename을 사용한다.

```powershell
$CODEX_DIR = Join-Path $env:USERPROFILE ".codex"
if (Test-Path $CODEX_DIR) {
  $BackupName = ".codex.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Rename-Item -Path $CODEX_DIR -NewName $BackupName
}
New-Item -ItemType Directory -Force $CODEX_DIR | Out-Null
```

## Windows OA 망 `config.toml` 생성

다음 설정은 Responses API 호환 endpoint를 전제로 한다.

```powershell
$CODEX_DIR = Join-Path $env:USERPROFILE ".codex"
$CONFIG_PATH = Join-Path $CODEX_DIR "config.toml"

New-Item -ItemType Directory -Force $CODEX_DIR | Out-Null

$Toml = @'
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"
model_reasoning_effort = "high"

[model_providers.dtgpt_oa]
name = "DTGPT OA"
base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"
env_key = "DTGPT_API_KEY"
wire_api = "responses"
stream_idle_timeout_ms = 600000

[profiles.oa_qwen]
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"
model_reasoning_effort = "high"

[profiles.oa_gemma]
model_provider = "dtgpt_oa"
model = "Gemma-4-31B-IT"
model_reasoning_effort = "high"
'@

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CONFIG_PATH, $Toml, $Utf8NoBom)

Get-Content $CONFIG_PATH
```

API key가 필요한 경우 사용자 환경변수로 저장한다.

```powershell
[Environment]::SetEnvironmentVariable("DTGPT_API_KEY", "<사내_발급_TOKEN>", "User")
$env:DTGPT_API_KEY = "<사내_발급_TOKEN>"
```

사내 gateway가 인증 없이 동작하더라도 Codex CLI가 `env_key`를 요구할 수 있으므로 더미 값을 넣어 둔다.

```powershell
[Environment]::SetEnvironmentVariable("DTGPT_API_KEY", "dummy", "User")
$env:DTGPT_API_KEY = "dummy"
```

추가 HTTP header가 필요하면 provider 설정에 `env_http_headers`를 추가한다. 값에는 실제 header 값이 아니라 환경변수 이름을 넣는다.

```toml
[model_providers.dtgpt_oa]
name = "DTGPT OA"
base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"
env_key = "DTGPT_API_KEY"
wire_api = "responses"
stream_idle_timeout_ms = 600000
env_http_headers = { "X-User-Id" = "DTGPT_USER_ID", "X-Dept-Code" = "DTGPT_DEPT_CODE" }
```

PowerShell에서 header 환경변수를 설정한다.

```powershell
[Environment]::SetEnvironmentVariable("DTGPT_USER_ID", "<사번_또는_ID>", "User")
[Environment]::SetEnvironmentVariable("DTGPT_DEPT_CODE", "<부서코드>", "User")

$env:DTGPT_USER_ID = "<사번_또는_ID>"
$env:DTGPT_DEPT_CODE = "<부서코드>"
```

## Windows OA 망 API 확인

### 1. Health check

```powershell
Invoke-RestMethod `
  -Uri "https://cloud.dtgpt.samsungds.net/llm/health" `
  -Method Get
```

### 2. Responses API 확인

이 테스트가 성공해야 Codex CLI custom provider가 정상 동작할 가능성이 높다.

```powershell
$RESPONSES_URL = "https://cloud.dtgpt.samsungds.net/llm/v1/responses"
$headers = @{
  Authorization = "Bearer $env:DTGPT_API_KEY"
}
$body = @{
  model = "Qwen3.6-27B"
  input = "ping"
  stream = $false
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri $RESPONSES_URL `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

### 3. Chat Completions만 되는지 확인

아래 테스트는 진단용이다. 이 endpoint가 성공하더라도 Codex CLI가 바로 붙는다는 의미는 아니다.

```powershell
$CHAT_URL = "https://cloud.dtgpt.samsungds.net/llm/v1/chat/completions"
$headers = @{
  Authorization = "Bearer $env:DTGPT_API_KEY"
}
$body = @{
  model = "Qwen3.6-27B"
  messages = @(
    @{
      role = "user"
      content = "ping"
    }
  )
  stream = $false
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri $CHAT_URL `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

`/chat/completions`만 성공하고 `/responses`가 404 또는 schema error로 실패하면 `config.toml` 수정만으로는 해결되지 않는다. 사내 gateway의 `/responses` 지원 또는 adapter가 필요하다.

## Windows OA 망 Codex CLI 실행 확인

PowerShell에서 직접 실행한다.

```powershell
& "$NPM_PREFIX\codex.cmd" exec `
  --strict-config `
  --profile oa_qwen `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

PATH를 등록하고 새 PowerShell을 열었다면 다음처럼 실행할 수 있다.

```powershell
codex.cmd exec `
  --strict-config `
  --profile oa_qwen `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

Gemma profile 테스트:

```powershell
codex.cmd exec `
  --strict-config `
  --profile oa_gemma `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

## Codex Workbench import

회사망에서 GitHub에 직접 접근할 수 없으면 외부 또는 사내 mirror에서 ZIP을 받아 반입한다.

원격 저장소:

```text
https://github.com/yjkim9670/codex-agent
```

Windows PowerShell에서 ZIP을 해제한다.

```powershell
$WORK_ROOT = "D:\Project_DBs\TG_Dev_2026"
Expand-Archive "$BASE\codex-agent-main.zip" -DestinationPath $WORK_ROOT -Force

if (Test-Path "$WORK_ROOT\codex_workbench") {
  $BackupName = "codex_workbench.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Rename-Item "$WORK_ROOT\codex_workbench" $BackupName
}

Rename-Item "$WORK_ROOT\codex-agent-main" "codex_workbench"
cd "$WORK_ROOT\codex_workbench"
```

Python wheelhouse가 함께 반입되어 있으면 오프라인으로 의존성을 설치한다.

```powershell
$VENV = "$WORK_ROOT\.venv_codex_workbench"
py -3 -m venv $VENV

& "$VENV\Scripts\python.exe" -m pip install `
  --no-index `
  --find-links "$BASE\wheelhouse" `
  -r ".\requirements.txt"
```

Workbench 실행:

```powershell
cd "$WORK_ROOT\codex_workbench"

$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
$env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
$env:CODEX_STORAGE_SUBDIR = ".agent_state_company"

.\run_codex_chat_server_company.ps1
```

브라우저 접속:

```text
http://localhost:3000
```

ExecutionPolicy로 막히면 현재 실행에 한해서 우회한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_chat_server_company.ps1
```

## Linux 폐쇄망 `config.toml`

Linux 폐쇄망은 `sudo` 없이 사용자 홈에만 설정한다.

```bash
mkdir -p "$HOME/.codex"

cat > "$HOME/.codex/config.toml" <<'EOF'
model_provider = "dtgpt_linux"
model = "DeepSeek-V4-Pro"
model_reasoning_effort = "high"

[model_providers.dtgpt_linux]
name = "DTGPT Linux"
base_url = "http://dtgpt.samsungds.net/llm/v1"
env_key = "DTGPT_API_KEY"
wire_api = "responses"
stream_idle_timeout_ms = 600000

[profiles.linux_deepseek]
model_provider = "dtgpt_linux"
model = "DeepSeek-V4-Pro"
model_reasoning_effort = "high"

[profiles.linux_qwen]
model_provider = "dtgpt_linux"
model = "Qwen3.5-397B-A17B-FP8"
model_reasoning_effort = "high"

[profiles.linux_glm]
model_provider = "dtgpt_linux"
model = "GLM4.7"
model_reasoning_effort = "high"

[profiles.linux_gpt_oss]
model_provider = "dtgpt_linux"
model = "OpenAI-GPT-OSS-120B"
model_reasoning_effort = "high"

[profiles.linux_gemma]
model_provider = "dtgpt_linux"
model = "Gemma-4-31B-IT"
model_reasoning_effort = "high"
EOF
```

환경변수:

```bash
export DTGPT_API_KEY="<사내_발급_TOKEN>"
```

인증이 없더라도 더미 값을 넣는다.

```bash
export DTGPT_API_KEY="dummy"
```

Codex CLI 단독 테스트:

```bash
codex exec \
  --strict-config \
  --profile linux_deepseek \
  --sandbox read-only \
  --skip-git-repo-check \
  --color never \
  "한국어로 hello 한 단어만 출력해줘."
```

## 자주 나는 오류

### `wire_api = "chat" is no longer supported`

현재 Codex CLI에서는 `wire_api = "responses"`로 설정해야 한다.

```toml
wire_api = "responses"
```

사내 API가 `/chat/completions`만 지원하면 `config.toml`만 수정해서는 해결되지 않는다.

### `404 Not Found`

`base_url`에 health URL을 넣었거나, 사내 gateway가 `/responses` endpoint를 제공하지 않는 경우가 많다.

올바른 예:

```toml
base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"
```

잘못된 예:

```toml
base_url = "https://cloud.dtgpt.samsungds.net/llm/health"
```

### `npm is not recognized`

현재 PowerShell 세션의 PATH 문제다.

```powershell
& "$NODE_HOME\npm.cmd" -v
```

### `npm.ps1 cannot be loaded`

PowerShell 실행 정책 문제다. `npm` 대신 `npm.cmd`를 사용한다.

```powershell
npm.cmd -v
```

### `codex.ps1 cannot be loaded`

`codex` 대신 `codex.cmd`를 사용한다.

```powershell
codex.cmd --version
```

### `ENOTCACHED`

오프라인 설치에 필요한 npm package가 `npm-cache`에 없다. 준비 장비에서 cache를 다시 만들고 아래 두 항목을 회사망으로 다시 반입한다.

```text
npm-cache\
codex-version.txt
```

### `Missing optional dependency @openai/codex-win32-x64`

Windows용 Codex binary package가 빠졌다. cache에 `@openai/codex@<version>-win32-x64`가 포함되어야 한다.

## 최종 Windows 실행 요약

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_CACHE = "$BASE\npm-cache"
$NPM_PREFIX = "$BASE\npm-global"
$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"

$CODEX_VER = (Get-Content "$BASE\codex-version.txt").Trim()
& "$NODE_HOME\npm.cmd" install -g `
  "@openai/codex@$CODEX_VER" `
  --offline `
  --include=optional `
  --cache "$NPM_CACHE" `
  --prefix "$NPM_PREFIX"

& "$NPM_PREFIX\codex.cmd" --version
```

`.codex` 삭제 후 `config.toml` 재생성:

```powershell
$CODEX_DIR = Join-Path $env:USERPROFILE ".codex"
if (Test-Path $CODEX_DIR) {
  Remove-Item -Path $CODEX_DIR -Recurse -Force
}
New-Item -ItemType Directory -Force $CODEX_DIR | Out-Null

$CONFIG_PATH = Join-Path $CODEX_DIR "config.toml"
$Toml = @'
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"
model_reasoning_effort = "high"

[model_providers.dtgpt_oa]
name = "DTGPT OA"
base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"
env_key = "DTGPT_API_KEY"
wire_api = "responses"
stream_idle_timeout_ms = 600000

[profiles.oa_qwen]
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"
model_reasoning_effort = "high"

[profiles.oa_gemma]
model_provider = "dtgpt_oa"
model = "Gemma-4-31B-IT"
model_reasoning_effort = "high"
'@

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CONFIG_PATH, $Toml, $Utf8NoBom)

[Environment]::SetEnvironmentVariable("DTGPT_API_KEY", "dummy", "User")
$env:DTGPT_API_KEY = "dummy"
```

Codex CLI 테스트:

```powershell
codex.cmd exec `
  --strict-config `
  --profile oa_qwen `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```
