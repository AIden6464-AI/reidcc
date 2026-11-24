# Spec: the TUI and GUI in Rust, 1:1

Status: **BUILT 2026-11-20** (see "As built" at the end). This is stage 1 of `SPEC-rust-rewrite.md`.
No sign-off was recorded, but the Rust app has been what Reidcc and `reid` run since 0.2.0 (2026-11-21).
Since then Rust may differ from Python on purpose; each case is listed in the parity tests' `KNOWN`.

## Reid's words

> "um how do i launch the app? the rust versoin?" · "move the python to a /python folder" ·
> "ok 1:1 tui and gui spec that" (Reid, 2026-11-20)

## What 1:1 means

The Rust TUI and GUI look, read and behave exactly like today's Python ones in `python\reid.py`
(`TUI`) and `python\reid_gui.py` (`App`, `Gate`). They have:
- the same screens, rows, words, colours, keys and messages
- the same gate
- the same files written

Nothing new is added and nothing is "improved" along the way. The vision v1 work (three sizes,
session windows, snap) and `SPEC-tui.md`'s redesign come **after** this, on top of a launcher that
already matches.

The exact words come from the Python code and `vision\reidcc-voice.md`, not from memory. Stage 0 ported the core
(profiles, engines, memory, state, proxy) to `rs\core`, and parity holds today at 153 of 154. Both
front ends sit on that core and add no logic of their own about what a profile means.

## Order

**TUI first, then GUI.**

The TUI goes into `reid.exe`, which already exists. It is about 700 lines of Python and can be
checked automatically, screen by screen. Once it's done, `reid.exe` with no arguments is a complete
daily driver, and `/reid` lands back in a Rust TUI. The GUI is bigger (about 1,250 lines plus the
gate). It needs the Tauri shell, which doesn't exist yet.

## Part 1: the TUI in reid.exe

### What it covers

Everything `TUI` does today:
- **Main screen** (`draw_main`):
  - the banner when it fits
  - the folder row and the `last … r resumes it` row
  - the flash message
  - the profile list (the `→` marker, the emerald `●` default, scrolling with `↑↓ n more`)
  - the selected profile's rows (name, engine, model, sign-in, persona, persona mode, proxy, tools, mcp, switches, extra args)
  - Codex greying and `CODEX_TAG`
  - the command preview, or the error wrapped in oxide
  - the two help lines
  - `folder → profile → open gate` and the `● ready · …` / `● not ready` status
- **Keys:** ↵ open gate · r resume · e/→ edit · n new · x delete · d default · w pick folder ·
  m memory · 1–9 jump · ↑↓/jk move · q/esc quit.
- **The edit screen** (`edit`, `change`) with all of its pickers, the text prompts (`ask`) and `confirm`.
  This includes:
  - the model lists per engine
  - sign-in files (this needs `signin_files`, which stage 0 skipped)
  - rename, which keeps the default
  - "Claude's. Switch engine to change it."
- **The gate in text** (`gate`): the half-block frames from `assets\tui\gate_<cols>.json.gz` at the
  widest size that fits, the GUI's step times at pace 1.375, synchronized output, and any key skips
  it without reaching the session.
- **Around a session:**
  - the alternate screen on and off
  - `after_session` messages ("Back from the session. r resumes it.", "Back from Codex.", exit codes)
  - `/reid` coming back to this TUI instead of printing a message
  - Codex `/quit` coming back here too
- **Background Codex sign-in check** (`check_login`), which redraws when it finishes.
- **Saving:** the fixes from 2026-11-20 (reload after each key press, edits saved onto a fresh `reid.json`).
- **Choosing app or tool:** `reid` with no arguments picks the TUI in a terminal and the GUI when
  started as an app (`launched_from_terminal`). `--tui` and `--gui` force one.

### How it's built

