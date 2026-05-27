# 사내망 Codex CLI 오프라인 설정 가이드

검토 기준일: 2026-05-24

이 문서는 외부 인터넷 접속이 불가능한 회사망에서 Codex CLI를 설치하고, 사내 DTGPT Responses API로 `codex exec`를 단독 실행하는 절차를 정리한다.

Codex Workbench import, Python 가상환경, Workbench 실행 절차는 `dtgpt_internal_llm_setup.md`에서 다룬다. 이 문서는 Workbench 실행 전제인 "Codex CLI가 사내 LLM으로 정상 응답한다"까지를 목표로 한다.

## 전제

- 회사망에서는 외부 인터넷 접속이 불가능하다.
- OA Windows 망에서는 WSL을 사용하지 않는다. 모든 작업은 PowerShell에서 수행한다.
- Windows OA 망에는 기존 Codex 사용 흔적인 `%USERPROFILE%\.codex` 폴더가 있으며, 이를 삭제하고 새로 셋업한다.
- Linux 폐쇄망은 `sudo` 권한과 외부 인터넷 접속이 없다고 가정한다.
- 사내 LLM gateway는 OpenAI Responses API 호환 endpoint를 제공한다고 가정한다.
- 사내 LLM 연결은 Codex CLI의 user-level 설정인 `.codex/config.toml`에서 처리한다.
- Codex Workbench 연동은 이 문서의 Codex CLI 단독 smoke test가 성공한 뒤 진행한다.

## 핵심 결론

현재 작업 환경의 Codex CLI `0.131.0` 기준으로 custom provider는 Responses API 설정을 사용한다. 따라서 `config.toml`은 반드시 다음 방향으로 작성한다.

```toml
wire_api = "responses"
```

Codex CLI는 provider의 `base_url` 뒤에 `/responses`를 붙여 호출한다.

```text
{base_url}/responses
```

예를 들어 `base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"`이면 Codex CLI가 호출할 endpoint는 아래와 같다.

```text
https://cloud.dtgpt.samsungds.net/llm/v1/responses
```

이 문서는 Responses API가 제공되는 전제만 다룬다.

## 사내 API 주소

Health check URL:

| 망 | URL |
| --- | --- |
| OA Windows | `https://cloud.dtgpt.samsungds.net/llm/health` |
| Linux 폐쇄망 | `http://dtgpt.samsungds.net/llm/health` |

`config.toml`의 `base_url`에는 health URL을 넣지 않는다. API root만 넣는다.

| 망 | `base_url` 후보 | Codex CLI 호출 endpoint |
| --- | --- | --- |
| OA Windows | `https://cloud.dtgpt.samsungds.net/llm/v1` | `https://cloud.dtgpt.samsungds.net/llm/v1/responses` |
| Linux 폐쇄망 | `http://dtgpt.samsungds.net/llm/v1` | `http://dtgpt.samsungds.net/llm/v1/responses` |

사내 gateway 안내가 위 URL과 다르면, health URL이 아니라 `/responses`가 붙는 API root를 `base_url`로 사용한다.

## Windows OA 망 모델 순서

Codex CLI profile은 코드 작업과 에이전트 작업 기준으로 아래 순서를 사용한다.

1. `Qwen3.6-27B`
2. `Gemma-4-31B-IT`

PowerShell에서 Workbench 모델 선택 목록에 보여줄 값:

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

Bash에서 Workbench 모델 선택 목록에 보여줄 값:

```bash
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"
export CODEX_CLI_MODEL_PROVIDER="dtgpt_linux"
```

## 모델 선택 방법

각 망의 `config.toml`에는 기본 모델 하나와 모델별 profile을 함께 둔다. 기본 모델은 `--profile`이나 `--model`을 주지 않았을 때만 사용된다.

| 망 | 기본 모델 | 제공 profile |
| --- | --- | --- |
| OA Windows | `Qwen3.6-27B` | `oa_qwen`, `oa_gemma` |
| Linux 폐쇄망 | `DeepSeek-V4-Pro` | `linux_deepseek`, `linux_qwen`, `linux_glm`, `linux_gpt_oss`, `linux_gemma` |

Codex CLI 단독 실행에서 다른 모델을 고르는 권장 방식은 profile을 지정하는 것이다.

```powershell
& "$NPM_PREFIX\codex.cmd" exec `
  --strict-config `
  --profile oa_gemma `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

```bash
codex exec \
  --strict-config \
  --profile linux_glm \
  --sandbox read-only \
  --skip-git-repo-check \
  --color never \
  "한국어로 hello 한 단어만 출력해줘."
```

