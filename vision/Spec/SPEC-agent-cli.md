# SPEC: the agent CLI that sits on top of agent CLIs

Status: SPEC 2026-11-23. Idea, not scheduled. Nothing here is built. An outside review was added
2026-11-25 (Part 7); its calls are suggestions, not decisions. The command center (a separate app with a
conductor) is replaced by `SPEC-unified-interface.md` (Reid, 2026-11-25); Part 7's plumbing carries over.

> "Idea   Spec a doc to have Gemini 4 argon and codex gpt 6.2 sol  act like there new users of Reidcc and saw
> the Reddit post and is installing it and useing what kind of parts the user likes wants or hopefulness for the
> project or what can be pushed more like a custom cli that sits on top of codex and Claude and agy etc"
> (Reid, 2026-11-23)

> "The agent cli that sits on top of agent clis" (Reid, 2026-11-23)

> "Like you talk to ether or not fully " talk to one agent, the conductor, and the other agent CLIs are its
> tools."" (Reid, 2026-11-23)

> "Reidcc harness/ the gate" (Reid, 2026-11-23, naming it)
> "No the harness is = to the gate" (Reid, 2026-11-23)
> "So there is Reid(Claude code).  And Reid(command center).  = Reidcc     So Reid's tools that's my idea of
> it rn" (Reid, 2026-11-23)
> "Na keep the Reidcc(Claude code).   There different apps but they can work linked" (Reid, 2026-11-23)

> "Remember it sits on top" (Reid, 2026-11-23)

**Two apps, linked, one on top.** **Reidcc** (Reid for Claude Code) is the launcher and stays as it is.
**Reid command center** is a separate app that **sits on top**: above Reidcc and the agent CLIs (Claude
Code, Codex, agy). It never replaces them.

> "But Reidcc launcher can work independently still" (Reid, 2026-11-23)

**Reidcc never needs the command center.** It installs, launches and updates on its own, and nothing in it
waits on, asks for or links to the command center unless the command center is installed. The dependency
only goes one way: the command center needs Reidcc, never the reverse. The command center drives what's below it
through Reidcc's profiles, and any session it starts can be opened in Reidcc and handed back (Part 2b).
Reid's tools is the name for the two together.

```
Reid command center   (the harness / the gate: you talk to it)
        │
Reidcc                (profiles, sign-in, persona, memory, the session window)
        │
Claude Code · Codex · agy   (each its own CLI and login)
```

**Names.** **The harness is the gate**: one thing, two names. It is the agent you talk to inside the command
center (this spec's "conductor"). The shared per-project log is **the ledger** (Argon's pick, not yet
confirmed by Reid). The Reidcc launcher's `open gate` button keeps its meaning (open the picked profile's
engine). Open: is that word clash fine now that they are separate apps (palette §5)?

Earlier parts of this spec, written before the split, call the conductor "a Reidcc profile" and the tools
`reid mcp`. Read those as the command center reusing Reidcc's core (profiles, `engines::build`, sign-in
env). Where the code lives is still open.

So the conductor is **not a wall** between you and the engines. You talk to either: the conductor, or any
engine directly, and you can switch at any point. See Part 2b.

The idea is also **not** "one launcher for many engines". Reidcc already launches Claude Code and Codex, and an
alias can launch anything. The idea is **an agent of its own**: you talk to one agent, and its hands are the
other agent CLIs. It sends a task to Claude Code, has Codex review the diff, asks agy for a second plan, and
carries the goal, persona and memory across all of them.

## Part 1: what the trial testers asked for (SPEC-user-trial-results-2026-11-23.md)

Both said yes, on one condition: **never get in the way of the native CLI.**

- **Hand off mid-task between engines** with something you can inspect: goal, current diff, commands run,
  open questions (Jo). Sam: a handoff summary into the next engine, logged to memory.
- **Same fields for every engine**, unsupported ones flagged before launch; native resume for each engine.
- **One usage bar** that shows each engine's real limits and says when an engine gives no data.
- **One memory per project**, with a switch for what each session reads or writes.
- Deal-breakers: blocking a native flag or subcommand, unclear which command or account runs.

## Part 2: the shape (recommended)

