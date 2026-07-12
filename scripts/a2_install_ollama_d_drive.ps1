param(
    [Parameter(Mandatory = $true)][string]$ArchiveUrl,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$Sha256,
    [string]$InstallRoot = 'D:\Ashr\ollama',
    [string]$ModelRoot = 'D:\Ashr\ollama-models',
    [string]$DownloadPath = '',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$install = [System.IO.Path]::GetFullPath($InstallRoot)
$models = [System.IO.Path]::GetFullPath($ModelRoot)
if (-not $install.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase) -or
    -not $models.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Ollama executable and model roots must both remain on D:.'
}
$free = (Get-PSDrive -Name D).Free
if ($free -lt 20GB) {
    throw 'At least 20 GiB free on D: is required before runtime installation.'
}

$staging = 'D:\Ashr\downloads'
$download = if ($DownloadPath) {
    [System.IO.Path]::GetFullPath($DownloadPath)
} else {
    Join-Path $staging 'a2-ollama-download.zip'
}
if (-not $download.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Ollama archive staging must remain on D:.'
}
if ($DryRun) {
    Write-Output 'DRY_RUN=true'
    Write-Output "ARCHIVE_URL=$ArchiveUrl"
    Write-Output "ARCHIVE_SHA256=$($Sha256.ToLowerInvariant())"
    Write-Output "INSTALL_ROOT=$install"
    Write-Output "MODEL_ROOT=$models"
    Write-Output "DOWNLOAD_PATH=$download"
    exit 0
}
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($download)) | Out-Null
Invoke-WebRequest -Uri $ArchiveUrl -OutFile $download
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $download).Hash
if ($actual -ne $Sha256.ToUpperInvariant()) {
    Remove-Item -LiteralPath $download -Force
    throw 'Ollama archive checksum mismatch.'
}

New-Item -ItemType Directory -Force -Path $install, $models | Out-Null
Expand-Archive -LiteralPath $download -DestinationPath $install -Force
Remove-Item -LiteralPath $download -Force
$executable = Get-ChildItem -LiteralPath $install -Filter ollama.exe -Recurse | Select-Object -First 1
if (-not $executable) {
    throw 'Verified archive did not contain ollama.exe.'
}
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $models, 'User')
Write-Output "OLLAMA_EXECUTABLE=$($executable.FullName)"
Write-Output "OLLAMA_MODELS=$models"
