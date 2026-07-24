param(
  [switch]$NoBrowser,
  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $repoRoot ".local-runtime\local-auth"
$composeFile = Join-Path $repoRoot "infra\docker\docker-compose.local-auth.yml"
$envFile = Join-Path $runtimeDir "local-auth.env"
$loginUrl = "https://localhost:4443/apps/webapp/out/login/"
$mailUrl = "http://127.0.0.1:18025"

function New-LocalSecret {
  $bytes = New-Object byte[] 48
  $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $generator.GetBytes($bytes)
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
  } finally {
    $generator.Dispose()
    [Array]::Clear($bytes, 0, $bytes.Length)
  }
}

function Ensure-Docker {
  docker info *> $null
  if ($LASTEXITCODE -eq 0) { return }
  $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  if (-not (Test-Path -LiteralPath $dockerDesktop)) {
    throw "Docker Desktop is not installed at the expected location."
  }
  Start-Process -FilePath $dockerDesktop
  $deadline = (Get-Date).AddMinutes(2)
  do {
    Start-Sleep -Seconds 3
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { return }
  } while ((Get-Date) -lt $deadline)
  throw "Docker Desktop did not become ready within two minutes."
}

function Ensure-LocalSecrets {
  New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
  $postgresPasswordFile = Join-Path $runtimeDir "postgres-password"
  $runtimePasswordFile = Join-Path $runtimeDir "postgres-runtime-password"
  if (-not (Test-Path -LiteralPath $postgresPasswordFile)) {
    Set-Content -LiteralPath $postgresPasswordFile -Value (New-LocalSecret) -Encoding ASCII -NoNewline
  }
  if (-not (Test-Path -LiteralPath $runtimePasswordFile)) {
    Set-Content -LiteralPath $runtimePasswordFile -Value (New-LocalSecret) -Encoding ASCII -NoNewline
  }
  if (-not (Test-Path -LiteralPath $envFile)) {
    $values = @(
      "ASHR_POSTGRES_RUNTIME_SECRET=$(Get-Content -Raw -LiteralPath $runtimePasswordFile)",
      "ASHR_IDENTITY_SESSION_HMAC_KEY=$(New-LocalSecret)",
      "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY=$(New-LocalSecret)",
      "ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_KEY=$(New-LocalSecret)",
      "ASHR_IDENTITY_VERIFICATION_HMAC_KEY=$(New-LocalSecret)"
    )
    Set-Content -LiteralPath $envFile -Value $values -Encoding ASCII
  }
}

function Build-Webapp {
  if ($NoBuild) { return }
  Push-Location (Join-Path $repoRoot "apps\webapp")
  try {
    $env:NEXT_PUBLIC_A1_API_BASE_URL = "https://localhost:4443"
    $env:NEXT_PUBLIC_A1_PROJECT_ID = "33333333-3333-4333-8333-333333333333"
    $env:NEXT_PUBLIC_A1_TENANT_ID = "11111111-1111-4111-8111-111111111111"
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "The A3 webapp build failed." }
  } finally {
    Pop-Location
  }
}

function Trust-CaddyCertificate {
  $certificate = Join-Path $runtimeDir "caddy-data\caddy\pki\authorities\local\root.crt"
  $deadline = (Get-Date).AddSeconds(45)
  while (-not (Test-Path -LiteralPath $certificate) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 1
  }
  if (-not (Test-Path -LiteralPath $certificate)) {
    throw "The local HTTPS certificate was not generated."
  }
  & certutil.exe -user -addstore Root $certificate *> $null
  if ($LASTEXITCODE -ne 0) { throw "The local HTTPS certificate could not be trusted for this user." }
}

Ensure-Docker
Ensure-LocalSecrets
Build-Webapp

& docker compose --env-file $envFile -f $composeFile up -d --build
if ($LASTEXITCODE -ne 0) { throw "The Ashr local auth stack failed to start." }

Trust-CaddyCertificate

$deadline = (Get-Date).AddMinutes(2)
do {
  $status = & curl.exe --silent --insecure --output NUL --write-out "%{http_code}" "https://localhost:4443/__health"
  if ($status -eq "200") { break }
  Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if ($status -ne "200") { throw "The Ashr local auth HTTPS endpoint did not become healthy." }

Write-Host "Ashr real local login is ready: $loginUrl" -ForegroundColor Green
Write-Host "Local verification inbox: $mailUrl" -ForegroundColor Cyan
Write-Host "Accounts and sessions are persisted in local PostgreSQL." -ForegroundColor Green
if (-not $NoBrowser) {
  Start-Process $loginUrl
  Start-Process $mailUrl
}
