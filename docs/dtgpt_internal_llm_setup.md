# Codex Workbench 사내 LLM 연동 및 폐쇄망 설치 가이드

검토일: 2026-05-24

이 문서는 사내망에 설치한 Codex CLI를 이용해 Codex Workbench를 구동하는 계획과 절차를 정리한다. Codex CLI 자체 설치, `.codex/config.toml` 재생성, CLI 단독 `codex exec` 검증은 `company_codex_offline.md`를 기준으로 한다.

이번 버전은 다음 제약을 전제로 한다.

- 폐쇄 Linux 망: `sudo` 권한 없음, 외부 인터넷 접속 불가
- OA Windows 망: WSL 사용 불가, PowerShell만 사용 가능
- OA Windows 망과 폐쇄 Linux 망에서 사용 가능한 LLM 모델 목록이 다름
- 사내 DTGPT gateway는 Codex CLI가 사용할 Responses API 호환 endpoint를 제공함

## 핵심 결론

현재 Codex Workbench는 LLM API를 직접 호출하지 않는다. 서버 코드가 `codex exec` 명령을 만들고 Codex CLI를 자식 프로세스로 실행한다.

핵심 코드 경로:

- `codex-web-app/services/codex_chat.py::_build_codex_command`
- `execute_codex_prompt()`와 스트리밍 worker가 `_build_codex_command()`를 호출
- `_build_codex_exec_env()`가 환경변수를 Codex CLI에 전달하고, 필요 시 `~/.codex/config.toml`을 queued `CODEX_HOME`으로 복사

따라서 1차 권장 방식은 Workbench 내부에 사내 LLM 클라이언트를 새로 만들지 않고, 이미 설치 및 검증된 Codex CLI의 user-level provider 설정으로 사내 API를 바라보게 하는 것이다.

현재 Workbench에는 사내망 전환을 위한 얇은 CLI routing 옵션을 반영했다.

- `CODEX_CLI_MODEL_PROVIDER`: `_build_codex_command()`가 `--config 'model_provider="..."'`로 Codex CLI에 전달
- `CODEX_CLI_PROFILE`: 값이 있으면 `_build_codex_command()`가 `--profile ...`로 Codex CLI에 전달
- `CODEX_CLI_BIN`: Codex CLI 실행 파일 경로를 강제한다. 회사망 launcher는 PATH, npm prefix, Windows `%APPDATA%\npm`, macOS Codex 앱 번들 경로를 순서대로 확인한다.
- provider URL, API key, 추가 header, SSO command는 계속 `~/.codex/config.toml` 또는 환경변수에만 둔다.

반드시 확인할 조건:

- `company_codex_offline.md`의 Codex CLI 단독 smoke test가 먼저 성공해야 한다.
- Codex CLI custom provider는 `Responses API` 호환 endpoint가 필요하다.
- Codex 공식 config reference 기준 `wire_api`는 `responses`만 지원된다.
- 이 문서는 Responses endpoint가 제공되는 전제만 다룬다.

참고:

- Codex CLI setup: <https://developers.openai.com/codex/cli>
- Codex CLI reference: <https://developers.openai.com/codex/cli/reference>
- Codex config reference: <https://developers.openai.com/codex/config-reference>

## 사내 API 주소

제공받은 health URL:

- OA Windows 망: `https://cloud.dtgpt.samsungds.net/llm/health`
- 폐쇄 Linux 망: `http://dtgpt.samsungds.net/llm/health`

`base_url`에는 `/llm/health`를 넣으면 안 된다. health는 상태 확인 경로이고 Codex CLI provider에는 실제 API root를 넣어야 한다.

우선 검증할 후보:

- OA Windows 망: `https://cloud.dtgpt.samsungds.net/llm/v1`
- 폐쇄 Linux 망: `http://dtgpt.samsungds.net/llm/v1`

Codex CLI는 위 `base_url` 뒤에 `/responses`를 붙여 호출한다.

```text
https://cloud.dtgpt.samsungds.net/llm/v1/responses
http://dtgpt.samsungds.net/llm/v1/responses
```

사내 gateway 안내가 다르면, `/responses`가 붙는 API root만 `config.toml`의 `base_url`로 사용한다.

## 모델 우선순위

정렬 기준은 Codex Workbench의 주 용도인 코드 수정, 터미널 작업, 에이전트 작업에 맞춰 잡았다.

1. `SWE-bench Verified` 또는 Hugging Face의 `Swe Bench Resolved`
2. `TerminalBench`, `LiveCodeBench`, `Codeforces`, `Aider`
3. `GPQA`, `MMLU-Pro`, `MMLU`
4. 동일 계열이라도 사내 gateway alias, reasoning mode, quantization, serving scaffold에 따라 결과가 달라질 수 있으므로 최종 운영 순위는 사내 모델카드 또는 내부 eval로 보정