**The top agent is itself an engine session. Reidcc gives it the other engines as tools.**

```
you ──► conductor (a normal Reidcc profile: Claude Code, Codex or agy, interactive)
            │  MCP tools from `reid mcp`
            ├── run(profile, task)      ─► claude -p … / codex exec … / agy …   (headless, in the folder)
            ├── review(profile, diff)   ─► another engine reads the diff, answers only
            ├── handoff(profile)        ─► writes the handoff file, starts that engine on it
            └── memory / status         ─► the project's memory file, each engine's usage
```

Why this shape:
- **Subscriptions keep working.** Each engine runs its own CLI with its own login (Max plan, ChatGPT,
  Google). An agent with its own API loop would need API keys and bill per token.
- **Small.** Reidcc already builds every engine's command (`engines::build`), its persona and memory prompt,
  and its sign-in env. The new part is one MCP server (`reid mcp`, stdio) that turns those into tools.
- **Any engine can conduct.** The conductor is just a profile with the `reid` MCP server added. Claude
  conducting Codex, or Codex conducting Claude: same tools.
- **Native stays native.** Every sub-run is the real CLI with the profile's flags; `reid --dry` shows it.

## Part 2b: talk to either

The conductor is one way in, never the only way.

| You want | You do | What happens |
|---|---|---|
| Hand it out | Talk to the conductor | It picks engines and uses `run` / `review` / `handoff` |
| Talk to one engine yourself | Open that engine's profile as today (`reid <profile>`, or its lane) | A normal session: native CLI, native keys, nothing in between |
| Take over a sub-run | Open the sub-run's lane | Reidcc resumes that engine's session interactively (its own resume, same session id). You talk to it directly |
| Give it back | `/reid` (Claude), quit (Codex) | You're back at the conductor. It reads what changed (the diff, the session id, a one-line note in the handoff file) and carries on |
| Skip the conductor entirely | Never open it | Reidcc stays exactly what it is today |

What makes this work: every sub-run is a **real engine session** with an id, not a hidden API call. So
anything the conductor started, you can open and talk to, and anything you did by hand, the conductor can
see. Neither side has to go through the other.

The other shape, Reidcc running its own agent loop against model APIs, is rejected for now: it loses
subscription use, duplicates what the engines already do well, and would make Reidcc a model client to keep
up with.

## Part 3: the tools (first cut)

