# First publish only. Captures the new PublishedFileID and writes it back into
# publish.vdf and workshop.txt.
#
# That write-back is the whole point: without it the next push creates a second
# Workshop item instead of updating this one, and there is no way to merge them
# afterwards.
#
#   .\first_publish.ps1 -Name YourModId
param([Parameter(Mandatory=$true)][string]$Name)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\config.ps1"
$cfg = Get-PzConfig

$sd  = Join-Path $cfg.WorkshopDir $Name
$vdf = Join-Path $sd 'publish.vdf'
$log = Join-Path $sd '_firstpublish.log'
if (-not (Test-Path $vdf)) { throw "no publish.vdf at $vdf - run publishvdf.py first" }

$txt = Get-Content $vdf -Raw
$fid = ([regex]::Match($txt, '"publishedfileid"\s+"(\d+)"')).Groups[1].Value
if ($fid -ne '0') { Write-Host ("ABORT - publishedfileid is already $fid; use push.ps1 to update"); exit 3 }
if (-not $cfg.SteamUser) { Write-Host '  ABORT - no steamUser in config (or PZ_STEAM_USER)'; exit 5 }

$out = & $cfg.SteamCmd +login $cfg.SteamUser +workshop_build_item $vdf +quit 2>&1 | Out-String
$out | Set-Content $log
if ($out -match 'password|Steam Guard|Two-factor|FAILED login') {
  Write-Host '  ABORT - steamcmd wants interactive credentials. Run this yourself:'
  Write-Host ("  & '$($cfg.SteamCmd)' +login $($cfg.SteamUser) +workshop_build_item `"$vdf`" +quit")
  exit 4
}

$m = [regex]::Match($out, 'PublishFileID\s*(\d+)')
if (-not $m.Success) { $m = [regex]::Match($out, 'publishedfileid[^0-9]*(\d{6,})') }
if (-not $m.Success) {
  Write-Host '  FAILED - no PublishFileID in the output. Tail:'
  $out -split "`n" | Select-Object -Last 15 | ForEach-Object { Write-Host ('    ' + $_.Trim()) }
  exit 1
}
$new = $m.Groups[1].Value
Write-Host ("  NEW ITEM id=$new")

$txt2 = [regex]::Replace($txt, '"publishedfileid"\s+"0"', ('"publishedfileid"' + "`t`t" + '"' + $new + '"'))
Set-Content -Path $vdf -Value $txt2 -NoNewline -Encoding UTF8
Add-Content -Path (Join-Path $sd 'workshop.txt') -Value ("`nid=" + $new)
Write-Host '  wrote the id back into publish.vdf and workshop.txt'
Write-Host ("  https://steamcommunity.com/sharedfiles/filedetails/?id=$new")
Write-Host ''
Write-Host ("  Put this in your config so the other tools know about it:")
Write-Host ("    `"fileId`": $new")
Write-Host '  First publish: check the item page for the Steam Workshop legal-agreement'
Write-Host '  banner - until it is accepted the item is undownloadable.'
