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
if (-not $env:CODEX_AGENT_BACKEND_OPTIONS) {
    $env:CODEX_AGENT_BACKEND_OPTIONS = "dtgpt,claude"
}
if (-not $env:CODEX_AGENT_BACKEND) {
    $env:CODEX_AGENT_BACKEND = "dtgpt"
}
if (-not $env:CODEX_CLAUDE_SETTINGS_PATH) {
    $env:CODEX_CLAUDE_SETTINGS_PATH = Join-Path $HOME ".claude\settings.json"
}
if (-not $env:CODEX_ENABLE_SERVICE_TIER) {
    $env:CODEX_ENABLE_SERVICE_TIER = "0"
}
if (-not $env:CODEX_SHOW_USAGE_LIMITS) {
    $env:CODEX_SHOW_USAGE_LIMITS = "0"
}
if (-not $env:CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS) {
    $env:CODEX_REQUIRE_ENCRYPTED_CHAT_PROMPTS = "0"
}
if (-not $env:CODEX_REQUIRE_ENCRYPTED_FILE_WRITES) {
    $env:CODEX_REQUIRE_ENCRYPTED_FILE_WRITES = "0"
}
if ($env:OS -eq "Windows_NT" -and -not $env:CODEX_CLI_SANDBOX) {
    # Corporate Windows images can block Codex CLI's Windows sandbox setup with
    # CreateProcessWithLogonW 1326. Keep this override local to the company
    # PowerShell runner and allow callers to opt back into workspace-write.
    $env:CODEX_CLI_SANDBOX = "danger-full-access"
}
if (-not $env:CODEX_STORAGE_SUBDIR) {
    $env:CODEX_STORAGE_SUBDIR = ".agent_state_company"
}
$env:CODEX_USE_GLOBAL_PYTHON = "1"
# Company/offline Workbench must not inherit the legacy global exec lock. The
# older variable is set to 0 as well so older bundled server code stays lock-free.
$env:CODEX_CLI_EXEC_LOCK = "0"
$env:CODEX_CLI_SERIALIZE_EXEC = "0"
if (-not $env:CODEX_CLI_BIN) {
    $CodexCommand = Get-Command codex.cmd -ErrorAction SilentlyContinue
    if (-not $CodexCommand) {
        $CodexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue
    }
    if (-not $CodexCommand) {
        $CodexCommand = Get-Command codex -ErrorAction SilentlyContinue
    }
    if ($CodexCommand) {
        $env:CODEX_CLI_BIN = $CodexCommand.Source
    }
}
if (-not $env:CODEX_CLI_BIN) {
    $CandidatePaths = @()
    foreach ($Prefix in @($env:NPM_PREFIX, $env:npm_config_prefix, $env:NPM_CONFIG_PREFIX)) {
        if ($Prefix) {
            $CandidatePaths += Join-Path $Prefix "codex.cmd"
            $CandidatePaths += Join-Path $Prefix "codex.exe"
        }
    }
    if ($env:APPDATA) {
        $NpmAppData = Join-Path $env:APPDATA "npm"
        $CandidatePaths += Join-Path $NpmAppData "codex.cmd"
        $CandidatePaths += Join-Path $NpmAppData "codex.exe"
    }
    foreach ($CandidatePath in $CandidatePaths) {
        if ($CandidatePath -and (Test-Path $CandidatePath)) {
            $env:CODEX_CLI_BIN = $CandidatePath
            break
        }
    }
}
if (-not $env:CODEX_CLAUDE_CLI_BIN) {
    $ClaudeHomeCandidates = @()
    foreach ($HomeCandidate in @($HOME, $env:USERPROFILE)) {
        if (-not [string]::IsNullOrWhiteSpace($HomeCandidate)) {
            $ClaudeHomeCandidates += $HomeCandidate
        }
    }
    if ($env:HOMEDRIVE -and $env:HOMEPATH) {
        $ClaudeHomeCandidates += "$($env:HOMEDRIVE)$($env:HOMEPATH)"
    }

    $ClaudeCliCandidatePaths = @()
    foreach ($HomeCandidate in $ClaudeHomeCandidates) {
        $ClaudeLocalBin = Join-Path $HomeCandidate ".local\bin"
        $ClaudeCliCandidatePaths += Join-Path $ClaudeLocalBin "claude.exe"
        $ClaudeCliCandidatePaths += Join-Path $ClaudeLocalBin "claude.cmd"
    }
    foreach ($CandidatePath in $ClaudeCliCandidatePaths) {
        if ($CandidatePath -and (Test-Path $CandidatePath)) {
            $env:CODEX_CLAUDE_CLI_BIN = $CandidatePath
            break
        }
    }
}
if (-not $env:CODEX_CLAUDE_CLI_BIN) {
    $ClaudeCommand = Get-Command claude.cmd -ErrorAction SilentlyContinue
    if (-not $ClaudeCommand) {
        $ClaudeCommand = Get-Command claude.exe -ErrorAction SilentlyContinue
    }
    if (-not $ClaudeCommand) {
        $ClaudeCommand = Get-Command claude -ErrorAction SilentlyContinue
    }
    if ($ClaudeCommand) {
        $env:CODEX_CLAUDE_CLI_BIN = $ClaudeCommand.Source
    }
}
if (-not $env:CODEX_CLAUDE_MODEL_OPTIONS -and (Test-Path $env:CODEX_CLAUDE_SETTINGS_PATH)) {
    try {
        $ClaudeSettings = Get-Content $env:CODEX_CLAUDE_SETTINGS_PATH -Raw -Encoding UTF8 | ConvertFrom-Json
        $ClaudeAvailableModels = @()
        $SeenClaudeModels = @{}
        foreach ($Model in @($ClaudeSettings.availableModels)) {
            $ModelName = ""
            if ($null -eq $Model) {
                continue
            }
            if ($Model -is [string]) {
                $ModelName = $Model.Trim()
            } else {
                foreach ($ModelNameKey in @("model", "name", "id", "slug")) {
                    $ModelNameProperty = $Model.PSObject.Properties[$ModelNameKey]
                    if ($ModelNameProperty -and $null -ne $ModelNameProperty.Value) {
                        $ModelName = "$($ModelNameProperty.Value)".Trim()
                        if ($ModelName) {
                            break
                        }
                    }
                }
            }
            if ($ModelName -and -not $SeenClaudeModels.ContainsKey($ModelName)) {
                $ClaudeAvailableModels += $ModelName
                $SeenClaudeModels[$ModelName] = $true
            }
        }
        if ($ClaudeAvailableModels.Count -gt 0) {
            $env:CODEX_CLAUDE_MODEL_OPTIONS = ($ClaudeAvailableModels -join ",")
            if (-not $env:CODEX_CLAUDE_MODEL) {
                $env:CODEX_CLAUDE_MODEL = $ClaudeAvailableModels[0]
            }
        }
    } catch {
        Write-Warning ("Failed to read Claude availableModels from {0}: {1}" -f $env:CODEX_CLAUDE_SETTINGS_PATH, $_.Exception.Message)
    }
}
if (-not $env:CODEX_CLAUDE_PERMISSION_MODE) {
    $env:CODEX_CLAUDE_PERMISSION_MODE = "acceptEdits"
}
if (-not $env:CODEX_CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS) {
    $env:CODEX_CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS = "1"
}

