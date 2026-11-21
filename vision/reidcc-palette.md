# Reidcc — Palette & Visual Language (from the art)

Source of truth: the three images in `vision\branding\`. **The art wins.** Where this file
and `reidcc_design_motion_system.md` disagree (section 2 colors, the "no texture" rule),
follow this file until that doc is updated to match.

Values marked *sampled* were measured from the images (2026-11-17). Values marked *derived*
are steps between sampled values, or colors the art doesn't contain but the UI needs.

---

## 1. The look in one line

Engraved stone and blueprint linework on near-black, with one emerald signal.

- **Ground:** near-pure black, never blue-black.
- **Material:** warm graphite and bone (stone, marble). Grays lean warm, never cool or neutral.
- **Line:** thin warm-gray hairlines, crosshairs, circles, registration marks.
- **Signal:** a single emerald point. It means *alive / ready / open gate*, nothing else.

---

## 2. Tokens

### Ground & surfaces
| Token | Hex | Source |
|---|---|---|
| `canvas` | `#040404` | sampled: all three backgrounds (`#030202`–`#040404`) |
| `surface-1` (composer, panels) | `#0E0D0C` | derived: canvas → stone dark |
| `surface-2` (hover, dropdown, code) | `#171513` | derived |
| `stone-dark` (raised / selected) | `#292723` | sampled: arch shadow stone |

### Line
| Token | Hex | Source |
|---|---|---|
| `hairline` | `#2A2724` | derived: flow line at about 25% on canvas |
| `hairline-strong` (focus, active) | `#4A4540` | derived |
| `linework` (art-style construction lines, crosshairs) | `#928A82` | sampled: the flow line, image 1 |

### Text
| Token | Hex | Source |
|---|---|---|
| `text` (primary, titles, file names) | `#D6D0C8` | derived: marble highlight, a touch brighter than the `#C0B9B2` average, for legibility |
| `text-2` (secondary, explanations) | `#9F978E` | sampled: the `REIDCC · READY` tag, image 2 |
| `text-3` (muted telemetry, `·`, timestamps) | `#746F69` | sampled: stone mid-tone |

### Signal
| Token | Hex | Source |
|---|---|---|
| `emerald` (the `●`, ready, `+12`, open gate) | `#00C463` | sampled: dot core, image 1 |
| `emerald-hot` (focus or press flash only) | `#07E86A` | sampled: portal dot, image 2 |
| `emerald-glow` (soft halo around the dot) | `#00B15C` | sampled: dot edge, image 1 |

### Warnings (not in the art, derived from classical materials)
| Token | Hex | Use |
|---|---|---|
| `bronze` | `#C99A45` | context 75–89%, loading pulse |
| `oxide` | `#C0584B` | context 90%+, limit reached, `−4`, errors |

Use these only for warnings. The art has one color, and the UI should feel that way too.

---

## 3. Art language → UI

| In the art | In the UI |
|---|---|
| One emerald point per image | At most one emerald element visible at a time (the `●` or `open gate`). |
| Construction lines through the subject | 1px `hairline` dividers; crosshair ticks may mark the active item. |
| Circles framing each subject | A thin `linework` ring around the status dot and the app icon. |
| Corner registration marks (`+` with ticks) | Optional corner ticks on the main frame. Static, `text-3`. |
| `REIDCC · READY` small mono caps | System tags exactly like this: mono, 11px, uppercase, `text-2`. |
| Engraved texture | **Lives in the artwork only** (hero banner, splash, about). UI surfaces stay flat. |
| Serif "R" on stone | Logo and artwork only. UI type stays sans + mono. |

---

## 4. Where each image goes

- **Image 1, "Classical Blueprint Flow"** (folder → persona → ●): the launcher banner shown before anything is picked. It's the `folder → profile → open gate` flow.
- **Image 2, "Emerald Portal": the gate.** Pressing `open gate` (or `resume`) shows it full window
  while the session opens. Reid, 2026-11-17: "now opening the gate opens the gate..." Its baked-in
  `REIDCC · READY` tag is painted out of `assets\gate.png` and drawn live in the same spot:
  `REIDCC · OPENING` (bronze) → `REIDCC · READY` (`text-2`). The art's edges fade into `#030202`
  (its own background median) so it has no visible border.
  The gate fills the window: `python\build\make_assets.py` draws on image 2 at its full 1672 px and films it
  into frames the launcher's size (1000×880), framed on the monument and its lions (rebuilt 2026-11-19,
  Reid: "they're not sized right [...] it's kind of just looks like a picture").
  Its ghost (hovering `open gate` / `resume`): the gate's blueprint, its stone edges as bone lines plus
  the emerald point, at `0.14` window strength over the launcher. Opening, the gate rises out of those
  lines; the keystone's emerald glow (`#00B15C`, core `#07E86A`) flares and its light runs down the
  gate's mouldings (the same one emerald signal, travelling); the passage fills with bone `#D6D0C8`
  light that spills down the steps; the view goes through it into `#030202` dark.
