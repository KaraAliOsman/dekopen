# Start DEKOPEN local stack services
$ErrorActionPreference = "Continue"
$root = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { (Get-Location).Path }
$logDir = Join-Path $root ".run"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Load .env into process env
Get-Content (Join-Path $root ".env") | ForEach-Object {
  if ($_ -match '^\s*([A-Z0-9_]+)=(.*)$') {
    Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
  }
}

Write-Host "DATABASE_URL=$env:DATABASE_URL"
Write-Host "SUPABASE_URL=$env:SUPABASE_URL"

# Storage bucket
docker exec supabase_db_dekopen psql -U postgres -d postgres -c "INSERT INTO storage.buckets (id, name, public) VALUES ('documents','documents', false) ON CONFLICT (id) DO NOTHING;"

$py = Join-Path $root ".venv\Scripts\python.exe"

# Django
Start-Process -FilePath $py `
  -ArgumentList @("backend\manage.py","runserver","127.0.0.1:8000","--noreload") `
  -WorkingDirectory $root `
  -RedirectStandardOutput "$logDir\django.out.log" `
  -RedirectStandardError "$logDir\django.err.log" `
  -WindowStyle Hidden
Write-Host "Django launched"

# Jobs worker
Start-Process -FilePath $py `
  -ArgumentList @("backend\manage.py","runjobs","--poll","1.5") `
  -WorkingDirectory $root `
  -RedirectStandardOutput "$logDir\jobs.out.log" `
  -RedirectStandardError "$logDir\jobs.err.log" `
  -WindowStyle Hidden
Write-Host "Jobs worker launched"

# Vite
Start-Process -FilePath "cmd.exe" `
  -ArgumentList @("/c","npm run dev > `"$logDir\vite.out.log`" 2> `"$logDir\vite.err.log`"") `
  -WorkingDirectory (Join-Path $root "frontend") `
  -WindowStyle Hidden
Write-Host "Vite launched"

Start-Sleep -Seconds 6
Write-Host "=== django err ==="
Get-Content "$logDir\django.err.log" -ErrorAction SilentlyContinue | Select-Object -Last 20
Write-Host "=== django out ==="
Get-Content "$logDir\django.out.log" -ErrorAction SilentlyContinue | Select-Object -Last 10
Write-Host "=== jobs ==="
Get-Content "$logDir\jobs.err.log" -ErrorAction SilentlyContinue | Select-Object -Last 10
Get-Content "$logDir\jobs.out.log" -ErrorAction SilentlyContinue | Select-Object -Last 10
Write-Host "=== vite ==="
Get-Content "$logDir\vite.out.log" -ErrorAction SilentlyContinue | Select-Object -Last 15
Get-Content "$logDir\vite.err.log" -ErrorAction SilentlyContinue | Select-Object -Last 10