It is a direct port of the Python painter: the same ANSI strings, the same full-screen repaint and the
same `fit` / `wrap_text` / `text_banner`. crossterm is used only for raw key input and the terminal
size. ratatui is **not** used for 1:1, because its own layout and diffing would make the output
differ. If `SPEC-tui.md`'s redesign needs ratatui later, it comes in then. The rewrite spec's stack
line is updated to say this. The gate frames need a gzip reader (`flate2`, already in the cargo
cache).

### Done when

`rs\tests\tui_parity.py` runs both TUIs in a pseudo-terminal at 80×24, 100×30 and 160×45. It sends
the same key sequences to each and compares the screen after every step: each cell's character and
colour, read with a terminal emulator library. The sequences are:
- every profile selected
- every edit picker opened and chosen
- new / rename / delete / default
- a broken `reid.json` while the TUI is open
- the gate skipped by a key
- a real session `--version` launch and back

The resulting `reid.json` must match byte for byte. Like stage 0, the test uses a temp copy of the
Reidcc folder and never touches the real `reid.json` or `reid_state.json`.

## Part 2: the GUI in Rust

### What it covers

Everything `App` and `Gate` do today, the same way:
- **Window:**
  - 1000 × min(880, screen − 140), centred above the taskbar, minimum 960 × 820
  - the `reidcc.ico` icon
  - the dark title bar (DWM dark mode, border, caption and text colours as in `theme_titlebar`)
- **Look:**
  - the palette tokens in `C` (from `reidcc-palette.md`)
  - fonts: Inter → Geist → Segoe UI Variable Text → Segoe UI for text; Geist Mono → JetBrains Mono → Cascadia Mono → Consolas for mono
  - the pixel sizes in `_fonts`
  - `PAD` 40
  - the banner image
- **One screen, top to bottom:**
  - title and subtitle
  - **folder** row (entry, pick folder, open recent ▾)
  - **profile** panel: the list with new profile / duplicate / delete / make default, a 1 px divider, and the fields
  - the fields: name + engine, model, sign-in, persona + browse + open persona, persona mode radios, proxy, tools, mcp, the switches checkboxes, extra args
  - the command preview
  - open memory / open reid.json / resume / **open gate**
  - the inline message bar (never a popup)
  - the footer `folder → profile → open gate` with `● status`
