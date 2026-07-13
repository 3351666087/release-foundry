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

Get-ChildItem -LiteralPath $resolvedSource -File -Recurse |
    ForEach-Object {
        [pscustomobject]@{
            operation = 'copy_dry_run'
            source = $_.FullName
            destination = Join-Path $Destination $_.Name
            size_bytes = $_.Length
            deletes_source = $false
        }
    } | ConvertTo-Json -Depth 4
