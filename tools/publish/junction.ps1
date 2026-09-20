# Junction <GameModsDir>\<ModId> at your working tree, so the game loads the
# checkout directly and you can test an edit without restaging.
#
# Do not switch branches while the game is running - it has the files open.
#
#   .\junction.ps1 -Mod YourModId
#   .\junction.ps1 -Mod YourModId -Off
param([Parameter(Mandatory=$true)][string]$Mod, [switch]$Off)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\config.ps1"
$cfg = Get-PzConfig

$link = Join-Path $cfg.GameModsDir $Mod
$src  = Join-Path $cfg.ModsSource $Mod

if ($Off) {
  if (Test-Path $link) {
    $item = Get-Item $link
    if ($item.LinkType -ne 'Junction') { throw "$link is a real folder, not a junction - refusing to delete it" }
    $item.Delete(); Write-Host "removed junction $link"
  } else { Write-Host "no junction at $link" }
  exit 0
}

if (-not (Test-Path (Join-Path $src '42\mod.info'))) { throw "no mod at $src" }
if (Test-Path $link) {
  $item = Get-Item $link
  if ($item.LinkType -eq 'Junction') { $item.Delete() }
  else { throw "$link exists and is a real folder - move it aside first" }
}
New-Item -ItemType Junction -Path $link -Target $src | Out-Null
Write-Host "junction $link -> $src"
