[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AllowedRoot,
    [string]$ProtectedPathsBase64 = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

$AllowedRootFull = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$AllowedRootPrefix = $AllowedRootFull + [IO.Path]::DirectorySeparatorChar
$MaxReadBytes = 2MB
$MaxWriteChars = 5MB
$MaxCommandOutputChars = 1MB
$MaxSearchResults = 100
$ProtectedPaths = @()

if (-not [string]::IsNullOrWhiteSpace($ProtectedPathsBase64)) {
    try {
        $ProtectedJson = $Utf8NoBom.GetString(
            [Convert]::FromBase64String($ProtectedPathsBase64)
        )
        $ProtectedPaths = @(
            $ProtectedJson |
                ConvertFrom-Json -ErrorAction Stop |
                ForEach-Object { [IO.Path]::GetFullPath([string]$_) }
        )
    }
    catch {
        throw "Protected path configuration is invalid."
    }
}

function Get-PropertyValue($Object, [string]$Name) {
    if ($null -eq $Object) {
        return $null
    }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $null
    }
    return $Property.Value
}

function Write-JsonRpc($Message) {
    $Json = $Message | ConvertTo-Json -Depth 30 -Compress
    [Console]::Out.WriteLine($Json)
    [Console]::Out.Flush()
}

function New-TextToolResult([string]$Text, [bool]$IsError = $false) {
    return @{
        content = @(
            @{
                type = "text"
                text = $Text
            }
        )
        isError = $IsError
    }
}

