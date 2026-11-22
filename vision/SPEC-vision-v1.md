# Vision version 1: sizes, session windows, snap, headless, orchestrator

Status: **session window, snap, the sizes and the pod built as betas in Rust** (under the old names full / medium / mini pod; renaming to main / medium / small with the pod as a toggle is to do, see §1). These are the ideas. How they get built (the Rust
rewrite) is a separate spec: `vision\Spec\SPEC-rust-rewrite.md`. The rules here are part of the vision;
the design doc's "Vision version 1" section points here.

## Reid's words

> "So I was thinking, so I can resize it, right, into any shape. And there's three different sizes
> where we have like a mini pod where it shows the sessions and the usage. And then you can pop it out
> into the full size, but then you can make it medium where it can show like the sessions, or just be a
> quick thing where you can do like combos to open different profiles. And then also I would make it
> where when you open the gate, it's not just a terminal, it's its own like app, right? And so its own
> window, it's a Claude window or codex or whatever. And when you're in that window, you can drag it,
> and then when you have another one, you can snap it together. And when you snap that together, then
> it becomes two windows, right? And then you can, when you, if you unsnap it, or even with it while
> it's snapped together, you can size it down into add headless mode, where the headless mode shows the
> process, how long it's taking. And then you can, we can have like a orchestrator mode or something
> like that. Just add this to the vision. I'm just thinking." (Reid, 2026-11-19, to Carbon)

> "well i want the rust part one spec and the ideas in one spec and apart of the vision" (Reid, 2026-11-19)

> "And for the actual view of the terminal window, like the custom terminal window, I want it to be like
> when you're like using it to hover, like when you're moving it, it like shimmers. And then when you're close
> to the other read cc terminal, it will, on that one side, wherever side it's close to, it will like shimmer
> on that side, like kind of transparent shimmer on that side, and the other terminal will shimmer on that
> side, and it will snap together, like fuse together, and be like a big animation type thing. And this is
> why we're building in Rust. And then I, for like the pod, I was thinking of something like the iPhone, like
> the iPhone dock, or like the pill type thing when it's in like the mini version. I don't know. I don't want
> it to be just like a rounded mess." (Reid, 2026-11-19)

The ideas, one per line, so nothing gets lost:
1. **Resize into any shape, with three sizes:** a mini pod (sessions + usage), medium (sessions, or
   quick combos that open profiles), and full.
2. **The gate opens into its own app window**, "a Claude window or codex or whatever", not just a
   terminal.
3. **Drag a session window and snap it onto another**, so they become one two-window frame. They
   can be unsnapped.
4. **Headless mode:** size a window down, snapped or not, and it shows the process and how long it's
   taking.
5. **Orchestrator mode**, "or something like that" (the least defined; last).
6. **Session windows shimmer while you move them.** Near another Reidcc window, the facing side of each
   one shimmers ("kind of transparent shimmer on that side"), then they snap and **fuse** together in a big
   animation. "This is why we're building in Rust."
7. **The mini pod is shaped like the iPhone dock, or a pill**, and not "just like a rounded mess".

## Rules these must keep

- folder → profile → open gate stays the flow, at every size.
- "Simple means nothing to hunt for, not fewer things on screen." Smaller sizes are folds of the
  same window. Nothing moves into a hidden dialog, and full still shows every field.
- The palette (`#040404`, bone, one emerald at a time, oxide for errors), the gate (pace 1.375) and
  the `<engine> · <profile>` naming carry over unchanged.
- The engines' own programs (Claude Code, Codex, OpenCode) still run as themselves, with every
  slash command, login and approval prompt working.

## 1. Three sizes, and the pod

> "this is main      first image        sec is medium           small is        and pod is   (witch should be a toggle not a size thange)" (Reid, 2026-11-22, with four screenshots: the wide layout, the form, the folder / sessions / combos layout, and the pod)

The sizes are **main**, **medium** and **small**. The **pod** is a toggle, not a size:

| Name | Was | Shows |
|---|---|---|
| **main** | full, wide (1000 × 880) | the profile list beside the profile's fields |
| **medium** | full's form (from 480 × 720, `Spec\SPEC-form.md`) | the same things in the old launcher's tall, narrow form |
| **small** | medium (380 × 320) | folder, `sessions`, `combos` |
| **pod** (toggle) | mini pod, the third size | the capsule. Toggling folds the launcher from any size; toggling again brings it back at the size it was. Dragging the window small doesn't fold into it |