### 폐쇄 Linux 망 모델 순위

| 순위 | 모델 | 공개 벤치마크 근거 | 비고 |
| --- | --- | --- | --- |
| 1 | `DeepSeek-V4-Pro` | DeepSeek 공식 HF 카드 기준 `DS-V4-Pro Max`: SWE Verified 80.6, Terminal Bench 67.9, LiveCodeBench 93.5, GPQA Diamond 90.1, MMLU-Pro 87.5 | 사내 alias가 Max/High reasoning을 쓰는지 확인 필요 |
| 2 | `Qwen3.5-397B-A17B-FP8` | Qwen HF eval 기준 Swe Bench Resolved 76.4, GPQA Diamond 88.4, TerminalBench 52.5 | FP8 serving alias라도 모델 계열 공개 점수는 Qwen3.5-397B-A17B 기준 |
| 3 | `GLM4.7` | Z.ai HF eval 기준 Swe Bench Resolved 73.8, GPQA Diamond 85.7, TerminalBench 33.4 | coding agent 순위에서는 Qwen3.5 뒤 |
| 4 | `OpenAI-GPT-OSS-120B` | OpenAI model card 기준 high reasoning: SWE-Bench Verified 62.4, MMLU 90.0, Aider Polyglot 44.4, Codeforces 2463/2622 | 지식/일반 추론은 강하지만 SWE 기준으로는 4위 |
| 5 | `Gemma-4-31B-IT` | Google HF 카드 기준 MMLU-Pro 85.2, LiveCodeBench v6 80.0, Codeforces 2150, GPQA Diamond 84.3 | 공식 카드에 SWE-bench 점수가 없어 Codex agent 순위에서는 보수적으로 5위 |

Linux 기본 모델 목록은 이 순서로 둔다.

```bash
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"
export CODEX_CLI_MODEL_PROVIDER="dtgpt_linux"
```

### OA Windows 망 모델 순위

| 순위 | 모델 | 공개 벤치마크 근거 | 비고 |
| --- | --- | --- | --- |
| 1 | `Qwen3.6-27B` | Qwen HF eval 기준 Swe Bench Resolved 77.2, SWE Bench Pro 53.5, TerminalBench 59.3, GPQA Diamond 87.8, MMLU-Pro 86.2 | Windows OA 망 기본값 |
| 2 | `Gemma-4-31B-IT` | Google HF 카드 기준 MMLU-Pro 85.2, LiveCodeBench v6 80.0, Codeforces 2150, GPQA Diamond 84.3 | Qwen3.6보다 agent coding 지표가 약함 |

Windows 기본 모델 목록은 이 순서로 둔다.

```powershell
$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
$env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
```

## Workbench 모델 선택 방법

Workbench에서 모델을 바꾸는 값은 세 가지로 나뉜다.

- `CODEX_MODEL_OPTIONS`: Workbench 설정 화면의 모델 선택 목록이다. Codex CLI provider나 API URL을 바꾸지 않는다.
- `~/.codex/config.toml` 또는 `$HOME\.codex\config.toml`의 최상단 `model`: Workbench 저장 설정이 아직 없을 때 읽는 초기 기본값이다.
- Workbench 설정 화면에서 저장한 `model`: 실제 `codex exec` 실행 시 `--model <선택한 모델>`로 전달된다.

따라서 다른 모델을 쓰려면 먼저 해당 망에서 허용된 모델명이 `CODEX_MODEL_OPTIONS`에 들어 있어야 한다. 그 다음 Workbench 화면의 모델 선택 드롭다운에서 모델을 바꾸고 적용한다.

OA Windows 망:

```powershell
$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
$env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
```

폐쇄 Linux 망:

```bash
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"
export CODEX_CLI_MODEL_PROVIDER="dtgpt_linux"
```

새 Workbench 상태에서 초기 기본 모델을 바꾸려면 user-level `config.toml`의 최상단 `model = "..."` 값을 바꾼다. 이미 Workbench에서 한 번 저장한 모델이 있으면 그 값이 우선하므로, UI에서 다시 선택해 적용하거나 저장 상태 파일을 지운 뒤 재시작한다. 기본 저장 위치는 `CODEX_WORKSPACE_DIR`을 따르며, 별도 지정이 없으면 repo의 `workspace/.agent_state_company/codex_settings.json`이다.

