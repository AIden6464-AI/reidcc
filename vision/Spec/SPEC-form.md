# SPEC: the form (Reidcc 2.0 in the old launcher's form factor)

Status: BUILT 2026-11-22 (Rust app, `rs/ui/src/main.ts` `buildForm` / `placeForm` / `push`), from the second
draft with the open questions' defaults (Reid: "build with the updated spec"). As built, see "As built" at the end.

> "old vs new in the same form    can we meger the uis for the 2.0  because i like the form facter also can
> we have the ui like slide in to the other veiw not just switch" (Reid, 2026-11-22, with the old Python
> launcher beside Reidcc 0.2.0 at the same tall, narrow window size)

> "so it just whats on the front for Reidcc 2.0 but in that form" (Reid, 2026-11-22)

> "ok spec doc a ui because what you made was bad bad....." (Reid, 2026-11-22, about the first build)

> "it lots nothing like" (Reid, 2026-11-22, about the first draft of this spec, sent with the old launcher)

So: **0.2.0's main screen, the same things, laid out the way the old launcher is.** That means the old
launcher's layout, spacing, type sizes and kinds of rows, with Reidcc's colours and words. Nothing from
the old launcher's extras (theme toggle, Claude path, Tokens, Settings file, Work dir, the prompt editor,
Stats, Copy cmd).

---

## The old launcher, measured

From Reid's screenshot (the old window at 500 × 800) and `reidcc.py` (`geometry("500x800")`,
`minsize(480, 720)`, `body.columnconfigure(1, weight=1)`):

| Thing | Measure |
|---|---|
| Side edges | 20 px |
| Head | a big bold wordmark `Reidcc` (~28 px), a one-line subtitle under it in the muted colour (cut off when too long), and one small button top right (`→ Light`) |
| Head to first row | ~40 px |
| Label column | ~88 px. Labels in normal body text (Segoe UI 10), sentence words, not small caps or tiny labels |
| Row pitch | ~35 px: a 26 px field with ~9 px of air. Roomy |
| Field | starts after the label column and runs to the right edge, or to the button column when the row has a button |
| Button column | right side, ~95 px. Word buttons: `Save` `Del`, `Browse`, `Restart`, `Edit...`. Every row's buttons end on the same right edge |
| On/off settings | **each is its own row**: label (`Memory`), then a checkbox with a short sentence saying what it does (`☒ remember across sessions`) |
| Modes | a dropdown (`Prompt [Default - Claude's own prompt ▾]`), not radio buttons |
| Bottom | a separator, `Command preview` (muted) over a one-line read-only field, then one row of buttons with the main one last |

What makes it: **one thing per row, a sentence beside each checkbox, real word buttons, and room.**

## What the first build and the first draft got wrong

- The first build squeezed the wide layout into one column: 12 px labels, a 2×2 block of profile buttons,
  rows that wrapped, two ragged action rows.
- The first draft of this spec swapped the word buttons for `⋯` menus, packed the four switches onto one
  line, put the persona mode in radios and tightened the rows to 4 px gaps. That's the opposite of the old
  form, which shows everything as its own roomy row.

---

## Part 1: the layout

Default window **500 × 860**. That's the old form's width, and 60 px taller because 2.0's main screen has
more rows. It uses Reidcc's tokens: `canvas` background, `text` for values, `text-2` for labels, `line`
separators, zero radius, `emerald` only for the running signal.

```
 ┌────────────────────────────────────────────────┐
 │  Reidcc                              [settings]│
 │  Open a folder. Start coding.                  │
 │                                                │
 │  folder      [~/projects/kiln         ▾]  [browse]
 │  profile     [main                    ▾]  [new] [delete]
 │  name        [main                     ]  [duplicate]
 │  default     ☐ the profile reid uses when you don't name one
 │  engine      [claude                         ▾]│
 │  model       [sonnet                         ▾]│
 │  sign-in     [subscription                   ▾]│
 │  persona     [plain                   ▾]  [browse] [edit]
 │  prompt      [add to Claude Code's prompt    ▾]│
 │  proxy       [off                            ▾]│
 │  tools       [all                            ▾]│
 │  mcp         [your servers                   ▾]│
 │  memory      ☐ add your memory file to the session
 │  chrome      ☒ let Claude Code use Chrome      │
 │  connectors  ☒ use your claude.ai connectors   │
 │  safe mode   ☐ no CLAUDE.md files, only the MCP servers set here
 │  extra args  [                                ]│
 │ ────────────────────────────────────────────── │
 │  command                                       │
 │  [claude --model sonnet --settings <temp>     ]│
 │                                                │
 │      [open memory] [open reid.json] [resume] [open gate]
 ├────────────────────────────────────────────────┤
 │  Session window open.                   ● ready│
 └────────────────────────────────────────────────┘
```

