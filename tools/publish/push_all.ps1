# Push every published mod in the config, with one changenote.
#   .\push_all.ps1 -Note "42.20.4 compatibility pass"
param([Parameter(Mandatory=$true)][string]$Note)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\config.ps1"
$cfg = Get-PzConfig

$mods = @($cfg.Mods | Where-Object { $_.fileId } | ForEach-Object { $_.id })
if (-not $mods) { Write-Host 'nothing to push - no mod in the config has a fileId'; exit 2 }
Write-Host ("pushing " + $mods.Count + " mod(s) from " + $cfg.Path)

$ok = @(); $bad = @()
foreach ($name in $mods) {
  Write-Host ('=== ' + $name)
  & "$PSScriptRoot\push.ps1" -Name $name -Changenote $Note
  if ($LASTEXITCODE -eq 0) { $ok += $name } else { $bad += ($name + ' (exit ' + $LASTEXITCODE + ')') }
}
Write-Host ''
Write-Host ('PUSHED  ' + $ok.Count + ': ' + ($ok -join ', '))
if ($bad.Count) { Write-Host ('FAILED  ' + $bad.Count + ': ' + ($bad -join ', ')); exit 1 }
