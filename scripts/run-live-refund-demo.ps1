param(
  [ValidateRange(1, 65535)]
  [int]$Port = 4175,
  [string]$Model = "qwen2.5:0.5b",
  [switch]$SkipModelPull,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $repoRoot "infra/docker/docker-compose.refund-agent-demo.yml"
$outputDir = Join-Path $repoRoot ".demo-output/live-refund"
$runPath = Join-Path $outputDir "a1_run_result.json"
$gradePath = Join-Path $outputDir "a2_grade_result.json"
$source = "live-refund-demo"
$baseUrl = "http://127.0.0.1:$Port"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-DockerCompose {
  param([Parameter(Mandatory = $true)][string[]]$Arguments)
  & docker compose -f $composeFile @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed with exit code $LASTEXITCODE."
  }
}

function Wait-Ollama {
  $deadline = (Get-Date).AddMinutes(3)
  while ((Get-Date) -lt $deadline) {
    & docker compose -f $composeFile exec -T ollama ollama list *> $null
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 2
  }
  throw "The Docker Ollama service did not become ready within three minutes."
}

Write-Host "[1/7] Checking Docker..."
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker Desktop is not ready. Open Docker Desktop and wait until the engine is running."
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$env:OLLAMA_MODEL = $Model

Write-Host "[2/7] Starting the local Ollama container..."
Invoke-DockerCompose -Arguments @("up", "-d", "ollama")
Wait-Ollama

if (-not $SkipModelPull) {
  Write-Host "[3/7] Pulling local model $Model (cached layers will be reused)..."
  Invoke-DockerCompose -Arguments @("exec", "-T", "ollama", "ollama", "pull", $Model)
} else {
  Write-Host "[3/7] Reusing the existing local model cache..."
}

Write-Host "[4/7] Running the real model Agent through A1 Runner and A2 Judge..."
Invoke-DockerCompose -Arguments @("run", "--rm", "-e", "OLLAMA_MODEL=$Model", "demo-runner")

Write-Host "[5/7] Exporting A3 JSON, Markdown, and CSV reports..."
& node (Join-Path $repoRoot "services/report/a3_demo_report_cli.mjs") `
  --runs $runPath `
  --grades $gradePath `
  --output-dir $outputDir
if ($LASTEXITCODE -ne 0) {
  throw "A3 report export failed with exit code $LASTEXITCODE."
}

Write-Host "[6/7] Starting the local product console and importing fresh evidence..."
& (Join-Path $repoRoot "scripts/start-local-demo.ps1") -Port $Port -Source $source -NoBrowser
$runResult = Get-Content $runPath -Raw -Encoding UTF8 | ConvertFrom-Json
$gradeResult = Get-Content $gradePath -Raw -Encoding UTF8 | ConvertFrom-Json
$runId = [string]$runResult.run_id
$headers = @{ "Idempotency-Key" = "live-refund-$runId"; "x-a3-role" = "admin" }
$runBody = @{ source = $source; source_label = "Docker Ollama live refund"; run_result = $runResult } | ConvertTo-Json -Depth 100
$gradeBody = @{ source = $source; source_label = "Docker Ollama live refund"; grade_result = $gradeResult } | ConvertTo-Json -Depth 100
Invoke-RestMethod -Method Post -Uri "$baseUrl/api/a3/import/a1-run-result" -Headers $headers -ContentType "application/json" -Body $utf8.GetBytes($runBody) | Out-Null
$headers["Idempotency-Key"] = "live-refund-grade-$runId"
Invoke-RestMethod -Method Post -Uri "$baseUrl/api/a3/import/a2-grade-result" -Headers $headers -ContentType "application/json" -Body $utf8.GetBytes($gradeBody) | Out-Null

$shareReceipt = $null
try {
  $shareReceipt = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/a3/reports/share?source=$source" `
    -Headers @{ "x-a3-role" = "reviewer" } `
    -ContentType "application/json" `
    -Body (@{ title = "Live refund Agent report" } | ConvertTo-Json)
  $shareReceipt | ConvertTo-Json -Depth 100 | Set-Content -Path (Join-Path $outputDir "a3_hosted_report_receipt.json") -Encoding UTF8
} catch {
  Write-Warning "The local file reports are ready, but hosted report creation was not accepted: $($_.Exception.Message)"
}

Write-Host "[7/7] Demo ready."
$dashboardUrl = "$baseUrl/apps/webapp/out/overview/?source=$source"
Write-Host "Dashboard: $dashboardUrl"
Write-Host "Artifacts: $outputDir"
if ($shareReceipt) {
  Write-Host "Hosted report: $baseUrl$($shareReceipt.share_url_path)"
}
if (-not $NoBrowser) {
  Start-Process $dashboardUrl
}
