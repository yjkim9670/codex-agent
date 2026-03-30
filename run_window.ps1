Param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassthroughArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
Set-Location $ParentDir

# Windows route must use cloud DTGPT endpoint only.
$env:MODEL_DTGPT_API_BASE_URL = "http://cloud.dtgpt.samsungds.net/llm/v1"
$env:MODEL_DTGPT_API_BASE_URLS = "http://cloud.dtgpt.samsungds.net/llm/v1"

if (-not $env:MODEL_CHAT_QUIET) {
    $env:MODEL_CHAT_QUIET = "1"
}

$pythonBin = $null
if ($env:TG_PYTHON) {
    $pythonBin = Join-Path $env:TG_PYTHON "python.exe"
    if (-not (Test-Path $pythonBin)) {
        throw "Python executable not found: $pythonBin"
    }
} else {
    $venvPython = Join-Path $ParentDir ".venv\\Scripts\\python.exe"
    if (Test-Path $venvPython) {
        $pythonBin = $venvPython
    } else {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            $pythonBin = $pythonCmd.Source
        } else {
            throw "Python not found. Configure TG_PYTHON or create ../.venv."
        }
    }
}

$entryPoint = Join-Path $ScriptDir "run_model_chat_server.py"
& $pythonBin $entryPoint @PassthroughArgs
exit $LASTEXITCODE
