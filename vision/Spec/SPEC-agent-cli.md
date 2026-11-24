# SPEC: the agent CLI that sits on top of agent CLIs

Status: SPEC 2026-11-23. Idea, not scheduled. Nothing here is built.

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
