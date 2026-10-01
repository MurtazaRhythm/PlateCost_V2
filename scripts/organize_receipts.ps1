<#
.SYNOPSIS
    Removes duplicate files from the "Receipt demos" folder and renames the
    remaining files in order (Receipt_01.jpeg, Receipt_02.jpeg, ...).

.DESCRIPTION
    Duplicates are detected by SHA-256 content hash, so renamed copies such as
    "IMG_1423(1).jpeg" are caught even though their names differ. Duplicates
    are sent to the Recycle Bin rather than permanently deleted.

    Files are ordered by the number in their original name (IMG_1423 before
    IMG_1424), falling back to the file name.

.PARAMETER Folder
    Folder to organize. Defaults to "Receipt demos" in the project root.
    Only files directly in the folder are processed, not subfolders.

.PARAMETER Prefix
    Prefix for the renamed files. Defaults to "Receipt".

.PARAMETER DryRun
    Show what would happen without changing anything.

.EXAMPLE
    .\scripts\organize_receipts.ps1 -DryRun
    .\scripts\organize_receipts.ps1 -Folder ".\Receipt demos\RThree"
#>
param(
    [string]$Folder = (Join-Path (Split-Path $PSScriptRoot -Parent) "Receipt demos"),
    [string]$Prefix = "Receipt",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName Microsoft.VisualBasic

if (-not (Test-Path -LiteralPath $Folder -PathType Container)) {
    throw "Folder not found: $Folder"
}

function Get-SortKey([System.IO.FileInfo]$File) {
    $base = $File.BaseName -replace '\(\d+\)$', '' -replace '\s+$', ''
    if ($base -match '(\d+)') { return [long]$Matches[1] }
    return [long]::MaxValue
}

# Original names (no "(1)" / " - Copy" suffix) win when choosing which copy to keep.
function Get-CopyPenalty([System.IO.FileInfo]$File) {
    if ($File.BaseName -match '(\(\d+\)| - Copy( \(\d+\))?)$') { return 1 }
    return 0
}

$files = Get-ChildItem -LiteralPath $Folder -File

$removed = 0
$keep = foreach ($group in ($files | Group-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })) {
    $sorted = $group.Group | Sort-Object { Get-CopyPenalty $_ }, { $_.Name.Length }, Name
    $sorted[0]
    foreach ($dup in ($sorted | Select-Object -Skip 1)) {
        Write-Host "Duplicate of $($sorted[0].Name): removing $($dup.Name)" -ForegroundColor Yellow
        if (-not $DryRun) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
                $dup.FullName,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)
        }
        $removed++
    }
}

$keep = @($keep | Sort-Object { Get-SortKey $_ }, Name)
$digits = [Math]::Max(2, "$($keep.Count)".Length)

# Rename in two passes via temporary names so new names never collide with existing ones.
$plan = for ($i = 0; $i -lt $keep.Count; $i++) {
    $newName = "{0}_{1}{2}" -f $Prefix, ($i + 1).ToString("D$digits"), $keep[$i].Extension.ToLower()
    [pscustomobject]@{ File = $keep[$i]; NewName = $newName; TempName = "__tmp_$([guid]::NewGuid())$($keep[$i].Extension)" }
}

foreach ($p in $plan) {
    Write-Host "$($p.File.Name) -> $($p.NewName)"
    if (-not $DryRun) { Rename-Item -LiteralPath $p.File.FullName -NewName $p.TempName }
}
if (-not $DryRun) {
    foreach ($p in $plan) { Rename-Item -LiteralPath (Join-Path $Folder $p.TempName) -NewName $p.NewName }
}

$mode = if ($DryRun) { " (dry run, nothing changed)" } else { "" }
Write-Host "`nDone$mode. Kept $($keep.Count) files, removed $removed duplicates." -ForegroundColor Green
