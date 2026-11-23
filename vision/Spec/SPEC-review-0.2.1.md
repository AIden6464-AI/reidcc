# SPEC: review fixes after 0.2.1 (the emblem opening and the new tagline)

Status: OPEN 2026-11-22. Nothing here is fixed yet. Source: a read-only review by Gemini 4 Neon (agy) of
commit `17973a3` (the emblem) and the uncommitted tagline change, with each finding then checked against
the code by Claude. Fix on Reid's word; tick each item off as **Done <date>** when it ships.

> "Yo open the terminal app agy and ask Gemini 4 neon to reveiw" (Reid, 2026-11-22)

> "Save as a spec doc" (Reid, 2026-11-22)

Verdicts: **real** = checked in the code or measured; **Reid's call** = a design question;
**unchecked** = plausible from the code, not tried; **out of scope** = older than this change.

## Real

### 1. The emerald goes grey while the hand and leaves grow
- **Where:** `python/build/make_assets.py` `save_frame()` (shared with the gate), used by `emblem()`.
- **What happens:** every frame is cut to 256 colours on its own (MEDIANCUT). Once the big grey hand is in
  the frame, the jewel's few green tones lose their palette slots. Measured green (`G - max(R,B)` at the
  emerald): rest 15, grow 4–6, leaves 4, then 14 at ignite. So it greys out and snaps back.
- **Fix:** give `save_frame` an optional shared palette; build one palette from the finished emblem (`lit`)
  and use it for all emblem frames. The gate keeps its per-frame palette. Rerun `make_assets.py --emblem`.

### 2. The emblem keeps 53 frames in memory from startup (~120 MB)
- **Where:** `rs/ui/src/gate.ts` `resident()` = ghost + closed image + every step but the last.
- **What happens:** the gate has 3 steps (16 frames resident); the emblem has 5, so 53 decoded
  640×900 bitmaps stay loaded even if medium is never used.
- **Fix:** keep only the ghost, the closed image and the first step resident; `warm()`/`cool()` load and free
  the other steps (hover or press), as they already do for the last step.

### 3. The opening can stay stuck in the dark (rare)
- **Where:** `rs/ui/src/main.ts` `go()`, `rs/ui/src/gate.ts` `open()`, `rs/app/src/gate.rs` watcher.
- **What happens:** Rust starts watching for the terminal window before `invoke("go")` returns, and sends
  `gate-found` once. If the window shows up in that gap, the UI drops the event (`this.opening` is still
  null, or still the other size's opening), and `open()` resets `found` anyway. Rust never re-sends it and
  skips its 8 s timeout, so the terminal stays hidden until a key or click. Unlikely (Windows Terminal starts
  slower than the reply), and the gate had the same gap; two openings make the wrong-target case new.
- **Fix:** in `go()`, set `this.opening = g` and `g.found = false` before the invoke; drop the reset in
  `open()`; after the reply, hand off at once if `r.found || g.found`.

### 4. The README and site screenshot show the old tagline
- **Where:** `docs/launcher.png` (README), `site/public/shots/launcher.webp` (made from it by
  `make_assets.py --site`).
- **What happens:** it still reads "Open a folder. Start coding." and Reidcc 0.1.1.
- **Fix:** retake it from the current build with sample data only (profile `main`, `~/projects/kiln`, no
  personal paths), then rerun `make_assets.py --site`.

### 5. Two test screenshots show the old tagline
- **Where:** `rs/tests/gui_shots/emblem_ghost.png`, `rs/tests/gui_shots/settings_button.png`.
- **Fix:** rerun the tests that take them (`settings_flow.py`, the emblem shot).

### 6. Doc and comment drift
- `vision/reidcc-palette.md:109` says the emblem runs "about 2 s"; it is 2.5 s.
- `python/build/make_assets.py:225` says the hand grows "bringing the compass", and palette line 157 says
  "with the compass". The compass stands from the start; the hand grows around it. Change both.

### 7. Settings opened by keyboard keeps the hover ghost
- **Where:** `rs/ui/src/main.ts` `openSettings()`.
- **What happens:** pointer resting on `open gate`, then Tab + Enter on `settings`: no mouseleave, so the
  ghost stays over Settings and the warm frames stay loaded.
- **Fix:** call `this.calm()` in `openSettings()`. One line.

### 8. A frame that finishes loading after `cool()` leaks
- **Where:** `rs/ui/src/gate.ts` `load()`.
- **What happens:** a stale fetch's bitmap is thrown away without `close()`, and its cleanup deletes the
  newer fetch's entry from `loading`.
- **Fix:** `else bmp?.close();` and `if (this.loading.get(name) === p) this.loading.delete(name);`.

## Reid's call

### 9. Enter in medium
In main, Enter on the profile list opens the gate. In medium, focus sits on the profile picker, where
Enter picks a profile (`widgets.ts` uses Enter to confirm the popup). SPEC-form.md doesn't say. If Enter
should open the gate in medium too: in `onReturn()`, treat `this.listFocus()` like `this.lb.root` when no
popup is open.

## Unchecked

### 10. Message buttons may be pushed off the edge in medium
`wrapTexts()` reserves no room for `msgActions` in medium, and `say()` wraps before adding the buttons.
At 480–520 px, `[try again]` or `[delete] [keep]` may sit past the right edge (`overflow: hidden`). Try it
in the app before fixing; the fix is to wrap after adding the buttons and subtract their width.

## Out of scope

### 11. Alt+1 on a narrow screen
On a work area narrower than main's minimum (960 px), Alt+1 can't reach main and the 500 ms guard drops
the resize, leaving the medium layout in a main-sized window. Older than 0.2.1; goes to To do.

## Wrong

### 12. "A plain run skips the emblem"
False: the full `make_assets.py` run calls `emblem()`. Its other point is true but harmless: `--emblem`
rewrites `assets/banner.png` first, with the same bytes each time.
