# Codex Workbench 사내 LLM 연동 및 폐쇄망 설치 가이드

검토일: 2026-05-24

이 문서는 Codex Workbench가 Codex CLI를 경유해 사내 DTGPT 계열 LLM API를 사용하는 방법을 정리한다. 이번 버전은 다음 제약을 전제로 한다.

- 폐쇄 Linux 망: `sudo` 권한 없음, 외부 인터넷 접속 불가
- OA Windows 망: WSL 사용 불가, PowerShell만 사용 가능
- OA Windows 망과 폐쇄 Linux 망에서 사용 가능한 LLM 모델 목록이 다름

## 핵심 결론

현재 Codex Workbench는 LLM API를 직접 호출하지 않는다. 서버 코드가 `codex exec` 명령을 만들고 Codex CLI를 자식 프로세스로 실행한다.

핵심 코드 경로:

- `codex-web-app/services/codex_chat.py::_build_codex_command`
- `execute_codex_prompt()`와 스트리밍 worker가 `_build_codex_command()`를 호출
- `_build_codex_exec_env()`가 환경변수를 Codex CLI에 전달하고, 필요 시 `~/.codex/config.toml`을 queued `CODEX_HOME`으로 복사

따라서 1차 권장 방식은 Workbench 내부에 사내 LLM 클라이언트를 새로 만들지 않고, Codex CLI의 user-level provider 설정으로 사내 API를 바라보게 하는 것이다.

현재 Workbench에는 사내망 전환을 위한 얇은 CLI routing 옵션을 반영했다.

- `CODEX_CLI_MODEL_PROVIDER`: `_build_codex_command()`가 `--config 'model_provider="..."'`로 Codex CLI에 전달
- `CODEX_CLI_PROFILE`: 값이 있으면 `_build_codex_command()`가 `--profile ...`로 Codex CLI에 전달
- provider URL, API key, 추가 header, SSO command는 계속 `~/.codex/config.toml` 또는 환경변수에만 둔다.

반드시 확인할 조건:

- Codex CLI custom provider는 `Responses API` 호환 endpoint가 필요하다.
- Codex 공식 config reference 기준 `wire_api`는 `responses`만 지원된다.
- 사내 API가 `/chat/completions`만 제공한다면 Codex CLI 경유 방식은 바로 붙지 않는다. 이 경우 사내 gateway에서 `/responses` 호환 endpoint를 제공해야 한다.

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

벤치마크 출처:

- DeepSeek-V4-Pro HF model card: <https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro>
- Qwen3.5-397B-A17B HF model card: <https://huggingface.co/Qwen/Qwen3.5-397B-A17B>
- Qwen3.6-27B HF model card: <https://huggingface.co/Qwen/Qwen3.6-27B>
- GLM-4.7 HF model card: <https://huggingface.co/zai-org/GLM-4.7>
- Gemma 4 31B IT HF model card: <https://huggingface.co/google/gemma-4-31B-it>
- OpenAI gpt-oss model card: <https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf>

## Codex CLI provider 설정

provider 설정은 repo 안에 넣지 말고 user-level config에 둔다. Codex 공식 문서 기준 project-local `.codex/config.toml`에서는 `model_provider`, `model_providers`, `profile`, `profiles` 같은 machine-local routing key가 무시된다.

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

[profiles.dtgpt_linux]
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

[profiles.dtgpt_oa]
model_provider = "dtgpt_oa"
model = "Qwen3.6-27B"
model_reasoning_effort = "high"
```

사내 gateway가 추가 header를 요구하면 `env_http_headers`를 사용한다.

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

## 폐쇄 Linux 망 설치 전략

폐쇄 Linux 망에서는 다음 명령을 전제로 하면 안 된다.

```bash
sudo apt-get install ...
npm i -g @openai/codex
pip install -r requirements.txt
git clone https://github.com/...
```

권장 방식은 인터넷 가능한 준비 장비에서 user-space bundle을 만든 뒤 폐쇄망에 반입하는 것이다.

필수 구성품:

- Codex Workbench source archive
- Python 3.10+ 실행 환경
- Python wheelhouse: `flask==3.0.3`, `cryptography==48.0.0` 및 하위 의존성
- Node.js LTS Linux x64 tarball
- Codex CLI npm package를 user prefix에 설치한 결과물
- 선택: Git. 폐쇄망 서버에 Git이 없으면 source archive 방식으로 가져오고 Workbench의 Git 기능은 제한된다.

### 준비 장비에서 bundle 만들기

준비 장비는 폐쇄망 Linux와 같은 CPU architecture, 가능한 한 비슷한 glibc 계열을 사용한다. `cryptography` wheel 호환성 때문이다.

```bash
mkdir -p ~/codex_workbench_offline_bundle
cd ~/codex_workbench_offline_bundle

git clone https://github.com/yjkim9670/codex-agent.git codex_workbench
git -C codex_workbench status
git -C codex_workbench archive --format=tar.gz --output ../codex_workbench-src.tgz HEAD
```

Python wheelhouse:

```bash
python3 -m pip download \
  -r codex_workbench/requirements.txt \
  --only-binary=:all: \
  -d wheelhouse

