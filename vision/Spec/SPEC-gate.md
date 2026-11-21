# SPEC: the gate opens (hover ghost + opening animation)

Status: BUILT 2026-11-17 (`reid_gui.py`, class `Gate`), REBUILT 2026-11-19 (see "Rebuilt" below).
Asked by Reid 2026-11-17:
> "can we make a animasion of the gate opening up pulling out the claude code ses and when you
> hover over the "open gate" it shows a light "ghost" of the gate over the app"

Builds on what exists today (`reid_gui.py`): pressing `open gate` / `resume` swaps the window to
`assets\gate.png` (image 2) with a live corner tag `REIDCC · OPENING` → `REIDCC · READY`, starts the
session in Windows Terminal at the same moment, and returns to the launcher about 1.7 s later.

## The idea in one line
Hover: the gate's blueprint appears faintly over the app. Press: the gate rises out of its lines,
the emerald point lights and its light runs down the gate, the doors open on light, and the view
goes through the passage into the dark, where the session window appears.

---

## Part 1: the hover ghost

**Trigger.** The pointer enters `open gate` or `resume`, or either button gets keyboard focus
(Tab). Both open the gate, so both show it. Gone on leave / focus out.

**Look.** The gate's blueprint: the edges of its stone as bone lines, plus the emerald point, at
low strength over the app. No dark veil: the launcher stays fully readable underneath.
- Same size and position as the gate screen, so pressing feels like the ghost *becomes* the gate.
- Strength `0.14` (window alpha). See Open question 2.

