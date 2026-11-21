<span class="tag">the launcher</span>

# Session windows

Each session runs in its own Reidcc window: the real engine in a terminal, under a bar that says where you stand.

![A Reidcc session window](/shots/session-window.webp)

## The telemetry bar

From left to right: the folder, `PROFILE · main`, the persona if there is one, the engine, then the meters.

- **context** and **limit** in percent. They turn bronze at 75% and oxide at 90%.
- Hover a meter for the detail: `84k / 200k` for context, `resets in 3h 12m` for the limit.
- A clock shows how long the session has run. When it ends it says `finished`, or `failed · code N` (then any key closes the window).

## Keys in the window

| Key | Does |
|---|---|
| `Ctrl+C` | Copies when text is selected; otherwise goes to the engine |
| `Ctrl+V` | Pastes. With no text on the clipboard, the engine can read an image instead |
| `Ctrl+Shift+C` / `Ctrl+Shift+V` | Copy / paste |
| `Ctrl+=` / `Ctrl+-` / `Ctrl+0` | Bigger / smaller / reset text |

## Snap (beta)

Drag session windows together to share one frame of up to four live panes. Drag the frame's header to move them together, or a pane's header to pull it out. Double-click a header to maximize it.

## Windows Terminal instead

**settings → sessions open in → Windows Terminal** starts sessions there instead.
