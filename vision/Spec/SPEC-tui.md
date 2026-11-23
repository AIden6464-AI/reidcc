# SPEC: what the TUI is missing next to the GUI

Status: **PROPOSED** (2026-11-17). Nothing here is built yet.

Reid, 2026-11-17, with a screenshot of the GUI and `reid` side by side:
> "spec what your missing from useing the tui"

The TUI already shows the GUI's one screen (banner, folder, profiles + fields, command, `● ready`)
and plays the gate. This lists what you can do in the GUI but not in the TUI, from reading
`reid.py` (`TUI.run`, `TUI.edit`, `TUI.change`) against `reid_gui.py`. Ordered by how much each one
gets in the way.

## Gaps

### 1. Editing happens in a separate "settings" screen (biggest)
**GUI:** every field of the selected profile is editable right there on the one screen.
**TUI:** the fields on the main screen are read-only. `e` / → opens a different screen
(`settings · claude`, own layout, its own field order: model first, name last). That is the
"hidden in settings" pattern Reid rejected for the GUI ("why are we hiding in settings?").

**Proposed:** edit in place on the main screen.
- → or Tab moves focus from the profile list into the right pane; the focused field row gets the
  same `→` marker and highlight the list uses. ← / Esc goes back to the list.
- ↑↓ move between fields in GUI order: name, model, sign-in, persona, persona mode, proxy, tools,
  mcp, switches, extra args.
- ↵ changes the focused field. Pickers open as a short list right under the field (not a new
  screen); text fields (name, extra args, custom paths) edit inline on their row.
- Switches row: ←→ move between `memory · chrome · connectors · safe mode`, Space toggles.
  Persona mode: Space flips add/replace.
- Every change saves at once (as `TUI.change` does now) and the command line below updates.
- The `settings · name` screen goes away.

### 2. Missing actions
| GUI | TUI today | Proposed key |
|---|---|---|
| new profile (blank, named `new`) | none: `n` copies the selected profile | `n` = blank, like the GUI |
| duplicate (`<name>-copy`) | `n`, and it asks for a name first | `c` = duplicate, like the GUI (rename in the name field) |
| open reid.json | none | `j` |
| open persona | only inside the settings screen (`o`) | `o` on the main screen |
| browse persona (file dialog) | picker of ~/personas, proxy prompts, ~/mds + "type a path…" | keep the picker; add "browse…" that opens the same Windows file dialog |
| pick folder (folder dialog) | `w`: recent folders + "type a path…" | add "browse…" to the `w` list, opening the Windows folder dialog |
| open recent ▾ | inside `w` | fine as is |

### 3. A broken reid.json throws you out
**GUI:** shows the error with an `open reid.json` button and stays open.
**TUI:** `load_config` raises inside `TUI.run`, nothing catches it, `reid` exits and prints the
error. You can't fix it from the TUI.
**Proposed:** catch it in `run`, show the error on the message line with `j open reid.json · ↵
try again · q quit`.

### 4. Messages have no actions
**GUI:** the message bar can carry buttons (`open reid.json`, `pick folder`, `delete` / `keep`).
**TUI:** the flash line is text only.
**Proposed:** messages that need an action name its key on the same line (`No projects yet. w pick
folder`), and the key works while the message shows.

### 5. The command is cut off
**GUI:** the full command line.
**TUI:** one line, ending in `…`.
**Proposed:** wrap it over up to 3 lines (dim), cutting only past that.

### 6. The tab says "PowerShell"
**GUI:** the window is titled `Reidcc`.
**TUI:** the terminal tab keeps the shell's title.
**Proposed:** set the title to `Reidcc` while `reid` runs (OSC 0), restore it on exit.

### 7. Ready state only updates on a key press
**GUI:** re-checks every 3 s (e.g. Claude Code installed, folder still there).
**TUI:** re-checks when you press a key.
**Proposed:** while waiting for a key, redraw every 3 s if the result changed.

### 8. No mouse
**GUI:** everything is clickable.
**TUI:** keyboard only. Windows Terminal passes mouse clicks to apps that ask (SGR mouse mode).
**Proposed (optional):** click a profile to select it, click a field to focus it, double-click a
profile to open the gate. Keyboard stays the main way.

## Look and feel: the TUI should beat the GUI
Reid, 2026-11-17:
> "add that the gui does look or feel as nice as the gui (i lowkey want the Reidcc tui to look and feel better then the gui)"