| Tool | Does | Returns |
|---|---|---|
| `engines()` | Lists profiles: engine, model, signed in or not, fields this engine can't use | the list |
| `run(profile, task, write?)` | Starts that profile headless in the current folder. `write: false` = read-only (plan/answer only) | final answer, files changed, the session id |
| `review(profile, what)` | Another engine reads the diff or files and answers. Never writes | the review |
| `handoff(profile, note)` | Writes `.reid/handoff.md` (goal, diff summary, commands run, open questions, conductor's note), runs `profile` on it | as `run` |
| `resume(session, task)` | Continues an earlier sub-run with that engine's own resume | as `run` |
| `usage()` | Context and limit per engine, "no data" where an engine gives none | numbers |

Headless commands to build on (check each on the day, flags move):
- Claude Code: `claude -p "<task>" --output-format stream-json`, resume with `--resume <id>`.
- Codex: `codex exec --json "<task>"` (`--skip-git-repo-check` outside a repo), resume with `codex exec resume`.
- agy: its headless mode and output format are **not checked yet**.

## Part 4: rules

1. **One writer at a time** in a folder. A second writing run waits or goes to a git worktree. Reviews read only.
2. **Depth 1.** Sub-runs don't get the `reid` tools, so no engine calls engines calling engines.
3. **Show the cost.** Every `run` reports which engine, model and account it used, and its usage after.
4. **Pass through.** A profile's own `args` go to the engine untouched. Reidcc never blocks a native
   subcommand it doesn't understand (fixes Codex `resume` being refused today).
5. **Memory is the project's.** All engines read the same memory file; a sub-run writes to it only if its
   profile has memory on.
6. Sub-run transcripts stay where each engine keeps them; the conductor links to them by session id.

## Part 5: the order

0. **Codex level with Claude first** (from the trial): pass `codex resume` through, `reid -l` login status,
   MCP for Codex via `-c`, a check before launch. Without this the conductor's tools are lopsided.
1. **`reid mcp` with `engines`, `run`, `review`** for Claude Code and Codex. Test: a Claude conductor asks
   Codex to review its diff in `kiln`.
2. **`handoff` and `resume`.** Test: start in Claude, hand off to Codex mid-task, Codex finishes from the
   handoff file alone.
3. **agy** as the third engine (after checking its headless mode).
4. **The window:** sub-runs shown as lanes under the session bar, each with its engine, state and usage.
   Clicking a lane takes it over (Part 2b); `/reid` gives it back.

## Part 6: open (Reid's call)

- ~~The name~~: named 2026-11-23: Reid command center, a separate app linked to Reidcc. Its agent is the
  harness, which is the gate (see the top). Still open: one repo with two exes, or two repos.
- Whether the conductor may write code itself, or only plans and delegates.
- How this meets COS (Planner/Builder/Critic/Dreamer): `review` is a Critic, `run` a Builder. Reuse that
  split, or keep Reidcc's tools plain.
- Watch: every engine added is upkeep (flags change). Ship step 1 with two engines before adding more.

## Part 7: outside review (2026-11-25)

Reid pasted this review to add here. Its words are kept; **notes** in this style say where it doesn't
match this spec or the code (checked 2026-11-25).

**Note: the review read a different draft.** It names 4 tools (`ask`, `peek`, `handoff`, `sessions`), a
"Worker Strip", `open <worker>`, "One screen, two areas", "refusing node-graph clutter" and 7 open questions.
None of these are in this file or its history. This spec has `engines`, `run`, `review`, `handoff`,
`resume`, `usage` (Part 3) and the open items in Part 6. Read the review's `ask` as `run`/`resume`
(`continue=true` = `resume`), `sessions` as `engines` plus a list of sub-runs, and `peek` as a new
read-only tool: show a sub-run's state and last output without taking it over. The open-question table
below answers its own 7 questions. Most of them match Part 6 or the naming notes at the top.

> You already have the hardest part right: the two-app boundary, the MCP tools, and refusing node-graph
> clutter. Where a Claude dev will get stuck or invent awkward workarounds is in the plumbing between the
> conductor, the workers, and Reidcc.

### 7a. Seven missing parts

1. **Session locking (preventing collisions).** What happens if the conductor resumes a session while you
   have that same session open in a Reidcc window? *Fix:* give every session a state in a shared registry:
   `idle`, `running-headless`, `attached-in-window`. While attached, the conductor can peek but can't ask
   until you close or hand back the window.
2. **Working-tree concurrency.** If Claude Code edits files while Codex runs tests or fixes in the same
   folder, they clobber each other's uncommitted diffs. *Fix:* one writer per folder at a time (read-only
   reviews and peeks any time). Defer `git worktree` isolation to v2 unless parallel edits on one repo are
   wanted.
   **Note:** Part 4 rule 1 already says one writer, and offers a worktree as the fallback. The review
   moves the worktree to v2.
3. **One normalized headless engine trait (reidcc-core).** Claude (`-p --output-format stream-json`), Codex
   (`exec --json`) and agy all output different JSON. *Fix:* one small trait, e.g. `HeadlessEngine`, that
   turns every CLI into 5 events: `started(session_id)`, `chunk(text)`, `tool_call(name, summary)`,
   `usage(tokens, ctx_pct, cost)`, `done(status, reply)`. That one stream drives the live status and
   context % beside each sub-run.
   **Note:** a plain enum of those 5 events plus one parser per engine does the same job. A trait only pays
   off at 3+ engines.
4. **Auto-mode guardrails and a hard kill.** "Claude codes → Codex reviews → Claude fixes" can loop and burn
   tokens. *Fix:* circuit breakers in the spec: max turns per ask, max consecutive handoffs (e.g. 3), a
   per-task cost/token cap, a wall-clock timeout. A visible Stop button kills the child process tree
   cleanly on Windows.
   **Note:** the kill exists. `rs/core/src/win.rs` puts children in a job object
   (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `TerminateJobObject`). Reuse it.