profile을 추가하지 않고 한 번만 다른 모델을 쓰려면 `--model`을 직접 넘긴다. provider는 현재 망에 맞게 명시한다.

```powershell
& "$NPM_PREFIX\codex.cmd" exec `
  --strict-config `
  --config 'model_provider="dtgpt_oa"' `
  --model "Gemma-4-31B-IT" `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

```bash
codex exec \
  --strict-config \
  --config 'model_provider="dtgpt_linux"' \
  --model "Qwen3.5-397B-A17B-FP8" \
  --sandbox read-only \
  --skip-git-repo-check \
  --color never \
  "한국어로 hello 한 단어만 출력해줘."
```

기본 모델 자체를 바꾸려면 `~/.codex/config.toml` 또는 `%USERPROFILE%\.codex\config.toml`의 최상단 `model = "..."` 값을 원하는 모델명으로 바꾼다. 반복해서 사용할 모델이면 `--model`을 매번 쓰기보다 `[profiles.<name>]` 항목을 추가하고 `--profile <name>`으로 실행한다.

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

Workbench용 `codex-agent-main.zip`, Python `wheelhouse`는 `dtgpt_internal_llm_setup.md`의 Workbench 설치 단계에서 별도로 다룬다.

### Linux 폐쇄망 필수 파일

예상 기준 경로:

```text
$HOME/apps/offline_codex
```

필수 구성:

```text
node-v*-linux-x64.tar.xz
codex-node-linux-x64.tgz
```

Workbench용 `codex_workbench-src.tgz`, `wheelhouse.tgz`는 `dtgpt_internal_llm_setup.md`에서 다룬다.

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

## Linux 폐쇄망 Codex CLI 설치

폐쇄망 Linux에서는 `sudo` 없이 사용자 홈 아래에만 설치한다.

```bash
mkdir -p "$HOME/apps/node" "$HOME/apps/codex-node"

tar -xf /path/to/node-v*-linux-x64.tar.xz -C "$HOME/apps/node" --strip-components=1
tar -xzf /path/to/codex-node-linux-x64.tgz -C "$HOME/apps/codex-node"

export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
node --version
npm --version
codex --version
```

로그인할 때마다 자동으로 잡히게 하려면 shell profile에 추가한다. 회사 표준 shell이 `bash`라면 `~/.bashrc`가 보통 대상이다.

```bash
cat >> "$HOME/.bashrc" <<'EOF'

# Codex CLI offline install
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
EOF
```

현재 세션에는 즉시 다시 적용한다.

```bash
. "$HOME/.bashrc"
codex --version
```

`~/.bashrc`가 적용되지 않는 배치/원격 실행 환경이면 실행 스크립트 앞에 `export PATH=...`를 명시한다.

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
$NODE_HOME = [System.IO.Path]::GetFullPath($NODE_HOME)
$NPM_PREFIX = [System.IO.Path]::GetFullPath($NPM_PREFIX)

if (-not (Test-Path "$NODE_HOME\node.exe")) {
  throw "node.exe not found: $NODE_HOME"
}

if (-not (Test-Path "$NPM_PREFIX\codex.cmd")) {
  throw "codex.cmd not found: $NPM_PREFIX"
}

$UserPathRaw = [Environment]::GetEnvironmentVariable("Path", "User")
$UserEntries = @(([string]$UserPathRaw) -split ';' | Where-Object { $_.Trim() })

foreach ($PathToAdd in @($NODE_HOME, $NPM_PREFIX)) {
  $AlreadyExists = $false
  foreach ($Entry in $UserEntries) {
    if ($Entry.Trim().TrimEnd('\') -ieq $PathToAdd.TrimEnd('\')) {
      $AlreadyExists = $true
      break
    }
  }
  if (-not $AlreadyExists) {
    $UserEntries = @($PathToAdd) + $UserEntries
  }
}

$NewUserPath = ($UserEntries -join ';')
[Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")

# 현재 PowerShell 세션도 즉시 갱신한다.
$MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = "$NewUserPath;$MachinePath"

where.exe node.exe
where.exe npm.cmd
where.exe codex.cmd
codex.cmd --version
```

새 PowerShell을 열고 확인한다. `codex` 대신 `codex.cmd`를 사용하면 PowerShell 실행 정책의 영향을 덜 받는다.

```powershell
node.exe -v
npm.cmd -v
codex.cmd --version
```

### 5. 새 PowerShell에서 `codex.cmd`가 계속 안 잡힐 때

먼저 실제 파일이 있는지 확인한다.

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_PREFIX = "$BASE\npm-global"

