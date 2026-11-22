# SPEC: the emblem (medium's opening: the hand grows out, the leaves come out, the view zooms into the emerald)

Status: BUILT 2026-11-22 (Rust app). Frames from `python python\build\make_assets.py --emblem`; played by
`rs/ui/src/gate.ts` as a second `Gate` named `emblem`. Waiting for Reid to see it.

> "for this form can we have the hand come down toughing the house   not the gate   [the Engraved Compass
> and Marble Hand Emblem] with codex with it's image gen and video gen stuff work with gpt 6.2 sol for this"
> (Reid, 2026-11-22)

> "the spec_hand md is for the medium size" (Reid, 2026-11-22)

> "umm thats not the same hand at all" (Reid, 2026-11-22, about the hand Codex drew)

> "Well, it doesn't look like it's touching the top. It looks like it's coming around and it's growing out.
> And we should have the leaves come out. And then it zooms into the green, into the emerald. Like it's the
> image, not making it touch the tip." (Reid, 2026-11-22)

> "it's pretty cool just a little short and i can see the blackouts" (Reid, 2026-11-22, about the first build:
> 1.2 s, with black holes where the hand and leaves would grow)

> "i can see the patching job of it" (Reid, 2026-11-22, with a shot of the base over the form: smoke scraps and
> a cut edge where the filled area met the art)

So the opening is **the emblem itself coming to life**, compass and all. Nothing touches anything. The
sizes are main / medium / small (SPEC-vision-v1 §1): main keeps the gate (SPEC-gate.md), **medium** (the
form, SPEC-form.md) plays the emblem, small opens the session straight away.

## What the person sees

**Hover** (`open gate` or `resume`, pointer or keyboard focus): the emblem's lines at strength `0.14`,
see-through and click-through, with the gate's timing (60 ms delay, 140 ms in, 120 ms out).

> "lets get it to 2.5 sec" (Reid, 2026-11-22)

**Press:** five steps back to back at the gate's pace (`PACE` 1.375), 2.5 s (1820 design ms; "a little short" at
1.2 s, then 2 s). The longer steps run past the design doc's `240 ms` per step, as the gate's `open` already does:

| Step | Frames | Design ms | What happens |
|---|---|---|---|
| `rest` | 8 | 0–250 | the blueprint lines, then the base fills in under them: house, columns, steps, circles and the compass. No hand or leaves yet |
| `grow` | 20 | 250–750 | the hand and its drapery grow out from the top right (a soft front running from the drapery to the fingers, the part scaling up from 82 %), around the compass |
| `leaves` | 13 | 750–1080 | the laurels grow out from their stems by the columns |
| `ignite` | 10 | 1080–1330 | the emerald in the compass hinge flares and settles |
| `open` | 20 | 1330–1820 | the view zooms into the emerald until the hinge ring fills it, then goes dark; the session window appears there |

Any key or click skips it. Words are the gate's (`REIDCC · OPENING` → `REIDCC · READY`).

## The art

Only `vision\branding\Engraved Compass and Marble Hand Emblem.png`, as it is. `make_assets.py` splits it
with hand-measured masks (emblem pixels, measured 2026-11-22): the hand and drapery; the two laurels; the
base (everything else, the compass included). The base is a **plate** with nothing missing, so no black holes
show before a part grows ("i can see the blackouts"). The plate keeps only the stone (house, steps, plinth, the
columns' own shape, the compass); **all** the rest is background, cleaned whole and the construction lines
redrawn on it (fitted to the art: circles at (621, 502) r 402 and (627, 692) r 335, lines at y 465, y 705,
y 1136, x 626). Cleaning only the hidden spots showed as patches ("i can see the patching job of it"). Under the
cloth's foot, the right column's capital is mirrored; where a leaf covers its column, that column's other side.
The hand and the laurels are cut by their own shape, not their area, so the art's smoke around them doesn't end in
a cut edge. Each part is revealed by a soft front from where it grows (the drapery's top right, each laurel's stem). The emerald is the gate's `glow`; the zoom is the gate's
`camera` / `push` aimed at the emerald (`ZF` 14).

Frames are 640 × 900, centred on the window (the emblem 520 px wide), their edges fading into the window
colour, so any medium window from 480 wide looks right. The tag stays inside the window when the art is
wider than it. 256-colour PNGs like the gate's: 71 frames + ghost, about 9 MB (the gate's are 21 MB).

## Build

- `assets\emblem.json` (the gate's shape), `assets\emblem.png`, `assets\emblem_ghost.png`,
  `assets\emblem_{rest,grow,leaves,ignite,open}\NN.png`. The installer bundles `assets\` whole.
- `rs/app`: `init` returns `emblem` beside `gate`.
- `rs/ui/src/gate.ts`: `Gate` takes a name (`gate` / `emblem`) for its asset prefix and element id.
- `rs/ui/src/main.ts`: `opener()` is this size's opening (full → gate, form → emblem, medium → none);
  `go()` passes `gateOk` when there is one and plays it; hover drives that one's ghost.
- Tests: `rs/tests/sizes_flow.py` in the form: hovering `open gate` shows the emblem's ghost; `open gate`
  plays the emblem, then the session window appears.

## Retired

The touch (the hand coming down onto the roof's peak, compass removed) and its Codex runs. Codex drew a
different hand (a straight-pointing photographic one: "thats not the same hand at all"), and the GIF
animation mode refused ("GIF output is not enabled for this request"). The drafts `Touch - Plate.png` and
`Touch - Hand.png` and the prompts in `vision\Spec\hand\` are deleted. Codex isn't used for this opening.
