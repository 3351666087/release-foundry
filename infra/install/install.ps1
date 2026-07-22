param(
    [ValidateSet("Check", "Up")]
    [string]$Mode = "Up",
    [string]$EnvFile = $env:ASHR_ENV_FILE,
    [string]$ComposeFile = $env:ASHR_COMPOSE_FILE
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ComposeFile) {
    $ComposeFile = Join-Path $ScriptRoot "..\docker\docker-compose.self-host.yml"
}
if (-not $EnvFile) {
    $EnvFile = Join-Path $ScriptRoot "..\docker\.env.self-host"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop with Compose v2 is required."
}
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "Compose file not found: $ComposeFile"
}
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Private environment file not found. Start from infra/docker/self-host.env.example and do not commit it."
}

$required = @(
    "ASHR_POSTGRES_AUTH_SECRET",
    "ASHR_POSTGRES_RUNTIME_SECRET",
    "ASHR_OBJECT_STORE_ACCESS_KEY",
    "ASHR_OBJECT_STORE_SECRET_KEY",
    "ASHR_IDENTITY_SESSION_HMAC_KEY",
    "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY"
)
$configured = @{}
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.+)$') {
        $configured[$Matches[1]] = $Matches[2].Trim()
    }
}
foreach ($name in $required) {
    $fileValue = if ($configured.ContainsKey($name)) { $configured[$name] } else { $null }
    $processValue = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($fileValue) -and [string]::IsNullOrWhiteSpace($processValue)) {
        throw "Required variable is missing or empty: $name"
    }
}

$baseArgs = @(
    "compose", "--env-file", $EnvFile,
    "-f", $ComposeFile,
    "--profile", "commercial"
)
& docker @baseArgs "config" "--quiet"
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose validation failed."
}
if ($Mode -eq "Check") {
    exit 0
}

& docker @baseArgs "up" "-d" "--build"
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose startup failed."
}
Write-Host "Ashr self-host services were submitted. Verify health before accepting traffic."