- **The gate has doors, in the GUI and the TUI.** Reid, 2026-11-17, sending
  `branding\Engraved Lion Door Collection.png` and `branding\Ornate Monochrome Gothic Door Set.png`:
  > "for both the gui and tui"

  The arch's passage holds a closed pair of lion doors (laurel panel, lion knocker, studs), the two
  single leaves from the Lion Door Collection, cut from their background and fitted hinge-to-hinge
  into the passage. They're in `gate.png`, so the hover ghost's lines show them too. When the gate opens they
  swing inward on the light (to 82°: each leaf narrows, its free edge shortens, it darkens as it
  turns) while the view pushes through the passage. The TUI arch gets the same doors. The Gothic Door Set
  (closed pair, half-open pair in a frame, single leaves) is unused so far.
  > "can we make a animasion of the gate opening up pulling out the claude code ses and when you hover over the "open gate" it shows a light "ghost" of the gate over the app" (Reid, 2026-11-17)
- **Image 3, "Compass and Marble Hand":** README and marketing hero.
- **The TUI gets its own images.** Reid, 2026-11-17, after seeing the GUI art shrunk into terminal
  cells (it turns to blocks):
  > "im thinking we will need to make new images for the Tui because it's a differnet veiw and feel"

  The terminal is a grid of characters, so its art is made for that grid, not scaled-down
  paintings: same subjects, same one emerald point, drawn to read at about 100 columns.
  - **TUI gate: `branding\Engraved Arches and Pedestals.png`** (Reid sent it, 2026-11-17). A parts
    sheet: the arch unlit and with the keystone lit (matched, 384 px apart), five columns, four
    pedestals, two keystones, three sets of steps. The arch is one clean silhouette that still
    reads at ~40 terminal rows. `python\build\make_assets.py` crops both arches and builds the TUI gate
    frames from them (`assets\tui\gate_<cols>.json.gz`, half-block text, 24-bit colour). The
    columns, pedestals, keystones and steps are unused so far.
  - **TUI banner: drawn in text**, not an image: `folder` → `profile` → `●` in linework boxes
    (`#928A82`), labels in `text-2`, the `●` emerald. Sharp at any width.
- **App icon and main logo: `branding\Reidcc Logo - Engraved RC.png`** (Reid, 2026-11-17).
  Engraved stone "RC" on a classical column, emerald marble inside the R's stem and the C's
  curve, the emerald point in a ring above, construction lines, a rounded tile. It carries
  the old R mark forward in the art's language. `reidcc.ico` is cut from it by
  `python\build\make_assets.py`: the full tile from 40 px up, the RC letters alone at 16–32 px.
  Earlier, Reid on the logo:
  > "We had the main logo, which it was the ico that was in the root."

  Retired: the flat R mark (`python\build\reidcc_icon.png`, green bar `#50faa0`), the emerald
  dot-and-ring mark, and an "IR" draft that was sent by mistake.

---

## 5. Open

