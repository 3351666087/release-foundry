param(
  [ValidateRange(1, 65535)]
  [int]$Port = 4174,
  [ValidatePattern("^[a-zA-Z0-9._-]+$")]
  [string]$Source = "a3-golden-path",
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$healthUrl = "http://127.0.0.1:$Port/__health"
$demoUrl = "http://127.0.0.1:$Port/apps/webapp/out/overview/?source=$([uri]::EscapeDataString($Source))"

function Test-DemoServer {
  try {
    $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 1
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

if (-not (Test-DemoServer)) {
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($listener) {
    throw "Port $Port is already used by another program. Close it or choose another port."
  }

  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    throw "Node.js was not found. Install Node.js before starting the Ashr demo."
  }

  $overviewFile = Join-Path $repoRoot "apps/webapp/out/overview/index.html"
  if (-not (Test-Path $overviewFile)) {
    Write-Host "Building the local web application..."
    Push-Location $repoRoot
    try {
      & npm run build --prefix apps/webapp
      if ($LASTEXITCODE -ne 0) {
        throw "The web application build failed with exit code $LASTEXITCODE."
      }
    } finally {
      Pop-Location
    }
  }

  Write-Host "Starting the Ashr local demo on port $Port..."
  Start-Process `
    -FilePath $node.Source `
    -ArgumentList @("tests/e2e/static-dashboard-server.mjs", "--port", "$Port") `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden

  $deadline = (Get-Date).AddSeconds(15)
  while ((Get-Date) -lt $deadline -and -not (Test-DemoServer)) {
    Start-Sleep -Milliseconds 300
  }

  if (-not (Test-DemoServer)) {
    throw "The Ashr local demo did not become ready within 15 seconds."
  }
}

Write-Host "Ashr local demo is ready: $demoUrl"
if (-not $NoBrowser) {
  Start-Process $demoUrl
}
