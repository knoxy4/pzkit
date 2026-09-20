# Shared configuration for the Workshop publishing scripts. Dot-source it:
#   . "$PSScriptRoot\config.ps1"
# Resolution: $env:PZPUBLISH_CONFIG, then .\pzpublish.json, then <repo root>\pzpublish.json.
# Path fields can be overridden per-machine with PZ_WORKSHOP_DIR, PZ_MODS_DIR,
# PZ_STEAMCMD and PZ_STEAM_USER, so the committed config stays machine-neutral.

function Get-PzRepoRoot {
    # Git root of the directory you are working in, not of this script. These
    # tools are meant to be usable from any mod repo, including one that does
    # not contain them.
    param([string]$Start = (Get-Location).Path)
    $r = (& git -C $Start rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and $r) { return ($r.Trim() -replace '/', '\') }
    return $Start
}

function Select-PzFirst {
    # First non-empty value wins. Written out rather than using `?:` so this
    # runs on Windows PowerShell 5.1, which ships with Windows.
    param([string]$First, [string]$Second)
    if (-not [string]::IsNullOrWhiteSpace($First)) { return $First }
    return $Second
}

function Resolve-PzPath {
    param([string]$Value, [string]$Default)
    $v = if ([string]::IsNullOrWhiteSpace($Value)) { $Default } else { $Value }
    if ($v -like '~*') { $v = (Join-Path $env:USERPROFILE $v.TrimStart('~', '\', '/')) }
    return $v
}

function Get-PzConfig {
    $path = $env:PZPUBLISH_CONFIG
    if (-not $path) {
        $local = Join-Path (Get-Location) 'pzpublish.json'
        $path = if (Test-Path $local) { $local } else { Join-Path (Get-PzRepoRoot) 'pzpublish.json' }
    }
    if (-not (Test-Path $path)) {
        throw ("no config found at $path`n" +
               "Copy pzpublish.example.json to pzpublish.json at your repo root and edit it, " +
               "or set PZPUBLISH_CONFIG to point at one.")
    }
    $cfg = Get-Content $path -Raw | ConvertFrom-Json

    $root = Get-PzRepoRoot
    $modsSource = if ($cfg.modsSource) { $cfg.modsSource }
                  elseif (Test-Path (Join-Path $root 'mods')) { Join-Path $root 'mods' }
                  else { $root }

    [pscustomobject]@{
        Path        = $path
        RepoRoot    = $root
        ModsSource  = $modsSource
        WorkshopDir = Resolve-PzPath (Select-PzFirst $env:PZ_WORKSHOP_DIR $cfg.workshopDir) (Join-Path $env:USERPROFILE 'Zomboid\Workshop')
        GameModsDir = Resolve-PzPath (Select-PzFirst $env:PZ_MODS_DIR $cfg.modsDir) (Join-Path $env:USERPROFILE 'Zomboid\mods')
        SteamCmd    = Resolve-PzPath (Select-PzFirst $env:PZ_STEAMCMD $cfg.steamcmd) 'steamcmd.exe'
        SteamUser   = Select-PzFirst $env:PZ_STEAM_USER $cfg.steamUser
        Author      = $cfg.author
        Mods        = @($cfg.mods)
    }
}
