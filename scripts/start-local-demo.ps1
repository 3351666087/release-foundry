param(
  [ValidateRange(1, 65535)]
  [int]$Port = 4174,
  [ValidatePattern("^[a-zA-Z0-9._-]+$")]
  [string]$Source = "a3-golden-path",
  [switch]$NoBrowser,
  [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$healthUrl = "http://127.0.0.1:$Port/__health"
$demoUrl = "http://127.0.0.1:$Port/apps/webapp/out/login/"
$runtimeDir = Join-Path $repoRoot ".local-runtime"
$pidFile = Join-Path $runtimeDir "a3-demo-$Port.pid"
$stdoutLog = Join-Path $runtimeDir "a3-demo-$Port.stdout.log"
$stderrLog = Join-Path $runtimeDir "a3-demo-$Port.stderr.log"

function Test-DemoServer {
  try {
    $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 1
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Test-WebBuildCurrent {
  $outputFile = Join-Path $repoRoot "apps/webapp/out/login/index.html"
  if (-not (Test-Path $outputFile)) {
    return $false
  }
  $sourceRoots = @(
    (Join-Path $repoRoot "apps/webapp/app"),
    (Join-Path $repoRoot "apps/webapp/components"),
    (Join-Path $repoRoot "apps/webapp/lib"),
    (Join-Path $repoRoot "apps/webapp/public")
  )
  $sourceFiles = foreach ($sourceRoot in $sourceRoots) {
    if (Test-Path $sourceRoot) {
      Get-ChildItem -LiteralPath $sourceRoot -Recurse -File
    }
  }
  $sourceFiles += Get-Item (Join-Path $repoRoot "apps/webapp/package.json")
  $sourceFiles += Get-Item (Join-Path $repoRoot "apps/webapp/next.config.mjs")
  $latestSource = $sourceFiles | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
  return (Get-Item $outputFile).LastWriteTimeUtc -ge $latestSource.LastWriteTimeUtc
}

if (-not (Test-Path $runtimeDir)) {
  New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

if ($Rebuild -or -not (Test-WebBuildCurrent)) {
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npm) {
    throw "Node.js/npm was not found. Install Node.js 24 first."
  }
  Write-Host "[1/3] Building the latest web application..." -ForegroundColor Cyan
  Push-Location $repoRoot
  try {
    & $npm.Source run build --prefix apps/webapp
    if ($LASTEXITCODE -ne 0) {
      throw "The web application build failed with exit code $LASTEXITCODE."
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "[1/3] The web build is current." -ForegroundColor DarkGray
}

if (-not (Test-DemoServer)) {
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($listener) {
    throw "Port $Port is already used. Close that program or choose another port with -Port."
  }

  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    throw "Node.js was not found. Install Node.js 24 first."
  }

  Write-Host "[2/3] Starting the local web server on port $Port..." -ForegroundColor Cyan
  $process = Start-Process `
    -FilePath $node.Source `
    -ArgumentList @("tests/e2e/static-dashboard-server.mjs", "--port", "$Port") `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru
  Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII

  $deadline = (Get-Date).AddSeconds(15)
  while ((Get-Date) -lt $deadline -and -not (Test-DemoServer)) {
    Start-Sleep -Milliseconds 300
  }

  if (-not (Test-DemoServer)) {
    throw "The local web server did not start within 15 seconds. Error log: $stderrLog"
  }
} else {
  Write-Host "[2/3] The local web server is already running." -ForegroundColor DarkGray
}

Write-Host "[3/3] ReleaseFoundry local demo is ready: $demoUrl" -ForegroundColor Green
Write-Host "A reboot stops this local process. Double-click the desktop shortcut to restore it." -ForegroundColor Yellow
Write-Host "This HTTP entry is a read-only demo. Real email auth also needs same-origin HTTPS, A1 API, PostgreSQL, and SMTP." -ForegroundColor Yellow
if (-not $NoBrowser) {
  Start-Process $demoUrl
}
