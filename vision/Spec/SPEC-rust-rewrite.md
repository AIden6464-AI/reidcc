# Spec: the Rust rewrite

Status: **stage 0 built 2026-11-20** (see "Stage 0 as built"). **Stage 1's 1:1 TUI and GUI built
2026-11-20**, waiting on Reid's sign-off (`SPEC-rust-tui-gui.md`). Betas built 2026-11-20: session windows
(stage 2), snap (stage 3), and all three sizes and the pod (main, medium, small; named full, medium, mini pod until 2026-11-24). Stage 4 (rigs) beta built 2026-11-23 ("Ya build that as you can because we have added a lot from that time"; vision v1 §5). Headless isn't built.
**Since 0.2.0 (2026-11-21) the Rust app is what ships** (installer, updater, `reid.exe`); the Python app
in `python\` is legacy, kept only as the parity reference (`rs/tests/*parity.py`). Checked 2026-11-23.
This is how Reidcc is rebuilt in Rust. What it builds
toward (sizes, session windows, snap, headless, orchestrator) is `vision\SPEC-vision-v1.md`. Today's
Python app (source in `python\`, built into `app\`) stays the daily driver until stage 2 passes.

## Reid's words

> "Rust?" · "na how big would rust be? and a hole reright?" · "spec doc "vision verson 1 (Rust
> rewright)"" · "No spec the build for the ideas I had quote my ideas from my input and make a spec for
> rewriting in rust" (Reid, 2026-11-19, to Carbon; Carbon ran out of credits before writing it)

> "well i want the rust part one spec and the ideas in one spec and apart of the vision" (Reid, 2026-11-19)

## Why Rust

Tkinter carries today's single launcher window and the layered gate overlay. It can't reasonably
carry what vision version 1 needs: embedded terminals, windows that snap together, smooth resizing
between sizes, and custom borderless frames.

In Rust these are well-trodden:
- ConPTY (`portable-pty`, from WezTerm)
- Win32 windowing (`windows` crate)
- a small native shell (Tauri 2, using the WebView2 already on Windows)

Codex itself is a Rust program.

> "it will snap together, like fuse together, and be like a big animation type thing. And this is why we're
> building in Rust." (Reid, 2026-11-19)

The drag shimmer, the facing-edge shimmer, the fuse sequence and the capsule-shaped mini pod all need
borderless windows with per-pixel transparency, redrawn smoothly while they're being dragged. Tkinter only has
whole-window alpha or a single see-through colour. A Tauri 2 window is transparent per pixel and
animates on the GPU through WebView2. See `vision\SPEC-vision-v1.md`, "Snap: shimmer, then fuse" and
"The mini pod's shape".

## Checked on this machine (2026-11-19)

| Claim from the chat | Checked |
|---|---|
| The app is two files | True for the app itself: `reid.py` is **1,731** lines (core + CLI + TUI) and `reid_gui.py` is **1,218**. Not counted: `proxy\` (about 1,670 lines of mitmproxy add-ons), `python\build\make_assets.py` (283), `aca\` (a separate project). |
| `app\` is ~35–55 MB | **44 MB in 1,025 files** (PyInstaller). |
| Rust toolchain needs installing | **Already installed:** rustc/cargo 1.96.1, target `x86_64-pc-windows-msvc`, VS 2022 Build Tools (MSVC 14.44, `link.exe`), Windows SDK 10.0.26100. WebView2 runtime 157 is installed. Node and Bun are there too. |
| Codex on this machine is 0.160.1 | **Wrong:** it's 0.170.0. |
| "Clean engines/ adapter boundary" already exists | **Wrong:** there's no `engines\` folder. Engines are an `engine_of()` branch in `reid.py`. |
| ~800–1,200 lines of Rust for everything | **Optimistic.** Estimate 3–5k Rust + 1.5–2.5k TS/CSS for parity plus session windows. |
| Tauri `.exe` is ~6–10 MB | Plausible, not measured. Stage 1 measures it. |

## What does not change

- **Data:** `reid.json`, `reid_state.json`, memory files, `personas\`, `mds\`, `json\`, and the
  planned `codex\` and `opencode\` folders are read and written in exactly today's formats. No
  migration. Both apps can run against the same files during the changeover, which makes a
  cross-process lock on `reid_state.json` mandatory (Astra's review, finding 2).
- **Proxy:** the mitmproxy add-ons stay Python. Rust starts `mitmdump` as a child process inside a
  Job Object, the same way `reid.py` does now.
- **Art:** gate frames, doors, icon and banner still come from `python\build\make_assets.py`.
- **Vision:** palette, voice and motion rules carry over unchanged.

## Stack

- **Tauri 2** (stable 2.x, pinned exact; 3.0 is alpha) with Rust for the core and windows, and
  WebView2 for the UI.
- **UI:** plain TypeScript + CSS, no framework. The design doc's tokens are already CSS. Bundled
  with Vite.
- **Terminal in a window:** `portable-pty` (ConPTY) in Rust, `xterm.js` with the WebGL renderer in
  the page. Claude Code already runs inside xterm.js every day as VS Code's terminal, which is the
  best evidence it renders right.
- **Win32:** the `windows` crate (snapping, DWM title bar colours, Job Objects).
- **CLI and TUI:** a separate `reid.exe` on the same core crate. For 1:1 the TUI is a direct port of
  the Python painter with `crossterm` for keys and size (`SPEC-rust-tui-gui.md`); `ratatui` comes in
  only if `SPEC-tui.md`'s redesign needs it. That redesign carries the goal: "i lowkey want the Reidcc
  tui to look and feel better then the gui".

Layout, built next to the Python app and never touching files it uses:

```
E:\reidcc\rs\
  core\     profiles, engines (claude · codex · opencode), memory, state + lock, proxy launcher
  cli\      reid.exe: today's CLI flags + TUI
  app\      Tauri shell: launcher window, session windows, snapping
  ui\       TS + CSS
```

`core` gets a real engine boundary (one module per engine behind one `build(profile) → argv, env,
temp files` function). That's what the chat assumed already existed.

## Stages

Each stage ends with something Reid can use. The Python app stays installed and untouched until stage
2 passes. Feature names refer to `vision\SPEC-vision-v1.md`.

| Stage | Builds | Done when |
|---|---|---|
| **0 · core** | `rs\core` + `reid.exe` CLI (no TUI yet) | `reid --dry <p>` is **byte-identical** to Python's for every profile in reid.json (Claude, Codex, and later OpenCode). Same errors, same state-file writes. Tests use a temp reid.json. |
| **1 · TUI + GUI, 1:1** | today's TUI in `reid.exe`, then today's GUI in Tauri, exactly as they are (`SPEC-rust-tui-gui.md`); after that, the three sizes + combos (vision §1) | The TUI matches screen for screen and the GUI writes the same `reid.json` and looks the same, per `SPEC-rust-tui-gui.md`. `.exe` size and cold start are measured and written here. |
| **2 · session windows** | embedded terminal per session, Telemetry Bar, run strip (vision §2, §4) | a full day of Reid's normal work in Reidcc windows without falling back. **Then** the Python GUI is retired. |
| **3 · snap** | magnetic snap, unsnap, headless panes inside a frame (vision §3) | two to four sessions in one frame, resized, unsnapped and resnapped with nothing lost |
| **4 · rigs** | saved layouts, one-combo launch (vision §5) | a rig opens and restores its layout |
| **TUI redesign** | `SPEC-tui.md`'s look and feel in `reid.exe` | after stage 1's 1:1 TUI |

## Stage 0 as built (2026-11-20)

> "Let's start on the Rust rewrite" (Reid, 2026-11-20)

`E:\reidcc\rs\` is a Cargo workspace: `core` (library `reidcc`) and `cli` (`reid.exe`). `app\` and
`ui\` come with stage 1. Build with `cargo build --release` in `rs\`. Nothing in the Python app
changed, and the Python app is still what Reid uses every day.

**What reid.exe does:** the same flags as `reid.py`:
- `--dry`, `-l`, `-h`, `--edit`, `--mem`
- `<profile> [args]` and `--resume`
- `--back` (the `/reid` command) and `--statusline`
- the proxy, in a kill-on-close Job Object, as today

Engines are one module each behind `engines::build(profile) -> argv, env, temp files`
(`core\src\engines\claude.rs`, `codex.rs`). Paths, JSON errors, command lines, CRLF and text-mode
files follow CPython 3.13 (`core\src\py.rs`, `pyjson.rs`), because the output has to match.

**Done-when check:** `python rs\tests\parity.py` runs both CLIs against a temp copy of the Reidcc
folder and compares them byte for byte. It never touches the real `reid.json` or `reid_state.json`.
It covers:
- every real profile, plus 57 edge-case profiles
- 35 broken-JSON settings files
- the statusline with 5 inputs × 4 profiles
- missing and broken `reid.json`
- six real launches (Claude, Codex, safe mode, proxy), comparing the `reid_state.json` they write

Result: **153 of 154 identical, 0 differ.** The one accepted difference is a known gap: a broken
`codex\*.toml` gets the toml crate's wording, not tomllib's. The line and column match.

The audit fixes of 2026-11-20 landed in both apps the same way and the harness checks them on both:
- a `claude.cmd` or `codex.cmd` in the project folder never runs
- the temp sweep keeps the files of a session that's still running (the pid is in the file name)
- `reid_state.json` writes take a lock file and use a temp name of their own
- the three inputs that used to crash Python (a numeric `model`, a settings file holding a JSON
  list) now give the same result as Rust

By design, the statusline command in the settings file names `reid.exe` instead of `python reid.py`.
The test gives Python the same command so that everything else can be compared.

**Measured:** `reid.exe` is 0.96 MB. Start-up (median of 5): `-l` 16 ms vs Python's 119 ms;
`--dry opus47` 31 ms vs 134 ms.

**Not in stage 0:**
- The TUI and `signin_files`: both came with stage 1 (`SPEC-rust-tui-gui.md`).
- Lossy JSON edge cases: NaN/Infinity load as null, integers past 64 bits as floats.

The open question below is still open. Stage 0 didn't need an answer.

## Ready for vision v1 (checked 2026-11-20)

> "Get ready for the other visions" (Reid, 2026-11-20)

What the vision stages build on, checked on this machine:
- **Embedded terminals (stage 2):** `portable-pty` 0.9.0 (ConPTY, from WezTerm) is in the cargo
  cache. On npm: `@xterm/xterm` 6.0.0, `@xterm/addon-webgl` 0.19.0, `@xterm/addon-fit` 0.11.0.
- **Several windows (sizes, session windows, the pod):** the stage 1 Tauri app makes its windows in code
  (`tauri.conf.json` lists none), so new windows (session, pod) are added the same way.
  Per-pixel transparency for the pod's capsule and the snap shimmer is a Tauri window option.
- **Missing foundation: a live session list.** Nothing records which sessions are running. The
  statusline prints context and limit but stores nothing, and `reid_state.json` holds only the last
  session and recent folders. The mini pod, medium's session list, the Telemetry Bar, the run strip and
  rigs all need it. It comes first: each session writes a small file (engine, profile, folder, pid,
  start time, state, last context/limit), the statusline updates it, and the file is removed when the
  session ends.

Order:
1. Reid signs off stage 1 and the Rust app goes into `app\`.
2. The session list.
3. The three sizes + combos (vision §1). **Built 2026-11-20**: full, medium (the session list and combos
   1–9) and the mini pod. Still to do: a letter per profile, and pinning the pod on top.
4. Session windows (stage 2). **Beta built 2026-11-20** (vision v1 §2). This is the biggest risk: Codex's and OpenCode's full-screen TUIs inside
   xterm.js are unproven, so check that first.
5. Snap (stage 3).
6. Rigs (stage 4). **Beta built 2026-11-23**: save rig on a frame, open from medium (vision v1 §5).

Vision v1's open questions 1, 2, 3, 5 and 6 were answered on 2026-11-20 (see that doc):
- the pod is a normal window
- combos are `1`–`9` plus an optional letter per profile
- the pod is a dock
- **the session window is the default**, and Windows Terminal stays a real choice, not only a fallback
- Windows Terminal is picked on a settings page that holds app-wide choices only

Still open: the seam's colour (needed for snap).

## Risks (said plainly)

- **This is a rewrite.** Reid's memory says to watch "optimizing substrate instead of shipping".
  Stage 0's byte-identical `--dry` check, and keeping Python as the daily driver until stage 2, exist
  so the rewrite can't stall the launcher he uses every day.
- **Work already specced for Python** (Codex sign-in and persona, Astra's fixes, OpenCode) either
  lands in Python first and gets ported, or is frozen and built only in Rust. That's the open
  question below.
- **Terminal fidelity:** ConPTY + xterm.js is proven for Claude Code (VS Code). Codex's and OpenCode's
  full-screen TUIs need checking in stage 2.
- **Build times:** the first `cargo build` takes minutes; later builds take seconds. The UI reloads
  instantly in dev.

## Open question for Reid

Do Codex sign-in/persona, Astra's fixes and OpenCode get built in Python now (and ported), or go
straight into Rust? Recommended: Codex sign-in/persona in Python now (it unblocks the `claude`
profile); freeze the rest for Rust.
