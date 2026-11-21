; Tauri NSIS hooks (vision/Spec/SPEC-github-repo.md 3b, 3d). reid.exe does the work; its lines show
; in the installer's details. Neither touches %USERPROFILE%\Reidcc.

!macro NSIS_HOOK_POSTINSTALL
  nsExec::ExecToLog '"$INSTDIR\reid.exe" --install'
  Pop $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog '"$INSTDIR\reid.exe" --uninstall'
  Pop $0
!macroend