**Not built yet** (palette §5): the app still names them full / form / medium, `Alt+1` is full, `Alt+2` is
today's medium (small), no key goes to the form, and `Alt+3` or dragging under 340 × 240 folds into the
pod. The rest of this section describes what's built, with the old names.

The window size is the mode. Dragging an edge or corner moves between sizes at two thresholds, and
`Alt+1/2/3` jumps straight to one.

| Size | About | Shows |
|---|---|---|
| **Full** | today's 1000×860 | everything today's GUI shows |
| **Medium** | semi-mini, 380×320 (was ~520×420; see below) | folder + recents, the session list, and **combos**: one keystroke per profile to open the gate on the current folder. `1`–`9` work in profile order, and a profile can also have its own letter (Reid: "Find a both", 2026-11-20) |
| **Mini pod** | ~300×120 proposed, built 320×64 (see below); a normal window: not on top unless you pin it (Reid, 2026-11-20) | running sessions (`codex · main ●`) and **usage**: for Claude, the context % and limit % that Reidcc's statusline already collects; for Codex and OpenCode, elapsed time until they expose usage |

The motion between sizes follows the design doc: no bounce, 120–180 ms, ease
`cubic-bezier(0.16, 1, 0.3, 1)`.

**Full and medium built 2026-11-20** in the Rust app only. Reid: "fix 1 and 2 also lets start on the windows sizeing".
- The page picks its layout from its own size. It's full while the full layout fits (960 × 820, or less on
  a short screen), and medium below that. Dragging an edge across that line switches it. The second
  threshold is under 340 × 240: let go there and it folds into the mini pod.
  - Built 2026-11-22 (`vision\Spec\SPEC-form.md`): a tall, narrow window (from 480 × 720) keeps full as the
    old launcher's form instead of dropping to medium; medium is only for windows smaller than that. Views push
    (`240ms`) instead of cutting. See "Vision version 1" in the design doc.
    > "old vs new in the same form    can we meger the uis for the 2.0  because i like the form facter also can we have the ui like slide in to the other veiw not just switch" (Reid, 2026-11-22, with a screenshot of the old Python launcher beside Reidcc 0.2.0 at the same tall, narrow window size, where 0.2.0 showed medium)
- `Alt+1` and `Alt+2` ease the window to full (1000 × 880) or medium (380 × 320) in 160 ms with the
  design ease. The top-left corner stays put unless the new size would go off screen.
- Medium is semi-mini, changed 2026-11-21:
  > "The medium is to medium can we make it simi-mini" (Reid, 2026-11-21)

  It was 520 × 420 with empty space below the combos. Now it's 380 × 320 with 16 px edges. It has no
  `folder` label and no `folder → profile → open gate` hint, and the message bar takes no room until
  there's a message. All nine combos still fit, in two columns.
- Medium has the folder row (the same field, pick folder and open recent), then `sessions`, then `combos`.
  - `sessions` lists the session windows that are running, as `<engine> · <profile>  ● running · 01:42`.
    Failed sessions show oxide. With nothing running it says `No sessions running.` Clicking a row brings
    that window or its frame forward.
  - `combos` lists the first nine profiles in order. Pressing `1`–`9` (when the cursor isn't in the folder
    field) or clicking a combo selects that profile and opens it on the current folder.
- At medium the gate doesn't play. The session window opens at once at full size, centred on the
  launcher and kept on screen.
- not yet: a letter per profile for combos, and Windows Terminal sessions in the list (only session
  windows show).
- checked by `rs\tests\sizes_flow.py`

**Mini pod built 2026-11-20** in the Rust app only. Reid: "do the mini pod next".
- `Alt+3`, or dragging the launcher under 340 × 240 and letting go, folds the launcher into the pod at
  its top-left corner. The capsule fades in over 150 ms.
- It's **64 px tall** and 320 px wide or more, growing with its slots. That's thinner than the ~120 in the
  table above, so it reads as a dock and not a ball. Reid can still pick the height.