**Measures:** 20 px edges. Label column 88 px. Rows are 26 px tall on a 34 px pitch. Button column on the
right: buttons 26 px tall, 6 px apart, right edges flush. A field with buttons ends 12 px before them; a
field without buttons runs to the edge.

**Type:** the wordmark is `Reidcc` at 28 px in `text`, the heaviest weight the UI font has. The subtitle
is body (14 px) in `text-2`, one line, cut with an ellipsis. Labels are body (14 px) in `text-2`.
Checkbox sentences are body in `text`. Fields keep 2.0's combo and entry (mono 12 px) at the short 26 px
height. Buttons are 2.0's quiet button; `open gate` is the filled one.

**Rows, and what each one does** (all of it is on 0.2.0's main screen today):

| Row | Widget | Does |
|---|---|---|
| top right | `settings` button | opens settings (where the old `→ Light` sat) |
| folder | editable combo, its list = recent folders; `browse` | the folder; `▾` replaces `open recent ▾`, `browse` replaces `pick folder`; Enter commits |
| profile | readonly combo; `new`, `delete` | picks the profile (replaces the list); new/delete as today |
| name | entry; `duplicate` | renames on Enter or leaving the field, as today; duplicate as today |
| default | checkbox + sentence | checked = this is the default profile (`make default`). Checking it moves default here; it can't be unchecked, only moved |
| engine, model, sign-in | combos | as today |
| persona | combo; `browse`, `edit` | as today; `edit` = `open persona` |
| prompt | combo: `add to Claude Code's prompt` / `replace Claude Code's prompt` | the persona mode (today's radios) |
| proxy, tools, mcp | combos | as today |
| memory, chrome, connectors, safe mode | one checkbox row each, with its sentence | as today's switches; sentences match what the engine does (`--no-chrome`, `ENABLE_CLAUDEAI_MCP_SERVERS=false`, `CLAUDE_CODE_DISABLE_CLAUDE_MDS` + `--strict-mcp-config`) |
| extra args | entry | as today |
| command | read-only one-line field, mono, selectable, scrolls sideways | the preview |
| bottom | `open memory`, `open reid.json`, `resume`, `open gate` | as today, right-aligned, `open gate` last |

The message line and the footer (`● ready`) stay as 2.0 has them. Fields an engine can't use stay visible
and greyed out, as today. Checkbox sentences go in the voice guide (§6).

## Part 2: when the form shows

Sizes stay **full / medium / mini pod**, with keys `Alt+1/2/3`. (Renamed 2026-11-22, not built yet: the form is now **medium**, the wide layout **main**, old medium **small**, and the pod a toggle; see SPEC-vision-v1 §1.) Full has two layouts of the same things:

| Window | Layout |
|---|---|
| at least 960 × 820 | wide: the profile list beside the fields, as 0.2.0 |
| narrower than that, at least 480 × 720 (the old `minsize`) | **the form** |
| smaller than 480 × 720 | medium |
| smaller than 340 × 240, let go | mini pod |

Below 860 tall the rows scroll (the settings page's scrollbar). The head and the bottom button row stay
put, so `open gate` is always on screen.

## Part 3: build

- **Its own view.** A `#form` view beside `#main` / `#medium`, built by `buildForm()`, with a grid of
  `88px minmax(0,1fr) auto`. A row without buttons spans columns 2–3. No `!important`, and no CSS fighting
  inline styles.
- **Each widget exists once.** Combos, checks and entries move into whichever view shows, as the folder row
  already moves between `#main` and `#medium`. One `apply()`, one state.
- **Two new widgets, both made from existing ones:** the switches become checkbox rows (the existing
  `Check`, with the sentence as its text), and the persona mode becomes a readonly `Combo` bound to the same
  `mode`. The wide layout keeps its radios and switch line.
- **Remove the first build:** the `column` size, `profCombo`, the `.wide` / `.plist` / `.pcmds` /
  `.wrapflex` / `.actrow` / `.actgap` / `.resume` classes, and the `body[data-size="column"]` CSS.

## Part 4: the slide

> "can we have the ui like slide in to the other veiw not just switch"

A **push**: both views move together, the old one out and the new one in, across the whole window.

- **Opening settings:** the launcher slides out to the left while settings slides in from the right.
  Back or Esc reverses it. `240 ms`, `cubic-bezier(0.16, 1, 0.3, 1)`, no fade, no bounce. The two views sit
  side by side in one track that moves, so there is no gap and no overlap.
- **`Alt+1` / `Alt+2`:** the same push. Medium comes in from the right, full from the left.
- **Dragging a window edge** across a size line: a cut, so the layout follows the hand without stutter.
- **Reduced motion:** a cut everywhere. Focus moves to the new view's first control when the push ends.

## Part 5: tests

`rs/tests/sizes_flow.py` at 500 × 860:
- the form shows; the wide list and banner don't;
- every row is 26 px tall on a 34 px pitch (none wrapped);
- all right edges match, ±1 px: field-only rows and the last button of rows that have buttons;
- labels are 14 px; the wordmark is 28 px;
- picking in the profile combo selects that profile; `name` + Enter renames; `default` moves the default
  (`reid.json` changes exactly as the wide layout's commands change it);
- the `prompt` combo and the checkbox rows change the command preview exactly as the radios and switches do;
- at 500 × 720 the rows scroll and `open gate` stays visible; `scrollWidth <= innerWidth`.

`settings_flow.py`: opening settings pushes (both views move by `translateX`), and back reverses it.
`gui_parity.py` stays 175/175, since the wide layout is untouched.

Screenshots go to `rs/tests/session_shots/form.png`, at 500 × 860 next to the old launcher at 500 × 800,
**for Reid to judge before anything is committed.**

## Open questions (Reid's call)

1. **Buttons:** square, with Reidcc's zero-radius rule (the default), or rounded like the old launcher?
2. **`default` as a checkbox row** (the default), or a `make default` button on the profile row?
3. **Wordmark:** the word `Reidcc` (the default), or the RC logo beside it?

## As built (2026-11-22)

- **No command preview in the form.** Reid, about the `command` row: "can we remove this"
  (2026-11-22). The wide layout keeps its preview. With it gone the head is back to 20 / 24 px and the
  bottom bar to 12 px; the margins in the next bullets were for the build that still had it.

- Everything in Parts 1–5, at the defaults of the open questions: square buttons, `default` as a checkbox
  row, the word `Reidcc`.
- To fit 500 × 860 without scrolling (with 2.0's message line and footer under it): head margins 14 / 12 px,
  the bottom bar 10 px above and below, 10 px above the hairline and the command, 2 px under `command`.
  Rows keep 26 px on a 34 px pitch.
- The scrollbar sits in the right edge's gutter (`scrollbar-gutter: stable`), so right edges line up when the
  rows scroll (from 720 tall).
- The window still opens at full's size; the form shows when the window is dragged narrower (or shorter)
  than full, down to 480 × 720. No key jumps to it.
- The form's opening is the emblem, not the gate (`SPEC-hand.md`, built 2026-11-22). Before that the form had
  no opening: `open gate` opened the session window straight away.
- The push slides a still copy of the old view out, so the widgets that move between layouts never leave a
  hole mid-slide.
- Tests: `rs/tests/sizes_flow.py` 45/45 (the Part 5 checks), `settings_flow.py` (the push), `gui_parity.py`
  175/175, `gui_flow.py`. Screenshot: `rs/tests/session_shots/form.png`.
