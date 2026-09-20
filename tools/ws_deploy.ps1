# ws_deploy.ps1 - one-command PZ Workshop publish via SteamCMD
# Usage:  .\ws_deploy.ps1 -ModFolder "C:\path\to\YourMod" -ChangeNote "v1.1 fixed dist lists"
# First run: steamcmd will prompt for password + Steam Guard IN YOUR TERMINAL - creds are
# cached by steamcmd after that; this script never stores or sees them.
# First publish: leave PublishedFileId=0 - Steam creates the item and prints the new ID
# in the output. Paste it into $PublishedFileId below for all future updates.

param(
    [Parameter(Mandatory=$true)][string]$ModFolder,
    [string]$ChangeNote = "update"
)

# ==== EDIT THESE ONCE ====
$SteamUser       = "YOUR_STEAM_USERNAME"   # username only. never put a password in this file.
$SteamCmd        = "C:\steamcmd\steamcmd.exe"
$PublishedFileId = "3783958244"                        # 0 = create new item; then paste the real ID here
$Title           = "Alpha Shipment - '93 Collectibles"
# =========================

$ErrorActionPreference = "Stop"
$ModName = Split-Path $ModFolder -Leaf
$Stage   = Join-Path $env:TEMP "ws_stage_$ModName"

# Workshop item layout: <item root>\mods\<ModName>\<b42 mod layout>
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path "$Stage\content\mods" -Force | Out-Null
Copy-Item $ModFolder "$Stage\content\mods\$ModName" -Recurse

# Preview image: uses mod's poster if present
$Preview = Join-Path $ModFolder "poster.png"
$PreviewLine = ""
if (Test-Path $Preview) {
    Copy-Item $Preview "$Stage\preview.png"
    $PreviewLine = "`t`"previewfile`"`t`"$Stage\preview.png`""
}

$vdf = @"
"workshopitem"
{
`t"appid"`t`t"108600"
`t"publishedfileid"`t"$PublishedFileId"
`t"contentfolder"`t"$Stage\content"
$PreviewLine
`t"title"`t`t"$Title"
`t"changenote"`t"$ChangeNote"
}
"@
$VdfPath = "$Stage\item.vdf"
Set-Content -Path $VdfPath -Value $vdf -Encoding UTF8

Write-Host "Publishing $ModName (item $PublishedFileId) ..." -ForegroundColor Cyan
& $SteamCmd +login $SteamUser +workshop_build_item $VdfPath +quit

Write-Host ""
Write-Host "If this was the first publish, find 'PublishFileID' in the output above" -ForegroundColor Yellow
Write-Host "and paste it into `$PublishedFileId in this script." -ForegroundColor Yellow


