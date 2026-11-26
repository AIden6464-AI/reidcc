# r/ClaudeAI

Status: **blocked**. Feed posts need OP karma over 100; the account has 3 (2026-11-24).

## Rules (read 2026-11-24, old.reddit.com/r/ClaudeAI/about/rules)

- **7. Showcase your project in a way that helps educate and inspire others.** Promotion is OK if:
  built with Claude / Claude Code (or for Claude) by you; a clear description of what was built, **how Claude
  helped, in detail**, and what it does; free to try (paid tiers OK) and the post says so; minimal promotional
  language; no referral links (a link to the project is fine); no job seeking.
  **Posts on the feed now require OP karma > 100.**
- 2. Be relevant: about Claude and Claude Code. 3. Be constructive.
- 6. Competitor posts need homework: Codex support is fine to mention, but no "X is better than Claude" claims.
- 9. Use relevant post flair (pick the project / showcase one on the day).
- 10. No vote manipulation (bots watch for it).

## Angle

A Windows launcher for Claude Code with profiles, persona, memory, live context and usage limits. Explain in detail how Claude Code built it to meet rule 7.

## Title

I built a Windows launcher for Claude Code with Claude Code: profiles for persona, model, login and memory, plus a live context and usage bar

## Body

I'm a self-taught solo dev. I run Claude Code all day across different setups with different personas, models, logins and memory files. Switching between them meant editing configs and retyping flags every time. So I built this: **Reidcc**, a Windows launcher for Claude Code, and I built it with Claude Code.

**What it does**

You pick a project folder, pick a profile, and press open gate.

Each profile saves its own model, sign-in (your subscription or an API key), persona, tools, MCP config, switches, and a long-term memory file you can turn on or off. Sessions run in a Reidcc window with a top bar that shows the current folder, the active profile, and your live context and usage-limit percentages.

If you run several sessions at once, you can snap the windows together, save that layout as a rig, and reopen the whole set in one click. It comes as both a desktop window app and a terminal UI (`reid`). Typing `/reid` inside a running session takes you back to the launcher so you can resume the same conversation under a different profile. It can launch Codex profiles from the same place too.

**How Claude Code helped build it**

Claude Code wrote most of the codebase. The app is built with Rust (Tauri 2) and TypeScript.

My workflow was writing plain text docs for the specs and design rules. I put the colours, motion rules, and every word that appears on screen into those docs. Claude Code read the specs, wrote the Rust and TypeScript code, and wrote the tests.

The biggest help was having Claude Code wire up tests that drive the real app through DevTools. A change does not count as done until Claude Code opens the actual app and checks that the screen works as written. Three things made the biggest difference for me: keeping one spec file per feature, quoting my own words in the spec so Claude builds what I meant instead of guessing, and telling Claude Code to flag problems in my plan instead of just agreeing with me.

**Trying it out**

It is free for personal use on Windows. It has an installer that updates itself, and it runs on top of your own Claude Code installation.

Site: https://aiden6464-ai.github.io/reidcc/
Source: https://github.com/AIden6464-AI/reidcc

If you switch between different Claude Code setups during the day, what would you want a profile to save that isn't here?

## Media

`docs/session-window.png` (sample project, profile `main`). Add a rig screenshot from sample data if one is made.

## Checklist

- [ ] Karma over 100
- [ ] Old comments hidden or a clean account
- [ ] Flair picked on the day
- [ ] Reid read this and said yes