- The capsule follows "The mini pod's shape" below. Clicking a slot brings that window forward.
- More on each slot, changed 2026-11-21:
  > "For the mini pod I can have more on it" (Reid, 2026-11-21)

  Asked what to add, Reid picked the session details and usage per session, in one row that grows wider
  (not two rows). Each slot now reads `CL  main  ●  01:42 · ctx 42% · lim 61%`:
  - the engine mark (`CL` for Claude, `CX` for Codex, `OC` for OpenCode) in `text-3`, then the profile
  - `●`: emerald while running, oxide when failed
  - the elapsed time, then that Claude session's own context % and limit % once its statusline has
    written them (Codex and OpenCode show the time only). A failed session adds `code <n>`.
  - The folder shows as the slot's tooltip.

  This replaces the single usage readout at the right end and the hover name. With no sessions the pod
  says `No sessions running.`. It stays 64 px tall and grows sideways, but never past the screen's edge
  (it moves left to stay on screen).
- Drag the capsule to move it. A double-click or `Alt+1` unfolds it to full, and `Alt+2` to medium,
  from where the pod is.
- It's a normal window, in the taskbar, not on top. Closing it (`Alt+F4`) closes Reidcc.
- Built as its own borderless, transparent window that stands in for the launcher, rather than the
  launcher's window turning see-through. That would put the themed title bar at risk and make
  resizing at full size flicker. It looks and acts like one window.
- not yet: pinning it on top, and an animated fold (today the launcher swaps to the pod with a fade).
- checked by `rs\tests\sizes_flow.py` (screenshot `rs\tests\session_shots\pod.png`)

### The mini pod's shape

> "for like the pod, I was thinking of something like the iPhone, like the iPhone dock, or like the pill type
> thing when it's in like the mini version. I don't know. I don't want it to be just like a rounded mess."

- **One capsule.** The pod's outer edge is a single pill: fully round ends (radius = half its height), `surface-1`,
  a 1 px `hairline` edge. It's the only rounded shape in it.
- **Inside, it's a dock** (Reid chose the dock over a growing island pill, 2026-11-20): each running session is one slot in a row (engine mark + `●`), evenly spaced and
  split by 1 px hairlines. No rounded chips, cards or bubbles inside the capsule. That nesting is the
  "rounded mess".
- **Usage** is `tabular-nums` text inside each slot (`01:42 · ctx 42% · lim 61%`), since 2026-11-21
  ("For the mini pod I can have more on it"). Before that it was one readout at the right end.
- Each slot names its `<engine mark> <profile>`. Clicking it brings that session window forward.
- The pod is a borderless, per-pixel transparent window (the corners outside the capsule show the desktop).
  The Rust stack can do that; Tkinter can't.

## 2. Session windows

> "Wait don't do fallback only make it default" · "No the Reid session window is default" (Reid, 2026-11-20)

**The Reidcc session window is the default**: open gate opens a Reidcc window out of the gate's dark,
where the Windows Terminal window appears today. **Windows Terminal stays a real choice**, not only a
fallback. You pick it **on a settings page** ("In a settings page", Reid, 2026-11-20). The page holds
app-wide choices only; a profile's fields stay on the one screen. Each session window:
- runs the real engine in an embedded terminal
- wears the design doc's §5 layout (Telemetry Bar on top: `folder · profile · engine`, context/limit,
  elapsed), with the "Changed Rail" as a later step
- keeps today's return flow: `/reid` brings back the launcher, and resume works for Claude

Snap and headless (§3, §4) are for session windows. A Windows Terminal session can't snap.

**Beta built 2026-11-20** in the Rust app only (`rs\target\release\Reidcc.exe`; the Python app still opens
Windows Terminal). Reid: "Make a beta Terminal the "Reid session window" with stuff I designed/described".
- open gate makes the window hidden over the launcher, and the gate shows it out of the dark at the hand-off
- Telemetry Bar: `folder · PROFILE · <name> · PERSONA · <name> · ENGINE · <engine>`, then `context` / `limit`
  (from the statusline, which prints nothing inside a session window) and the elapsed clock
- the real engine (`reid.exe <profile>`) in xterm.js over ConPTY, with the drag shimmer from §3
- `/reid`, Codex's `/quit` or a clean exit close it and bring the launcher back; a failure stays open
  with its code until a key; `×` ends the session
- not yet: the settings page (until then `"open_in": "terminal"` in reid.json picks Windows Terminal),
  the Changed Rail, and a check of Codex's TUI with a real sign-in
- checked by `rs\tests\session_flow.py`

## 3. Snap: shimmer, then fuse

