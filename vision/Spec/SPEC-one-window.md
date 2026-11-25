# SPEC: one window (Reidcc comes to the session, not the other way round)

Status: **SPEC, not built** (2026-11-25). It follows a review of every part of the app that opens on its
own instead of staying in the session window. It builds on `SPEC-one-look.md`: Part 3 there (the
borderless launcher) makes step 2 here seamless.

> "Review every ui part that opens up that isn't streamlined like the Reidcc session terminal because
> it's own unit when you type "/reid or there should be a button for a sidebar of like medium Reidcc or
> full but in the app not a outside part etc" (Reid, 2026-11-24)

> "Spec the ui fix's and the whys and step by step how it would work and be smooth" (Reid, 2026-11-25)

## The problem in one paragraph

The session window and the launcher are two separate places, and every way between them closes one and
opens the other. `/reid` ends Claude, closes the session window and pulls the launcher window forward from
behind (`sess_close` in `rs\app\src\session.rs`). Codex's `/quit` and a clean exit do the same. The
launcher can't be reached from a session at all: no button, no key. So settings and plugins can't be
reached from a session either, yet the plugins row says "use /plugin in a session". And because sessions
open on top of the launcher (`sizes::session_rect`), the launcher spends its life hidden behind them.

## What every surface does today, and what this spec does with it

| # | Surface | Today | This spec |
|---|---|---|---|
| 1 | `/reid` in a session window | Ends the session, closes the window, the launcher jumps forward from behind | **Fix 2**: the window you're in turns into Reidcc |
| 2 | Codex `/quit`, a clean exit | The same, 1.5 s later | **Fix 2**, the same way |
| 3 | The launcher | Its own window, behind the sessions | **Fix 1**: it comes into the session window, beside it or full |
| 4 | Settings, plugins | Only from the launcher | Free with fix 1: settings is part of the launcher page |
| 5 | Snapped frames, rigs | Inside the app | **Fix 3**: the launcher docks there too |
| 6 | open gate from the docked launcher | n/a | **Fix 4** |
| 7 | The pod | Its own see-through window | Stays. Only its window can be see-through around the capsule. Fix 5 sets how it gets along with docking |
| 8 | File pickers (pick folder, persona, location `change`) | The Windows dialog | Stays: Windows draws it, so it can't take Reidcc's look, and the recent-folders menu covers the quick case. Fix 1 changes only which window owns the dialog |
| 9 | open memory / config / persona | `$EDITOR` or the file's default program | Stays. Reidcc isn't an editor, and `$EDITOR` is your choice |
| 10 | Locations `open` | Explorer | Stays |
| 11 | "sessions open in: Windows Terminal" | The session runs in Windows Terminal, `/reid` returns to the TUI there | Stays: you chose it. The TUI's look is `SPEC-one-look.md` Part 6 |
| 12 | A failed start | A black window for one line | `SPEC-one-look.md` Part 7.5, unchanged |
| 13 | The update installer | Not checked | Not part of this spec |

## The idea: one launcher, and it comes to you

There is still exactly **one** launcher page (`index.html`, with its state and its settings). It no longer
lives in one window. It lives in one of two places:

- **Home**: the launcher window, as today. It shows when no session is open, and at start.
- **Docked**: inside the session window you called it from, either **beside** the terminal (a column on
  the left, under the RC mark) or **full** (it takes the whole window and the terminal waits behind it).

It moves between them; it is never copied. What you typed in the folder box, the selected profile and an
open settings page all go with it.

**Why move it and not open a second copy in each session window:**
- One copy has one state, so two copies can never disagree about the profile list.
- The page is already loaded and drawn. Moving it shows it on the next frame, with no load and no white
  flash. A new page would take a few hundred milliseconds the first time.
- It already works this way for session panes: `dock::transfer` moves a pane's page into a frame with
  `Webview::reparent`, and moves it back.
- Memory: one launcher page, not one per open session.

**Why the launcher page fits a column without new layouts:** the page already picks its layout from its
own size (`main.ts`, `view()`: main when the wide layout fits, else medium, else small). A 500 px column
gets the medium form, a whole window gets main, a short column gets small.

## The keys and the button (the same meaning everywhere)

