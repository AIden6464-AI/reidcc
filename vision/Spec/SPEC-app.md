# SPEC: Reidcc app packaging fixes

Status: BUILT 2026-11-17 (fixes 1-4). Fix 3 also steps any Explorer window showing app\ up to the parent, since that blocks the rename. Source: ponytail review of the .exe packaging (2026-11-17).

## Current layout (for reference)
- `app\Reidcc.exe`: windowed, always the GUI.
- `app\reidcc.com` and `app\reid.com`: console, TUI/CLI with auto-detect.
- `app\reid` and `app\reidcc`: extensionless shims for Git Bash.
- Built from `reid.py` + `reid_gui.py` by `build\build.ps1` using `build\reidcc.spec`. The icon is `reidcc.ico` (root).
- Data folder (`HOME`) = `E:\reidcc`, found by looking for `reid.json` next to the exe or one level up. `REIDCC_HOME` overrides it.

## Fix 1: restore the broken app (operational)
`app\_internal` was half-deleted by a rebuild that collided with a running `reid` TUI (pid 44176).
- Precondition: nothing runs from `app\` (`Get-Process | ? Path -like 'E:\reidcc\app\*'` is empty).
- Action: run `build\build.ps1`. Rather than rebuilding, it may move the staged `build\dist\app` into place if that is still current. Rebuild anyway, because Fix 2 changes `reid.py`.
- Done when: `reidcc.com -l` lists the profiles, `Reidcc.exe` opens the window with the icon, and `_internal` has its full file set (not 20 files).

## Fix 2: the frozen GUI must use the bundled reid_gui
- Bug: `reid.py` `open_gui` runs `sys.path.insert(0, HOME)` and then `import reid_gui`. PyInstaller 6 finds bundled modules through `sys.path_hooks`, so `E:\reidcc\reid_gui.py` on disk shadows the bundled copy. The result is a frozen `reid.py` running a live `reid_gui.py`, which breaks whenever the two drift apart.
- Change: delete that line. Source runs already have the script folder at `sys.path[0]`.
- Check, frozen: rename `E:\reidcc\reid_gui.py` temporarily, then start `app\Reidcc.exe`. The window must still open. Restore the file afterwards.
- Check, source: `python E:\reidcc\reid.py --gui` still opens the window.

## Fix 3: atomic swap in build.ps1
- Bug: `Remove-Item -Recurse $app` can fail partway if any file is locked after the busy check (Explorer, AV, or a `reid` started mid-build). That leaves a half-deleted app.
- Change: replace the delete-then-move with:
  1. If `app` exists: `Rename-Item app app.old`. Renaming a folder with locked files fails as a whole, so nothing is damaged. On failure, throw "close Reidcc" and leave the staged build in place.
  2. `Move-Item build\dist\app app`.
  3. `Remove-Item -Recurse app.old`. This is best-effort: if it fails, warn and continue, because the next build removes a leftover `app.old` first.
- Keep: the existing busy check (it gives a friendlier message that names the pid).
- Check: start `reid.com` (TUI), then run the build. It must refuse with `app\` fully intact. Then close the TUI and run the build again; it must succeed.

## Fix 4 (optional): reid.com as a hard link
- `Copy-Item reidcc.com reid.com` becomes `New-Item -ItemType HardLink -Path reid.com -Target reidcc.com`. That saves 2 MB and means one file instead of two copies.
- Risk: none on NTFS. If E: is ever FAT/exFAT, fall back to copying.

## Out of scope
- A desktop shortcut, a folder case rename (`reidcc` → `Reidcc`), moving `E:\reidcc.zip` to `legacy\`. Each needs a separate yes.
- A reid per-profile `plugins: off` switch, so lean profiles skip ponytail's SessionStart context. This is a separate spec if wanted.

## Verify after all fixes
1. `reid -l`, `reid --dry plain`, and `REID_FLAG=x reid --back` must work in cmd, PowerShell and Git Bash.
2. Start Menu → Reidcc: the window opens with the icon in the title bar and taskbar.
3. GUI → LAUNCH `plain` opens Windows Terminal running Claude. `/reid` returns to the TUI, `r` resumes, `/exit` leaves.
4. Update the README "Editing reid.py / reid_gui.py" line: it becomes true for both files after Fix 2.