5. **Single-writer ledger.** If every engine edits the ledger, it turns into a bloated transcript. *Fix:*
   only the conductor writes it (workers read). Cap it to a fixed ~40-line template: Goal, Current State,
   Decisions, Open Tasks, Last Touch (engine, time, changed files / commit).
   **Note:** this narrows Part 4 rule 5 ("a sub-run writes to it only if its profile has memory on") for the
   ledger. The project's memory file (ACA) stays as rule 5 says.
6. **App-to-app handoff (IPC).** The command center and Reidcc are separate apps: click a sub-run and Reidcc
   opens on that session; the command center needs to know when you close it. *Fix:* a small shared
   session registry file (e.g. `%LOCALAPPDATA%\reidcc\sessions.json`) plus a Windows named pipe (or loopback
   JSON-RPC) so Reidcc tells the command center on attach / detach.
   **Notes:** `Reidcc.exe` has no `--resume <session_id>` today. `reid --resume [profile]` continues the
   *last* session (`rs/cli/src/main.rs`), not one by id, so that flag is new work. The registry belongs in
   Reidcc's own folder (`REIDCC_HOME`, beside `reid_state.json`), not a second `%LOCALAPPDATA%` folder.
   Reidcc stays independent (top of this spec): it writes the registry and the pipe events whether or not
   the command center listens.
7. **Structured failure recovery.** Engines hit rate limits, lose auth or fill their context mid-run. *Fix:*
   the run tool returns typed errors (`rate_limited`, `auth_expired`, `context_full`, `crashed`) instead of
   raw stderr. The conductor can then offer "open in Reidcc to sign in again" or a handoff to another
   engine.

### 7b. Calls on the open questions (the review's 7)

| Open question | Recommended call | Why |
|---|---|---|
| CLI name | Keep `reid` for Reidcc; `reid-cmd` (or `reid gate`) for the command center | Doesn't break `reid.exe` habits and scripts |
| Repo / crate | Same repo, new workspace crate `rs/command` next to `rs/app` | Shares reidcc-core directly, no version drift while it moves fast |
| "Gate" name clash | Call the conductor **the conductor** (or **the desk**); keep **gate** for Reidcc's `open gate` | No confusion when talking about both apps in one sentence |
| Which engine conducts | A profile you pick, Claude Code by default | Fits the ACA memory and hooks; Codex / agy stay possible |
| Minimum agy wrapper | agy in phase 2; Claude + Codex first | Two solid adapters prove the contract before a third CLI |
| "The ledger" name | Keep **the ledger** | Short, distinct, Reidcc's voice, no clash with "memory" (ACA) |
| First real-user test | "Code with Claude, review with Codex" on a real repo | Exercises run, handoff, sessions, the ledger and taking over a sub-run in one loop |

**Notes:** the gate rename goes against Reid's own words at the top ("the harness is = to the gate"). It's
his call. "Same repo" answers Part 6's "one repo with two exes, or two repos", but the public `main` is
built from `dev`'s file list (`.github/workflows/publish-main.yml`), so a new crate stays off `main`
until it's added to that list.

### 7c. Suggested build order

1. **Core headless + registry (reidcc-core):** the normalized events for Claude Code and Codex, the
   session registry and its lock states.
2. **The MCP server:** the tools with approval metadata, auto-mode caps and single-writer ledger updates.
   Testable from the CLI before any UI.
3. **Reidcc resume + attach / detach bridge:** opening a sub-run brings up a live Reidcc session window
   (the SPEC-one-look / SPEC-one-window chrome) and hands control back on close.
4. **The command center window ("one screen, two areas"):** a thin Tauri window on the same `tokens.css`.
   The conductor chat in the main area, the sub-runs with a Stop button and an approval banner at the side.

**Note:** this matches Part 5 steps 1–2 and 4, with Part 5's step 0 (Codex level with Claude) assumed
done. It adds the registry and IPC (7a items 1 and 6) as their own step before the window.

### 7d. What Reidcc itself needs (a second outside review, 2026-11-25, with corrections)

Reidcc needs no rewrite for the command center to sit on top: finish what's in flight on dev, then add four
small building blocks in `rs/core` and `rs/app`. Reidcc stays unaware of the command center.