| Input | In a session window | In the docked launcher | At home (today) |
|---|---|---|---|
| Click **RC** (session bar) | open beside; again: full; again: close | n/a | n/a |
| **Alt+2** | open beside | go to beside (from full) | medium/small size |
| **Alt+1** | open full | go to full | main size |
| **Alt+3** | n/a | close it, then fold to the pod | fold to the pod |
| **Escape** | n/a (Claude's own) | one layer back: popup, then settings, then message, then close | as today |
| `← <session>` (docked head) | n/a | close it, back to the terminal | n/a |

**Why these keys:** Alt+1 and Alt+2 already mean "the big one" and "the form" at home, so they mean the same
when docked. Escape already steps back through popups and settings, so closing the dock is just one more
step. **RC** is the mark you already look at for "Reidcc", so it becomes the button.

The session page catches Alt+1 and Alt+2 before the terminal (xterm's `attachCustomKeyEventHandler`, which
already catches copy, paste and zoom), so they never reach Claude. Every other key still goes to Claude. The
docked launcher is a separate page with its own focus, so typing in it never reaches the terminal.

## Fix 1. Beside and full, in a session window

### Beside, step by step (click RC or press Alt+2)

1. The session page sends `dock_open { id, mode: "beside" }`.
2. The backend remembers the session window's rect and whether the home window was showing.
3. **The window grows to the left by the column's width** (500 logical px, `sizes::MEDIUM.0`). The
   terminal stays exactly where it was on screen, at exactly its size. If there's no room on the left,
   the whole window moves right as far as needed. Moving the window never changes the terminal's size.
   Only when the screen is narrower than window plus column does the terminal give up width.
4. In the same step, the launcher's page moves into the session window as the left column. The terminal
   pane moves right by the column's width inside the window, so on screen it doesn't move. The home window
   hides; with its page gone it would just be an empty frame.
5. The launcher page gets `docked = "beside"`. Its layout picks medium (or small if the window is short).
   Its contents slide in: 160 ms, 24 px from the left plus a fade, `cubic-bezier(0.16, 1, 0.3, 1)` from the
   design doc. With "reduce motion" on, it just appears.
6. Focus goes to the profile list.

### Full, step by step (click RC again, or press Alt+1)

1. The column widens to the whole window in one step. The page's layout becomes main, using the slide the
   page already uses between sizes (`push()` in `main.ts`).
2. The terminal pane is **hidden, not resized**. The PTY keeps its size, Claude keeps writing into the
   hidden terminal, and coming back costs no redraw.
3. The docked head shows the window controls (– ☐) and a drag area, because the session bar is covered.

### Closing, step by step (RC a third time, Escape, `← claude · kiln`)

1. The launcher's contents slide out (the same 160 ms, reversed).
2. Its page goes home. The window goes back to **exactly** the rect it had before, so the terminal never
   moved. If home was showing before, it shows again where it was.
3. Focus goes back to the terminal.

### The docked head (the launcher's own top row while docked)

The column has no window chrome of its own, so the page draws a 36 px row that lines up with the session
bar: `RC` in linework, then `reidcc` and `← claude · kiln` (the session it sits beside). In full mode it
adds – ☐ and the drag area.

There's **no ×** in the docked head. **Why:** × on a session window ends the session, and from inside
Reidcc you should never end a session by accident. Ending stays the session bar's ×.

### Why it's smooth

1. **The terminal doesn't reflow** when Reidcc opens beside it (the window grows) or full (the terminal is
   hidden, not resized). A resize makes Claude Code redraw its whole screen, and doing that on every frame of
   a slide would smear the screen and the scrollback. When a resize can't be avoided (no room on screen),
   it happens once, at the end, never during the motion.
2. **The window changes in one step; the motion happens inside the page.** Moving a native window
   frame by frame while also moving the panes inside it can wobble for a frame, because the two updates
   don't land together. A CSS slide inside an already-placed page doesn't.
3. **Nothing new is created on the press.** No window, no page: the launcher page is already loaded.
4. **Closing puts the window back exactly where it was**, so the terminal never moves.
5. **Focus follows you**: in to the profile list, back to the terminal.
6. **Keys never leak.** Alt+1/2 are caught before Claude, and the launcher has its own focus.

## Fix 2. A session that ends turns its window into Reidcc

Today, after `/reid`, `/quit` or a clean exit, the window closes and the launcher pops up from wherever
it was. New:

1. The session ends exactly as now. Nothing changes in `reid.exe` or the `/reid` slash command; the TUI
   path stays as it is.
2. `session.ts` gets the exit (`back`, or a clean end) and sends `sess_back { id }` instead of
   `sess_close`.
3. **A window of its own:** the home window moves to the ended window's rect (while it's still hidden),
   shows itself on top of it, and then the session window is destroyed. The launcher page is already
   drawn, so the swap takes one frame. "Back from the session." shows in the launcher's message line, as
   today.
