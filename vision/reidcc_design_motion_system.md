# Reidcc — Design & Motion Guide

How Reidcc looks, moves, and holds its ground.
Pair this with `reidcc-voice.md` before building any screen, component, or animation.
Colors and the visual language come from the art in `branding\`; the tokens below are the
ones defined in `reidcc-palette.md`. If they ever disagree, the palette file wins.

---

## Direction from Reid (2026-11-17, after the first restyle)

> "if it's supposed to be simple to use, why are we hiding in settings? We had the main logo,
> which it was the ico that was in the root. I like the way the UI looks, but the functionality
> of it is worse than the original, like before this one, before this UI."

What this means for every screen:

1. **Keep the look.** Palette, banner, type, hairlines and spacing from the restyle stay.
2. **Simple means nothing to hunt for, not fewer things on screen.** Everything the original
   launcher showed on one screen stays on one screen: the profile list with
   `new profile` / `duplicate` / `delete` / `make default`, the selected profile's fields
   (model, sign-in, persona, persona mode, proxy, tools, mcp, switches, extra args), folder and
   `open recent ▾`, `open memory`, `open reid.json`, `resume`, `open gate` and the command preview.
   No separate settings view for any of that. **Exception:** app-wide choices that belong to no
   profile go on one settings page ("In a settings page", Reid, 2026-11-20).

   > "In the Reidcc app we do need a settings page but the thange you quoted about not putting stuff in a settings is because before everything was in settings all of the stuff in the page does not need to be in settings but the plugin or default engine pages ya they do or switching to dev releases updates or the default for the custom Reidcc terminal or the windows default" (Reid, 2026-11-21)

   The 2026-11-17 rule was about the old launcher, where *everything* sat in settings. The settings
   page is wanted; it just never takes what's on the main screen. It holds, each as its own section:
   - **Plugins:** installed plugins and the `reidcc` marketplace.
   - **Default engine:** which engine (Claude, Codex) a new profile starts with.
   - **Updates:** stable releases or dev releases.
   - **Where sessions open:** Reidcc's own session window (the default) or Windows Terminal.

   > "Default local stuff, temp files.   And the temp work the ai uses location, etc" (Reid, 2026-11-21)

   - **Locations:** where Reidcc keeps its local data by default (reid.json, memory, personas, prompts),
     where its temp files go, and where the AI's temp work goes (the scratch folder a session writes
     intermediate files to). Each shows the current path, with change and open buttons.

   > "on the Reidcc app we need a button for opening the settings page" (Reid, 2026-11-21)

   Built 2026-11-21 in the Rust GUI (palette §5 lists what's still to do). The way in is a plain `settings` button in the bottom action row, after `open memory` and
   `open reid.json`, in the same quiet style. No gear icon, no menu. The page replaces the launcher
   view in the same window, and `back` returns to the launcher.

   A profile's fields never move there, including which plugins *that profile* turns on.
3. **Order is how you get simplicity.** The eye and the keyboard still run
   `folder → profile → open gate`; the profile's fields sit beside the profile list, quieter (`text-2`
   labels, `surface-1` fields), so they're there when you need them and calm when you don't.
4. **The R is the main logo.** Reid's answer to this was a new logo, the engraved RC on a
   column (`branding\Reidcc Logo - Engraved RC.png`). It is the app icon. See
   `reidcc-palette.md` §4.

### The TUI should look and feel better than the GUI (proposed, not built)

> "add that the gui does look or feel as nice as the gui (i lowkey want the Reidcc tui to look and feel better then the gui)" (Reid, 2026-11-17)

He means the TUI doesn't look or feel as nice as the GUI yet, and he wants it to be the nicer of
the two. So the TUI is not a text copy of the GUI to be judged by parity: it gets its own care, and
wins on what a terminal does best: crisp mono type, instant response, every action one key away,
motion with no lag. The plan (ground and surfaces, type hierarchy, terminal-made banner art, short
motion, flicker-free redraws, type-to-filter) is in `E:\reidcc\vision\Spec\SPEC-tui.md`, "Look and feel".
Until it's built, the TUI is as described under "Launcher Flow".

### Multi-engine direction (Codex built 2026-11-19; OpenCode not built)

> "in vision(E:\reidcc\vision) let's make a spec on makeing this tool work for codex and opencode" (Reid, 2026-11-17)

The proposed extension keeps this exact screen and flow. A profile chooses Claude Code,
Codex or OpenCode in an `engine` row above `model`; there is no separate launcher or settings
view.

> "i wanted to add a engine right not remakeing the hole app" (Reid, 2026-11-18)

So the spec is now small: one `engine` check where the command is built, Codex first, OpenCode
second; OpenCode `mini`, engine-specific resume, and persona/memory for the new engines are
follow-ups (persona/memory first, since "it already knows you" is the point). The gate does not change.
Codex is built (Reid: "talk with codex in some way and build the spec", 2026-11-19): the engine box sits on the `name` row,
right above `model`, so the form keeps its height. The gate's opening line names the actual engine (`claude · main`,
`codex · main` or `opencode · main`), and unsupported engine-specific controls remain visible
but disabled with a reason (the tag `CODEX · GREYED FIELDS ARE CLAUDE'S`). Full behavior is in
`vision\Spec\SPEC-codex-opencode.md`, "As built"; OpenCode is not a current app capability.

