# Specs: what each one is, and why Reidcc moved the way it did

Checked against the code 2026-11-23. Each spec's own status line is the detail; this page is the map.
Newest direction wins: where an older spec disagrees, it now says what replaced it.

## The six threads

Each spec belongs to one thread, and each step was set off by something specific: Reid using the app and
hitting a wall, going public, or outside voices. That's the "why".

### 1. Engines: from "a Claude launcher" to "on top of every CLI"

| Date | Spec | What set it off | State |
|---|---|---|---|
| 11-17 | SPEC-codex-opencode | "let's make a spec on makeing this tool work for codex and opencode"; cut down after "i wanted to add a engine right not remakeing the hole app" | Codex built 11-19 · OpenCode: milestone 2 goes into SPEC-0.2.6 |
| 11-19 | SPEC-codex-signin-persona | Codex profiles had sign-in, persona and memory greyed out: "can we spec [...] for codex the signin and persona's" | built 11-19 |
| 11-19 | SPEC-codex-proxy | his `claude` profile (codex + `proxy: capture`) was refused: "persona's don't work? what man" | built 11-23 ("All of the build proxy's [...] needs to be ported") |
| 11-23 | SPEC-user-trial (+ results) | "act like there new users [...] what can be pushed more like a custom cli that sits on top" | run · 13/13 fixes done on dev, not released |
| 11-23 | SPEC-agent-cli | the trial plus his Discord poll: "The agent cli that sits on top of agent clis" | idea · Reid command center, a separate app on top of Reidcc · outside reviews added 11-25 (Part 7: plumbing, what Reidcc needs) · command center replaced by SPEC-unified-interface |
| 11-25 | SPEC-unified-interface (+ `.html` page) | Reid's Rev 4 blueprint: one GUI + TUI straight over Claude Code and Codex, no boss AI ("no NVIDIA SLI") | draft vision · Step 0 (Codex resume both ways) and Milestone 1 (reid --stream, Switch, OS locks; core + CLI) built on dev 11-25, hardened 74e8484; Milestone 2 decisions (Part 6) and a design-pass mock (`unified-interface/mock/`) in, awaiting Reid; next: Milestone 2 UI |
| 11-27 | SPEC-0.2.6 | "The handoff.md that's not a full context switch this is 02.6" · "O and the opencode engine" · "Deterministic but [...] just shove the context it self around" | built on dev 11-27 · not released |

**Why it moved this way:** every step came from using Codex inside Reidcc and finding the gap with Claude
(greyed fields, then the refused proxy). Once Codex came close to Claude, the next question was more
engines (OpenCode, agy), and then one agent above them all. The trial's one condition holds across the
whole thread: **never get in the way of the native CLI.**

### 2. Rust: from the Python app to the vision

| Date | Spec | What set it off | State |
|---|---|---|---|
| 11-19 | SPEC-vision-v1 (in `vision\`) | "I can resize it [...] three different sizes [...] orchestrator mode or something" | sizes, session windows, snap, pod built as betas; headless not built; orchestrator moved to SPEC-agent-cli |
| 11-19 | SPEC-rust-rewrite | "Rust?" ... "the rust part one spec and the ideas in one spec" | stages 0–3 built; stage 4 (rigs) beta 11-23 ("Ya build that as you can"); headless not built |
| 11-20 | SPEC-rust-tui-gui | "ok 1:1 tui and gui spec that" | built; Rust ships since 0.2.0 |

**Why:** the vision (snap, shimmer, session windows) needed a real window toolkit: "This is why we're
building in Rust." It was ported 1:1 first so nothing broke, and the Python app is now only the parity
reference.

### 3. One screen, simple: how it looks and moves

| Date | Spec | What set it off | State |
|---|---|---|---|
| 11-17 | SPEC-tui | "spec what your missing from useing the tui" | not built; the Rust TUI kept the gaps |
| 11-17 | SPEC-gate | "a animasion of the gate opening up pulling out the claude code ses" | built 11-17, rebuilt 11-19 ("half done") |
| 11-22 | SPEC-form | "can we meger the uis for the 2.0 because i like the form facter" | built 11-22 (third draft) |
| 11-22 | SPEC-hand | the emblem as medium's opening: "it's coming around and it's growing out" | built 11-22 |
| 11-24 | SPEC-one-look | a UI review: "the Reidcc terminal vs the Reidcc main don't look the same at all" | built on dev (2026-11-25) |
| 11-25 | SPEC-one-window | a review of what opens on its own: "there should be a button for a sidebar of like medium Reidcc or full but in the app not a outside part" | built on dev 11-25 (dock_flow 43/43, frames too); not released |

**Why:** one rule, "if it's supposed to be simple to use, why are we hiding in settings?" (11-17). Every
redesign since then removed a screen or merged two. Open next: renaming the sizes to main / medium / small,
with the pod as a toggle (palette §5).

### 4. Going public

| Date | Spec | What set it off | State |
|---|---|---|---|
| 11-17 | SPEC-app | a review of the .exe packaging | built |
| 11-21 | SPEC-github-repo | "Spec out this as a GitHub repo and how it would be installed" | built through 0.2.x |
| 11-21 | SPEC-github-pages | "a github pages website with docs and the feel that the Reidcc project/app feels" | built |
| 11-27 | SPEC-website-0.2.5 | "spec doc a update to the Website and pull for other website for details" | built · published with 0.2.5 (11-27) |
| 11-22 | SPEC-review-0.2.1 | "ask Gemini 4 neon to reveiw" | 0/8 fixed |
| 11-23 | SPEC-reddit | "post on Reddit about Reidcc the right way. Spec that" | nothing posted (Reid posts) |

**Why:** once there was an installer, every step after it prepares people seeing it: a site, a review,
a post, a trial run with stand-in users.

### 5. Proxy and plugins: what goes into a session

| Date | Spec | What set it off | State |
|---|---|---|---|
| 11-17 | SPEC-proxy | the `proxy\claude-*.cmd` launchers turned into profile fields | built |
| 11-21 | SPEC-plugins | "make ACA its own repo, make it a plugin, make a spec for plugins" | step 1 built; install / switch not built |
| 11-22 | (palette §5) | "install plugins like in the settings and auto detect if it's codex or Claude" | not built; changes SPEC-plugins' "Codex: not yet" |
| 11-23 | SPEC-codex-proxy | thread 1 | built |

### 6. The name

Reidcc means Reid for Claude Code, the launcher. Reid command center is the app on top of it. Together
they are "Reid's tools" (voice §1, 11-23).

## What's built and what's waiting

- **Built and shipping:** the Rust app, Codex parity (sign-in, persona, memory, proxy), the form, the
  gate and emblem openings, the repo / installer / updater, the site.
- **Specced, waiting on Reid's pick:** the 13 trial fixes, the 8 review fixes, OpenCode, the TUI gaps,
  plugin install / switch, the size rename, the Reddit post.
- **Beta, built 11-23:** rigs (save a snapped frame, open it from medium).
- **Ideas:** headless mode, the command center.

**Flag:** the things that block a public launch (trial fixes 1–4 are about an hour; the review fixes;
the stale screenshots) are the oldest unbuilt items. New specs keep landing ahead of them. Thread 1 can
keep growing, but the launch path is threads 3 and 4.
