param(
    [Parameter(Mandatory = $true)]
    [string]$Root
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = (Resolve-Path -LiteralPath $Root).Path
$runtimeDir = Join-Path $Root "runtime"
$pythonExe = Join-Path $runtimeDir "python.exe"
$readyFile = Join-Path $runtimeDir "portable-ready.txt"

if ($env:OS -ne "Windows_NT" -or -not [Environment]::Is64BitOperatingSystem) {
    throw "The bundled runtime setup requires 64-bit Windows."
}
if ((Test-Path $pythonExe) -and (Test-Path $readyFile)) {
    exit 0
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("ut-review-setup-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$setupSucceeded = $false

function Get-PyPiWheel {
    param(
        [string]$Project,
        [string]$Version,
        [string]$Filename,
        [string]$Destination
    )

    $metadata = Invoke-RestMethod -Uri "https://pypi.org/pypi/$Project/$Version/json"
    $wheel = $metadata.urls | Where-Object { $_.filename -eq $Filename } | Select-Object -First 1
    if (-not $wheel) {
        throw "PyPI did not provide the expected wheel $Filename."
    }

    Invoke-WebRequest -Uri $wheel.url -OutFile $Destination
    $actualHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $wheel.digests.sha256.ToLowerInvariant()) {
        throw "SHA-256 verification failed for $Filename."
    }
}

try {
    # Rebuild an incomplete runtime from scratch; the app folder itself is left intact.
    if (Test-Path $runtimeDir) {
        Remove-Item -LiteralPath $runtimeDir -Recurse -Force
    }

    $runtimeZip = Join-Path $tempRoot "python-3.14.10-embed-amd64.zip"
    Invoke-WebRequest `
        -Uri "https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip" `
        -OutFile $runtimeZip
    $runtimeHash = (Get-FileHash -LiteralPath $runtimeZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($runtimeHash -ne "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159") {
        throw "SHA-256 verification failed for the embedded Python runtime."
    }
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    Expand-Archive -LiteralPath $runtimeZip -DestinationPath $runtimeDir

    $wheelDir = Join-Path $tempRoot "wheels"
    $sitePackages = Join-Path $runtimeDir "Lib\site-packages"
    New-Item -ItemType Directory -Path $wheelDir, $sitePackages -Force | Out-Null
    $openpyxlWheel = Join-Path $wheelDir "openpyxl-3.1.5-py2.py3-none-any.whl"
    $etXmlfileWheel = Join-Path $wheelDir "et_xmlfile-2.0.0-py3-none-any.whl"
    Get-PyPiWheel -Project "openpyxl" -Version "3.1.5" `
        -Filename "openpyxl-3.1.5-py2.py3-none-any.whl" -Destination $openpyxlWheel
    Get-PyPiWheel -Project "et-xmlfile" -Version "2.0.0" `
        -Filename "et_xmlfile-2.0.0-py3-none-any.whl" -Destination $etXmlfileWheel

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($openpyxlWheel, $sitePackages)
    [IO.Compression.ZipFile]::ExtractToDirectory($etXmlfileWheel, $sitePackages)

    $pthFile = Join-Path $runtimeDir "python314._pth"
    if (-not (Test-Path $pthFile)) {
        throw "The downloaded embedded runtime is missing python314._pth."
    }
    @("python314.zip", ".", "Lib\site-packages", "..\src") |
        Set-Content -LiteralPath $pthFile -Encoding Ascii

    & $pythonExe -c "import evaluator, openpyxl, et_xmlfile; print('Portable runtime ready')"
    if ($LASTEXITCODE -ne 0) {
        throw "The bundled runtime could not import the app and its workbook libraries."
    }

    @(
        "CPython 3.14.10 embedded runtime",
        "openpyxl 3.1.5",
        "et-xmlfile 2.0.0"
    ) | Set-Content -LiteralPath $readyFile -Encoding Ascii
    $setupSucceeded = $true
}
catch {
    [Console]::Error.WriteLine("Portable setup failed: " + $_.Exception.Message)
    exit 1
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
    if (-not $setupSucceeded -and (Test-Path $runtimeDir)) {
        Remove-Item -LiteralPath $runtimeDir -Recurse -Force
    }
}