function Test-IsWithinPath([string]$Parent, [string]$Child) {
    $ParentFull = [IO.Path]::GetFullPath($Parent).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $ChildFull = [IO.Path]::GetFullPath($Child)
    if ($ChildFull.Equals(
        $ParentFull,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        return $true
    }
    return $ChildFull.StartsWith(
        $ParentFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Test-IsProtectedPath([string]$Path) {
    foreach ($ProtectedPath in $ProtectedPaths) {
        if (Test-IsWithinPath $ProtectedPath $Path) {
            return $true
        }
    }
    return $false
}

function Assert-NoReparsePoint([string]$Path) {
    $Current = $AllowedRootFull
    $Relative = $Path.Substring($AllowedRootFull.Length).TrimStart(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    foreach ($Part in @($Relative -split '[\\/]')) {
        if ([string]::IsNullOrWhiteSpace($Part)) {
            continue
        }
        $Current = Join-Path $Current $Part
        if (-not (Test-Path -LiteralPath $Current)) {
            break
        }
        $Item = Get-Item -LiteralPath $Current -Force
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Symbolic links and reparse points are not allowed: $Part"
        }
    }
}

function Resolve-WorkspacePath(
    [string]$RelativePath,
    [bool]$MustExist = $false,
    [bool]$AllowRoot = $false
) {
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        $RelativePath.IndexOf([char]0) -ge 0) {
        throw "path must be a non-empty relative path."
    }
    if ([IO.Path]::IsPathRooted($RelativePath)) {
        throw "Absolute paths are not allowed."
    }
    $Resolved = [IO.Path]::GetFullPath(
        (Join-Path $AllowedRootFull $RelativePath)
    )
    if (-not (Test-IsWithinPath $AllowedRootFull $Resolved)) {
        throw "Path is outside the allowed workspace."
    }
    if (-not $AllowRoot -and
        $Resolved.Equals(
            $AllowedRootFull,
            [StringComparison]::OrdinalIgnoreCase
        )) {
        throw "The workspace root cannot be used as a file target."
    }
    Assert-NoReparsePoint $Resolved
    if (Test-IsProtectedPath $Resolved) {
        throw "Path is protected by Workbench policy."
    }
    if ($MustExist -and -not (Test-Path -LiteralPath $Resolved)) {
        throw "Path does not exist: $RelativePath"
    }
    return $Resolved
}

function Get-RelativeWorkspacePath([string]$FullPath) {
    if ($FullPath.Equals(
        $AllowedRootFull,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        return "."
    }
    return $FullPath.Substring($AllowedRootPrefix.Length).Replace(
        [IO.Path]::DirectorySeparatorChar,
        [char]'/'
    )
}

function Read-RequiredString($Arguments, [string]$Name) {
    $Value = Get-PropertyValue $Arguments $Name
    if (-not ($Value -is [string]) -or
        [string]::IsNullOrWhiteSpace([string]$Value)) {
        throw "$Name must be a non-empty string."
    }
    return [string]$Value
}

function Invoke-ReadTextFile($Arguments) {
    $RelativePath = Read-RequiredString $Arguments "path"
    $Path = Resolve-WorkspacePath $RelativePath $true
    $Item = Get-Item -LiteralPath $Path
    if ($Item.PSIsContainer) {
        throw "path must refer to a file."
    }
    if ($Item.Length -gt $MaxReadBytes) {
        throw "File exceeds the 2 MiB read limit."
    }
    return [IO.File]::ReadAllText($Path, $Utf8NoBom)
}

function Invoke-WriteTextFile($Arguments) {
    $RelativePath = Read-RequiredString $Arguments "path"
    $ContentValue = Get-PropertyValue $Arguments "content"
    if (-not ($ContentValue -is [string])) {
        throw "content must be a string."
    }
    $Content = [string]$ContentValue
    if ($Content.Length -gt $MaxWriteChars) {
        throw "content exceeds the 5 MiB write limit."
    }
    $Path = Resolve-WorkspacePath $RelativePath
    $Parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    Assert-NoReparsePoint $Parent
    [IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
    return "Wrote $($Content.Length) characters to $RelativePath"
}

function Invoke-EditTextFile($Arguments) {
    $RelativePath = Read-RequiredString $Arguments "path"
    $OldText = Read-RequiredString $Arguments "old_text"
    $NewTextValue = Get-PropertyValue $Arguments "new_text"
    if (-not ($NewTextValue -is [string])) {
        throw "new_text must be a string."
    }
    $Path = Resolve-WorkspacePath $RelativePath $true
    $Item = Get-Item -LiteralPath $Path
    if ($Item.PSIsContainer -or $Item.Length -gt $MaxReadBytes) {
        throw "Editable file must be no larger than 2 MiB."
    }
    $Content = [IO.File]::ReadAllText($Path, $Utf8NoBom)
    $FirstIndex = $Content.IndexOf($OldText, [StringComparison]::Ordinal)
    if ($FirstIndex -lt 0) {
        throw "old_text was not found."
    }
    if ($Content.IndexOf(
        $OldText,
        $FirstIndex + $OldText.Length,
        [StringComparison]::Ordinal
    ) -ge 0) {
        throw "old_text must match exactly once."
    }
    $Updated = $Content.Substring(0, $FirstIndex) +
        [string]$NewTextValue +
        $Content.Substring($FirstIndex + $OldText.Length)
    if ($Updated.Length -gt $MaxWriteChars) {
        throw "edited content exceeds the 5 MiB write limit."
    }
    [IO.File]::WriteAllText($Path, $Updated, $Utf8NoBom)
    return "Edited $RelativePath"
}

function Invoke-ListDirectory($Arguments) {
    $RelativePathValue = Get-PropertyValue $Arguments "path"
    $RelativePath = if ([string]::IsNullOrWhiteSpace([string]$RelativePathValue)) {
        "."
    } else {
        [string]$RelativePathValue
    }
    $Path = Resolve-WorkspacePath $RelativePath $true $true
    $Item = Get-Item -LiteralPath $Path
    if (-not $Item.PSIsContainer) {
        throw "path must refer to a directory."
    }
    $Entries = @(
        Get-ChildItem -LiteralPath $Path -Force |
            Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name |
            Select-Object -First 500 |
            ForEach-Object {
                if (Test-IsProtectedPath $_.FullName) {
                    return
                }
                $Suffix = if ($_.PSIsContainer) { "/" } else { "" }
                "$(Get-RelativeWorkspacePath $_.FullName)$Suffix"
            }
    )
    return ($Entries -join [Environment]::NewLine)
}

function Invoke-SearchText($Arguments) {
    $Query = Read-RequiredString $Arguments "query"
    $RelativePathValue = Get-PropertyValue $Arguments "path"
    $RelativePath = if ([string]::IsNullOrWhiteSpace([string]$RelativePathValue)) {
        "."
    } else {
        [string]$RelativePathValue
    }
    $Path = Resolve-WorkspacePath $RelativePath $true $true
    $Files = if ((Get-Item -LiteralPath $Path).PSIsContainer) {
        Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        @(Get-Item -LiteralPath $Path)
    }
    $Results = New-Object Collections.Generic.List[string]
    foreach ($File in $Files) {
        if ((Test-IsProtectedPath $File.FullName) -or
            $File.Length -gt $MaxReadBytes) {
            continue
        }
        try {
            Assert-NoReparsePoint $File.FullName
            $LineNumber = 0
            foreach ($Line in [IO.File]::ReadLines($File.FullName, $Utf8NoBom)) {
                $LineNumber += 1
                if ($Line.IndexOf($Query, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $DisplayLine = if ($Line.Length -gt 500) {
                        $Line.Substring(0, 500) + "..."
                    } else {
                        $Line
                    }
                    $Results.Add(
                        "$(Get-RelativeWorkspacePath $File.FullName):$($LineNumber):$DisplayLine"
                    )
                    if ($Results.Count -ge $MaxSearchResults) {
                        return ($Results -join [Environment]::NewLine)
                    }
                }
            }
        }
        catch {
            continue
        }
    }
    return ($Results -join [Environment]::NewLine)
}

function Invoke-RunCommand($Arguments) {
    if ($ProtectedPaths.Count -gt 0) {
        throw (
            "run_command is disabled because this workspace contains " +
            "Workbench-protected paths."
        )
    }
    $Command = Read-RequiredString $Arguments "command"
    if ($Command.Length -gt 8192 -or $Command.IndexOf([char]0) -ge 0) {
        throw "command exceeds the 8 KiB limit or contains invalid data."
    }
    $TimeoutValue = Get-PropertyValue $Arguments "timeout_seconds"
    $TimeoutSeconds = 120
    if ($null -ne $TimeoutValue) {
        $TimeoutSeconds = [Math]::Max(1, [Math]::Min(300, [int]$TimeoutValue))
    }

    $PowerShellPath = Join-Path $PSHOME "powershell.exe"
    if (-not (Test-Path -LiteralPath $PowerShellPath)) {
        $PowerShellPath = Join-Path $PSHOME "pwsh.exe"
    }
    if (-not (Test-Path -LiteralPath $PowerShellPath)) {
        throw "Unable to locate the PowerShell executable."
    }

    $EncodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($Command)
    )
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $PowerShellPath
    $StartInfo.Arguments = (
        "-NoLogo -NoProfile -NonInteractive -EncodedCommand $EncodedCommand"
    )
    $StartInfo.WorkingDirectory = $AllowedRootFull
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.StandardOutputEncoding = $Utf8NoBom
    $StartInfo.StandardErrorEncoding = $Utf8NoBom

    $Process = New-Object Diagnostics.Process
    $Process.StartInfo = $StartInfo
    if (-not $Process.Start()) {
        throw "Failed to start command."
    }
    $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
    $StderrTask = $Process.StandardError.ReadToEndAsync()
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $Process.Kill()
        }
        catch {
        }
        throw "Command timed out after $TimeoutSeconds seconds."
    }
    $Stdout = $StdoutTask.Result
    $Stderr = $StderrTask.Result
    $ExitCode = $Process.ExitCode
    $Process.Dispose()
    $Combined = @(
        "exit_code=$ExitCode"
        if (-not [string]::IsNullOrEmpty($Stdout)) { $Stdout.TrimEnd() }
        if (-not [string]::IsNullOrEmpty($Stderr)) { "[stderr]`n$($Stderr.TrimEnd())" }
    ) -join [Environment]::NewLine
    if ($Combined.Length -gt $MaxCommandOutputChars) {
        $Combined = $Combined.Substring(0, $MaxCommandOutputChars) +
            "`n[output truncated at 1 MiB]"
    }
    return $Combined
}

function Get-ToolDefinitions {
    $PathProperty = @{
        path = @{
            type = "string"
            description = "Path relative to the Workbench execution directory."
        }
    }
    return @(
        @{
            name = "read_text_file"
            description = "Read a UTF-8 text file inside the Workbench execution directory."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = $PathProperty; required = @("path")
            }
        },
        @{
            name = "write_text_file"
            description = "Create or replace a UTF-8 text file inside the Workbench execution directory."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = @{
                    path = $PathProperty.path
                    content = @{ type = "string" }
                }
                required = @("path", "content")
            }
        },
        @{
            name = "edit_text_file"
            description = "Replace one exact text occurrence in a UTF-8 workspace file."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = @{
                    path = $PathProperty.path
                    old_text = @{ type = "string"; minLength = 1 }
                    new_text = @{ type = "string" }
                }
                required = @("path", "old_text", "new_text")
            }
        },
        @{
            name = "list_directory"
            description = "List one directory inside the Workbench execution directory."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = $PathProperty
            }
        },
        @{
            name = "search_text"
            description = "Search UTF-8 workspace files for a literal text query."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = @{
                    path = $PathProperty.path
                    query = @{ type = "string"; minLength = 1 }
                }
                required = @("query")
            }
        },
        @{
            name = "run_command"
            description = "Run a PowerShell command from the Workbench execution directory."
            inputSchema = @{
                type = "object"; additionalProperties = $false
                properties = @{
                    command = @{ type = "string"; minLength = 1 }
                    timeout_seconds = @{
                        type = "integer"; minimum = 1; maximum = 300
                    }
                }
                required = @("command")
            }
        }
    )
}

