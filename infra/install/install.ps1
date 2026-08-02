param(
    [ValidateSet("Check", "Up")]
    [string]$Mode = "Up",
    [string]$EnvFile = $env:RELEASEFOUNDRY_ENV_FILE,
    [string]$ComposeFile = $env:RELEASEFOUNDRY_COMPOSE_FILE
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
    "RELEASEFOUNDRY_POSTGRES_AUTH_SECRET",
    "RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY",
    "RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY"
)
$configured = @{}
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.+)$') {
        $configured[$Matches[1]] = $true
    }
}
foreach ($name in $required) {
    if (-not $configured.ContainsKey($name)) {
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
Write-Host "ReleaseFoundry self-host services were submitted. Verify health before accepting traffic."