`CODEX_CLI_PROFILE`은 profile에 묶인 provider, reasoning, 기타 설정을 강제로 적용할 때 사용한다. 다만 Workbench에 저장된 모델이 있으면 Workbench가 `--model <저장된 모델>`을 함께 넘기므로 profile 안의 `model`보다 Workbench 모델 선택값이 우선한다. 모델만 바꾸려는 목적이면 `CODEX_CLI_PROFILE`보다 Workbench 모델 드롭다운을 사용하는 편이 명확하다.

벤치마크 출처:

- DeepSeek-V4-Pro HF model card: <https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro>
- Qwen3.5-397B-A17B HF model card: <https://huggingface.co/Qwen/Qwen3.5-397B-A17B>
- Qwen3.6-27B HF model card: <https://huggingface.co/Qwen/Qwen3.6-27B>
- GLM-4.7 HF model card: <https://huggingface.co/zai-org/GLM-4.7>
- Gemma 4 31B IT HF model card: <https://huggingface.co/google/gemma-4-31B-it>
- OpenAI gpt-oss model card: <https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf>

## Codex CLI provider 설정

provider 설정은 repo 안에 넣지 말고 user-level config에 둔다. 자세한 생성 절차와 Windows `.codex` 삭제 후 재생성 방법은 `company_codex_offline.md`를 따른다. 이 절은 Workbench가 기대하는 provider/profile 이름을 확인하기 위한 요약이다.

Codex 공식 문서 기준 project-local `.codex/config.toml`에서는 `model_provider`, `model_providers`, `profile`, `profiles` 같은 machine-local routing key가 무시된다.

### 폐쇄 Linux 망

파일: `~/.codex/config.toml`

```toml
model_provider = "dtgpt_linux"
model = "DeepSeek-V4-Pro"

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
```

### OA Windows 망

파일: `$HOME\.codex\config.toml`

```toml
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"

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
```

사내 gateway가 추가 header를 요구하면 `env_http_headers`를 사용한다. 값에는 실제 header 값이 아니라 환경변수 이름을 넣는다.

```toml
[model_providers.dtgpt_oa]
name = "DTGPT OA"
base_url = "https://cloud.dtgpt.samsungds.net/llm/v1"
env_key = "DTGPT_API_KEY"
wire_api = "responses"
env_http_headers = { "X-User-Id" = "DTGPT_USER_ID", "X-Dept-Code" = "DTGPT_DEPT_CODE" }
```

짧은 수명의 SSO token을 발급해야 하면 `auth.command`를 사용한다. 폐쇄망에서는 이 command도 사내에서 제공되는 로컬 실행 파일이어야 한다.

```toml
[model_providers.dtgpt_linux]
name = "DTGPT Linux"
base_url = "http://dtgpt.samsungds.net/llm/v1"
wire_api = "responses"

[model_providers.dtgpt_linux.auth]
command = "/home/user/bin/get-dtgpt-token"
timeout_ms = 5000
refresh_interval_ms = 300000
```

## Workbench 오프라인 반입 파일

Workbench 단계에서는 Codex CLI 설치 파일을 다시 준비하지 않는다. `company_codex_offline.md`의 CLI 단독 테스트가 성공한 장비에 아래 Workbench 파일만 추가 반입한다.

폐쇄 Linux 망:

```text
codex_workbench-src.tgz
wheelhouse.tgz
```

OA Windows 망:

```text
codex-agent-main.zip
wheelhouse\
```

준비 장비에서 Workbench archive와 wheelhouse를 만들 때는 인터넷이 가능한 곳에서 실행한다.

```bash
mkdir -p ~/codex_workbench_offline_bundle
cd ~/codex_workbench_offline_bundle

git clone https://github.com/yjkim9670/codex-agent.git codex_workbench
git -C codex_workbench archive --format=tar.gz --output ../codex_workbench-src.tgz HEAD

python3 -m pip download \
  -r codex_workbench/requirements.txt \
  --only-binary=:all: \
  -d wheelhouse

tar -czf wheelhouse.tgz wheelhouse
```

Windows용 ZIP은 GitHub ZIP 또는 사내 mirror ZIP을 반입한다. 외부망 접속이 안 되는 회사망에서 `git clone`, `pip install`이 인터넷으로 나가는 전제를 두지 않는다.

## 폐쇄 Linux 망 Workbench 설치

전제: `company_codex_offline.md` 절차로 아래 명령이 이미 성공해야 한다.

```bash
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
codex --version
codex exec --strict-config --profile linux_deepseek --sandbox read-only --skip-git-repo-check --color never "한국어로 hello 한 단어만 출력해줘."
```

Workbench source와 wheelhouse를 사용자 홈 아래에 푼다.

