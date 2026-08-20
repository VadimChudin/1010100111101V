$ErrorActionPreference = 'Stop'

$Repository = 'VadimChudin/1010100111101V'
$ReleaseApi = "https://api.github.com/repos/$Repository/releases/tags/runtime-latest"
$StateDir = if ($env:AGENT_ROOM_HOME) { $env:AGENT_ROOM_HOME } else { Join-Path $HOME '.agent-room' }
$VenvDir = Join-Path $StateDir 'venv'
$BootstrapDir = Join-Path $StateDir 'bootstrap'

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) {
  $Winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($Winget) {
    Write-Host 'Installing the isolated Agent Room Python runtime…'
    & $Winget.Source install --id Python.Python.3.11 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    $Candidate = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
    if (Test-Path $Candidate) { $Python = @{ Source = $Candidate } }
  }
}
if (-not $Python) { throw 'Python 3.11 could not be provisioned automatically. Install it once, then restart Agent Room.' }

New-Item -ItemType Directory -Force -Path $BootstrapDir | Out-Null
$headers = @{ Accept = 'application/vnd.github+json'; 'User-Agent' = 'agent-room-runtime-installer' }
$release = Invoke-RestMethod -Headers $headers -Uri $ReleaseApi
$assets = @{}
foreach ($asset in $release.assets) { $assets[$asset.name] = $asset.browser_download_url }
if (-not $assets.ContainsKey('runtime-update.json')) { throw 'runtime-latest does not provide an update manifest' }
$manifest = Invoke-RestMethod -Headers $headers -Uri $assets['runtime-update.json']
if (-not $assets.ContainsKey($manifest.asset_name) -or $assets[$manifest.asset_name] -ne $manifest.asset_url) { throw 'manifest asset is not a published runtime-latest asset' }
$Wheel = Join-Path $BootstrapDir $manifest.asset_name
Invoke-WebRequest -Headers $headers -Uri $manifest.asset_url -OutFile $Wheel
$Digest = (Get-FileHash -Algorithm SHA256 -Path $Wheel).Hash.ToLower()
if ($Digest -ne $manifest.sha256.ToLower()) { Remove-Item -Force $Wheel; throw 'runtime checksum verification failed' }
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $BootstrapDir 'runtime-update.json')
Write-Host "Verified Agent Room Runtime $($manifest.version) ($($manifest.build.Substring(0, 12)))"

& $Python.Source -m venv $VenvDir
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check --upgrade $Wheel

$Runtime = Join-Path $VenvDir 'Scripts\agent-room-runtime.exe'
Write-Host "`nAgent Room Runtime is installed in $VenvDir."
Write-Host 'Create a one-time pairing token in the Agent Room dashboard, then run:'
Write-Host "  $Runtime init --cloud-url https://app-production-cc16.up.railway.app --project-id default --workspace-root C:\path\to\project --state-dir $StateDir\default --device-name `"$env:COMPUTERNAME`""
Write-Host "  $Runtime register --config $StateDir\default\runtime.json --pairing-token <token>"
Write-Host "  $Runtime serve --config $StateDir\default\runtime.json --auto-update"
