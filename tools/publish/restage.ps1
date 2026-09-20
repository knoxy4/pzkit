# Stage a mod into <WorkshopDir>\<ModId>\Contents\mods\<ModId> from a git ref.
#
# Staging happens through `git archive`, not a file copy, for two reasons: the
# staged tree is exactly what the tag contains rather than whatever is in your
# working directory, and .gitattributes export-ignore applies, so generator
# sources and audit folders never reach the Workshop.
#
#   .\restage.ps1 -Mod YourModId -Ref YourModId-v1.4.0
#   .\restage.ps1 -All                    (HEAD of the current branch; test pushes only)
param([string]$Mod, [string]$Ref = 'HEAD', [switch]$All)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\config.ps1"
$cfg = Get-PzConfig
Set-Location $cfg.RepoRoot

$mods = if ($All) {
  Get-ChildItem $cfg.ModsSource -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName '42\mod.info') } |
    Select-Object -ExpandProperty Name
} else { @($Mod) }
if (-not $mods -or -not $mods[0]) { throw 'give -Mod <id> or -All' }

$flat = ($cfg.ModsSource -eq $cfg.RepoRoot)
foreach ($m in $mods) {
  $dest = Join-Path $cfg.WorkshopDir "$m\Contents\mods\$m"
  if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $dest | Out-Null

  $tmp = Join-Path $env:TEMP "pzstage_$m.tar"
  if ($flat) { $rel = $m; $strip = 1 } else { $rel = "mods/$m"; $strip = 2 }
  & git archive --format=tar -o $tmp $Ref -- $rel
  if ($LASTEXITCODE -ne 0) { throw "git archive failed for $rel at $Ref" }
  & tar -xf $tmp -C $dest --strip-components=$strip
  Remove-Item $tmp -Force

  $n = (Get-ChildItem $dest -Recurse -File).Count
  Write-Host ("{0,-22} {1,4} files  <- {2}" -f $m, $n, $Ref)
}
