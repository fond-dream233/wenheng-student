[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Document,
    [string]$Output = 'competition\aip-evidence.local.json',
    [int]$FormatPort = 9021,
    [int]$LogicPort = 9022
)

$ErrorActionPreference = 'Stop'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$DocumentPath = (Resolve-Path -LiteralPath $Document).Path
$OutputPath = Join-Path $ProjectDir $Output

& $Python -m competition.aip_leader $DocumentPath `
    --format-url "http://127.0.0.1:$FormatPort/rpc" `
    --logic-url "http://127.0.0.1:$LogicPort/rpc" `
    --output $OutputPath
if ($LASTEXITCODE -ne 0) {
    throw "AIP 冒烟测试失败，退出码：$LASTEXITCODE"
}

$evidence = Get-Content -Raw -LiteralPath $OutputPath | ConvertFrom-Json
$states = @($evidence.partners | ForEach-Object { $_.state })
if ($states.Count -ne 2 -or @($states | Where-Object { $_ -ne 'completed' }).Count -gt 0) {
    throw 'AIP 冒烟测试未得到两个 completed 结果。'
}
Write-Host "AIP 冒烟测试通过，证据：$OutputPath"
