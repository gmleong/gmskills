#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath
)

$ErrorActionPreference = 'Stop'
$resolvedScript = (Resolve-Path -LiteralPath $ScriptPath).Path
$running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match 'Illustrator'
}
if (-not $running) {
    throw 'ILLUSTRATOR_NOT_RUNNING|Open Illustrator and the target document first.'
}

try {
    $illustrator = [Runtime.InteropServices.Marshal]::GetActiveObject('Illustrator.Application')
}
catch {
    throw 'ILLUSTRATOR_NOT_CONNECTED|Illustrator is running but its automation object is unavailable.'
}

if ($illustrator.Documents.Count -lt 1) {
    throw 'ILLUSTRATOR_DOCUMENT_REQUIRED|Open the target document first.'
}

$result = $illustrator.DoJavaScriptFile($resolvedScript)
Write-Output $result
