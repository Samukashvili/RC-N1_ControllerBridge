param(
    [switch]$SkipDjiInstaller
)

$ErrorActionPreference = "Stop"
$SetupScript = Join-Path $PSScriptRoot "setup.ps1"
$DjiDownloadPage = "https://www.dji.com/downloads/softwares/dji-assistant-2-consumer-drones-series"
$FallbackDjiUrl = "https://dl.djicdn.com/downloads/dji_assistant/20260423/DJI Assistant 2(Consumer Drones Series) 2.1.40.exe"

Write-Host "Installing the bridge dependencies..." -ForegroundColor Cyan
try {
    & $SetupScript
}
catch {
    if ($_.Exception.Message -notmatch "Python 3\.10\+ with Tkinter was not found") {
        throw
    }
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Python 3.10+ with Tkinter is required, and Windows Package Manager (winget) is unavailable. Install Python from python.org, then run this file again."
    }
    Write-Host "Python is missing. Installing Python 3.12 for the current user..." -ForegroundColor Cyan
    & $Winget.Source install --id Python.Python.3.12 --exact --scope user --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Windows Package Manager could not install Python 3.12."
    }
    & $SetupScript
}

if ($SkipDjiInstaller) {
    Write-Host "DJI installer download skipped for validation."
    exit 0
}

function Get-DjiInstallerUrl {
    try {
        Write-Host "Checking DJI's official download page for the current Windows installer..."
        $Page = Invoke-WebRequest -Uri $DjiDownloadPage -UseBasicParsing
        $Pattern = 'https://dl\.djicdn\.com/downloads/dji_assistant/\d+/DJI[^"''<>\r\n]*Consumer[^"''<>\r\n]*\.exe'
        $Matches = [regex]::Matches($Page.Content, $Pattern)
        if ($Matches.Count -gt 0) {
            return [System.Net.WebUtility]::HtmlDecode($Matches[$Matches.Count - 1].Value)
        }
    }
    catch {
        Write-Warning "Could not resolve the latest DJI installer: $($_.Exception.Message)"
    }
    Write-Warning "Using the verified DJI Assistant 2 v2.1.40 fallback URL."
    return $FallbackDjiUrl
}

function Test-DjiSignature([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    return $Signature.Status -eq "Valid" -and
        $null -ne $Signature.SignerCertificate -and
        $Signature.SignerCertificate.Subject -match "DJI"
}

$InstallerUrl = Get-DjiInstallerUrl
$InstallerUri = [Uri]$InstallerUrl
if ($InstallerUri.Scheme -ne "https" -or $InstallerUri.Host -ne "dl.djicdn.com") {
    throw "DJI returned an unexpected installer location: $InstallerUrl"
}

$DownloadDirectory = Join-Path $env:TEMP "RCN1Bridge"
$InstallerPath = Join-Path $DownloadDirectory "DJI-Assistant-2-Consumer-Drones.exe"
$PartialPath = "$InstallerPath.download"
New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null

if (-not (Test-DjiSignature $InstallerPath)) {
    Write-Host "Downloading DJI Assistant 2 from dl.djicdn.com..." -ForegroundColor Cyan
    Remove-Item -LiteralPath $PartialPath -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $InstallerUri.AbsoluteUri -OutFile $PartialPath -UseBasicParsing
    Move-Item -LiteralPath $PartialPath -Destination $InstallerPath -Force
}

if (-not (Test-DjiSignature $InstallerPath)) {
    Remove-Item -LiteralPath $InstallerPath -Force -ErrorAction SilentlyContinue
    throw "The downloaded DJI installer does not have a valid DJI digital signature. It was not launched."
}

Write-Host ""
Write-Host "Launching DJI Assistant 2..." -ForegroundColor Yellow
Write-Host "Approve the Windows installer prompts and complete the installation manually."
Write-Host "Close DJI Assistant after installation so it does not hold the controller's COM port."
Start-Process -FilePath $InstallerPath -Wait

Write-Host ""
Write-Host "Dependency and driver setup complete." -ForegroundColor Green