Test-Path "$NODE_HOME\node.exe"
Test-Path "$NODE_HOME\npm.cmd"
Test-Path "$NPM_PREFIX\codex.cmd"
```

`codex.cmd`가 없으면 PATH 문제가 아니라 설치 위치 또는 npm 설치 실패 문제다. 아래 명령으로 실제 설치 위치를 찾는다.

```powershell
& "$NODE_HOME\npm.cmd" config get prefix
Get-ChildItem -Path $BASE -Filter "codex.cmd" -Recurse -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty FullName
```

파일은 있는데 새 PowerShell에서만 안 잡히면 현재 프로세스 PATH와 사용자 레지스트리 PATH를 비교한다.

```powershell
[Environment]::GetEnvironmentVariable("Path", "User") -split ';' |
  Select-String -Pattern "offline_codex|npm-global|node-v"

$env:Path -split ';' |
  Select-String -Pattern "offline_codex|npm-global|node-v"
```

사용자 PATH에는 있는데 `$env:Path`에 없으면 새 PowerShell을 띄운 부모 프로세스가 오래된 환경변수를 들고 있는 상태다. Windows Terminal, VS Code, 사내 launcher를 완전히 종료한 뒤 다시 열거나, 로그오프 후 재로그인한다. 당장 현재 세션에서만 복구하려면 다음을 실행한다.

```powershell
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$MachinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = "$UserPath;$MachinePath"

where.exe codex.cmd
codex.cmd --version
```

사용자 PATH에도 없으면 4번의 PATH 영구 등록을 다시 실행한다. 회사 보안 정책이 사용자 PATH를 로그인 시점에 덮어쓰는 환경이라면 영구 등록 대신 Codex CLI 실행 직전에 아래처럼 현재 프로세스 PATH를 매번 지정한다.

```powershell
$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
& "$NPM_PREFIX\codex.cmd" --version
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

사내 gateway가 `https://.../llm/v1/responses`를 제공하는 전제의 설정이다.

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
$env:DTGPT_API_KEY = [Environment]::GetEnvironmentVariable("DTGPT_API_KEY", "User")

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

## Linux 폐쇄망 API 확인

Health check:

```bash
python3 - <<'PY'
from urllib.request import urlopen
with urlopen("http://dtgpt.samsungds.net/llm/health", timeout=10) as r:
    print(r.status)
    print(r.read().decode("utf-8", errors="replace")[:500])
PY
```

Responses API 확인:

```bash
python3 - <<'PY'
import json
import os
from urllib.request import Request, urlopen

api_key = os.environ.get("DTGPT_API_KEY", "")
payload = json.dumps({
    "model": "DeepSeek-V4-Pro",
    "input": "ping",
    "stream": False,
}).encode("utf-8")
req = Request(
    "http://dtgpt.samsungds.net/llm/v1/responses",
    data=payload,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urlopen(req, timeout=30) as r:
    print(r.status)
    print(r.read().decode("utf-8", errors="replace")[:500])
PY
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

## 다음 단계: Codex Workbench

이 문서의 목표는 Codex CLI 단독 실행 확인까지다. 아래 두 명령 중 하나가 성공하면 Workbench 설치 및 실행은 `dtgpt_internal_llm_setup.md`로 넘어간다.

```powershell
& "$NPM_PREFIX\codex.cmd" exec --strict-config --profile oa_qwen --sandbox read-only --skip-git-repo-check --color never "한국어로 hello 한 단어만 출력해줘."
```

```bash
codex exec --strict-config --profile linux_deepseek --sandbox read-only --skip-git-repo-check --color never "한국어로 hello 한 단어만 출력해줘."
```

## 자주 나는 오류

### `wire_api` 설정 오류

현재 Codex CLI에서는 Responses API provider로 설정해야 한다.

```toml
wire_api = "responses"
```

### `404 Not Found`

`base_url`에 health URL을 넣었거나, 사내 gateway의 `/responses` endpoint URL이 다른 경우가 많다.

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

새 PowerShell에서만 실패하면 `PATH 영구 등록`의 5번 진단 절차로 사용자 PATH와 현재 프로세스 PATH를 비교한다.

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

## 새 창에서 환경변수 없이 처음부터 Codex CLI 실행

이 절은 새 PowerShell 또는 새 shell을 열었고, 현재 프로세스에 `PATH`, `DTGPT_API_KEY`, `CODEX_*` 환경변수가 하나도 잡혀 있지 않은 상태를 전제로 한다. 영구 PATH가 반영되지 않는 회사 launcher 환경에서도 아래 순서대로 실행하면 현재 창에서만 Codex CLI를 사용할 수 있다.

### Windows OA 망 PowerShell

1. 새 PowerShell을 연다.

2. 오프라인 설치 경로를 다시 지정한다.

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_PREFIX = "$BASE\npm-global"
```

