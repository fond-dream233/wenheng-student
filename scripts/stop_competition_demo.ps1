[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $ProjectDir 'competition\runtime'
$PidFile = Join-Path $RuntimeDir 'processes.json'

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host '未发现运行中的竞赛演示服务。'
    exit 0
}

$state = Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json
foreach ($processId in @($state.web, $state.format, $state.logic, $state.crossStage)) {
    if ($processId -is [int] -or $processId -is [long]) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}
Remove-Item -LiteralPath $PidFile -Force
Write-Host '竞赛演示服务已停止。'