To do (app, proposed 2026-11-17): support Claude Code, Codex and OpenCode through profiles
without changing the gate; the engine is a profile field (the app-wide default engine sits on the settings page). Reid: "in vision(E:\reidcc\vision) let's
make a spec on makeing this tool work for codex and opencode", then "i wanted to add a engine
right not remakeing the hole app" (2026-11-18): one `engine` row, Codex first, OpenCode second.
The gate's opening line names the selected engine. Codex is built, with sign-in, persona and memory (Done 2026-11-19 below); OpenCode is not. See `vision\Spec\SPEC-codex-opencode.md`.
OpenCode: Reid, "Opencode?" (2026-11-19). Researched, not built: `opencode`/`opencode2` are one exe (2.3.0); launch with `--standalone`; model, persona and memory go through `OPENCODE_CONFIG_CONTENT`, with the prompt file in `opencode\prompts\`. See "Milestone 2, researched" in the spec.
The proxy for Codex: Reid, "ok spec doc proxys for codex that fit the idea of the claude" (2026-11-19), after his `claude` profile (codex + `proxy: capture`) was refused. Proposed in `vision\Spec\SPEC-codex-proxy.md`, not built: the same `proxy` field, picker and per-session mitmdump; `capture` saves to `proxy\codex_prompts\`, `slim` / `ultra` shorten Codex's tool descriptions; no `optimize` for Codex.
Vision version 1: Reid, "well i want the rust part one spec and the ideas in one spec and apart of the vision" (2026-11-19). Proposed, not built, in two specs. The ideas are in `vision\SPEC-vision-v1.md`: three window sizes (mini pod / medium / full), the gate opening into Reidcc's own session windows, snapping them together, headless run strips, then orchestrator rigs. How they get built is `vision\Spec\SPEC-rust-rewrite.md`: Tauri 2 + Rust, same data files, Python stays the daily driver until stage 2. Added the same day: session windows shimmer while dragged and fuse when snapped ("kind of transparent shimmer on that side"), and the mini pod is a capsule like the iPhone dock ("I don't want it to be just like a rounded mess"). The shimmer is bone `#D6D0C8` at low alpha, not emerald, so the one emerald signal keeps its meaning. Whether the fuse seam may flash emerald is open question 4 in the spec. Answered 2026-11-20: the session window is the default and Windows Terminal is picked on a settings page ("In a settings page"), the only settings page, for app-wide choices only. Built 2026-11-20 in the Rust app only ("fix 1 and 2 also lets start on the windows sizeing"): the full and medium sizes. Medium uses the same tokens: hairlines between sections, mono rows in `text-2` (`text` on hover and for the current profile), `●` emerald while running and oxide when failed. Built the same day ("do the mini pod next"): the mini pod capsule, 64 px tall, `surface-1` #0E0D0C with a 1 px `line` #2A2724 edge and fully round ends, the desktop showing outside it. Slots are split by `line` hairlines. Since 2026-11-21 ("For the mini pod I can have more on it") each slot has its engine mark in `text-3`, then the profile, elapsed time and that session's own usage in `text-2` (`text` on hover), all mono and `tabular-nums`. `No sessions running.` is `text-3`. The pod stays 64 px tall and grows wider, the layout Reid picked. Still to do: a letter per profile for combos.

To do (app, 2026-11-21): the settings page. Reid: "In the Reidcc app we do need a settings page [...] the plugin or default engine pages ya they do or switching to dev releases updates or the default for the custom Reidcc terminal or the windows default". App-wide choices only, five sections: plugins, default engine, updates (stable / dev releases), where sessions open (Reidcc's session window by default, or Windows Terminal; today `"open_in"` in reid.json), and locations, added the same day ("Default local stuff, temp files.   And the temp work the ai uses location, etc"): local data, temp files, the AI's temp work folder. Opened by a `settings` button in the bottom action row beside `open reid.json` ("on the Reidcc app we need a button for opening the settings page"). Open: moving local data needs a pointer stored outside the data folder (Reidcc has to find it before reading reid.json), so the app can't keep it in reid.json. The AI temp folder goes to each session through its environment (`TEMP`/`TMP`); check per engine that Claude Code and Codex use it. Same tokens as the launcher. Dev releases need a dev release channel, which doesn't exist yet (releases come only from `main`). See "Direction from Reid" in the design doc.

Done 2026-11-21 (app, Rust GUI; Reid: "Build"): the settings page. A `settings` button after `open reid.json` opens it in the launcher's place; `back` or Escape returns. Sessions open in (writes `"open_in"`) and default engine (writes `"default_engine"`; `new profile` makes `{"engine": "codex"}` when it's codex) work, and choosing the default removes the key. Updates shows the version and a `check for updates` button that answers in the footer. Plugins lists Claude Code's installed plugins (emerald `●` on, `text3` off), read-only. Locations shows local data, temp files and Claude Code's temp folder (`%TEMP%\claude`), each with `open`. Section labels `text3`, hairlines between sections, the scrollbar in `line`. Still to do: dev releases (shown disabled), changing locations, turning plugins on or off, a TUI way in, a settings button in the medium size. `rs	ests\settings_flow.py` 24/24.

