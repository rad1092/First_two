param(
  [string]$BundleDir = "$(Join-Path $PSScriptRoot '.offline_bundle')",
  [string]$PolicyFile = ""
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PolicyFile)) {
  $PolicyFile = Join-Path $BundleDir 'meta/offline_policy.json'
}
$WheelDir = Join-Path $BundleDir 'wheels'
$ReqFile = Join-Path $BundleDir 'meta/offline_requirements.txt'

Write-Host '[1/3] Verifying offline bundle policy/hash/license...'
python -m bitnet_tools.offline_bundle verify --bundle-dir "$BundleDir" --policy "$PolicyFile"
if ($LASTEXITCODE -ne 0) {
  Write-Error '[ERROR] Policy verification failed. Installation aborted.'
  exit 1
}

Write-Host '[2/3] Installing from offline wheel bundle only...'
if (Test-Path $ReqFile) {
  python -m pip install --no-index --find-links "$WheelDir" -r "$ReqFile"
} else {
  python -m pip install --no-index --find-links "$WheelDir" bitnet-tools
}
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host '[3/3] Offline installation complete.'
