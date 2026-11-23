# SPEC: the user trial (two AI testers play new users who found Reidcc on Reddit)

Status: SPEC 2026-11-23. Not run. Runs on Reid's word; it uses his Gemini, Codex and a little Claude usage.

> "Idea   Spec a doc to have Gemini 4 argon and codex gpt 6.2 sol  act like there new users of Reidcc and saw
> the Reddit post and is installing it and useing what kind of parts the user likes wants or hopefulness for the
> project or what can be pushed more like a custom cli that sits on top of codex and Claude and agy etc"
> (Reid, 2026-11-23)

Two outside models each play a new user. They see the Reddit post (SPEC-reddit.md Part 4), follow it to the
site and the repo, set Reidcc up and use it. Then each writes what they liked, what they wanted, what they hope
Reidcc becomes, where they got stuck, and what could be pushed further.

> "Well Reidcc supports codex and Claude code" (Reid, 2026-11-23)

So the testers use **both engines as they are today**: Claude Code and Codex profiles side by side, from the
same launcher. They judge how well that works now. Then one question is asked straight out: should `reid` go
further, to agy and the other agent CLIs, as one CLI on top of all of them?

Simulated users are good at finding confusing words, missing steps and broken flows, and at reacting to ideas.
They don't prove anyone wants it. The real check is the Reddit post itself.

## Part 1: the testers

| Tester | Runs in | Plays |
|---|---|---|
| **Gemini 4 Argon** (`gemini-4-argon-high`) | agy, in its own console window (`agy --model gemini-4-argon-high -i "<prompt>"`) | **Sam**: uses Claude Code every day on a Max plan, three projects, a couple of MCP servers, tired of retyping flags. Reads r/ClaudeAI. |
| **Codex GPT 6.2 Sol** (`gpt-6.2-sol`) | Codex, in its own console window (`codex -m gpt-6.2-sol -s workspace-write -C <trial folder> "<prompt>"`) | **Jo**: uses both Claude Code and Codex (and has agy installed), and switches between them by hand today. |

Each tester gets the same task and the same rules, with its own persona. They don't see each other's reports.

## Part 2: what they get, what they can't touch

They see exactly what a new user sees, nothing more:

1. **The post**: SPEC-reddit.md Part 4's title and body, pasted into the prompt as if read on Reddit, with the
   session-window shot (`docs/session-window.png`).
2. **The public repo**: a fresh clone of `main` from GitHub into a temp trial folder
   (`%TEMP%\reidcc-trial-<name>\repo`). That's the user README, the site source, the license. No `dev` branch, no
   vision docs, no Reid files.
3. **The site**: https://aiden6464-ai.github.io/reidcc/ (they may fetch it).
4. **Reidcc itself, portable**: `Reidcc.exe` and `reid.exe` from the latest release build, copied into
   `%TEMP%\reidcc-trial-<name>\bin`, with `REIDCC_HOME=%TEMP%\reidcc-trial-<name>\home`. Reidcc makes a fresh
   `reid.json`, memory file and folders there on first run, as it does for a real new user.

**Not the installer.** Running the setup would replace Reid's own installed copy in `%LOCALAPPDATA%\Reidcc`.
The testers read the install page and may download the setup to check it exists and is signed, but they
don't run it. They describe what they expected from the install step instead.

**Hands off:** the trial folder is the whole world. They must not read or write anything outside it: not
Reid's Reidcc folder, `reid.json`, memory, personas, `json\` keys, `~/.claude` or `~/.codex` settings. The
prompt says so, and Codex's `workspace-write` sandbox keeps its writes inside the trial folder. No personal
paths or names go into either prompt.