To do (app, proposed 2026-11-17): the TUI looks and feels better than the GUI, and can do
everything the GUI can. Reid: "add that the gui does look or feel as nice as the gui (i lowkey want
the Reidcc tui to look and feel better then the gui)". In the TUI: `canvas` ground, `surface-1` /
`surface-2` bands, `line` hairline frames, a thin emerald selection bar. See `E:\reidcc\vision\Spec\SPEC-tui.md`;
none of it is built yet.

- Image 3 (compass over a lettered stone) will read as Masonic to some people. Fine as hero art; avoid it as the logo or icon.
- The banner's own emerald dot plus the `●` ready dot means two emerald points on the launcher. The banner dot counts as artwork; if it reads as two signals, desaturate the ready dot while the banner shows.

Done 2026-11-17: the design doc points here (section 2 replaced, texture only inside artwork); the launcher uses these tokens; `reidcc.ico` is the engraved RC logo.
Done 2026-11-17 (app): the launcher is one screen again: profile list + every field of the selected profile beside it, no settings view ("Direction from Reid" in `reidcc_design_motion_system.md`).
Done 2026-11-17 (app): the gate opens: hover ghost + the opening sequence that pulls the session out of the arch (§4 above, "Launcher Flow" in the design doc, `E:\reidcc\vision\Spec\SPEC-gate.md`). Built with the spec's proposed answers to its 4 open questions: ~0.9s (then 10% slower per Reid: "can we make it a little slower like 10%", then 25% slower again, GUI and TUI: "can we make it 25% slower for the gui" / "and tui"), ghost 0.14, the session lands over Reidcc at its size, Reidcc stays behind it. Reid can still change any of them.
Done 2026-11-19 (app): Codex profiles (`"engine": "codex"`), per Reid's "talk with codex in some way and build the spec". Engine box on the name row; Claude-only fields greyed (`text-3`); gate card `codex · <profile>`; resume is Claude's. OpenCode is still to do. See `vision\Spec\SPEC-codex-opencode.md`, "As built".
Done 2026-11-19 (app): sign-in, persona and memory for Codex. Reid: "we still haven't setup all of the stuff for codex support witch is first in line", building his spec ("can we spec [...] for codex the signin and persona's"; "1. In the Reidcc application folder 2.just like the Claude side 3.um like Claude engine with the idea"). Sign-in row `codex login · ChatGPT` (status checked in the background) or a `codex\*.toml` provider file; persona + memory in `codex\prompts\<profile>.md` in the Reidcc folder, nothing in `~/.codex`; add / replace Codex's prompt. Only proxy, tools, mcp and the switches stay greyed, tag `CODEX · GREYED FIELDS ARE CLAUDE'S`. See `vision\Spec\SPEC-codex-signin-persona.md`, "As built".
Done 2026-11-19 (app): Reidcc inside the Codex session. Reid: "reidcc codex launch doesn't have reidcc". Quitting Codex comes back to the TUI (`Back from Codex.`); Codex's status line shows model · folder · context · 5h · weekly; the tab reads `REIDCC · codex · <profile>`. Codex's status line can't show PROFILE / PERSONA. See the spec, "Reidcc inside the Codex session".
Done 2026-11-17 (app): the window's title bar is in the theme (Reid, sending a shot of the white Windows title bar: "can we make this if the theme?"): Windows' own title bar, coloured through DWM: background `canvas` #040404, title `text-2` #9F978E, border `line` #2A2724, dark-mode buttons. Native drag, snap and resize stay. Windows 10 shows only the dark mode, not the colours.
Done 2026-11-19 (app): the gate rebuilt in the GUI and TUI, per Reid's "review the gate animation [...] they're not sized right [...] It looks like half done" and "fix plan is go": frames fill the launcher, even motion, real light, the view goes through the passage into the dark where the session window appears (the session card is gone), blueprint ghost; TUI frames never tear. See `vision\Spec\SPEC-gate.md`, "Rebuilt 2026-11-19".
Done 2026-11-17 (app): the gate's doors, closed in the arch and swinging open on the light, in the GUI (gate, ghost, opening frames) and the TUI gate, per Reid's "for both the gui and tui".
Done 2026-11-17 (app): the TUI matches the GUI's one screen (text banner, folder, profiles + the selected one's fields, command, `● ready`) and opens the gate in text from the arch sheet, per Reid's "we will need to make new images for the Tui".
