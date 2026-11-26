# r/tauri

Status: rules not read yet. Technical posts only; an ad gets removed.

## Angle

How I built it: what was hard in Tauri 2 and how I solved it.

## Title

Snapping ConPTY + xterm.js windows together in Tauri 2 (and the webview reparenting bug that froze them)

## Body

I built this Windows launcher for AI coding CLIs, called **Reidcc**, in Tauri 2 and Rust. Most of the code was written with Claude Code from my specs.

Each session is a ConPTY child process rendered by xterm.js in its own webview window. The hardest part was snapping separate session windows together into one frame. Here is what I ran into:

- **Snapping windows into one frame.** A group is a parent window holding a header webview plus one child webview per pane, laid out from a split tree. To move a pane between windows, I reparent its webview.
- **The freeze bug.** Moving a pane's webview while terminal output was streaming sometimes froze that terminal for good. Output goes over an ordered channel. If you lose one message during the move, every message after it waits forever. My fix for saved layouts was to build the frame first and create each pane's webview inside it, so nothing live ever moves.
- **Late page loads.** If a pane's page loaded after it was grouped, it missed the "you're grouped" event. Now each pane asks for its state on load.
- **Window creation from async commands.** Sync commands run on the main thread, so any async command that creates windows has to hop to the main thread and wait.

Source (free for personal use):
https://github.com/AIden6464-AI/reidcc

Has anyone here found a cleaner way to move a live webview between windows in Tauri 2?

## Media

A rig screenshot (three panes in one frame) from sample data.

## Checklist

- [ ] Rules read on the day
- [ ] Facts double-checked against `rs/app/src/dock.rs` and `session.rs` at posting time
- [ ] Reid said yes
