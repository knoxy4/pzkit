# Update the changenote in publish.vdf, then push via steamcmd's cached credentials.
#
# This never handles a Steam password. steamcmd caches credentials after one
# interactive login; if it asks for one here, this aborts and hands you the exact
# command to run yourself.
#
#   .\push.ps1 -Name YourModId -Changenote "0.4.1 - fixed the shower"
#   .\push.ps1 -Name YourModId -Changenote "..." -DryRun
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [Parameter(Mandatory=$true)][string]$Changenote,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\config.ps1"
$cfg = Get-PzConfig

$sd  = Join-Path $cfg.WorkshopDir $Name
$vdf = Join-Path $sd 'publish.vdf'
if (-not (Test-Path $vdf)) { Write-Host ("SKIP $Name - no publish.vdf"); exit 2 }

$txt = Get-Content $vdf -Raw
$fid = ([regex]::Match($txt, '"publishedfileid"\s+"(\d+)"')).Groups[1].Value
if ([string]::IsNullOrWhiteSpace($fid) -or $fid -eq '0') {
  Write-Host ("ABORT $Name - publishedfileid is '$fid'. A push now would create a DUPLICATE item.")
  Write-Host ("  Use first_publish.ps1 for a mod that has never been uploaded.")
  exit 3
}

$new = [regex]::Replace($txt, '"changenote"\s+"[^"]*"', ('"changenote"' + "`t`t" + '"' + $Changenote + '"'))
if ($new -eq $txt) { Write-Host ("WARN $Name - changenote field not found; leaving the file as-is") }
else { Set-Content -Path $vdf -Value $new -NoNewline -Encoding UTF8; Write-Host ("  changenote -> " + $Changenote) }

$vis = ([regex]::Match($new, '"visibility"\s+"(\d)"')).Groups[1].Value
Write-Host ("  fileid=$fid visibility=$vis (unchanged)")
if ($DryRun) { Write-Host ("  DRYRUN - not pushing"); exit 0 }
if (-not $cfg.SteamUser) { Write-Host '  ABORT - no steamUser in config (or PZ_STEAM_USER)'; exit 5 }

$out = & $cfg.SteamCmd +login $cfg.SteamUser +workshop_build_item $vdf +quit 2>&1 | Out-String
if ($out -match 'password|Steam Guard|Two-factor|FAILED login') {
  Write-Host ("  ABORT $Name - steamcmd wants interactive credentials. Run this yourself:")
  Write-Host ("  & '$($cfg.SteamCmd)' +login $($cfg.SteamUser) +workshop_build_item `"$vdf`" +quit")
  exit 4
}
if ($out -match 'Success') {
  Write-Host ("  PUSHED $Name  https://steamcommunity.com/sharedfiles/filedetails/?id=$fid")
  exit 0
}
Write-Host ("  FAILED $Name")
$out -split "`n" | Select-Object -Last 12 | ForEach-Object { Write-Host ('    ' + $_.Trim()) }
exit 1