New-Item -ItemType Directory -Path $AllowedRootFull -Force | Out-Null

while ($null -ne ($Line = [Console]::In.ReadLine())) {
    if ([string]::IsNullOrWhiteSpace($Line)) {
        continue
    }
    $Request = $null
    try {
        $Request = $Line | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-JsonRpc @{
            jsonrpc = "2.0"; id = $null
            error = @{ code = -32700; message = "Parse error" }
        }
        continue
    }

    $Id = Get-PropertyValue $Request "id"
    $Method = [string](Get-PropertyValue $Request "method")
    try {
        switch ($Method) {
            "initialize" {
                $Params = Get-PropertyValue $Request "params"
                $ProtocolVersion = [string](
                    Get-PropertyValue $Params "protocolVersion"
                )
                if ([string]::IsNullOrWhiteSpace($ProtocolVersion)) {
                    $ProtocolVersion = "2024-11-05"
                }
                Write-JsonRpc @{
                    jsonrpc = "2.0"; id = $Id
                    result = @{
                        protocolVersion = $ProtocolVersion
                        capabilities = @{ tools = @{} }
                        serverInfo = @{
                            name = "claude-structured-workspace"
                            version = "1.0.0"
                        }
                    }
                }
            }
            "notifications/initialized" {
            }
            "ping" {
                Write-JsonRpc @{ jsonrpc = "2.0"; id = $Id; result = @{} }
            }
            "tools/list" {
                Write-JsonRpc @{
                    jsonrpc = "2.0"; id = $Id
                    result = @{ tools = @(Get-ToolDefinitions) }
                }
            }
            "tools/call" {
                $Params = Get-PropertyValue $Request "params"
                $ToolName = [string](Get-PropertyValue $Params "name")
                $Arguments = Get-PropertyValue $Params "arguments"
                $Text = switch ($ToolName) {
                    "read_text_file" { Invoke-ReadTextFile $Arguments; break }
                    "write_text_file" { Invoke-WriteTextFile $Arguments; break }
                    "edit_text_file" { Invoke-EditTextFile $Arguments; break }
                    "list_directory" { Invoke-ListDirectory $Arguments; break }
                    "search_text" { Invoke-SearchText $Arguments; break }
                    "run_command" { Invoke-RunCommand $Arguments; break }
                    default { throw "Unknown tool: $ToolName" }
                }
                Write-JsonRpc @{
                    jsonrpc = "2.0"; id = $Id
                    result = (New-TextToolResult ([string]$Text))
                }
            }
            default {
                if ($null -ne $Id) {
                    Write-JsonRpc @{
                        jsonrpc = "2.0"; id = $Id
                        error = @{
                            code = -32601
                            message = "Method not found: $Method"
                        }
                    }
                }
            }
        }
    }
    catch {
        if ($Method -eq "tools/call") {
            Write-JsonRpc @{
                jsonrpc = "2.0"; id = $Id
                result = (New-TextToolResult $_.Exception.Message $true)
            }
        }
        elseif ($null -ne $Id) {
            Write-JsonRpc @{
                jsonrpc = "2.0"; id = $Id
                error = @{ code = -32603; message = $_.Exception.Message }
            }
        }
    }
}
