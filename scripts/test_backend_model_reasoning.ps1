[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:5000',
    [string[]]$Backend = @('claude', 'opencode'),
    [string[]]$Model = @(),
    [string[]]$Reasoning = @(),
    [switch]$All,
    [switch]$ListOnly,
    [ValidateSet('stream', 'sync')][string]$Mode = 'stream',
    [ValidateSet('off', 'failed', 'all')][string]$Direct = 'off',
    [int]$TimeoutSeconds = 90,
    [string]$OutputDirectory = '',
    [string]$Python = '',
    [string]$RestoreSettings = '',
    [switch]$ContextChecks,
    [switch]$WorktreeCheck,
    [switch]$QueueCheck,
    [string]$ExpectedWorkspace = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    foreach ($candidate in @('python3', 'python', 'py')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { $Python = $found.Source; break }
    }
}
if (-not $Python) { throw 'Python 3.9+ executable not found. Use -Python.' }
$cliArgs = @((Join-Path $PSScriptRoot 'test_backend_model_reasoning.py'), '--base-url', $BaseUrl,
    '--mode', $Mode, '--direct', $Direct, '--timeout', "$TimeoutSeconds")
foreach ($value in $Backend) { $cliArgs += @('--backend', $value) }
foreach ($value in $Model) { $cliArgs += @('--model', $value) }
foreach ($value in $Reasoning) { $cliArgs += @('--reasoning', $value) }
if ($All) { $cliArgs += '--all' }
if ($ListOnly) { $cliArgs += '--list-only' }
if ($ContextChecks) { $cliArgs += '--context-checks' }
if ($WorktreeCheck) { $cliArgs += '--worktree-check' }
if ($QueueCheck) { $cliArgs += '--queue-check' }
if ($ExpectedWorkspace) { $cliArgs += @('--expected-workspace', $ExpectedWorkspace) }
if ($OutputDirectory) { $cliArgs += @('--output-directory', $OutputDirectory) }
if ($RestoreSettings) { $cliArgs += @('--restore-settings', $RestoreSettings) }
& $Python @cliArgs
exit $LASTEXITCODE
