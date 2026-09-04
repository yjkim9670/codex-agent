param(
    [Alias("Host")]
    [string]$BindHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 4096,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

function Resolve-OpenCodeCommand {
    foreach ($Name in @("opencode.cmd", "opencode.exe", "opencode")) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command) {
            return $Command.Source
        }
    }

    $CandidatePaths = @()
    foreach ($Prefix in @($env:NPM_PREFIX, $env:npm_config_prefix, $env:NPM_CONFIG_PREFIX)) {
        if (-not [string]::IsNullOrWhiteSpace($Prefix)) {
            $CandidatePaths += Join-Path $Prefix "opencode.cmd"
            $CandidatePaths += Join-Path $Prefix "opencode.exe"
        }
    }
    if ($env:APPDATA) {
        $NpmAppData = Join-Path $env:APPDATA "npm"
        $CandidatePaths += Join-Path $NpmAppData "opencode.cmd"
        $CandidatePaths += Join-Path $NpmAppData "opencode.exe"
    }
    foreach ($CandidatePath in $CandidatePaths) {
        if (Test-Path -LiteralPath $CandidatePath) {
            return $CandidatePath
        }
    }
    return $null
}

$OpenCodeBin = Resolve-OpenCodeCommand
if (-not $OpenCodeBin) {
    throw "OpenCode CLI was not found. Install it or add opencode to PATH, then run this script again."
}

$Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($Listener) {
    $Process = Get-Process -Id $Listener.OwningProcess -ErrorAction SilentlyContinue
    $ProcessName = if ($Process) { $Process.ProcessName } else { "PID $($Listener.OwningProcess)" }
    throw "Port $Port is already in use by $ProcessName. Reuse the existing OpenCode server or choose another -Port."
}

Write-Host "OpenCode CLI: $OpenCodeBin"
Write-Host "Starting OpenCode server at http://${BindHost}:$Port"
Write-Host "Keep this PowerShell window open while Workbench uses the OpenCode backend. Press Ctrl+C to stop it."

& $OpenCodeBin serve --hostname $BindHost --port $Port @RemainingArgs
if ($LASTEXITCODE -ne 0) {
    throw "OpenCode server exited with code $LASTEXITCODE."
}
