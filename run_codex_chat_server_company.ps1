param(
    [Alias("Host")]
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 3000,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir

if (-not $env:CODEX_MODEL_OPTIONS) {
    $env:CODEX_MODEL_OPTIONS = "Qwen3.6-27B,Gemma-4-31B-IT"
}
if (-not $env:CODEX_REASONING_OPTIONS) {
    $env:CODEX_REASONING_OPTIONS = "low,medium,high,xhigh"
}
if (-not $env:CODEX_CLI_MODEL_PROVIDER) {
    $env:CODEX_CLI_MODEL_PROVIDER = "dtgpt_oa"
}
if (-not $env:CODEX_STORAGE_SUBDIR) {
    $env:CODEX_STORAGE_SUBDIR = ".agent_state_company"
}

$DefaultVenvDir = Join-Path $ParentDir ".venv"
if ($env:CODEX_COMMON_VENV_DIR) {
    $VenvDir = $env:CODEX_COMMON_VENV_DIR
} elseif ($env:COMMON_PYTHON_VENV) {
    $VenvDir = $env:COMMON_PYTHON_VENV
} elseif ($env:VIRTUAL_ENV) {
    $VenvDir = $env:VIRTUAL_ENV
} else {
    $VenvDir = $DefaultVenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Invoke-HostPython {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$PythonArgs
    )

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & py -3 @PythonArgs
        return $LASTEXITCODE
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        & python @PythonArgs
        return $LASTEXITCODE
    }

    throw "Python executable not found on PATH."
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[INFO] Venv python missing at $VenvPython. Recreating..."
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
    }
    $ExitCode = Invoke-HostPython @("-m", "venv", $VenvDir)
    if ($ExitCode -ne 0) {
        throw "Failed to create a usable venv at $VenvDir"
    }
}

if (-not (Test-Path $VenvPython)) {
    throw "Failed to create a usable venv at $VenvDir"
}

$RequirementsPath = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $RequirementsPath) {
    & $VenvPython -c "import flask, cryptography" *> $null
    if ($LASTEXITCODE -ne 0) {
        $WheelhousePath = Join-Path $ScriptDir "wheelhouse"
        Write-Host "[INFO] Installing Python dependencies from $RequirementsPath..."
        if (Test-Path $WheelhousePath) {
            & $VenvPython -m pip install --no-index --find-links $WheelhousePath -r $RequirementsPath
        } else {
            & $VenvPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) {
                throw "pip upgrade failed."
            }
            & $VenvPython -m pip install -r $RequirementsPath
        }
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed."
        }
    }
}

Set-Location $ParentDir
& $VenvPython (Join-Path $ScriptDir "run_codex_chat_server.py") --host $BindHost --port $Port @RemainingArgs
exit $LASTEXITCODE