4. **A pane in a frame (rig):** the pane closes as now, and the launcher docks beside in that frame (fix 3).

**Why the home window takes the session's place, and not the launcher page moving into the session's
shell:** the home window carries what the app needs from "the launcher's window": its sizes (Alt+1/2),
the pod fold, and "closing it quits Reidcc". A session shell window has none of that. After
`SPEC-one-look.md` Part 3 both windows have the same borderless frame and 36 px bar, so the swap can't be
seen. Before Part 3, the home window's Windows title bar makes the content drop by about 32 px at the swap.

**Why `/reid` still ends the session (the default):** the slash command's text goes to Claude as a prompt
unless the session ends first. `reid --back` sleeps 8 s so that never happens. A `/reid` that only opened
the panel would cost a Claude turn every time, and Claude would answer it. For "Reidcc without ending",
there's now RC and Alt+2. (Open question 1.)

## Fix 3. Frames and rigs

A frame (snapped sessions, a rig) is one window with a header and panes (`dock.rs`). The launcher docks
there the same way: a column on the left of the whole frame, before the pane tiles (`layout()` keeps the
column's width aside, then tiles the rest as now). Full hides every pane. The frame header's "save rig"
leaves the launcher out of the saved rig (`rig_of` gets no leaf for it).

## Fix 4. open gate from the docked launcher

1. Beside: medium's emblem opening plays in the column. Full: main's gate plays in the whole window. Both
   are the openings that exist today, played in the launcher page wherever it is.
2. The new session's window is made hidden over the window the launcher is in (today: over the launcher
   window), and the hand-off shows it, exactly as now.
3. After the hand-off, the launcher goes home (hidden). The window it was docked in shrinks back behind the
   new one, where you don't see it.

**Why a new window, not a split in the current frame (the default):** a split would halve the running
session and make it redraw, and a 500 px column is too narrow for Claude. You can still snap the new window
into a frame by dragging. (Open question 3.)

## Fix 5. The rules that keep it from breaking

1. **A window that holds the launcher is about to close** (× on the session bar, Alt+F4, the session ending,
   a frame closing): the launcher goes home first. Otherwise its page would be destroyed with the window.
   This runs in the close-requested event (`dock::window_event`), before the window goes.
2. **If the launcher page is ever lost anyway**, the home window makes a new one (`index.html`). Reidcc is
   never left without a launcher.
3. **RC in another session window** while docked: the launcher moves there. The first window goes back to
   its rect.
4. **The pod:** folding (Alt+3, or dragging small) closes the dock first, then folds as now. Unfolding the
   pod while docked brings the launcher home first.
5. **The launcher's auto-fold** (narrower than 340 × 240 folds into the pod) is off while docked: a column
   never turns into the pod.
6. **A minimised session window** gets restored before the launcher docks into it.
7. **Two screens with different scaling:** the column's width uses the scale of the screen the session
   window is on, not the home window's.