> "when you're moving it, it like shimmers. And then when you're close to the other read cc terminal [...]
> it will like shimmer on that side, like kind of transparent shimmer on that side, and the other terminal
> will shimmer on that side, and it will snap together, like fuse together, and be like a big animation type
> thing."

- **Moving shimmers.** While a session window is being dragged, a faint band of bone light (`#D6D0C8`,
  ~8–12% alpha, transparent) travels along its frame. It stops the moment you let go. A window that's sitting
  still never shimmers.
- **Near another window, the facing sides shimmer.** Within ~48 px of another Reidcc window's edge, the shimmer
  gathers onto the side facing it. That other window's facing side starts shimmering too, so you see
  which two edges will meet. Move away and it spreads back out.
- **Close enough, they snap and fuse.** Within 16 px (or on drop), the two edges pull together and fuse in one
  staged sequence, the second "big animation" after the gate:
  1. **Draw** `0–180ms`: the window slides the last pixels into place, and both shimmering edges brighten.
  2. **Meet** `180–360ms`: the two edges touch, and the light runs along the seam from end to end.
  3. **Fuse** `360–600ms`: the two frames become one frame. The doubled border becomes a single 1 px hairline
     between the panes, and one header strip spans both.
  4. **Settle** `600–780ms`: the light fades out. What's left is the plain welded frame.
  Like the gate, every step is within the design doc's 240 ms step budget, with no bounce, and it runs at the
  same pace setting as the gate.
- After that they **move as one frame**: two panes, one header strip. Up to 4 panes.
- Dragging a pane's header out unsnaps it into its own window again.
- Reidcc's own windows only.

**Beta built in Rust.** The facing edges preview the join within 48 px. Within 16 px they align while
dragging, and releasing within the preview range runs the bone-light fuse. The shared top strip moves
the frame and a pane's Telemetry Bar pulls that pane out. Each pane keeps its WebView, terminal buffer,
and engine process. Open the sessions from the same Rust launcher. The live test is
`.test\merge_windows.py`.

## 4. Headless mode

Below a size threshold (a pane under ~220 px tall, or a window under ~360 px wide), the terminal
gives way to a **run strip**, and the process keeps running underneath:

```
codex · main  ● running · 01:42 · "Editing src/auth.rs"
```

- **Always:** engine, profile, state (running / waiting for you / finished / failed + exit code),
  elapsed time, and the last meaningful line of output.
- **Claude, at first:** context % and limit % from the statusline.
- **Waiting for you** (an approval or question on screen) turns the dot oxide. It's the one thing
  allowed to pull attention. Detection is best effort per engine, and when unsure the strip says
  `running`.
- Growing the window brings back the live terminal at the same scroll position.

## 5. Orchestrator mode (defined later)

Reid left this open ("or something like that"). The first useful step, after 1–4 work:
- **Rigs:** a saved layout of profiles and panes on one folder (for example `claude · plan` large,
  `codex · tests` and `opencode · ui` headless). One combo opens the whole rig.
- An agent driving other panes (spawn, read status, review a diff) is a later spec, once rigs are
  used for real.

## Words (proposed; the voice guide lists them as not built)

`main` · `medium` · `small` · `pod` (a toggle, not a size; were `full` · `medium` · `mini pod` until Reid, 2026-11-22) · `combo` · `session window` · `snap` / `unsnap` · `headless` ·
`run strip` · `running` / `waiting for you` / `finished` / `failed` · `rig`

Design names, not on-screen labels: `shimmer` (the drag light), `fuse` (the snap sequence), `capsule` and
`slot` (the mini pod).

## Open questions for Reid

Answered 2026-11-20:
1. Mini pod on top by default? **No, a normal window.**
2. Combos: `1`–`9` or a letter per profile? **Both** ("Find a both").
3. Windows Terminal once session windows exist? **The session window is the default, and Windows Terminal
   stays a real choice, not only a fallback** ("Wait don't do fallback only make it default" · "No the
   Reid session window is default").
5. Mini pod: dock or island pill? **The dock.**
6. How do you pick Windows Terminal over the default session window? **On a settings page** ("In a
   settings page"). It's app-wide, not per profile.

Still open:
4. The fuse is drawn in bone light. Should the seam flash emerald for an instant, like the gate's keystone, or
   stay bone so emerald keeps meaning "alive / ready"? The beta uses bone.