3. 현재 PowerShell 프로세스의 PATH만 보정한다.

```powershell
$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
```

4. 실행 파일이 실제로 있는지 확인한다.

```powershell
Test-Path "$NODE_HOME\node.exe"
Test-Path "$NPM_PREFIX\codex.cmd"
& "$NODE_HOME\node.exe" -v
& "$NPM_PREFIX\codex.cmd" --version
```

5. API key를 현재 프로세스에 넣는다. 사용자 환경변수로 저장해 둔 값이 있으면 먼저 읽고, 없으면 직접 입력한다.

```powershell
$env:DTGPT_API_KEY = [Environment]::GetEnvironmentVariable("DTGPT_API_KEY", "User")
if ([string]::IsNullOrWhiteSpace($env:DTGPT_API_KEY)) {
  $env:DTGPT_API_KEY = "<사내_발급_TOKEN>"
}
```

6. `config.toml`이 있는지 확인한다.

```powershell
$CONFIG_PATH = Join-Path $env:USERPROFILE ".codex\config.toml"
Test-Path $CONFIG_PATH
Get-Content $CONFIG_PATH
```

7. Responses API가 직접 응답하는지 확인한다. 다른 모델을 테스트하려면 `$MODEL`만 바꾼다.

```powershell
$MODEL = "Qwen3.6-27B"
# $MODEL = "Gemma-4-31B-IT"

$headers = @{
  Authorization = "Bearer $env:DTGPT_API_KEY"
}
$body = @{
  model = $MODEL
  input = "ping"
  stream = $false
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "https://cloud.dtgpt.samsungds.net/llm/v1/responses" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

8. Codex CLI를 절대 경로로 실행한다. 다른 모델을 쓰려면 `$CODEX_PROFILE`을 해당 profile로 바꾼다.

```powershell
$CODEX_PROFILE = "oa_qwen"
# $CODEX_PROFILE = "oa_gemma"

& "$NPM_PREFIX\codex.cmd" exec `
  --strict-config `
  --profile $CODEX_PROFILE `
  --sandbox read-only `
  --skip-git-repo-check `
  --color never `
  "한국어로 hello 한 단어만 출력해줘."
```

### Linux 폐쇄망 Bash

1. 새 shell을 연다.

2. 현재 shell 프로세스의 PATH만 보정한다.

```bash
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
```

3. 실행 파일이 실제로 있는지 확인한다.

```bash
command -v node
command -v codex
node --version
codex --version
```

4. API key를 현재 shell에 넣는다.

```bash
export DTGPT_API_KEY="<사내_발급_TOKEN>"
```

인증이 없는 gateway라면 dummy 값을 넣는다.

```bash
export DTGPT_API_KEY="dummy"
```

5. `config.toml`이 있는지 확인한다.

```bash
test -f "$HOME/.codex/config.toml"
sed -n '1,120p' "$HOME/.codex/config.toml"
```

6. Responses API가 직접 응답하는지 확인한다. 다른 모델을 테스트하려면 `DTGPT_TEST_MODEL`만 바꾼다.

```bash
export DTGPT_TEST_MODEL="DeepSeek-V4-Pro"
# export DTGPT_TEST_MODEL="GLM4.7"

python3 - <<'PY'
import json
import os
from urllib.request import Request, urlopen

payload = json.dumps({
    "model": os.environ.get("DTGPT_TEST_MODEL", "DeepSeek-V4-Pro"),
    "input": "ping",
    "stream": False,
}).encode("utf-8")
req = Request(
    "http://dtgpt.samsungds.net/llm/v1/responses",
    data=payload,
    headers={
        "Authorization": f"Bearer {os.environ.get('DTGPT_API_KEY', '')}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urlopen(req, timeout=30) as r:
    print(r.status)
    print(r.read().decode("utf-8", errors="replace")[:500])
PY
```

7. Codex CLI를 실행한다. 다른 모델을 쓰려면 `CODEX_PROFILE`을 해당 profile로 바꾼다.

```bash
CODEX_PROFILE="linux_deepseek"
# CODEX_PROFILE="linux_qwen"
# CODEX_PROFILE="linux_glm"

codex exec \
  --strict-config \
  --profile "$CODEX_PROFILE" \
  --sandbox read-only \
  --skip-git-repo-check \
  --color never \
  "한국어로 hello 한 단어만 출력해줘."
```