(He means the TUI doesn't look or feel as nice as the GUI yet.) The goal isn't parity: the TUI
should be the nicer of the two. A terminal can't do the GUI's paintings at full size, so it wins
on what terminals do best: crisp mono type, instant response, every action one key away, and
motion with no lag.

### Why it feels worse today
- **L1 Flat.** Plain text straight on the terminal's background. No surfaces: fields read as text,
  not fields; the selected profile is just a `→`. The GUI has `surface-1` fields, hairline frames
  and buttons.
- **L2 No art on the screen.** The banner is three outline boxes; the GUI has the engraved folder,
  bust and emerald point.
- **L3 Static.** Nothing moves except the gate. Every key repaints the whole screen.
- **L4 One weight.** Hierarchy is grey levels only; the title and the profile name don't stand out.
- **L5 Low contrast.** In Reid's screenshot his terminal background image shows through behind the
  profile list and fields.

### Proposed
1. **A ground and surfaces.** Paint `canvas` #040404 behind the whole screen while `reid` runs (the
   gate already paints its ground, so gate and screen join seamlessly). The profile list and the
   fields sit on `surface-1` bands. The selected profile is a full-width `surface-2` band with a thin
   emerald bar at its left edge, instead of `→`. The focused field gets the same band. Panels are
   framed with sharp hairlines (`┌─┐│└┘`) in `line` #2A2724.
2. **Type hierarchy.** Bold for `Folder. Profile. Gate.` and the profile name. Tags letter-spaced
   in caps (`P E R S O N A · N Y X I E`). Labels `text-3`, values `text`, help `text-3`. One emerald
   point on screen: the ready `●` (the selection bar is the second only while it's there; see open
   question 6).
3. **Art made for the terminal.** An engraved banner in half-block text (folder → bust → emerald),
   about 8 rows, dropped when the window is short. It needs a parts sheet like the arch sheet: the
   GUI banner shrunk into cells turns to blocks.
4. **Motion the terminal does well, all short:**
   - the screen fades up from `canvas` on start and when you come back from a session (~4 steps,
     ~150 ms);
   - the selection band slides to the new row instead of jumping (1–2 in-between frames);
   - pickers unfold under their field one row at a time (~15 ms a row);
   - the ready `●` breathes slowly (two emerald tones, ~2 s) while ready, still when not ready;
   - then the gate.
5. **No flicker, no lag.** Redraw only the lines that changed, and wrap each frame in synchronized
   output (`ESC[?2026h` … `ESC[?2026l`, supported by Windows Terminal) so frames never tear. A key
   shows its result within one frame (~16 ms).
6. **Faster than the GUI.** Start typing a profile name to filter the list; `1`–`9` jump; ↵ opens the
   gate from anywhere on the screen; one key per action, confirmation only for delete; it remembers
   the last profile and field you were on.

## Different on purpose (not gaps)
- **Where the session runs.** GUI: a new Windows Terminal window, the launcher stays open. TUI: the
  same terminal, back with `/reid` or on exit. The TUI could open a new window instead (see open
  questions).
- **No hover ghost** in the TUI: a terminal has no hover. The gate itself plays.
- **TUI extras the GUI lacks:** `1`–`9` jump to a profile, and the `last main2 · 23:09 r resumes it`
  row. The GUI could get the `last` row too.

## Open questions (proposed answers in bold)
1. `n` blank + `c` duplicate like the GUI, or keep `n` = copy? **Match the GUI.**
2. Should the TUI ever open the session in a new window (like the GUI)? **No by default; maybe a
   `shift+↵` for it.**
3. Paint the TUI background `canvas` while `reid` runs, hiding the terminal's own background image?
   **Yes: the look is the point now (look and feel, proposal 1). It comes back when `reid` exits.**
4. Mouse support (gap 8): build it now or later? **Later; keyboard first.**
5. The terminal banner art (proposal 3): a new parts sheet from Reid, like the arch sheet? **Yes;
   until then keep the linework banner.**
6. Selection bar in emerald, or `text` so the ready `●` stays the only emerald point? **Emerald, thin;
   change if it reads as two signals.**

## Build order
1. Look and feel 1, 2, 5 (ground, surfaces, type, no flicker) together with gap 1 (in-place
   editing): they redraw the same screen, so build them once.
2. Gap 2 (actions), gap 3 (broken reid.json).
3. Look and feel 4, 6 (motion, type-to-filter); gaps 5, 6, 4, 7.
4. Look and feel 3 (banner art) when the sheet exists; gap 8 (mouse).
