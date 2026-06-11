param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    throw "CSV file not found: $InputPath"
}

$rows = @(Import-Csv -LiteralPath $InputPath -Encoding UTF8)
if ($rows.Count -eq 0) {
    throw "CSV has no data rows: $InputPath"
}

$originalHeaders = @($rows[0].PSObject.Properties.Name)
$upperHeaders = @($originalHeaders | ForEach-Object { $_.ToUpperInvariant() })
$duplicates = @(
    $upperHeaders |
        Group-Object |
        Where-Object { $_.Count -gt 1 } |
        ForEach-Object { $_.Name }
)
if ($duplicates.Count -gt 0) {
    throw "Uppercasing creates duplicate headers: $($duplicates -join ', ')"
}

$normalizedRows = foreach ($row in $rows) {
    $normalized = [ordered]@{}
    for ($index = 0; $index -lt $originalHeaders.Count; $index++) {
        $normalized[$upperHeaders[$index]] = $row.($originalHeaders[$index])
    }
    [pscustomobject]$normalized
}

$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory) {
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
}

$normalizedRows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding UTF8
Write-Host "Prepared CSV: $OutputPath"
