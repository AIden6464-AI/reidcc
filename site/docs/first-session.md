<span class="tag">start</span>

# Your first session

Three steps, all on one screen: `folder → profile → open gate`.

![The Reidcc launcher](/shots/launcher.webp)

## 1 · pick folder

Click **pick folder** (`Ctrl+O`), or open a recent folder from the list. This is the folder the session works in, for example `~/projects/kiln`.

## 2 · pick a profile

The first launch writes `reid.json` with one profile, `main`: Claude Code on Opus, with memory on. The list on the left holds your profiles; every field of the selected one sits next to it, and changes save as you make them. See [profiles](./profiles).

## 3 · open gate

Press **open gate** (`Enter` on the profile list, or `Ctrl+Enter` from anywhere). The gate opens and the session starts in its own [session window](./session-windows), with your persona, memory and settings in place. Any key or click skips the animation.

The command it will run is shown under the profile before you press it, so nothing is hidden.

## Coming back

- `/reid` inside Claude Code ends the session and returns to Reidcc with the conversation kept.
- **resume** (`Ctrl+R`) picks the last Claude session up again, with any profile.
- **open chat**, beside resume, opens one composer over Claude Code and Codex in the same folder and profile ([chat](./chat)).
- `/exit` leaves as usual.