tar -czf wheelhouse.tgz wheelhouse
```

Node.js와 Codex CLI:

```bash
# Node.js LTS Linux x64 tarball은 nodejs.org 또는 사내 artifact 저장소에서 받아 둔다.
tar -xf node-v*-linux-x64.tar.xz
NODE_DIR="$(find "$PWD" -maxdepth 1 -type d -name 'node-v*-linux-x64' | head -n 1)"
export PATH="${NODE_DIR}/bin:$PATH"

npm install --global --prefix "$PWD/codex-node" @openai/codex
tar -czf codex-node-linux-x64.tgz -C codex-node .
```

반입할 파일 예:

```text
codex_workbench-src.tgz
wheelhouse.tgz
node-v*-linux-x64.tar.xz
codex-node-linux-x64.tgz
```

### 폐쇄 Linux 망에서 설치

모두 `$HOME/apps` 아래에 설치한다.

```bash
mkdir -p "$HOME/apps/codex_workbench" "$HOME/apps/node" "$HOME/apps/codex-node"
cd "$HOME/apps"

tar -xzf /path/to/codex_workbench-src.tgz -C "$HOME/apps/codex_workbench" --strip-components=1
tar -xf /path/to/node-v*-linux-x64.tar.xz -C "$HOME/apps/node" --strip-components=1
tar -xzf /path/to/codex-node-linux-x64.tgz -C "$HOME/apps/codex-node"

export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
codex --version
```

wheelhouse 배치:

```bash
cd "$HOME/apps/codex_workbench"
tar -xzf /path/to/wheelhouse.tgz
```

Python venv:

```bash
python3 -m venv "$HOME/apps/.venv"
. "$HOME/apps/.venv/bin/activate"
python -m pip install --no-index --find-links ./wheelhouse -r requirements.txt
```

`python3 -m venv`가 동작하지 않으면 폐쇄망 사용자가 해결할 수 있는 범위가 아니다. 사내 표준 Python 배포본에 `venv` 또는 `ensurepip`가 포함되어 있어야 한다. 대안은 같은 경로 기준으로 미리 만든 Python runtime/venv bundle을 사내 artifact로 제공하는 것이다.

### 폐쇄 Linux 망 실행

```bash
cd "$HOME/apps/codex_workbench"
export PATH="$HOME/apps/node/bin:$HOME/apps/codex-node/bin:$PATH"
export DTGPT_API_KEY="replace-with-token"
export CODEX_MODEL_OPTIONS="DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT"

./run_codex_chat_server_company.sh
```

접속:

```text
http://localhost:3000
```

## OA Windows PowerShell 설치 전략

WSL은 사용하지 않는다. Codex CLI 공식 문서도 Windows에서는 PowerShell에서 네이티브 실행할 수 있다고 설명한다.

필수 구성품:

- Git for Windows 또는 GitHub ZIP 다운로드
- Python 3.10+
- Node.js LTS
- Codex CLI npm package
- PowerShell

회사 정책상 installer 실행이 제한되면 사내 소프트웨어 센터 또는 승인된 ZIP 배포본을 사용한다.

### GitHub import

Git이 있으면:

```powershell
cd $HOME
git clone https://github.com/yjkim9670/codex-agent.git codex_workbench
cd .\codex_workbench
git status
```

Git이 없으면 GitHub에서 ZIP을 받아 압축 해제한다.

```powershell
Expand-Archive .\codex-agent-main.zip -DestinationPath $HOME
Rename-Item "$HOME\codex-agent-main" "$HOME\codex_workbench"
cd "$HOME\codex_workbench"
```

### Codex CLI 설치

Node.js가 설치되어 있다고 가정한다.

```powershell
node --version
npm --version

npm config set prefix "$HOME\.npm-global"
npm i -g @openai/codex

$env:Path = "$HOME\.npm-global;$env:Path"
codex --version
```

새 PowerShell 창에서도 쓰려면 사용자 PATH에 `$HOME\.npm-global`을 추가한다.

```powershell
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$HOME\.npm-global*") {
    [Environment]::SetEnvironmentVariable("Path", "$HOME\.npm-global;$UserPath", "User")
}
```

### Python 환경

```powershell
cd "$HOME\codex_workbench"
py -3 -m venv "$HOME\.venv_codex_workbench"
& "$HOME\.venv_codex_workbench\Scripts\python.exe" -m pip install --upgrade pip
& "$HOME\.venv_codex_workbench\Scripts\python.exe" -m pip install -r .\requirements.txt
```

인터넷이 제한된 OA 환경에서는 Linux와 같은 방식으로 `wheelhouse`를 준비한 뒤 다음 명령을 사용한다.

```powershell
& "$HOME\.venv_codex_workbench\Scripts\python.exe" -m pip install --no-index --find-links .\wheelhouse -r .\requirements.txt
```

### OA Windows 실행

```powershell
cd "$HOME\codex_workbench"
$env:DTGPT_API_KEY = "replace-with-token"
$env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"

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

