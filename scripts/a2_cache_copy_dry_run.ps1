param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Destination = 'D:\Ashr\cache-copy'
)

$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
if (-not $resolvedSource.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Source must resolve under D:\.'
}
if (-not $Destination.StartsWith('D:\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must be under D:\.'
}

$plans = Get-ChildItem -LiteralPath $resolvedSource -File -Recurse | ForEach-Object {
        $sourcePrefix = $resolvedSource.TrimEnd('\') + '\'
        if (-not $_.FullName.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Enumerated file escaped the resolved source.'
        }
        $relative = $_.FullName.Substring($sourcePrefix.Length)
        [pscustomobject]@{
            operation = 'copy_dry_run'
            source = $_.FullName
            relative_path = $relative
            destination = Join-Path $Destination $relative
            size_bytes = $_.Length
            deletes_source = $false
        }
    }
$collisions = $plans | Group-Object destination | Where-Object Count -gt 1
if ($collisions) { throw 'Destination collision detected.' }
$plans | ConvertTo-Json -Depth 4