function Test-GlobalPythonReady {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Python
    )

    $ReadyArgs = @($Python.Args) + @("-c", "import sys; sys.exit(1) if sys.version_info < (3, 10) else None; import flask, cryptography")
    & $Python.Command @ReadyArgs *> $null
    return $LASTEXITCODE -eq 0
}

function Resolve-GlobalPython {
    foreach ($Candidate in @($env:CODEX_PYTHON_BIN, $env:PYTHON_BIN, $env:PYTHON)) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) {
            continue
        }
        if (Test-Path $Candidate) {
            return [pscustomobject]@{
                Command = $Candidate
                Args = @()
            }
        }
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($Command) {
            return [pscustomobject]@{
                Command = $Command.Source
                Args = @()
            }
        }
        throw "Configured Python executable not found: $Candidate"
    }

    $Fallbacks = @()
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        $Fallbacks += [pscustomobject]@{
            Command = "py"
            Args = @("-3")
        }
    }

    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        $Fallbacks += [pscustomobject]@{
            Command = $Python.Source
            Args = @()
        }
    }

    $Fallback = $null
    foreach ($PythonCandidate in $Fallbacks) {
        if (-not $Fallback) {
            $Fallback = $PythonCandidate
        }
        if (Test-GlobalPythonReady $PythonCandidate) {
            return $PythonCandidate
        }
    }

    if ($Fallback) {
        return $Fallback
    }

    throw "Python executable not found on PATH."
}

function Invoke-GlobalPython {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Python,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$PythonArgs
    )

    $InvocationArgs = @($Python.Args) + @($PythonArgs)
    & $Python.Command @InvocationArgs
}

$GlobalPython = Resolve-GlobalPython
$RequirementsPath = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $RequirementsPath) {
    $VersionCheckArgs = @("-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)")
    Invoke-GlobalPython $GlobalPython @VersionCheckArgs *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.10+ is required for Workbench. Configured global Python is: $($GlobalPython.Command)"
    }

    $ImportCheckArgs = @("-c", "import flask, cryptography")
    Invoke-GlobalPython $GlobalPython @ImportCheckArgs *> $null
    if ($LASTEXITCODE -ne 0) {
        $WheelhousePath = Join-Path $ScriptDir "wheelhouse"
        if (Test-Path $WheelhousePath) {
            throw "Required Python packages are missing from the configured global Python: $($GlobalPython.Command). Install them before launching Workbench: $($GlobalPython.Command) -m pip install --no-index --find-links $WheelhousePath -r $RequirementsPath"
        } else {
            throw "Required Python packages are missing from the configured global Python: $($GlobalPython.Command). Install them before launching Workbench: $($GlobalPython.Command) -m pip install -r $RequirementsPath"
        }
    }
}

Set-Location $ParentDir
$ServerArgs = @((Join-Path $ScriptDir "run_codex_chat_server.py"), "--host", $BindHost, "--port", "$Port", "--reload") + $RemainingArgs
Invoke-GlobalPython $GlobalPython @ServerArgs
exit $LASTEXITCODE