> "can we spec [the profile form: engine codex, sign-in / persona / persona mode greyed out] for codex
> the signin and persona's" (Reid, 2026-11-19)
>
> "1. In the Reidcc application folder 2.just like the Claude side 3.um like Claude engine with the idea" (Reid, 2026-11-19)

Built 2026-11-19 (see `vision\Spec\SPEC-codex-signin-persona.md`, "As built"):
- On a Codex profile, `sign-in`, `persona`, `persona mode` and `memory` stop being greyed out. They
  use the same files and the same picker as Claude, and work the same way. Only proxy, tools, mcp
  and the switches stay Claude's.
- Everything Reidcc generates for Codex lives in the Reidcc folder (`codex\prompts\<profile>.md`),
  never in `~/.codex`.
- Memory and accounts work like the Claude side:
  - no extra folder access for memory; Codex asks by its own approval rules
  - one `codex login`, with other accounts through API provider files (`codex\*.toml`)

### Vision version 1: sizes, session windows, snap, headless (partly built, Rust app only)

> "So I was thinking, so I can resize it, right, into any shape. And there's three different sizes
> where we have like a mini pod where it shows the sessions and the usage. [...] when you open the gate,
> it's not just a terminal, it's its own like app, right? [...] you can snap it together. [...] you can
> size it down into add headless mode, where the headless mode shows the process, how long it's taking.
> And then you can, we can have like a orchestrator mode or something like that. Just add this to the
> vision. I'm just thinking." (Reid, 2026-11-19; full quote in the spec)
>
> "well i want the rust part one spec and the ideas in one spec and apart of the vision" (Reid, 2026-11-19)