- **Behaviour:**
  - every change saves at once, onto a fresh `reid.json`
  - rename on Enter and on leaving the field
  - Codex greys Claude-only fields with the same reasons
  - the background Codex sign-in check
  - a not-ready profile is re-checked every 3 s
  - unique names for new and duplicate
  - delete asks inline
  - persona browse starts in `personas\`
- **Keys:** Enter (a focused button presses itself; on the list it opens the gate), Esc clears
  the message, Ctrl+Enter opens the gate, Ctrl+O picks a folder, Ctrl+R resumes. While the gate
  plays, any key skips it.
- **The gate** (`SPEC-gate.md`, as rebuilt 2026-11-19):
  - the ghost at 0.14 on hover or focus of open gate / resume
  - the opening from `assets\gate.json` and its frames at pace 1.375, with the `REIDCC · OPENING → READY` tag
  - the view through the passage into the dark
  - the session's Windows Terminal window placed over the launcher (the `WT_CELL` / `WT_CHROME` / `WT_BORDER` geometry)
  - the foreground locked so keys skip instead of typing into the session
  - click to skip
  - plays even with Windows animations off
- **Launch:** Windows Terminal (`wt -w new --pos … --size … new-tab --title "Reidcc · <name>" -d <folder>`)
  running `reid <profile>`, with `;` escaped. With no `wt`, a new console instead.

### How it's built

It uses Tauri 2 and plain TypeScript + CSS (the rewrite spec's stack), on `rs\core`.

Tauri's per-pixel transparent window lets the gate be a layer in the launcher window instead of
Tk's separate layered window. What you see must be the same. "1:1" covers the look and behaviour,
not Tk's workarounds (window alpha, colour key, click-through bits).

Folder and file pickers use the Windows dialogs, as Tk does. `open memory`, `open reid.json` and
`open persona` use the same `startfile`.

### Done when

- **Same files:** a script drives both GUIs through the same actions:
  - create, duplicate, rename, delete, make default
  - every field to every value
  - each switch

  It compares `reid.json` after each action, byte for byte, using a temp Reidcc folder.
- **Same look:** screenshots of both at the same size, side by side, for these states:
  - a Claude profile
  - a Codex profile, signed in and not signed in
  - a profile that isn't ready
  - a message with actions
  - the ghost
  - three frames of the opening
  - the dark hand-off

  Font antialiasing may differ (WebView2 vs Tk). Layout, colours, words and spacing may not. Reid
  signs these off.
- **Same flow:** the gate opens Windows Terminal like today, `/reid` comes back, and resume works.
- **Measured and written here:** the `.exe` size and cold start, as the rewrite spec asks.

## Switching over

The Python app in `app\` stays what Start Menu "Reidcc" and `reid` run until both parts pass and
Reid says to switch. The switch then:
- puts the Rust `Reidcc.exe` (GUI) and `reid.exe` into `app\`
- removes `reid.com` and `reidcc.com` there, because `.com` comes before `.exe` on PATH and would keep running Python
- keeps the Git Bash shims pointing at the new exe

PATH and the Start Menu shortcut stay as they are, because `app\` doesn't move. `python\` stays as the
fallback until stage 2, as the rewrite spec says.

## Not in this spec

- `SPEC-tui.md`'s redesign (edit in place, etc.) comes after 1:1.
- Vision v1 (sizes, session windows, Telemetry Bar, snap, rigs) is stages 2–4 of the rewrite.
- OpenCode is still an open question in the rewrite spec.

## As built (2026-11-20)

> "both use agents" (Reid, 2026-11-20)

Both parts were built at the same time by two agents. Nothing in `python\` or `app\` changed, and
neither test touched the real `reid.json` or `reid_state.json`.

**TUI** (`rs/cli/src/tui.rs`, `console.rs`; `reid.exe` is now 1.3 MB):
- `reid.exe` with no arguments opens the TUI in a terminal, or `Reidcc.exe` when started as an app.
  `--tui` and `--gui` force one. `/reid`, `--resume` and Codex `/quit` come back to the TUI.
- Keys are read the way Python's `msvcrt` does (`getwch` / `kbhit`), directly on Win32. crossterm
  isn't used: it isn't in the cargo cache, and this way the keys behave exactly like Python's.
- `rs/tests/tui_parity.py` drives both TUIs in a pseudo-terminal at 80x24, 100x30 and 160x45 and
  compares every cell (character, colour, attributes) after every key, plus `reid.json`,
  `reid_state.json` and the exit code. Result: **48 of 48 identical**, no accepted differences. The
  only masking is the time on the "last" row.
- Not parity-tested: `reid` with no arguments when started as an app, because Python would open its
  own window.

**GUI** (`rs/app/` Tauri 2.12.5, `rs/ui/` TypeScript + Vite; `Reidcc.exe` is 9.3 MB, window shown in
about 0.6 s):
- `rs/tests/gui_parity.py`: **175 of 175** actions left `reid.json` byte-identical between the two apps.
  The actions covered new, duplicate, rename (including a refused one), every engine, every field value,
  both persona modes, each switch, default and delete, on Claude and Codex profiles.
- `rs/tests/gui_shots/`: side-by-side screenshots for each state the spec lists. Layout, sizes and colours match.
  The letters themselves are drawn slightly differently (WebView2 vs Tk), and a few edges are off by 1 px.
  The gate opening and the dark hand-off match pixel for pixel. **Reid signs these off.**
- `rs/tests/gui_flow.py`: open gate starts `reid.exe <profile>` in a Windows Terminal window over the
  launcher; resume starts `reid.exe --resume <profile>`.
- Not compared: tab order, keyboard paths, mouse wheel, the drop-down lists, the open recent menu, the
  title bar.

Stage-0 parity on the combined build is still 153 of 154, 0 differ.
