# r/rust

Status: rules not read yet. Strict about self-promotion and AI-written content; read the rules closely on the day and skip the sub if LLM-made projects aren't welcome. Never post the r/tauri text here unchanged.

## Angle

One Rust problem, explained well. The project is context, not the point.

## Title

Keeping a Windows ConPTY session alive across UI changes in a Tauri app: what I got wrong about ordered channels

## Body

I'm a self-taught solo dev working on Reidcc, a Windows launcher for Claude Code and Codex written in Rust and Tauri 2. I built this mostly with Claude Code from my own specs, and I want to say that up front.

While building the terminal handling, I ran into a channel bug that was easy to misdiagnose.

Each session in the app is a Windows ConPTY child process. A reader thread reads output from the PTY and forwards it to the UI over an ordered channel.

Ordered delivery has a sharp edge. If one message gets lost while the UI moves the receiving webview, every later message waits behind it. The child process keeps running fine in the background, but the terminal in the UI looks frozen.

The fix was structural, not a retry. Never move a live receiver. Build the destination in the UI first, and attach the receiver there once.

For process cleanup, each session goes into a Windows job object. When you close the app, Windows ends every child process automatically.

The app is free for personal use. The source is up under the PolyForm Noncommercial license:
https://github.com/AIden6464-AI/reidcc

How do you handle lossless streaming into a UI that can move or reload under you?

## Media

None needed; code snippets from `rs/app/src/session.rs` if the post is text.

## Checklist

- [ ] Rules read on the day (AI-content policy)
- [ ] Facts double-checked against the code at posting time
- [ ] Reid said yes
