param([string]$Version = "v1.0.0", [switch]$SkipBuild, [string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if ($Version -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') { throw "Use a version such as v1.0.0." }
if (-not $SkipBuild) { & (Join-Path $PSScriptRoot "build.ps1") -Python $Python }
$exe = Join-Path $PSScriptRoot "dist\Sekiro Resource Modifier.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Build the executable first." }
$base = "Sekiro-Resource-Modifier-$Version-Windows-x64"
$release = Join-Path $PSScriptRoot "release"
$folder = Join-Path $release $base
if (Test-Path -LiteralPath $folder) { throw "Package directory already exists; use a new version or review it manually." }
New-Item -ItemType Directory -Path $folder -Force | Out-Null
Copy-Item -LiteralPath $exe -Destination $folder
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "使用说明.txt") -Destination $folder
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY_NOTICES.txt") -Destination $folder
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "third_party_licenses") -Destination $folder -Recurse
$lines = Get-ChildItem -LiteralPath $folder -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($folder.Length + 1).Replace('\', '/')
    "{0}  {1}" -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $relative
}
[IO.File]::WriteAllLines((Join-Path $folder "SHA256SUMS.txt"), [string[]]$lines, [Text.UTF8Encoding]::new($false))
$zip = Join-Path $release "$base.zip"
Compress-Archive -LiteralPath $folder -DestinationPath $zip
$zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $release "$base.sha256"), "$zipHash  $base.zip`n", [Text.UTF8Encoding]::new($false))
Write-Output "Packaged: $zip"
Write-Output "SHA256: $zipHash"