Where Reidcc is going (full rules in `vision\SPEC-vision-v1.md`):
- **Three sizes, and the pod is a toggle:**
  > "this is main      first image        sec is medium           small is        and pod is   (witch should be a toggle not a size thange)" (Reid, 2026-11-22, with four screenshots: the wide layout, the form, the folder / sessions / combos layout, and the pod)

  The names are now **main** (the wide layout: the profile list beside the fields), **medium** (the form,
  the old launcher's tall, narrow layout) and **small** (folder, sessions and combos). The **pod** is not a
  size: it's a toggle that folds the launcher into the capsule and back, from any size, and the launcher
  comes back at the size it was. Dragging the window small never turns it into the pod. Not built yet
  (palette §5): the app still calls them full / form / medium, and `Alt+3` or dragging under 340 × 240
  folds into the pod. The older text below uses the old names: its "full" is main (wide) plus medium (the
  form), its "medium" is small, and its "mini pod" is the pod.

  The launcher's size is its mode. **Full** shows everything as today. **Medium**
  shows the folder, sessions and combos (one key opens a profile). The **mini pod** shows running
  sessions and usage. Smaller sizes are folds of the same window, never hidden dialogs. Full and medium are
  built, with `Alt+1` and `Alt+2` ("fix 1 and 2 also lets start on the windows sizeing", Reid, 2026-11-20).
  Medium is semi-mini, 380 × 320 with tight edges ("The medium is to medium can we make it simi-mini", Reid, 2026-11-21).
  So is the mini pod, with `Alt+3` or by dragging the launcher small ("do the mini pod next", Reid, 2026-11-20).

  > "old vs new in the same form    can we meger the uis for the 2.0  because i like the form facter also can we have the ui like slide in to the other veiw not just switch" (Reid, 2026-11-22, with a screenshot of the old Python launcher beside Reidcc 0.2.0 at the same tall, narrow window size, where 0.2.0 showed medium)

  What this means (built 2026-11-22 in the Rust app, per `vision\Spec\SPEC-form.md` after Reid rejected a first
  attempt: "ok spec doc a ui because what you made was bad bad....."):
  - **Full keeps its fields in a tall, narrow window.** Today a window narrower than the full layout drops to
    medium, so the form is gone. Instead, full has two arrangements of the same things. Wide: the profile list
    beside the profile's fields, as now. Tall and narrow: one column, the old launcher's form factor, top to
    bottom: folder row, the profile picker (a dropdown with `new profile` / `duplicate` / `delete` /
    `make default`), every field of the profile stacked (label left, field right), the command preview, then
    the action row with `open gate`. Same look, same fields, nothing hidden or moved to settings. Medium is
    only for windows too short for the form; the mini pod stays as is. No new size name: it's still `full`.
    The spec's layout copies the old form: a big wordmark, body-size labels, one roomy row per setting, a
    sentence beside each checkbox, word buttons in a right column, `open gate` last. It shows from 480 × 720
    (the old `minsize`) and scrolls below 860 tall.
    > "so it just whats on the front for Reidcc 2.0 but in that form" (Reid, 2026-11-22)

    So the column holds exactly what full shows today, nothing from the old form's extras.
  - **Views slide in, they don't cut.** Changing view (launcher ↔ settings, and the folds full ↔ medium)
    slides the new view in while the old one slides a short way out the same direction and fades. One step,
    `200ms`, the design curve, no bounce. Settings comes in from the right and `back` sends it out to the
    right. Reduced motion: a plain cut.
- **Session windows:** by default the gate opens into a Reidcc window running the real engine, with the §5
  Telemetry Bar ("No the Reid session window is default", Reid, 2026-11-20). The Windows Terminal hand-off
  stays a real choice, not only a fallback ("Wait don't do fallback only make it default").
- **Snap:** a session window shimmers (bone light, transparent) while it's dragged. Near another Reidcc
  window, the facing sides of both shimmer, then they **fuse** in a staged sequence (draw → meet → fuse →
  settle, ~780 ms, each step ≤240 ms) into one frame, and come apart again. Reid: "it will snap together,
  like fuse together, and be like a big animation type thing. And this is why we're building in Rust."
- **Mini pod shape:** one capsule like the iPhone dock, with session slots split by hairlines inside and no
  rounded chips. Reid: "I don't want it to be just like a rounded mess."
- **Headless:** a window or pane sized down becomes a run strip: engine · profile · state · elapsed
  · last line. "Waiting for you" is oxide.
- **Orchestrator:** rigs first (saved layouts opened by one combo). Agent-driven panes come later.

How it gets built is `vision\Spec\SPEC-rust-rewrite.md` (Tauri 2 + Rust, same data files). Betas are in the
Rust app only (`rs\target\release\Reidcc.exe`): session windows, snap, the sizes (built as full with its
form, and medium; to be renamed main / medium / small) and the pod. The Python app has none of it. Headless and orchestrator aren't built.

---

## 0. The Foundation (What Reidcc Is Empowered to Be)

> **You sit down. It already knows you. You build.**

Reidcc is not a "lite" wrapper, a side project, or a toy launcher. It is a **sovereign workspace**—the base layer for how you build software with intelligence that persists.

Most tools mistake clutter for power. They start clean, then bury the work under 200 switches, novelty fonts, plugin marketplaces, and loud animations until the tool gets in the way of the builder. Reidcc goes the opposite way: **high craft, zero friction, deep capability underneath.**

This is the base. As Reidcc grows—deeper memory (ACA), richer personas, sharper diffing, smarter orchestration—the surface stays calm, fast, and unreadable as "AI slop." Power scales underneath; the interface never bloats.

### The Three Pillars of the Base
1. **Sovereign Identity.** Your persona, your ACA memory, and your workflow live here. You never start from zero or re-explain who you are.
2. **Instrument-Grade Precision.** Every pixel, border, and number exists to give you awareness (`context`, `limit`, `changed`). If an element is purely decorative, delete it.
3. **Invisible Speed.** Animations exist to make state changes feel physical and immediate—never to put on a show, and never to make you wait.

---

## 1. Visual Discipline (Anti-Bloat Rules)

When an AI assistant builds UI without strict rules, it defaults to gradients, glowing neon borders, blurry glass cards, and bouncy animations. **Reidcc forbids all of these.**

| Element | Reidcc Standard | Never Do This |
|---|---|---|
| **Surfaces** | Deep, flat matte tones separated by crisp `1px` hairlines. Engraved texture lives **only inside artwork** (banner, splash, about, icon). | Heavy drop shadows, glowing cards, film grain or noise on UI surfaces, or glassmorphism (`backdrop-blur` everywhere). |
| **Typography** | Clean neo-grotesque sans for UI + sharp monospace for paths, diffs, and telemetry. | Pixel/retro novelty fonts, all-caps paragraphs, or mixing more than 2 font families. |
| **Numbers** | `tabular-nums` on every percentage, token count, line diff, and timer so layout never jitters when numbers tick. | Proportional numbers that shift neighboring text when `41%` becomes `42%`. |
| **Borders** | `1px solid` warm structural dividers (`#2A2724`). | Thick borders, animated gradient borders, or rounded-3xl pill boxes for main panels. |
| **Exceptions (vision version 1, proposed)** | Two, both from Reid (2026-11-19): the **drag shimmer** (bone light, ~8–12% alpha, only while a session window is moving or about to snap), and the **mini pod's capsule** (only its outer edge is round; everything inside stays square with hairlines). | Shimmer on a still window, an emerald or coloured shimmer, or rounded shapes nested inside the pod. |
| **Density** | Breathable center stage, compact edge telemetry. | Cramming 12 icons into the composer bar or floating toolbars over text. |

---

## 2. Color & Surface Tokens

Engraved stone and blueprint linework on near-black, with one emerald signal (see
`reidcc-palette.md` for where each value was sampled). Grays lean warm, never cool. Colors
only appear when they carry meaning.

### Ground & Lines
- **Canvas (base background):** `#040404`: near-pure black, as in the art.
- **Surface 1 (composer, panels, drawer):** `#0E0D0C`: a lift without a shadow.
- **Surface 2 (hover, dropdowns, code blocks):** `#171513`.
- **Stone dark (raised / selected):** `#292723`.
- **Hairline:** `#2A2724`: crisp `1px` structural lines.
- **Hairline strong (focus, active):** `#4A4540`.
- **Linework (art-style crosshairs, rings, corner ticks):** `#928A82`.

### Text Hierarchy (bone)
- **Primary (`#D6D0C8`):** main prose, active commands, primary buttons, file names.
- **Secondary (`#9F978E`):** subtitles, explanations, system tags, system messages.
- **Muted / Telemetry (`#746F69`):** separators (`·`, `→`), timestamps (`2h ago`), secondary metadata (`84k / 200k`).

### Signals (used sparingly; at most one emerald element visible at a time)
- **Emerald (`#00C463`):** the `●` ready dot, `+12` line additions. `#07E86A` for a press/focus flash only.
- **Bronze (`#C99A45`):** context at `75%–89%`, the loading pulse (`loading persona…`).
- **Oxide (`#C0584B`):** context `90%+`, limit reached, `−4` line deletions, errors.

---

## 3. Typography & Hierarchy

Two fonts. Strict roles.

1. **UI & Prose (`Inter`, `Geist`, or system sans):**
   - **Launcher Title:** `20px`, weight `500`, tracking `-0.02em`, line-height `1.3`. (`Open a folder. Start coding.`)
   - **Body / Session Text:** `14px`, weight `400`, line-height `1.6`. Comfortable reading width (`65ch–72ch` max).
   - **Buttons & Controls:** `13px`, weight `500`, lowercase (`pick folder`, `open gate`, `view diff`).

2. **Telemetry, Paths & Code (`Geist Mono`, `JetBrains Mono`, or system mono):**
   - **System Tags:** `11px`, weight `500`, uppercase, tracking `0.04em` (`PROFILE · KURE`, `ACA · 214`).
   - **Meters & Paths:** `12px`, weight `400`, `font-variant-numeric: tabular-nums` (`~/projects/kiln`, `context 42%`, `Nav.tsx +12 −4`).

---

## 4. Motion Physics ("Not Slow, Not Fast, Never Overdone")

Animations in Reidcc feel like a well-machined hardware switch. Nothing floats, bounces, or lingers. Every transition must obey these exact timing and curve constraints:

### Core Timing Rules
- **Micro-interactions (hover, press, focus, pill appear):** `120ms – 150ms`
- **Panel & Drawer transitions (Changed files drawer, dropdowns):** `180ms – 220ms`
- **Hard Ceiling:** No UI transition in Reidcc may ever exceed `240ms`.
- **Sequences:** the gate opening, and (proposed, vision version 1) the snap **fuse**, are staged sequences,
  not single transitions. Each step stays within `240ms`, and the steps run back to back at the gate's pace
  setting.
- **View changes slide (built 2026-11-22, `SPEC-form.md` Part 4):** launcher ↔ settings and `Alt+1` / `Alt+2`
  push: the old view slides out as the new one slides in, `240ms`, no fade; dragging an edge cuts; reduced motion cuts; see "Vision version 1" ("can we have the ui like slide in to the other veiw not just switch").
- **Primary Easing Curve:** `cubic-bezier(0.16, 1, 0.3, 1)` — Instant initial velocity, smooth deceleration, **zero overshoot/bounce**.

### Specific Choreography

1. **The Startup Sequence (`loading persona…` → `loading memory…` → `ready`)**
   - **No full-screen spinners or skeleton walls.**
   - Inside the status bar, the status text transitions vertically: old text fades out and moves `-4px` on the Y-axis while new text fades in from `+4px` over `140ms`.
   - The `●` glyph softly pulses in bronze (`#C99A45`) during loading, then locks into solid emerald (`#00C463`) on `ready`.
   - Only show the steps the profile actually has: no persona, no `loading persona…`.

2. **Launcher Flow (`folder → profile → open gate`)**
   - One screen: folder row, profile list, the selected profile's fields, `resume` / `open gate`, and the `settings` button beside `open reid.json`. Nothing a profile has goes behind a settings view; only app-wide choices (plugins, default engine, updates, where sessions open, locations) live on the settings page.
   - Selecting a folder snaps the path into place immediately; the profile selector highlights automatically for keyboard continuity.
   - Hovering (or tabbing to) `open gate` or `resume` shows a light ghost of the gate over the launcher:
     the gate's blueprint lines and its emerald point, at `0.14` strength, after a `60ms` delay, fading in over `140ms` and out
     over `120ms`. The launcher stays fully readable and clickable through it.
     > "can we make a animasion of the gate opening up pulling out the claude code ses and when you hover over the "open gate" it shows a light "ghost" of the gate over the app" (Reid, 2026-11-17)
   - Pressing `open gate` opens the gate (Reid: "now opening the gate opens the gate..."). The session
     starts in the same moment; the gate never delays it. One choreographed sequence, about `1s`.
     The step times below are the design timings; the app (GUI and TUI) plays them 10% slower, then 25% slower
     again (`Gate.PACE = 1.375`, about 1.2 s to the GUI hand-off):
     > "can we make it a little slower like 10%" (Reid, 2026-11-17)
     > "can we make it 25% slower for the gui" / "and tui" (Reid, 2026-11-17)
     The gate fills the window: its frames are the launcher's size, framed on the monument.
     > "Also, review the gate animation when you open the gate animation for both the TUI and the GUI, because
     > honestly they look okay, but they're not great and they're not sized right. Like most of them, it's kind of
     > just looks like a picture and like unwell done animation. It looks like half done, where it was kind of like
     > just shoved there." / "fix plan is go" (Reid, 2026-11-19)
     1. **Rise** `0–180ms`: the dark ground covers the launcher while the gate rises out of the ghost's
        lines into stone. Tag `REIDCC · OPENING` (bronze).
     2. **Ignite** `180–360ms`: the emerald point in the keystone flares and settles, and its light runs
        down the gate's mouldings to the floor.
     3. **Open and go through** `360–840ms`: the arch's lion doors swing open on bone light (brightest
        low in the passage, spilling down the steps) while the view pushes in, slowly, then faster,
        through the passage until the light fills the window; then the light goes dark.
        > "for both the gui and tui" (Reid, 2026-11-17, sending the door images)
     4. **Hand-off**: the real Windows Terminal window appears over the launcher, out of the dark. Until
        then it's kept hidden (Claude Code is already starting in it). If it's late, the dark says
        `claude · main · opening…` where its first line will be. The tag flips to `REIDCC · READY` only
        once that window exists.
     5. **Return** `180ms`: the gate fades out behind it, to the launcher with `Session open in Windows Terminal.`
     Any key or click skips to the end; exactly one session opens either way. While the gate plays,
     the new window can't take the keyboard, so keys skip instead of typing into the session. It
     plays even with Windows animations turned off: it's the one moment Reid asked to see.

   - **The TUI (`reid` in a terminal) is the same screen in text.** Top to bottom: the banner
     (`folder → profile → ●` in linework boxes, dropped when the window is short), `Open a folder.
     Start coding.`, the folder row, the profile list with the selected profile's fields beside it
     (same rows as the GUI form), the command, the keys, then `folder → profile → open gate` and
     `● ready · persona + memory`. ↵ / r play the gate in text: the screen goes to the gate's dark
     ground, the arch fades in with its doors shut, the keystone lights, the doors swing open on bone
     light and the view pushes through the passage into the dark, where the session starts (~1.2 s, same
     step times and pace as the GUI, any key skips; each frame is drawn whole, never torn). Unlike the GUI it runs before the session: both need the same terminal.

