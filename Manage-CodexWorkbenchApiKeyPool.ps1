<#
.SYNOPSIS
Safely manages the internal multi-user API Key Pool from the server console.

.DESCRIPTION
Uses the same Windows DPAPI format as Codex Workbench.  Run this script as
the same Windows account that starts the Workbench server; DPAPI credentials
protected by a different account cannot be read by that service.

.EXAMPLE
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action Add -Label 'team-a'
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action List
.\Manage-CodexWorkbenchApiKeyPool.ps1 -Action Remove -Id '<key-id>'
#>
[CmdletBinding()]
param(
    [ValidateSet('Add', 'List', 'Remove')]
    [string]$Action = 'List',
    [string]$Label,
    [string]$Id,
    [string]$InternalDataDir
)

$ErrorActionPreference = 'Stop'
$Entropy = [Text.Encoding]::UTF8.GetBytes('CodexWorkbench.CompanyApiKey.v1')
$MaxApiKeyChars = 8192
$MaxKeys = 64

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($InternalDataDir)) {
    $InternalDataDir = Join-Path (Split-Path -Parent $ScriptDir) 'internal-workbench-data'
}
$InternalDataDir = [IO.Path]::GetFullPath($InternalDataDir)
$PoolPath = Join-Path $InternalDataDir 'organization\credentials\api_key_pool.dpapi'

function Get-RequiredPropertyValue([object]$Object, [string]$Name, $Default = $null) {
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $Default }
    return $property.Value
}

function Read-KeyPool {
    if (-not (Test-Path -LiteralPath $PoolPath -PathType Leaf)) {
        return [ordered]@{ version = 2; keys = @(); next_key_index = 0; stats = [ordered]@{} }
    }
    try {
        $protected = [IO.File]::ReadAllBytes($PoolPath)
        $plain = [Security.Cryptography.ProtectedData]::Unprotect(
            $protected, $Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $raw = [Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
    } catch {
        throw "API Key Pool을 현재 Windows 계정으로 읽을 수 없습니다. Workbench 서버와 같은 계정에서 실행했는지 확인하세요. ($($_.Exception.Message))"
    }
    if ($null -eq $raw -or $null -eq $raw.keys) { throw 'API Key Pool 형식이 올바르지 않습니다.' }

    $keys = @(
        foreach ($item in @($raw.keys)) {
            $keyId = [string](Get-RequiredPropertyValue $item 'id' '')
            $keyLabel = [string](Get-RequiredPropertyValue $item 'label' '')
            $secret = [string](Get-RequiredPropertyValue $item 'secret' '')
            if ([string]::IsNullOrWhiteSpace($keyId) -or [string]::IsNullOrWhiteSpace($keyLabel) -or [string]::IsNullOrWhiteSpace($secret)) {
                throw 'API Key Pool에 유효하지 않은 항목이 있습니다.'
            }
            [ordered]@{ id = $keyId; label = $keyLabel; secret = $secret }
        }
    )
    $stats = [ordered]@{}
    $rawStats = Get-RequiredPropertyValue $raw 'stats' $null
    if ($null -ne $rawStats) {
        foreach ($property in $rawStats.PSObject.Properties) { $stats[$property.Name] = $property.Value }
    }
    $nextIndex = 0
    try { $nextIndex = [Math]::Max(0, [int](Get-RequiredPropertyValue $raw 'next_key_index' 0)) } catch { }
    return [ordered]@{ version = 2; keys = $keys; next_key_index = $nextIndex; stats = $stats }
}

function Save-KeyPool([System.Collections.IDictionary]$Pool) {
    if ($Pool.keys.Count -gt $MaxKeys) { throw "API Key는 최대 $MaxKeys개까지 등록할 수 있습니다." }
    $Pool.next_key_index = if ($Pool.keys.Count) { [int]$Pool.next_key_index % $Pool.keys.Count } else { 0 }
    $json = $Pool | ConvertTo-Json -Depth 8 -Compress
    $protected = [Security.Cryptography.ProtectedData]::Protect(
        [Text.Encoding]::UTF8.GetBytes($json), $Entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    $directory = Split-Path -Parent $PoolPath
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = "$PoolPath.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllBytes($temporary, $protected)
        Move-Item -LiteralPath $temporary -Destination $PoolPath -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Show-KeyPool([System.Collections.IDictionary]$Pool) {
    $rows = foreach ($item in $Pool.keys) {
        $stat = $Pool.stats[[string]$item.id]
        [pscustomobject]@{
            Id = $item.id
            Label = $item.label
            SelectionCount = if ($null -ne $stat -and $null -ne $stat.selection_count) { [int]$stat.selection_count } else { 0 }
            LastSelectedAt = if ($null -ne $stat -and $null -ne $stat.last_selected_at) { [string]$stat.last_selected_at } else { '' }
        }
    }
    Write-Host "API Key Pool: $PoolPath"
    if (@($rows).Count -eq 0) { Write-Host '등록된 API Key가 없습니다.'; return }
    $rows | Format-Table -AutoSize
}

if (-not ('Security.Cryptography.ProtectedData' -as [type])) {
    throw 'Windows DPAPI를 사용할 수 없습니다. 이 스크립트는 Windows PowerShell 또는 PowerShell on Windows에서만 실행할 수 있습니다.'
}

$pool = Read-KeyPool
switch ($Action) {
    'List' { Show-KeyPool $pool }
    'Add' {
        if ([string]::IsNullOrWhiteSpace($Label) -or $Label.Trim().Length -gt 100) { throw '1~100자 Key 이름을 -Label로 지정하세요.' }
        if ($pool.keys.Count -ge $MaxKeys) { throw "API Key는 최대 $MaxKeys개까지 등록할 수 있습니다." }
        $secureKey = Read-Host -Prompt "API Key for '$($Label.Trim())'" -AsSecureString
        $plainKey = [Net.NetworkCredential]::new('', $secureKey).Password.Trim()
        if ([string]::IsNullOrWhiteSpace($plainKey) -or $plainKey.Length -gt $MaxApiKeyChars) { throw '유효한 API Key를 입력하세요.' }
        $pool.keys += [ordered]@{ id = [guid]::NewGuid().ToString('N'); label = $Label.Trim(); secret = $plainKey }
        Save-KeyPool $pool
        Write-Host "API Key '$($Label.Trim())'를 등록했습니다. 실제 Key 값은 표시되지 않습니다."
        Show-KeyPool $pool
    }
    'Remove' {
        if ([string]::IsNullOrWhiteSpace($Id)) { throw '삭제할 Key의 Id를 -Id로 지정하세요. 먼저 -Action List로 확인할 수 있습니다.' }
        $remaining = @($pool.keys | Where-Object { [string]$_.id -ne $Id.Trim() })
        if ($remaining.Count -eq $pool.keys.Count) { throw "Id '$Id'에 해당하는 API Key가 없습니다." }
        $pool.keys = $remaining
        $pool.stats.Remove($Id.Trim())
        Save-KeyPool $pool
        Write-Host "API Key '$Id'를 삭제했습니다."
        Show-KeyPool $pool
    }
}
