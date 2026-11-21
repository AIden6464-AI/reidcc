# Rebuild E:\reidcc\app\ from python\reid.py + python\reid_gui.py. Run after editing either source file.
# Builds into python\build\dist first and only swaps it into app\ when no Reidcc process is running,
# so a failed or blocked build never leaves app\ half-deleted.
$ErrorActionPreference = "Stop"
$b = $PSScriptRoot
$root = Split-Path (Split-Path $b)   # python\build -> the Reidcc folder, which holds app\
$app = Join-Path $root "app"
$stage = Join-Path $b "dist"

& "$b\.venv\Scripts\python.exe" -m PyInstaller "$b\reidcc.spec" --noconfirm --clean `
    --distpath $stage --workpath "$b\work"
if ($LASTEXITCODE) { throw "PyInstaller failed ($LASTEXITCODE)" }
$new = Join-Path $stage "app"
Move-Item -Force "$new\reidcc-cli.exe" "$new\reidcc.com"
New-Item -ItemType HardLink -Path "$new\reid.com" -Target "$new\reidcc.com" | Out-Null   # short name: `reid`
# Git Bash only auto-appends .exe (so `reidcc` would hit the GUI exe); extensionless shims fix that.
foreach ($n in "reid", "reidcc") {
    [IO.File]::WriteAllText("$new\$n", "#!/bin/sh`nexec `"/e/reidcc/app/reidcc.com`" `"`$@`"`n")
}

$busy = Get-Process | Where-Object { $_.Path -like "$app\*" }
if ($busy) {
    $busy | ForEach-Object { Write-Host ("  in use: {0} (pid {1})" -f $_.Name, $_.Id) }
    throw "Close Reidcc (window / reid TUI) and run build.ps1 again. New build is waiting in $new"
}
# Rename first: a folder with a locked file inside fails to rename as a whole, so app\ is never half-deleted.
$old = "$app.old"
# An Explorer window showing app\ holds the folder and blocks the rename: step it up to the parent.
(New-Object -ComObject Shell.Application).Windows() |
    Where-Object { try { $_.Document.Folder.Self.Path -like "$app*" } catch { $false } } |
    ForEach-Object { $_.Navigate2($root) }
Start-Sleep -Milliseconds 300
if (Test-Path $old) { Remove-Item -Recurse -Force $old }
if (Test-Path $app) {
    try { Rename-Item $app $old } catch { throw "app\ is in use; close Reidcc and run build.ps1 again. New build is waiting in $new" }
}
Move-Item $new $app
if (Test-Path $old) {
    try { Remove-Item -Recurse -Force $old } catch { Write-Warning "could not delete $old; the next build removes it" }
}
Write-Host "built -> $app  (Reidcc.exe = GUI, reidcc.com / reid.com = TUI/CLI)"