8. **Events after a move:** a page can miss an event while it moves (`session.rs` says so about channel
   output; that's why rigs don't move a live session's page). The launcher gets no stream, only events,
   but after every move it asks once for what an event could have carried: the update line
   (`update_foot`), the rigs and the session list. `group.html` already does this ("listen first, then ask",
   `dock.ts`).

## Where the code assumes the launcher has its own window

Each place below asks for "main" (the launcher's window) and must ask "where is the launcher now". They
get one helper, `launcher_window(app)`: the window the page is in.

| Where | What it does | Change |
|---|---|---|
| `main.rs` window build | `WebviewWindowBuilder` "main": one window, one page | A plain window plus a child page labelled "main" (as session windows are built), so the page can move |
| `main.rs` `parent()` (used by `settings.rs` too) | Owner of the file pickers | The launcher's current window. Today's would leave the picker owned by the hidden home window, so it could open behind |
| `main.rs` `go_now` | Opens the new session over `gate::main_hwnd()` | Unchanged once `gate::MAIN` follows the launcher (next row) |
| `main.rs` setup, `gate::MAIN` | The launcher window's handle, for the gate and for placing sessions | Set again on every move to the window the launcher is in. `gate.rs` (3 places) and `rig.rs` follow by themselves |
| `main.rs` `show()` | Shows the home window after the first paint | The home window by its label |
| `session.rs` `sess_close` | Shows the home window and sends it the note | Fix 2, `sess_back`. The note is sent to the page "main" wherever it is |
| `sizes.rs` `set_size` | Alt+1/2 resize the home window | When docked: switch beside/full instead |
| `sizes.rs` `pod_fold` / `pod_unfold` | Hide/show the home window around the pod | Fix 5.4 |
| `sizes.rs` `window_event` | Closing home quits Reidcc, and takes the pod with it | Unchanged for home. Windows holding the launcher: fix 5.1 |
| `rig.rs` `emit_to("main")` (2), `session.rs` `emit_to("main")` | Events to the launcher | Unchanged: they target the page's label, which stays "main" |
| `main.ts` | Alt+1/2/3, Escape, auto-fold | `docked` mode: the keys table, fix 5.5, the docked head |
| `session.ts` | RC is only a mark; exit closes | RC button, Alt+1/2, `sess_back` |

If Tauri won't let the window and its page share the label "main", the window becomes "home" and only its
own lookups change. Events keep going to the page "main".

## Build order (each step leaves the app working and is tested before the next)

0. **Spike** (throwaway, not committed): move the launcher page into a session window and back. Check:
   - typed folder text survives
   - an event sent right after the move arrives
   - no white flash
   - the page still gets keys

   If moving the page fails, use plan B (below) and rewrite this spec's fix 1 before building it.
1. **The launcher window becomes a window plus a page**, with `launcher_window()` and the table above.
   Nothing changes on screen. `gui_flow.py`, `sizes_flow.py`, `settings_flow.py` and `session_flow.py`
   pass unchanged.
2. **Borderless launcher** (`SPEC-one-look.md` Part 3). Not strictly needed, but it makes fix 2's swap
   invisible and lines the docked head up with the session bar.
3. **Beside** (fix 1) in a single session window, with fix 5.1–5.3 and 5.6–5.8.
4. **Full** (fix 1).
5. **Session end turns into Reidcc** (fix 2): `/reid`, Codex `/quit`, clean exit.
6. **Frames and rigs** (fix 3).
7. **open gate from the docked launcher** (fix 4).
8. **The pod** (fix 5.4, 5.5).

## Tests (`rs\tests\dock_flow.py`, new, with the `guihome` temp home like the others)

- RC opens beside: the launcher page is in the session window, the home window is hidden, and the focus is
  on the profile list.
- **The terminal's screen rect and its PTY size are the same before, during and after beside and full.**
  This is the smoothness check. It needs a test-mode count of `sess_resize` calls: zero.
- Closing puts the window's rect back exactly, and the focus back in the terminal.
- Folder text typed before docking is still there after docking and after coming home.
- Alt+1 and Alt+2 typed in the terminal never reach the PTY (`sess_write` sees nothing).
- × on the session window while docked: the launcher is home and alive (`init` answers).
- A clean exit: the home window is at the ended window's rect and says "Back from the session."
  (`session_flow.py` line 226 checks the message today; it now also checks the rect).
- No dialog test: the pickers stay as they are. The `parent()` change is checked by asserting that the owner
  window is the docked one.

## Plan B (only if step 0 fails)

Each session window gets its own launcher page, made the first time RC is pressed there and kept after
that. It asks `init` every time it opens, so it starts in step with the shared state.

Costs:
- the first press takes a few hundred milliseconds
- two launcher pages showing at once can disagree until one is reopened
- more memory per session window
- the gate has to know which page pressed it

Fix 2 doesn't depend on this: the home window swap works either way.

## Open questions (defaults if Reid doesn't say)

1. `/reid` in a session window: ends the session and the window turns into Reidcc (**default**), or opens
   the launcher beside and keeps Claude running (each `/reid` then costs a Claude turn)?
2. The column on the left, under RC (**default**), or on the right?
3. open gate from the docked launcher: a new window over this one (**default**), or a split in this
   window?
4. A session that ends inside a frame: the launcher docks beside in that frame (**default**), or the pane
   just closes and nothing else happens?
5. The vision doc's §5 says Reidcc "avoids nested tabs, floating sidebars". The docked column is fixed
   and pushes the terminal over instead of floating on top of it. It still needs Reid's OK before that
   line in `reidcc_design_motion_system.md` gets a note (default: add "a docked launcher column is not a
   floating sidebar").

## Not in this spec

- The pod, the file pickers, Notepad/`$EDITOR`, Explorer, Windows Terminal mode (the table at the top says
  why each stays).
- Plugins install/switch from settings (`SPEC-plugins.md`, palette §5).
- The update installer's window: not checked.
