$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExecutable = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$UserOpenAIKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")

if (-not [string]::IsNullOrWhiteSpace($UserOpenAIKey)) {
    $env:OPENAI_API_KEY = $UserOpenAIKey
}

if (-not (Test-Path -LiteralPath $PythonExecutable)) {
    Write-Host "Sanal ortam bulunamadı. Önce README kurulum adımlarını çalıştırın." -ForegroundColor Yellow
    exit 1
}

if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    Write-Host "OPENAI_API_KEY kullanıcı ortam değişkeninde bulunamadı." -ForegroundColor Yellow
}

& $PythonExecutable (Join-Path $ProjectRoot "run.py")