**Sessions cost real usage**, so they're capped: at most 3 real engine runs each, kept short. A run is
`reid <profile> -p "<prompt>"` (one Claude print-mode answer) or a Codex profile's one-shot. `reid --dry
<profile>` shows the exact command for free and is the main way to explore.

## Part 3: what they do (the script both follow)

1. **The post.** Read it cold. Would you click? What did you think Reidcc was before clicking? Which line
   pulled you in, and which one put you off?
2. **The landing.** Site and README: in 30 seconds, do you know what it does, who it's for, and how to get it?
   What's missing?
3. **Install.** Follow the install page as written (stopping before running the setup). What do you need
   first? Anything unclear or scary (SmartScreen, permissions, where it puts things)?
4. **First run.** Start `reid` from the portable copy with the trial `REIDCC_HOME`. The window app can't be
   driven from their shell, so they use the CLI and TUI commands (`reid -l`, `reid --dry`, `reid --edit` to
   read `reid.json`, `reid <profile>`) and the screenshots in the repo and on the site.
5. **Make it yours.** Make a profile for your own work: a model, a persona, memory on, an MCP config. Both
   testers also make one Claude Code profile and one Codex profile, since Reidcc runs both. Use the docs to
   do it. Note every time you had to guess.
6. **Use it.** Up to 3 real runs, in a sample project folder inside the trial folder: a Claude Code
   session, a Codex session, and `resume` (Claude). How does switching engines feel?
7. **Step back.** What would make you keep it, uninstall it, or tell a friend?

## Part 4: what each report holds

Written to `%TEMP%\reidcc-trial-<name>\report.md`, in this order:

1. **Would I click the post?** yes or no, and the one line that decided it.
2. **First 30 seconds:** what I thought it was, and whether that turned out true.
3. **Install and first run:** each step, what I expected and what happened, with stuck points quoted.
4. **What I liked:** concrete parts (a word, a flow, a screen), not "it's nice".
5. **What I wanted and didn't find:** features, docs, words.
6. **What I hope it becomes:** where I'd want Reidcc to be in a year.
7. **Push further:** the parts that are better than anything else I use and should be bigger.
8. **Two engines today, more tomorrow:** how well do Claude Code and Codex sit together in Reidcc now
   (profiles, words, what works on one and not the other)? Then the one-CLI question: would I want `reid` to
   add agy (and OpenCode, Gemini CLI, ...) as more engines? What would it need: the same profile fields for
   every engine, resume for all of them, one usage bar, switching engines mid-task, one shared memory? What
   would make me stay with each tool's own CLI?
9. **Broken or wrong:** anything that failed, each with the command and the exact output.
10. **Score:** keep using it, 1 to 5, and why in one line.

Quote the docs or the app's exact words wherever something confused you.

## Part 5: after the trial (Claude)

1. Read both reports. Check every "broken or wrong" claim against the code and the app, the same way the
   Gemini reviews were checked. Mark each one real, can't reproduce, or wrong.
2. Merge both reports into `vision/Spec/SPEC-user-trial-results-<date>.md`:
   - **Fix now:** real bugs, missing install steps, confusing words. Each with the smallest fix.
   - **They liked:** what to protect and show more of (in the post, the site, the README).
   - **They wanted:** grouped and ranked by how often it came up and how much it costs.
   - **Push further:** the bigger bets, with the one-CLI answer from both testers side by side.
3. Report back to Reid in a short ranked list. Nothing goes into vision or the app until he picks.
4. Delete both trial folders. The testers' sessions may have left transcripts in `~/.claude/projects` (the
   trial folder's name). Remove those too.

## Part 6: the one-CLI idea, so the testers react to something concrete

Reidcc supports Claude Code and Codex today: both start from the same launcher and the same kind of profile
(`"engine": "codex"`), with one telemetry bar in session windows; resume and `/reid` are Claude's for now.
OpenCode is proposed in SPEC-codex-opencode.md. The idea Reid wants tested goes further: **`reid` as the one
CLI on top of every agent CLI**, agy included. The engine is just a field on a profile, `reid <profile>` starts any of them, and the
memory, persona and usage bar are the same whichever engine runs. Put to the testers as an idea, not a promise.

## Part 7: how to run it (when Reid says go)

1. Build the trial folders: clone `main`, copy the release exes, set `REIDCC_HOME`, add a small sample project
   (like the `kiln` one from the Reddit shot).
2. Write the two prompts from Parts 2–4, one per persona. Have Reid read them before they go out.
3. Open each tester in its own console window, the same way the agy reviews were run, so Reid can watch.
4. Wait for both `report.md` files, then do Part 5.

## Part 8: log

| Date | Tester | Score | Results doc |
|---|---|---|---|
| | | | |
