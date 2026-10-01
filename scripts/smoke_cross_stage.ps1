[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Proposal,
    [Parameter(Mandatory = $true)]
    [string]$Final,
    [string]$Midterm,
    [string]$Output = 'competition\cross-stage-evidence.local.json',
    [int]$CrossStagePort = 9023
)

$ErrorActionPreference = 'Stop'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$ProposalPath = (Resolve-Path -LiteralPath $Proposal).Path
$FinalPath = (Resolve-Path -LiteralPath $Final).Path
$OutputPath = Join-Path $ProjectDir $Output
$Arguments = @(
    '-m', 'competition.aip_leader',
    '--proposal', $ProposalPath,
    '--final', $FinalPath,
    '--cross-stage-url', "http://127.0.0.1:$CrossStagePort/rpc",
    '--output', $OutputPath
)
if ($Midterm) {
    $MidtermPath = (Resolve-Path -LiteralPath $Midterm).Path
    $Arguments += @('--midterm', $MidtermPath)
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "跨阶段 AIP 冒烟测试失败，退出码：$LASTEXITCODE"
}

$evidence = Get-Content -Raw -LiteralPath $OutputPath | ConvertFrom-Json
$partner = $evidence.partners[0]
if ($partner.state -ne 'completed' -or $partner.result.agent -ne 'cross_stage') {
    throw '跨阶段 AIP 冒烟测试未得到 completed 结果。'
}
Write-Host "跨阶段 AIP 冒烟测试通过，漂移风险：$($partner.result.report.riskLevel)，证据：$OutputPath"