Codex CLI 확인:

```bash
export DTGPT_API_KEY="replace-with-token"
codex --ask-for-approval never exec \
  --sandbox read-only \
  --skip-git-repo-check \
  --model DeepSeek-V4-Pro \
  --config 'model_provider="dtgpt_linux"' \
  --config 'model_reasoning_effort="low"' \
  "한국어 한 문장으로 짧게 응답해줘."
```

### OA Windows PowerShell

health 확인:

```powershell
Invoke-WebRequest `
  -Uri "https://cloud.dtgpt.samsungds.net/llm/health" `
  -UseBasicParsing
```

Codex CLI 확인:

```powershell
$env:DTGPT_API_KEY = "replace-with-token"
codex --ask-for-approval never exec `
  --sandbox read-only `
  --skip-git-repo-check `
  --model Qwen3.6-27B `
  --config 'model_provider="dtgpt_oa"' `
  --config 'model_reasoning_effort="low"' `
  "한국어 한 문장으로 짧게 응답해줘."
```

이 단계가 실패하면 Workbench 코드를 보기 전에 다음을 먼저 확인한다.

- `${base_url}/responses`가 실제로 존재하는지
- streaming 응답이 Codex CLI가 기대하는 Responses API SSE 형식인지
- API key/header/SSO token이 Codex CLI 프로세스 환경변수로 전달되는지
- OA Windows 망에서 사내 CA/TLS inspection 인증서가 Windows trust store에 들어있는지
- 폐쇄 Linux 망에서 DNS와 HTTP proxy 예외가 올바른지

## Workbench 수정 사항

현재 repo에서 반영한 실행 보조 변경:

- `codex-web-app/services/codex_chat.py`가 `CODEX_CLI_MODEL_PROVIDER`를 `model_provider` config override로 전달
- `codex-web-app/services/codex_chat.py`가 `CODEX_CLI_PROFILE`을 `--profile` 인자로 전달
- `/api/codex/settings` 응답과 UI status에 현재 CLI profile/provider id를 읽기 전용으로 표시
- `run_codex_chat_server_company.sh`의 Linux 기본 모델 목록을 폐쇄망 모델 순위로 정렬
- `run_codex_chat_server_company.sh`가 기본 `CODEX_CLI_MODEL_PROVIDER=dtgpt_linux`를 설정
- `run_codex_chat_server_company.ps1` 추가: Windows PowerShell 전용 회사망 실행 스크립트
- `run_codex_chat_server_company.ps1`이 기본 `CODEX_CLI_MODEL_PROVIDER=dtgpt_oa`를 설정
- `activate_venv.sh`, `run_codex_chat_server.sh`가 `wheelhouse/`가 있으면 `pip --no-index --find-links`로 오프라인 설치하도록 수정

선택적으로 사용할 수 있는 추가 전환 방식:

- 단일 장비에서 OA/Linux provider를 동시에 전환해야 하는 경우 유용하다.
- 예: `CODEX_CLI_PROFILE=dtgpt_linux` 또는 PowerShell `$env:CODEX_CLI_PROFILE = "dtgpt_oa"`
- 현재처럼 망별 장비가 분리되어 있으면 회사망 실행 스크립트의 기본 `CODEX_CLI_MODEL_PROVIDER`와 user-level config의 provider 정의만으로 충분하다.

피해야 할 방식:

- `codex_settings.json`에 provider URL이나 secret을 저장하지 않는다.
- repo-local `.codex/config.toml`에 `model_provider`나 `model_providers`를 넣지 않는다.
- `/llm/health`를 `base_url`로 쓰지 않는다.
- 폐쇄 Linux 망에서 실행 시점에 외부 `pip`, `npm`, `git clone`을 기대하지 않는다.

## 체크리스트

- 사내 API가 `${base_url}/responses`를 제공한다.
- Linux 폐쇄망에는 source archive, wheelhouse, Node.js tarball, Codex CLI user-prefix bundle을 반입했다.
- Linux 폐쇄망에서 `codex --version`이 user-space PATH로 잡힌다.
- Windows OA 망에서는 PowerShell에서 `codex --version`이 동작한다.
- Windows OA 모델 목록은 `Qwen3.6-27B,Gemma-4-31B-IT` 순서다.
- Linux 폐쇄망 모델 목록은 `DeepSeek-V4-Pro,Qwen3.5-397B-A17B-FP8,GLM4.7,OpenAI-GPT-OSS-120B,Gemma-4-31B-IT` 순서다.
- 회사망 실행 스크립트가 `CODEX_CLI_MODEL_PROVIDER`를 각각 `dtgpt_linux`, `dtgpt_oa`로 설정한다.
- profile 단위 전환이 필요하면 `CODEX_CLI_PROFILE`을 별도로 지정한다.
- Workbench 실행 전 Codex CLI 단독 smoke test가 성공한다.