**Step A: stabilize dev first.**
- Finish SPEC-one-window and SPEC-one-look. Frames are still untested on dev, and the windows the command
  center opens are these session windows.
- Clear the SPEC-user-trial reliability fixes (0/13), above all profiles, sign-in env and session crashes:
  the command center inherits every one of them.

**Step B: the four moves.**

| Move | Where | What | Why the command center needs it |
|---|---|---|---|
| 1. Headless runner | `rs/core/src/engines/` | A non-PTY runner (`claude -p --output-format stream-json`, `codex exec --json`) on the existing profile, sign-in, persona, proxy and memory builder, emitting `started`, `chunk`, `tool_call`, `usage`, `done`, `error` | Headless isn't built; the conductor's run tool can't exist without it |
| 2. Session registry and locks | `rs/core` | One file per session: id, engine, profile, folder, context %, state (`idle`, `running-headless`, `attached-in-window`), pid, window handle | Lists sessions, and stops the conductor writing to a session you're typing in |
| 3. `Reidcc.exe --resume <id>` | `rs/app` (`main.rs`, `session.rs`) | Open that session in a window, or bring it forward if it's already open; state `attached-in-window` while open, `idle` after | Clicking a sub-run (or "open it") takes you straight there, and the conductor can peek right after you close it |
| 4. Usage and typed errors | `rs/core` | Context %, cost and failures (`rate_limited`, `auth_expired`, `context_full`, `crashed`, `unknown { exit_code, raw }`) as plain Rust types | Status per sub-run, and the conductor pauses cleanly instead of reading stderr |

**Skip for now:** conductor, ledger and MCP code inside `rs/app` (Reidcc stays a standalone launcher);
OpenCode, agy and SPEC-tui polish. Prove the headless + `--resume` seam with Claude Code and Codex first.
Then the command center is a new `rs/command` crate in the same workspace.

**Corrections and additions** (checked against the code 2026-11-25; the last three from Reid via Gemini):

1. **"Release" waits for Reid.** A release means publishing dev to the public main, and main changes only
   when Reid says so (`git push origin dev:publish`, then a tag). Before that: fix the SPEC-one-window review
   finding (a session that ends in the background or minimized moves Reidcc to it, off screen if minimized)
   and test docking in a frame. The trial's fixes 1–4 are about an hour (README).
2. **Move 1, step 0: Codex session ids and resume.** Claude is half there: `session::run`
   (`rs/core/src/session.rs`) already picks Claude's session id at launch, so a headless Claude run gets one
   free. Codex has neither: resume is refused ("Resume is for Claude profiles for now") and its session id
   isn't recorded. Capture the Codex id (`codex exec --json` reports it; interactive sessions need it too)
   and pass `codex resume` / `codex exec resume` through. This blocks moves 2 and 3 for Codex, and is Part 5's
   step 0.
3. **Move 2: where and how.**
   - In Reidcc's own folder, not `%LOCALAPPDATA%`: `REIDCC_HOME\sessions\<id>.json`, beside
     `reid_state.json` (which already keeps the last session).
   - **One file per session**, written atomically (temp file, then rename). Reid runs 5+ `Reidcc.exe`
     processes at once, each owning the sessions it opened; one shared file would race. A file per session
     means each process writes only its own. Readers retry once: a rename can fail while a reader has the file
     open.
   - The command center **watches that folder** for attach / detach. No named pipe needed.
   - Stale entries: a crashed process leaves `attached-in-window` behind and would lock the conductor out
     for good. Prune on read (rule 4).
4. **Move 3: `Reidcc.exe` takes `--cwd` and `--update` today**, and every launch is a new process. `--resume
   <id>` is new. "Bring it forward if open" is the registry's pid and window handle plus a focus call; no IPC.
5. **Pid and window handle are checked together**, on focus and when pruning: the window still exists
   (`IsWindow`) and its owning process (`GetWindowThreadProcessId`) is the entry's pid. Windows reuses both
   numbers after a crash, so one alone can point at someone else's window.
6. **Move 4: reuse what's there, expect drift.** Claude's context % already comes from the statusline
   (`cmd_statusline`). The typed errors come from matching each engine's error text, which changes when the
   CLIs change; anything that doesn't match is `unknown { exit_code, raw }`, never dropped.
