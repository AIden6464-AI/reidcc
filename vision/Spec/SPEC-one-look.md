# SPEC: one look (the launcher, settings, TUI and session windows as one app)

Status: **BUILDING** (2026-11-24). Built: Part 1.1 (`tokens.css`), 1.2, 1.6, Part 5 (settings), Part 7.1–7.4
and 7.6 (session window; 7.1 also moves Claude's 24-bit colours into the palette, `rs\app\src\recolor.rs`,
Reid's pick of the two ways). Not built: 7.5, Parts 1.3–1.5, 2–4, 6, 8. It comes from a UI review of the Rust app
(screenshots in `rs\tests\gui_shots`, `rs\tests\session_shots`, and the Rust TUI captured at 120×40).

> "how does the UI of Reidcc feel and fit the theme and what is dumb looking like the "settings page" etc"
> (Reid, 2026-11-24)

> "Also the Reidcc terminal vs the Reidcc main don't look the same at all there different uis and designs"
> (Reid, 2026-11-24)

> "And the Reidcc session windows thange also looks different in the ui" (Reid, 2026-11-24)

> "Spec everything thange here from are chat about the ui" (Reid, 2026-11-24)

## The problem in one paragraph

Reidcc has four surfaces: the **launcher** (main / medium / small, plus settings), the **TUI** (`reid` in
a terminal), the **session window**, and the **pod**. They share words and field order, but they don't
share how they look. The art (marble, bust, emerald) says museum monument; the controls under it say a
1998 config dialog. The cause is the 1:1 port. Each surface was copied from its own ancestor and checked
against it: the window against Tk (`rs\app\src\fonts.rs` even measures Tk's text widths), the TUI against
`reid.py` cell by cell, colours included (`rs\tests\tui_parity.py`). Each page also keeps its own copy of
the colours (`style.css`, `session.css`, `pod.css`). Nobody designed the four together.

## Part 0. What stays

- The art: the folder → bust → emerald strip, the gate, the emblem opening.
- The palette and motion rules in `reidcc_design_motion_system.md` (tokens, the 240ms ceiling, the curve).
- The pod (`CL size_live ● 00:02`): the best-designed piece. Other surfaces should match it.
- The session window's frame: the 1px hairline, the 36px Telemetry Bar, the meters, the drag shimmer, the snap seam.
- The copy ("the profile reid uses when you don't name one", the rigs empty state).
- The "nothing hidden" rule: no field moves behind a menu to make a screen look simpler.

## Part 1. One foundation

1. **One tokens file.** `rs\ui\src\tokens.css` holds every token (`--canvas … --oxide`, `--emerald`,
   `--linework`, `--ui`, `--mono`, `--ease`). `style.css`, `session.css` and `pod.css` import it and drop
   their own `:root` colours. The TUI's colour constants (`rs\core\src\term.rs` and `rs\cli\src\tui.rs`)
   name the same tokens in a comment per line, as `term.rs` does now.
2. **One monospace font list.** `--mono` everywhere, including xterm (`session.ts` uses
   `"Cascadia Mono", Consolas` today).
3. **One emerald per screen**, and it means ready or live only. Today:
   - the main screen shows the hero emerald, the footer dot, and a green ring in the gate ghost
   - settings shows one dot per enabled plugin, plus the footer
   - the TUI shows the banner `●`, the default-profile `●` and the footer

   After: the footer's `● ready` (launcher, TUI) or the bar's live dot (session window, pod). The hero
   emerald rests in linework and lights only when the gate opens. The default profile is marked in bone,
   never emerald.
4. **One on/off mark:** `✓` on, `·` off (TUI and window alike). Never `☒`, which reads as "no".
5. **Button weights.**
   - primary: bone fill (`open gate` only)
   - secondary: today's dark button
   - destructive: `delete` in oxide text
   - disabled: text-3 on canvas

   `open gate` takes the disabled look while the footer says `not ready`.
6. **Focus:** a 1px `--line2` (`#4A4540`) border. The dotted Tk focus rectangle (`.btn` `--h`/`--v` in
   `style.css`) goes.

## Part 2. Six shared elements

Each is defined once and drawn natively on each surface.

| Element | Launcher (web) | TUI | Session window / pod |
|---|---|---|---|
| **Header** | engraved art strip (as now) | the half-block version of the same art, from `assets\tui\` (frames exist for the gate, not the header yet) | RC mark, 12px, in linework at the bar's left |
| **Selected row** | full-width `--stone` bar, bone text | full-width `#292723` background, bone text (today only the name gets it) | (n/a) |
| **Field row** | label `--text2` sans, value bone mono on `--s1` | label `#9F978E` (not `#746F69`), value bone on a `#0E0D0C` background | (n/a) |
| **On/off** | `✓` / `·` | `✓` / `·` | (n/a) |
| **Tags** | `main · claude · persona plain · memory`: lowercase, `--text2`, one line | same text | same text in the bar |
| **Status bar** | left: where (folder · profile · engine); right: state (`● ready`, `not ready`, update offer) | same layout, last line | the Telemetry Bar: where on the left, `● 00:19 · context 5% · limit 12%` on the right |

The static `folder → profile → open gate` footer is replaced by the status bar on every surface (it
means nothing on settings, and it never changes).

## Part 3. One window frame

- The launcher goes borderless with the session window's 36px bar: `Reidcc 0.2.2` and the RC mark on
  the left, the same `– ☐ ×` controls on the right, hairline frame. Today the launcher uses Windows' own
  title bar (DWM-themed, `theme_titlebar` in `rs\app\src\main.rs`) and session windows don't, so side by
  side (snap, rigs) they look like two apps.
- Dragging, snapping and maximize behave as they do now for session windows.

## Part 4. The launcher (main, medium, small)

1. **Controls.**
   - The profile list loses the OS scrollbar arrows (▲▼); a thin scrollbar like `.xterm-viewport`'s replaces them.
   - Dropdown arrows become one hairline chevron, not a grey box.
   - The selected radio is a filled bone dot, not the starburst.
   - Values stay mono but not bold.
2. **The gate ghost** is masked out behind the form panel (or drops to half its opacity there), so the
   fields stay readable at the moment of pressing.
3. **Not ready:** `open gate` greys out, and the error under `command` names its way out as an action
   where there is one (`copy codex login`).
4. **One place for settings:** top-right in every size (it is bottom-left in main, top-right in medium today).
5. **Medium:** right-side buttons get one width. `new` / `duplicate` / `delete` sit together on the
   profile row; today `duplicate` is on the name row.
6. **Small:**
   - "combos" becomes "profiles", with the 1–9 keys shown as they are now.
   - The folder field cuts from the left (`…/my-project`), not the right (`C:/Temp/reidgui_i`).
7. **The `CODEX · GREYED FIELDS ARE CLAUDE'S` tag** goes. Greyed fields show a one-line hint on hover
   (`Claude only`). The tag row then holds only the shared tags.

## Part 5. The settings page

Today it reads as a config dump.
- Section titles are smaller and greyer than the options under them.
- Everything is left-aligned, and the right half of the window is empty.
- Plugins are raw `name@marketplace` ids with commit hashes as versions, and read-only.
- `dev releases` is a disabled option for something that doesn't exist.
- `back` sits top-right with a dotted focus box.
- The launcher's footer shows here too.

New layout:
- `← back` top-left, title `settings` beside it. Settings still slides in from the right.
- **Two columns:** the section title on the left in bone (`--text`, 14px sans), the control on the
  right. Help text sits under the control in `--text2`.
- **Order:** sessions open in · default engine · default size · updates · locations · plugins (the list
  that grows goes last).
- **Updates:** `Reidcc 0.2.2` and `check for updates` on one row. A dev or portable copy says `updates
  come with the installed copy` in `--text2`, not "not the installed copy". `dev releases` is left out
  until it exists (it is a missing feature, not a hidden one).
- **Plugins:** one row each, `name · version`.
  - The marketplace goes in `--text3` after the name.
  - A version that is a commit hash shows as its first 7 characters in `--text3`.
  - On/off is a real toggle (the design doc already asks for this: "on or off where Claude and codex
    doesn't even know"). Until toggling is built, the row shows `on` / `off` in text, without dots.
- **No status bar** on settings. It belongs to the launcher.

## Part 6. The TUI

Builds on `SPEC-tui.md` ("Look and feel", and Reid's "i lowkey want the Reidcc tui to look and feel better
then the gui"); the six elements above are its look.

1. **Brighter:** labels, hints and the key legend move from `#746F69` to `#9F978E`. `#746F69` stays for
   separators, rules and timestamps only (palette §2). Today 633 of about 1,060 text cells use it.
2. **Surfaces:** values on `#0E0D0C`; the selected row full width on `#292723`.
3. **Header:** the half-block art replaces the box-drawing pills
   (`╭ folder ╮ → ╭ profile ╮ → ╭ ● ╮`). Below 100 columns it falls back to the pills.
4. **Fix:** the pane divider. On the header row it sits at column 10 (`profiles │  claude …`); on every
   row below, at column 23. The header row pads `profiles` to the list width.
5. The default profile's `●` turns bone, so the footer's `● ready` is the screen's one emerald.
6. `☒` / `☐` become `✓` / `·`.

## Part 7. The session window

1. **The terminal's 16 colours**, set in the xterm `theme` in `rs\ui\src\session.ts`:

   | Terminal colour | Reidcc token |
   |---|---|
   | red | oxide `#C0584B` |
   | yellow | bronze `#C99A45` |
   | green | emerald `#00C463` |
   | blue / cyan / magenta | stone tones from the bone family |
   | white | bone `#D6D0C8` |
   | bright black | `#746F69` |

   Today only background, text and cursor are set, so Claude Code's prompts show stock bright yellow,
   orange and blue. Claude Code draws some things in full RGB colour, which skips this mapping.
   - **Decided (Reid, 2026-11-24, "2"):** the session window moves every 24-bit colour to the nearest palette
     colour itself (`recolor.rs`), instead of switching Claude Code to its ANSI-only theme.
2. **The bar's left side** becomes the shared tags: folder name in bone (full path on hover), then
   `win_live · claude` in `--text2`, lowercase. Today it's
   `C:/Temp/…/work · PROFILE · WIN_LIVE · ENGINE · CLAUDE`, with labels and values in the same caps.
3. **The live dot:** an emerald `●` before the timer while the session runs, as the pod has. It's the
   screen's one emerald. Ended: no dot. Failed: as now (`failed · code 1 · any key closes` in oxide).
4. **No duplicate banner:** `reid.exe` skips `REIDCC · <profile> · /reid comes back here` when
   `REIDCC_SESSION` is set. Optional: keep `/reid comes back here` alone in `#746F69`.
5. **A failed start doesn't open a full-size black window for one line.** The launcher checks what it
   can before opening (it already runs `engines::build`). When the session still fails at once, the
   window shrinks to its bar plus the message. Also check `session_shots\failed.png`: it is entirely
   black, so the window may show nothing for a moment.
6. **The RC mark** at the bar's left (Part 2).

## Part 8. Tests

- `rs\tests\tui_parity.py`: keep the checks on keys, saved `reid.json`, editor calls and exit codes; stop
  comparing colours and layout cell by cell. The TUI's look is now this spec's, not `reid.py`'s.
- `rs\tests\gui_parity.py`: keep the `reid.json` checks. The Tk text metrics in `fonts.rs` stop driving
  layout once Part 4 lands.
- `rs\tests\gui_shots.py` and `session_flow.py` re-take their shots. Each shot is checked against this
  spec's emerald rule (one per screen).

## Build order (cheapest and most visible first)

1. Session window: the 16 colours and the shared font (Part 7.1, Part 1.2). One file.
2. `tokens.css` (Part 1.1).
3. The settings page (Part 5).
4. The on/off mark, button weights, focus and one emerald (Part 1.3–1.6).
5. Tags and status bar on all surfaces (Part 2, Part 7.2–7.4).
6. The TUI (Part 6), after relaxing `tui_parity.py` (Part 8).
7. Launcher controls and the borderless frame (Part 4, Part 3).

## Open questions (defaults if Reid doesn't say)

1. On/off mark: `✓` / `·` (default) or a small toggle?
2. The launcher borderless like session windows (default yes), or session windows get Windows' title bar?
3. The hero emerald resting in linework until the gate opens (default), or always lit as the one emerald,
   with the footer dot going bone?
4. The TUI header: half-block art above 100 columns (default), or always the pills?
