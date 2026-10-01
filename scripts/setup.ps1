[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv (Join-Path $ProjectDir '.venv')
}

& $Python -m pip install --disable-pip-version-check -r (Join-Path $ProjectDir 'requirements-aip.txt')
if ($LASTEXITCODE -ne 0) {
    throw "依赖安装失败，退出码：$LASTEXITCODE"
}

Write-Host '环境准备完成。'