**Timing** (design doc micro budget): fade in `140 ms` after a `60 ms` hover delay (so sweeping the
mouse across doesn't flash it); fade out `120 ms`.

**How, in Tk (Windows).** Tk has no per-widget opacity, so the ghost is its own window:
- A borderless `Toplevel` (`overrideredirect`) sitting exactly over the launcher's client area,
  `wm attributes -alpha` for strength and `-transparentcolor` for the see-through background.
- Asset `assets\gate_ghost.png`, made by `build\make_assets.py` from the closed gate frame: its
  edges (brightness gradient) drawn in bone, everything fainter than that becomes the key colour
  (`#010101`). Thin lines, so the hard colour key doesn't look jagged.
- **Click-through is required.** Without it the ghost steals the mouse, the button gets `<Leave>`,
  the ghost hides, the button gets `<Enter>` again: flicker. Set `WS_EX_LAYERED | WS_EX_TRANSPARENT
  | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` on its HWND with `ctypes` (`SetWindowLongW`). Not in the
  taskbar, never takes focus.
- Follows the main window: re-place on `<Configure>` of the root; hide on minimize, on focus loss,
  and while a menu or file dialog is open.
- Fade is `alpha` stepped by `after()` at ~16 ms per step.

## Part 2: opening the gate

Press `open gate` (or `resume`, or Enter on the profile list). **The session starts at t = 0, as
today.** The animation never delays it; it plays while Windows Terminal boots. Each step stays
inside the design doc's `240 ms` ceiling and they run back to back (Open question 1).

| Step | Time | What you see | Tag |
|---|---|---|---|
| 1. Rise | 0–180 ms | The ghost window ramps from `0.14` to `1.0` and its see-through key turns off, so the gate's dark ground covers the launcher, while the gate rises out of its blueprint: the lines give way to the stone (6 frames). If you pressed by keyboard with no ghost showing, it fades in from 0. | `REIDCC · OPENING` (bronze) |
| 2. Ignite | 180–360 ms | The emerald point in the keystone flares and settles (`emerald-glow #00B15C`, core `#07E86A`), and its light runs out from it down the gate's mouldings to the floor, leaving a low glow on them (8 frames). | OPENING |
| 3. Open and go through | 360–840 ms | The lion doors swing open on light: bone `#D6D0C8`, brightest low in the passage, a halo on the jambs, light spilling down the steps. The view pushes in, slowly while the doors open, then faster, through the passage until the light fills the window; then the light goes dark (30 frames). | OPENING |
| 4. Hand-off | at 840 ms, or when WT's window exists | The real Windows Terminal window is shown over the launcher, out of the dark. | `REIDCC · READY` |
| 5. Return | 180 ms | The gate fades out behind it, revealing the launcher with `Session open in Windows Terminal.` | – |

**READY is real.** It changes when the new terminal window actually exists, not on a timer. If WT
is up earlier, it stays hidden until the dark (step 4). If it isn't up by then, the dark frame says
`claude · main · opening…` over the folder, where the terminal's first line will be. After 8 s with
no window: `The session window didn't appear. It may still be starting.`

**Skip.** Any key or click jumps to the end: gate gone, WT raised as soon as it exists.
Enter never opens a second session (today's rule stays).

**Reduced motion.** If Windows "Show animations" is off (`SystemParametersInfo
SPI_GETCLIENTAREAANIMATION`), skip steps 2–4: static gate, tag, return. That's today's behaviour. **Not built:** see As built below.

### Where the session lands
Reidcc picks the terminal's place up front, so step 4 has a target at t = 0:
`wt -w new --pos X,Y --size COLS,ROWS new-tab --title "Reidcc · main" -d <cwd> <reidcc.com main>`.
WT 1.25.3131 (installed) has `--pos`/`--size`. Default target: centred on the Reidcc window, the
same outer size (Open question 3). `--size` is in character cells, so convert from pixels using
WT's default font metrics. Measure once on Reid's machine and keep the numbers as constants; it
only has to be close, since step 5 snaps to the real rectangle anyway.

### Finding the new terminal window
List top-level windows of class `CASCADIA_HOSTING_WINDOW_CLASS` just before launching, then poll
every 50 ms for one that wasn't there (`-w new` guarantees a new window). Don't match on the
title, because Claude Code changes the tab title. Then `GetWindowRect` it for step 5 and
`SetForegroundWindow` it (Windows allows this because Reidcc is the foreground app at that moment).

Fallback without WT (new console window): steps 1–3, then `REIDCC · READY` and step 5.

### Frames
Pre-rendered by `build\make_assets.py` at build time, not at runtime. Everything is drawn on image 2
at its full 1672 px and filmed by a camera into frames the size of the launcher's client area
(1000×880), framed on the monument and its lions, so the gate fills the window. Their edges fade into
the gate colour `#030202`, so a bigger window shows no border.
- `assets\gate_ghost.png` (Part 1) and `assets\gate.png` (the closed gate)
- `assets\gate_rise\00–05.png`, `assets\gate_ignite\00–07.png`, `assets\gate_open\00–29.png`
- `assets\gate.json`: frame size, colours, tag position, and each step's frame count and design times

46 PNGs in 256 dithered colours (looks the same on this art; ~22 MB), shipped with the whole
`assets\` folder. A frame is ~3.5 MB in memory, so the ghost, the closed gate, rise and ignite stay
loaded (the launcher idles at ~80 MB); the 30 open frames load while the gate is hovered, or while
rise and ignite play (~12 ms each), and are freed after. Playback is a `Canvas` `itemconfig(image=…)`
swap per frame, with Windows' timer at 1 ms while it plays (`timeBeginPeriod`); at the default
15.6 ms tick frames came 5–20 ms late in a sawtooth.

---

## Files
- `reid_gui.py`: `GateOverlay` (ghost + gate window, frame player, fades),
  hover/focus bindings on `open gate` and `resume`, WT window detection, the new launch command.
  It replaces today's in-window gate canvas.
- `build\make_assets.py`: ghost + frame generation.
- `build\reidcc.spec`: ship `assets\` as a folder.
- `vision\` (after it's built): design doc §4 "Launcher Flow" gets the sequence; palette §4 image 2
  gets the ghost; voice catalog gets `claude · main · opening…` and the 8 s message.

## Out of scope
- Moving or animating the real terminal window frame by frame. Resizing WT 60 times a second
  makes it reflow and flicker, which is why the terminal appears out of the gate's dark instead.
- Any sound.
- Changing what happens inside the session.

## As built (differences from the text above)
- **Doors** (Reid, 2026-11-17: "for both the gui and tui"): the passage holds the closed lion doors
  (`vision\branding\Engraved Lion Door Collection.png`, the two single leaves). Step 3 swings them
  open to 82° in perspective while the passage lights and the view pushes in. Same in the TUI gate.
- **The session window is hidden until the hand-off.** When WT is already running, its new window
  shows ~0.25 s after launch, on top of the gate. Reidcc finds it (polling every 10 ms), hides it,
  and shows it at step 5. Measured: found at ~0.2 s, hand-off at ~0.88 s, launcher back at ~1.23 s.
- **The keyboard stays with Reidcc while the gate plays** (`LockSetForegroundWindow`, unlocked at
  the hand-off). Otherwise the hidden terminal held the keyboard, so a key meant to skip would type
  into the Claude Code session.
- **No reduced-motion path.** Reid's Windows has animations turned off, so honouring
  `SPI_GETCLIENTAREAANIMATION` would have meant he never sees the animation he asked for. Any key skips it.
- The overlay is owned by the launcher window via `GWLP_HWNDPARENT` (Tk's `wm transient`
  doesn't set an owner for borderless windows, and a withdrawn transient window never maps again).
- Both play the step times above at `Gate.PACE = 1.375`: 10% slower (Reid: "can we make it a little slower like 10%"), then 25% slower again (Reid: "can we make it 25% slower for the gui" / "and tui"). The TUI gate (`TUI.gate`) uses the same pace.
  Measured then: hand-off at ~0.97 s, launcher back at ~1.36 s.
- WT geometry constants (cell 9×19, chrome 49×65, 8 px border) measured on WT 1.25.3131.

## Rebuilt 2026-11-19

> "Also, review the gate animation when you open the gate animation for both the TUI and the GUI, because
> honestly they look okay, but they're not great and they're not sized right. Like most of them, it's kind of
> just looks like a picture and like unwell done animation. It looks like half done, where it was kind of like
> just shoved there." / "fix plan is go" (Reid, 2026-11-19)

What the review found, from recorded frames: the art was a fixed 1000×563 picture centred in the
1000×880 window, with the gate itself ~120 px wide in it; the 12 open frames carried the ease inside them,
so frame 0→1 jumped (1.0→1.17× zoom, doors 0→20°) and the last 5 were nearly still; the zoom stretched
the already-shrunk image; the passage light was one flat colour; the session card was a dark box
growing out of the bright passage; the TUI's push-in cut the keystone off and its frames tore.

What changed (both GUI and TUI):
- **Sized to the window**: frames are the launcher's size, framed on the monument (Frames, above).
- **Even motion**: 30 open frames sampled evenly in time; the camera's curve moves slowly while the
  doors open and speeds up into the passage, so it builds instead of lurching then stopping.
- **Real light** in the passage (falloff, halo, spill on the steps, bloom), and the keystone's light
  running down the gate on ignite.
- **No card.** The view goes through the passage into the dark and the session window appears there,
  over the launcher. This replaces the old step 4, the card "pulling out" the session.
- **Ghost = blueprint lines**, which the gate then rises out of.
- **TUI**: the same story (fade in, ignite, open and go through, dark), 26 frames; colours rounded to
  steps of 6 so a frame needs fewer escape codes (88 KB at 100 columns, was 123 KB); each frame is
  drawn with synchronized output (`ESC[?2026h` … `ESC[?2026l`), so it's never shown half-drawn; sizes
  40–140 columns in steps of 10, plus 160 and 180.

Measured: GUI frames land a steady ~5 ms after their slot (draw time); the hand-off came at 1.19 s to
a real Windows Terminal window; a 160×45 terminal plays the 100-column art in ~1.2 s, untorn.

## Open questions for Reid (built with the proposed answers; change any)
1. **The 240 ms ceiling.** Each frame step fits, but the whole sequence runs 0.84 s of design time
   (1.16 s at the pace) (it never
   delays the session, and any key skips it). OK as the one choreographed moment in the app?
2. **Ghost strength:** `0.10` (barely there), `0.14` (proposed), or `0.20` (clearly visible)?
3. **Where the session lands:** centred over Reidcc at the same size (it visibly comes out of the
   app), or WT's own default spot?
4. After the hand-off, should Reidcc stay where it is behind the terminal (today), or minimize?

## Verify (when built)
- Hover `open gate`: ghost fades in within ~200 ms, the button stays clickable through it, no
  flicker when moving within the button, gone on leave. Same on Tab focus.
- Moving or resizing the window with the ghost showing: ghost follows. Minimize / alt-tab: ghost hides.
- Press: the session window appears over the launcher out of the dark; tag flips to READY only once it exists.
- Any key mid-sequence: jumps to the end, exactly one session opened.
- "Show animations" off: no steps 2–4.
- Start the Start Menu app through the real Explorer (see `refresh_path` in `reid.py`) and run the
  whole sequence from there, not only from a terminal.
- `reid.json` unchanged by hovering and pressing (`cmp` against a copy).