3. **Pasting Screenshots (`pasted · screenshot.png`)**
   - When the user pastes an image, do not open a modal.
   - A compact mono pill (`pasted · screenshot.png`) snaps into the bottom-left of the input box in `130ms` (`opacity: 0 → 1`, `scale: 0.96 → 1.0`). Hovering the pill shows a crisp, instant thumbnail tooltip; clicking `−` removes it in `100ms`.

4. **Meters (`context 42%`, `limit 61%`)**
   - Progress bars (if shown) are `2px` thin lines paired with the text.
   - When percentages update, the bar width interpolates over `200ms ease-out`, and the digits update cleanly with `tabular-nums`.

5. **Changed Files Drawer (`changed · 4`)**
   - When `No changes yet.`, the file indicator stays tucked in the header or rail without taking up canvas width.
   - On the first file change (`Done. 2 files changed.`), the header tag ticks up and the diff list slides/expands smoothly in `180ms` without shifting the user's scroll position in the chat.

---

## 5. Spatial Architecture (The 3 Zones)

Reidcc avoids nested tabs, floating sidebars, and cluttered headers. Every session lives in three predictable zones:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ~/projects/kiln · PROFILE · MAIN · PERSONA · KURE    context 42% · limit 61% │  ← 1. Telemetry Bar
├───────────────────────────────────────────────────────┬──────────────────┤
│                                                       │ changed · 2      │
│                                                       │                  │
│   Ready. Persona and memory loaded.                   │ Nav.tsx  +12 −4  │
│   ready in 2.1s · context 0%                          │ App.tsx   +3 −1  │
│                                                       │                  │  ← 3. Changed Rail
│   [Session stream — clean, centered, focused]         │ view diff        │     (quiet until needed)
│                                                       │ undo changes     │
│                                                       │                  │
│   ┌───────────────────────────────────────────────┐   │                  │
│   │ > type, or paste a screenshot               ↵ │   │                  │  ← 2. Center Stage
│   └───────────────────────────────────────────────┘   │                  │     & Composer
└───────────────────────────────────────────────────────┴──────────────────┘
```

1. **Zone 1: The Telemetry Bar (`36px` height, `1px` bottom border)**
   - **Left:** Where you are and who is loaded (`~/projects/kiln · PROFILE · MAIN · PERSONA · KURE`). `PROFILE` is the reid.json profile; `PERSONA` is its persona file and only appears when the profile has one.
   - **Right:** Where you stand (`context 42% · limit 61%`). Hovering or clicking reveals detail (`84k / 200k`, `resets in 3h 12m`).

2. **Zone 2: Center Stage & Composer**
   - The conversation and work stream sits centered with generous breathing room.
   - System notes appear as single-line inline notes in muted mono, never as loud toast popups that block the screen. (Memory events such as `Remembered: prefers Tailwind.` arrive only once Reidcc reads ACA; today it does not.)
   - The composer sits anchored at the bottom with a crisp `1px` border, `> type, or paste a screenshot`, and zero unnecessary toolbar buttons.

3. **Zone 3: The Changed Rail (`240px–280px` width, `1px` left border)**
   - Collapsible or auto-revealing when files are modified.
   - Lists changed files in monospace (`Nav.tsx  +12 −4`), with direct actions (`view diff`, `undo changes`) right beneath.

---

## 6. Reflection & Self-Audit Rules (For AI Builders / Claude Code)

Before writing or modifying any UI code for Reidcc, run this 6-point check against your work:

1. **The Clunk Check:** Did I add a modal, a confirmation popup, or a multi-step wizard where an inline expansion or single click would work? (If yes, flatten it.)
   **The Hiding Check:** Did I move something Reid uses behind a view, menu or settings screen to make the screen look simpler? (If yes, put it back. See "Direction from Reid".)
2. **The Speed Check:** Is any transition over its budget (micro `150ms`, panel `220ms`, never more than `240ms`), or using a bouncy spring that delays user input? (If yes, tighten to `140ms` and `cubic-bezier(0.16, 1, 0.3, 1)`.)
3. **The Slop Check:** Did I sneak in a gradient, a glowing shadow, an emoji, a pixel font, engraved texture outside artwork, a color that isn't in `reidcc-palette.md`, or marketing copy that violates `reidcc-voice.md`? (If yes, strip it immediately.)
4. **The Jitter Check:** Do all dynamic numbers (`%`, token counts, line diffs, timers) have `tabular-nums` applied so the layout stays rock solid?
5. **The Keyboard Check:** Can the user move through `folder → profile → open gate` and operate the composer without touching the mouse?
6. **The Base Principle:** Does this component feel like a permanent, high-craft foundation that more capability can plug into cleanly—or does it feel like tacked-on clutter?