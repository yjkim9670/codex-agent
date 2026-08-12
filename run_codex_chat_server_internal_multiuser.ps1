<#
.SYNOPSIS
Starts Codex Workbench in internal multi-user mode.

.DESCRIPTION
Keeps the existing company runner unchanged while selecting the internal
multi-user storage and creating the initial administrator IP mapping when it
does not yet exist.
#>
param(
    [Alias("Host")]
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 3300,
    [string]$InternalDataDir,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($InternalDataDir)) {
    $InternalDataDir = Join-Path (Split-Path -Parent $ScriptDir) "internal-workbench-data"
}
$InternalDataDir = [System.IO.Path]::GetFullPath($InternalDataDir)
$UserMapPath = Join-Path $InternalDataDir "user_map.json"

$env:CODEX_WORKBENCH_MODE = "internal-multiuser"
$env:CODEX_INTERNAL_DATA_DIR = $InternalDataDir
$env:CODEX_INTERNAL_USER_MAP_PATH = $UserMapPath
$env:CODEX_SHARED_KNOWLEDGE_DIR = Join-Path $InternalDataDir "organization\shared-knowledge"

# Never replace an existing map: it may contain the organization-wide user
# assignments maintained through the Workbench administration API.
if (-not (Test-Path -LiteralPath $UserMapPath)) {
    New-Item -ItemType Directory -Force -Path $InternalDataDir | Out-Null
    $InitialMap = [ordered]@{
        version = 1
        users = @(
            [ordered]@{
                ip = "12.80.214.204"
                username = "dinya"
                role = "admin"
            }
        )
    }
    # UTF8 works in both Windows PowerShell 5.1 and PowerShell 7; JSON readers
    # accept the BOM emitted by Windows PowerShell.
    $InitialMap | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $UserMapPath -Encoding UTF8
    Write-Host "Created initial internal user map: $UserMapPath (12.80.214.204 -> dinya, admin)"
} else {
    Write-Host "Using existing internal user map: $UserMapPath"
}

Write-Host "Starting Codex Workbench in internal-multiuser mode"
Write-Host "Internal data directory: $InternalDataDir"

$CompanyRunner = Join-Path $ScriptDir "run_codex_chat_server_company.ps1"
if (-not (Test-Path -LiteralPath $CompanyRunner)) {
    throw "Company runner was not found: $CompanyRunner"
}

& $CompanyRunner -BindHost $BindHost -Port $Port @RemainingArgs
exit $LASTEXITCODE
