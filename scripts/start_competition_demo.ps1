[CmdletBinding()]
param(
    [int]$WebPort = 5000,
    [int]$FormatPort = 9021,
    [int]$LogicPort = 9022,
    [int]$CrossStagePort = 9023
)

$ErrorActionPreference = 'Stop'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $ProjectDir 'competition\runtime'
$Python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$Waitress = Join-Path $ProjectDir '.venv\Scripts\waitress-serve.exe'
$PidFile = Join-Path $RuntimeDir 'processes.json'

if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $Waitress)) {
    throw '运行环境未准备，请先执行 scripts\setup.ps1。'
}
if (-not $env:DEFAULT_TEACHER_PASSWORD -or $env:DEFAULT_TEACHER_PASSWORD.Length -lt 12) {
    throw '请先设置至少 12 位的 DEFAULT_TEACHER_PASSWORD 环境变量。'
}
if (Test-Path -LiteralPath $PidFile) {
    $existing = Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json
    $alive = @($existing.web, $existing.format, $existing.logic, $existing.crossStage) |
        Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }
    if ($alive.Count -gt 0) {
        throw '检测到已有竞赛演示进程，请先执行 scripts\stop_competition_demo.ps1。'
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeDir 'logs') | Out-Null
$env:COMPETITION_MODE = 'true'
$env:PUBLIC_ORGANIZATION_NAME = '参赛作品'
$env:SYSTEM_NAME = '文衡·多智能体论文质检平台'
$env:APP_PORT = [string]$WebPort
$env:APP_SECRET_KEY = if ($env:APP_SECRET_KEY) { $env:APP_SECRET_KEY } else { [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N') }
$env:SESSION_COOKIE_SECURE = 'false'
$env:TRUSTED_HOSTS = "127.0.0.1:$WebPort,localhost:$WebPort,127.0.0.1,localhost"
$env:LOG_DIR = Join-Path $RuntimeDir 'logs'
$env:AIP_IDENTITY_BINDING_ENABLED = 'false'
$env:AIP_ALLOW_LOCAL_PATHS = 'false'

$web = Start-Process -FilePath $Waitress -ArgumentList '--host=127.0.0.1',"--port=$WebPort",'app:app' `
    -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RuntimeDir 'web.stdout.log') `
    -RedirectStandardError (Join-Path $RuntimeDir 'web.stderr.log')
$format = Start-Process -FilePath $Python -ArgumentList '-m','competition.aip_partner','--role','format','--port',([string]$FormatPort) `
    -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RuntimeDir 'format.stdout.log') `
    -RedirectStandardError (Join-Path $RuntimeDir 'format.stderr.log')
$logic = Start-Process -FilePath $Python -ArgumentList '-m','competition.aip_partner','--role','logic','--port',([string]$LogicPort) `
    -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RuntimeDir 'logic.stdout.log') `
    -RedirectStandardError (Join-Path $RuntimeDir 'logic.stderr.log')
$crossStage = Start-Process -FilePath $Python -ArgumentList '-m','competition.aip_partner','--role','cross-stage','--port',([string]$CrossStagePort) `
    -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $RuntimeDir 'cross-stage.stdout.log') `
    -RedirectStandardError (Join-Path $RuntimeDir 'cross-stage.stderr.log')

try {
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            Invoke-RestMethod "http://127.0.0.1:$WebPort/health" | Out-Null
            Invoke-RestMethod "http://127.0.0.1:$FormatPort/health" | Out-Null
            Invoke-RestMethod "http://127.0.0.1:$LogicPort/health" | Out-Null
            Invoke-RestMethod "http://127.0.0.1:$CrossStagePort/health" | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        throw '服务未在 20 秒内通过健康检查。'
    }
    [ordered]@{
        web = $web.Id
        format = $format.Id
        logic = $logic.Id
        crossStage = $crossStage.Id
        webUrl = "http://127.0.0.1:$WebPort"
        formatRpc = "http://127.0.0.1:$FormatPort/rpc"
        logicRpc = "http://127.0.0.1:$LogicPort/rpc"
        crossStageRpc = "http://127.0.0.1:$CrossStagePort/rpc"
        startedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding UTF8
    Write-Host "竞赛演示服务已启动：http://127.0.0.1:$WebPort"
} catch {
    Stop-Process -Id $web.Id,$format.Id,$logic.Id,$crossStage.Id -Force -ErrorAction SilentlyContinue
    throw
}