```bash
mkdir -p "$HOME/apps/codex_workbench"
tar -xzf /path/to/codex_workbench-src.tgz -C "$HOME/apps/codex_workbench" --strip-components=1

cd "$HOME/apps/codex_workbench"
tar -xzf /path/to/wheelhouse.tgz
```

Python 가상환경은 `sudo` 없이 만든다.

```bash
python3 -m venv "$HOME/apps/.venv_codex_workbench"
. "$HOME/apps/.venv_codex_workbench/bin/activate"
python -m pip install --no-index --find-links ./wheelhouse -r requirements.txt
```

`python3 -m venv`가 동작하지 않으면 사용자 권한으로 해결하기 어렵다. 사내 표준 Python 배포본에 `venv` 또는 `ensurepip`가 포함되어 있어야 하며, 없으면 같은 경로 기준으로 미리 만든 Python runtime/venv bundle을 사내 artifact로 제공해야 한다.

실행할 때는 Workbench 프로세스가 Codex CLI를 찾을 수 있도록 현재 shell PATH를 명시한다.

```bash
cd "$HOME/apps/codex_workbench"
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
export DTGPT_API_KEY="replace-with-token"
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"
export CODEX_CLI_MODEL_PROVIDER="dtgpt_linux"
export CODEX_STORAGE_SUBDIR=".agent_state_company"

./run_codex_chat_server_company.sh
```

접속:

```text
http://localhost:3000
```

## OA Windows PowerShell Workbench 설치

전제: `company_codex_offline.md` 절차로 `codex.cmd --version`과 `codex.cmd exec --profile oa_qwen ...`이 이미 성공해야 한다.

새 PowerShell에서 PATH 영구 등록이 반영되지 않는 환경이라도 Workbench 실행은 현재 세션 PATH를 보정하면 된다. 이 PATH는 Python 서버와 그 자식 프로세스인 `codex exec`에 상속된다.

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_PREFIX = "$BASE\npm-global"

$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
where.exe codex.cmd
codex.cmd --version
```

`where.exe codex.cmd`가 실패하지만 파일이 있으면 직접 실행으로 확인한다.

```powershell
& "$NPM_PREFIX\codex.cmd" --version
```

Workbench ZIP을 해제한다.

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

Workbench를 실행한다. 영구 PATH가 불안정하면 실행 직전에 `$env:Path`를 다시 지정한다.

```powershell
cd "$WORK_ROOT\codex_workbench"

$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
$env:DTGPT_API_KEY = "replace-with-token"
$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
$env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
$env:CODEX_STORAGE_SUBDIR = ".agent_state_company"

.\run_codex_chat_server_company.ps1
```

ExecutionPolicy로 막히면 현재 실행에 한해서 우회한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_chat_server_company.ps1
```

접속:

```text
http://localhost:3000
```

## API smoke test

Workbench 실행 전 Codex CLI 단독 테스트를 먼저 한다.

### 폐쇄 Linux 망

health 확인:

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

