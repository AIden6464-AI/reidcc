# Reidcc in Rust

The rewrite in `vision\Spec\SPEC-rust-rewrite.md`. Built so far, 1:1 with the Python app:
- `core`: profiles, engines, memory, state, proxy
- `cli` → `reid.exe`: the CLI and the TUI
- `app` + `ui` → `Reidcc.exe`: the window (Tauri 2, TypeScript + Vite), with embedded sessions and shared frames of up to four live panes (`SPEC-vision-v1.md`)

The Python app (`E:\reidcc\python`, built into `E:\reidcc\app`) is still what Reidcc and `reid` run.

```
cargo build --release          # -> target\release\reid.exe and Reidcc.exe (the UI is embedded)
cargo test --release           # unit tests
python tests\parity.py         # CLI: reid.exe vs reid.py, byte for byte; -k <text> runs matching cases
tests\.venv\Scripts\python tests\tui_parity.py [--size 100x30] [-k text]   # TUI, cell by cell
python tests\gui_parity.py     # GUI: reid.json after every action; gui_shots.py, gui_flow.py
python tests\session_flow.py   # session windows (vision v1 §2): gate reveal, bar, shimmer, endings
python tests\sizes_flow.py     # sizes (vision v1 §1): Alt+1/2/3, medium's sessions and combos, the mini pod, drag thresholds
python ..\.test\merge_windows.py ..\.test\next\merging   # vision v1 §3: live windows, real pointer
```

To try it: `target\release\reid.exe` (TUI) or `target\release\Reidcc.exe` (window). Both use the real
Reidcc folder: they find it by walking up from the exe to the first `reid.json`, or use `REIDCC_HOME`.

The first tracked Rust beta is **0.1.1**. Find the current version in the launcher title, in
`Reidcc.exe` Properties → Details, or by running `target\release\reid.exe --version`.
Set the next version in `[workspace.package]` in `Cargo.toml`. Use patch bumps for fixes
and minor bumps for new features during the beta. Run `cargo check` to refresh `Cargo.lock`
before building the release.
