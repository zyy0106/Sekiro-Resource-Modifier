param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if ($env:OS -ne "Windows_NT") { throw "Build on Windows x64." }
$buildPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12+ with Tkinter is required for building." }
}
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
& $buildPython -B -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
$catalog = Join-Path $PSScriptRoot "catalog_all.json"
& $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name "Sekiro Resource Modifier" --add-data "$catalog;." --distpath dist --workpath build --specpath build app\gui.py
if ($LASTEXITCODE -ne 0) { throw "Packaging failed." }
& $buildPython -B tools\verify_portable.py "dist\Sekiro Resource Modifier.exe"
if ($LASTEXITCODE -ne 0) { throw "Standalone executable smoke test failed." }
Write-Output "Built and verified: dist\Sekiro Resource Modifier.exe"