payload = json.dumps({
    "model": "DeepSeek-V4-Pro",
    "input": "hello",
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

Codex CLI 확인:

```bash
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
export DTGPT_API_KEY="replace-with-token"
codex exec \
  --strict-config \
  --profile linux_deepseek \
  --sandbox read-only \
  --skip-git-repo-check \
  "한국어 한 문장으로 짧게 응답해줘."
```

### OA Windows PowerShell

health 확인:

```powershell
Invoke-WebRequest `
  -Uri "https://cloud.dtgpt.samsungds.net/llm/health" `
  -UseBasicParsing
```

Responses API 확인:

```powershell
$headers = @{
  Authorization = "Bearer $env:DTGPT_API_KEY"
}
$body = @{
  model = "Qwen3.6-27B"
  input = "hello"
  stream = $false
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "https://cloud.dtgpt.samsungds.net/llm/v1/responses" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

Codex CLI 확인:

```powershell
$BASE = "D:\Project_DBs\TG_Dev_2026\offline_codex"
$NODE_HOME = "$BASE\node-v24.16.0-win-x64"
$NPM_PREFIX = "$BASE\npm-global"
$env:Path = "$NODE_HOME;$NPM_PREFIX;$env:Path"
$env:DTGPT_API_KEY = "replace-with-token"
codex.cmd exec `
  --strict-config `
  --profile oa_qwen `
  --sandbox read-only `
  --skip-git-repo-check `
  "한국어 한 문장으로 짧게 응답해줘."
```

이 단계가 실패하면 Workbench 코드를 보기 전에 다음을 먼저 확인한다.

- 사내 gateway 직접 연결 방식이면 `${base_url}/responses`가 실제로 존재하는지
- streaming 응답이 Codex CLI가 기대하는 Responses API SSE 형식인지
- API key/header/SSO token이 Codex CLI 프로세스 환경변수로 전달되는지
- OA Windows 망에서 사내 CA/TLS inspection 인증서가 Windows trust store에 들어있는지
- 폐쇄 Linux 망에서 DNS와 HTTP proxy 예외가 올바른지

## Workbench 수정 사항

현재 repo에서 반영한 실행 보조 변경:

- `codex-web-app/services/codex_chat.py`가 `CODEX_CLI_MODEL_PROVIDER`를 `model_provider` config override로 전달
- `codex-web-app/services/codex_chat.py`가 `CODEX_CLI_PROFILE`을 `--profile` 인자로 전달
- `codex-web-app/services/codex_chat.py`가 `CODEX_CLI_BIN` 또는 Windows `codex.cmd`를 Codex CLI 실행 파일로 사용
- `/api/codex/settings` 응답과 UI status에 현재 CLI profile/provider id를 읽기 전용으로 표시
- `run_codex_chat_server_company.sh`의 Linux 기본 모델 목록을 폐쇄망 모델 순위로 정렬
- `run_codex_chat_server_company.sh`가 기본 `CODEX_CLI_MODEL_PROVIDER=dtgpt_linux`를 설정
- `run_codex_chat_server_company.ps1` 추가: Windows PowerShell 전용 회사망 실행 스크립트
- `run_codex_chat_server_company.ps1`이 기본 `CODEX_CLI_MODEL_PROVIDER=dtgpt_oa`를 설정
- 회사망 launcher가 `codex`/`codex.cmd`를 찾아 `CODEX_CLI_BIN`에 설정
- `activate_venv.sh`, `run_codex_chat_server.sh`가 `wheelhouse/`가 있으면 `pip --no-index --find-links`로 오프라인 설치하도록 수정

선택적으로 사용할 수 있는 추가 전환 방식:

- 단일 장비에서 OA/Linux provider를 동시에 전환해야 하는 경우 `CODEX_CLI_PROFILE`을 사용할 수 있다.
- 예: `CODEX_CLI_PROFILE=linux_deepseek` 또는 PowerShell `$env:CODEX_CLI_PROFILE = "oa_qwen"`
- Workbench에 저장된 모델이 있으면 `codex exec`에 `--model`이 함께 전달되므로, profile의 `model`보다 Workbench 저장 모델이 우선한다.
- 현재처럼 망별 장비가 분리되어 있으면 회사망 실행 스크립트의 기본 `CODEX_CLI_MODEL_PROVIDER`, `CODEX_MODEL_OPTIONS`, user-level config의 provider 정의만으로 충분하다.

피해야 할 방식:

- `codex_settings.json`에 provider URL이나 secret을 저장하지 않는다.
- repo-local `.codex/config.toml`에 `model_provider`나 `model_providers`를 넣지 않는다.
- `/llm/health`를 `base_url`로 쓰지 않는다.
- 폐쇄 Linux 망에서 실행 시점에 외부 `pip`, `npm`, `git clone`을 기대하지 않는다.

## 체크리스트

- 사내 API가 `${base_url}/responses`를 제공한다.
- `company_codex_offline.md` 기준으로 Codex CLI 설치와 사내 LLM 단독 smoke test가 먼저 성공했다.
- Linux 폐쇄망에는 Workbench source archive와 wheelhouse를 추가 반입했다.
- Linux 폐쇄망에서 `codex --version`이 user-space PATH로 잡힌다.
- Windows OA 망에서는 PowerShell에서 `codex.cmd --version` 또는 `& "$NPM_PREFIX\codex.cmd" --version`이 동작한다. PATH가 불안정하면 `CODEX_CLI_BIN="$NPM_PREFIX\codex.cmd"`를 지정한다. macOS에서 앱 번들로만 설치된 경우 `/Applications/Codex.app/Contents/Resources/codex`를 자동 탐색한다.
- Windows OA 모델 목록은 `Qwen3.6-27B,Gemma-4-31B-IT` 순서다.
- Linux 폐쇄망 모델 목록은 `DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT` 순서다.
- 회사망 실행 스크립트가 `CODEX_CLI_MODEL_PROVIDER`를 각각 `dtgpt_linux`, `dtgpt_oa`로 설정한다.
- profile 단위 전환이 필요하면 `CODEX_CLI_PROFILE`을 별도로 지정한다.
- Workbench 실행 전 Codex CLI 단독 smoke test가 성공한다.
