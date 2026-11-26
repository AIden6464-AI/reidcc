# r/vibecoding

Status: rules not read yet. Check whether project posts are allowed and the flair.

## Angle

Focus on how it was built: directing an AI with plain specs and real app tests to build a non-trivial desktop app. Process first, app second.

## Title

What worked for me building a Windows desktop app with Claude Code: plain specs, design docs, and tests that click through the real app

## Body

I'm a self-taught solo dev. I built this mostly with Claude Code. The app is **Reidcc**, a Windows launcher for Claude Code and Codex.

Here is what kept the AI on track for me:

1. **A spec before every feature.** I quote my own words in the spec. That way Claude Code builds what I meant instead of what it guessed.
2. **Design docs for everything on screen.** Colours, motion, and every word live in docs. The AI checks its work against them.
3. **Tests that open the real app.** The test suite launches the app and clicks through it. A feature is only done when it works in the app, not just when it compiles.
4. **A thinking partner, not a yes-man.** I tell it to flag problems and push back on my ideas.

As for Reidcc itself, it has profiles (model, login, persona, tools, memory), session windows with live context and usage, saved window layouts, and a terminal UI. It runs on Windows and is free for personal use.

Source: https://github.com/AIden6464-AI/reidcc

What is your setup for keeping an AI on track on a bigger project?

## Media

`docs/session-window.png`.

## Checklist

- [ ] Rules read on the day
- [ ] Reid said yes
