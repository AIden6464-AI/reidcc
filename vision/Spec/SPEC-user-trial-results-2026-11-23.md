# User trial results, 2026-11-23

Status (2026-11-23): **0 of 13 "fix now" items done.** Reid hasn't picked yet.

Run from SPEC-user-trial.md. Two testers, Reidcc 0.2.2 portable, each in its own trial folder with a fresh
`REIDCC_HOME`, the r/ClaudeAI post (SPEC-reddit.md) and a clone of `main`. Nothing here goes into the app or
vision until Reid picks.

| Tester | Plays | Score | One line |
|---|---|---|---|
| Sam: Gemini 4 Argon (agy) | Claude Code Max user, 3 projects, MCP servers | **4/5** | "one-command profile switching, subscription auth protection, live context/limit % telemetry, and cross-profile `/reid` resume solve my real daily pain" |
| Jo: Codex GPT 6.2 Sol (`codex exec`) | Uses Claude Code and Codex, has agy, switches by hand | **3/5** | "I'd keep it around for profile previews and try it again with trial logins, but I'd still switch by hand for daily work today." |

Both would click the post. Sam: "Switching meant editing configs and retyping flags, so I built Reidcc."
Jo: "Codex profiles run from the same launcher, so both engines are one click apart."

**Caveats.** Jo signed in to nothing (it kept to fresh config folders inside the trial), so its Claude and
Codex runs stopped at "Not logged in" and its resume test has no meaning. Jo's first window sat on a Codex
start prompt for 10 minutes and was restarted with `codex exec`. Both testers got the engines through
`.cmd` shims in `bin\`, which is not how a normal npm install looks (see 1 below).

## Fix now (checked against the code)

| # | Finding | Who | Check | Smallest fix |
|---|---|---|---|---|
| 1 | `reid -h` is stale: points to `vision/SPEC-codex-opencode.md`, `vision/SPEC-codex-signin-persona.md`, `SPEC-proxy.md` (not on `main`, not installed); omits `--resume`, `--tui`, `--gui`; says "extra args go to claude" though they go to the engine. `NO_GUI` still says the window "isn't built yet". | both | **real** (rs/cli/src/main.rs:11-33, :36) | Rewrite HELP: add the 3 flags, "extra args go to the engine", point to the site docs instead of SPEC files. |
| 2 | install.md still says "The installer comes with the first release… Until it's out, build from source." build-from-source.md: "or until the first installer release". | both | **real** (site/docs/install.md:15, build-from-source.md:5) | Delete the callout; drop "or until the first installer release". |
| 3 | Setting `mcp` always adds `--strict-mcp-config` (your other servers are off), but reid-json.md says only `safe` "uses only the profile's MCP config". No example MCP file, no folder, no format anywhere in the docs. | both | **real** (rs/core/src/engines/claude.rs:122) | Docs: say `mcp` replaces your servers, show a 5-line `{"mcpServers": {...}}` example and where it lives. |
| 4 | `reid -l` prints `codex login · checking…` for every Codex profile: the CLI never runs the login check. | Sam | **real** (rs/core/src/engines/codex.rs:124) | In `-l`, run the check once (or print `codex login` without the status). |
| 5 | `reid --resume [profile]` drops any extra args; `reid --dry --resume` isn't a resume preview (it passes a bare `--resume` to the default profile). | Sam | **real** (rs/cli/src/main.rs:107-126, `&[]`; `--dry` doesn't know `--resume`) | Pass `args[2..]` as extra; teach `--dry` the `--resume` case. |
| 6 | Codex isn't found when the first `codex` on PATH is a wrapper that isn't the npm shim (here a `.cmd` shim; in real life pnpm/volta/scoop). Claude falls back to its shim; Codex doesn't. | both | **real, edge case** (codex.rs:24-41). A plain `npm i -g` install works. | Last fallback: run the `codex` shim found on PATH, like `find_claude`. |
| 7 | `reid -l` shows `mcp kiln` on a Codex profile, then launch says "Codex can't use an MCP choice." | Jo | **real** | Summary: leave Claude-only fields out for codex profiles, or mark them. |
| 8 | `reid --dry` deletes the temp settings/prompt files it just named, so you can't read what's injected; on Codex `--dry` runs `codex login status` / `debug prompt-input` and writes `codex/prompts/<profile>.md`. | Sam | **real, by design** (main.rs:197-201; Codex needs the base prompt to size the file) | Optional: `reid --dry -v` prints the files' text. Docs: say Codex's dry run writes the prompt file. |
| 9 | A misspelled profile (`reid --dry codex-klin`) silently runs the default profile with the typo as a Claude argument. | Jo | **by design** ("anything that isn't a profile goes to claude") | Optional: if the first word is one edit away from a profile name, say "no profile codex-klin (did you mean codex-kiln?)". |
| 10 | `docs/launcher.png` shows `Reidcc 0.1.1` and has other windows bleeding in at the edges. | Sam | **real** (already on the list) | The retake planned in SPEC-reddit.md Part 5. |
| 11 | profiles.md lists 6 fields and says the rest are reid.json-only, while launcher.png shows `proxy`, `tools`, `mcp`, `switches` on screen. | Sam | **real** | One line in profiles.md for the 4 screen fields. |
| 12 | A fresh reid.json writes `"memory_file": "reidcc_memory.md"` although "a setting left at its default isn't written"; the docs' `personas/plain.md` examples point to a file a new home doesn't have. | Sam | **real, minor** (rs/core/src/lib.rs:181) | Either leave it, or drop `memory_file` from `default_config`. Docs: say personas\ is yours to fill. |
| 13 | Without `REIDCC_HOME` Jo's sandboxed shell got a bare "The system cannot find the path specified. (os error 3)". | Jo | **sandbox** (Codex's sandbox user has no usable `%USERPROFILE%`); the bare message is real | Name the folder in the error ("Can't make the Reidcc folder C:\…"). |

**Not bugs:** Codex `resume`/`fork` refused ("Leave resume out of the extra args…") is the documented limit.
`reid codex -p "…"` hits Codex's own `-p` (`--profile`): Codex flags aren't Claude's. Jo's "No deferred tool
marker" on resume came from resuming a session that never signed in.

## They liked (protect it, show more of it)

- **The command preview** (`reid --dry`, and under the profile in the launcher). Jo: "the thing I'd miss most."
  Sam: "immediately builds trust."
- **The session bar.** Jo: "The session screenshot sold the bar better than the gate art did."
  `PROFILE · MAIN · ENGINE · CLAUDE` and `context 5% · limit 12%` are "where my eyes already go".
- **Cross-profile resume** (`/reid`, then resume with another profile). Sam: "the best workflow idea in Reidcc."
- **Subscription guard:** API key env vars are stripped from subscription profiles. Sam: on a Max plan
  "accidentally burning API credits… is a real hazard; Reidcc quietly prevents it."
- **Persona restores folder and platform** after replacing the prompt. Sam: "a great detail."
- **`reid -l` one-liners** and the TUI's `MEMORY · ON`.
- **Shared persona and memory across engines:** the Codex preview proved both landed in its prompt.

## They wanted (ranked: how often × how cheap)

1. **Docs for MCP** (both): example file, format, folder, and that it replaces your servers. Cheap.
2. **Engine-neutral headless syntax side by side** (both): Claude `reid p -p "…"` vs Codex
   `reid p exec --skip-git-repo-check "…"`. A table in cli.md. Cheap.
3. **License near the download** (both): "Companies and paid work… need a commercial license" sits at the
   bottom of the README. Both called it a surprise. One line on the site and by the download. Cheap.
4. **Explain the two signatures** (Sam, Jo): "It isn't code-signed yet" vs "Updates are signed". One
   sentence in updates.md: the update signature is Reidcc's own key; SmartScreen is separate. Cheap.
5. **A preflight** (Jo): engine found / signed in / fields this engine can't use, before launch. Medium.
6. **Additive MCP** (Sam): add a profile's servers on top of your own. Medium (a merged temp config).
7. **Per-project default profile and memory** (Sam: "I don't want build facts from Project A sent with every
   prompt in Projects B and C"). Today: a profile per project with its own `memory_file`. Bigger.
8. **Resume per folder, pick from recent** (Sam): `reid_state.json` keeps one `last`. Bigger.
9. **A reid.json snippet in the README** (Sam), and the launcher shot on the site home (Sam: the gate art
   and crosshair push it out). Cheap.
10. **Signed binaries, winget** (Sam). Known, later.

## Push further: the one-CLI idea, side by side

| | Sam | Jo |
|---|---|---|
| Want it? | **Yes**, "as long as `reid` stays a fast, transparent launcher… rather than a middleman" | **Yes**, "starting with agy since I already reach for it" |
| Same fields everywhere | Translate `mcp` and `safe` into each engine's flags (JSON vs TOML) | Same fields where they mean the same thing; unsupported ones called out before launch; room for native flags |
| Resume | Map `reid --resume` to each engine's own (`codex resume --last`), stop blocking it | Native resume where the engine has it |
| Usage bar | Keep one bar for all; later $/token burn, compaction warning, combined limit across panes | Worth it if it labels each engine's real limits and says when data is missing |
| Mid-task switch | A handoff summary into the next engine, or `/reid` logs a one-line handoff to memory | An inspectable handoff: goal, current diff, commands run, open questions, optional context |
| Memory | Already works across both; add per-project | One shared memory per project, with a switch for what each session reads/writes |
| What sends them back to the native CLI | Reidcc blocking a native subcommand, breaking on a wrapper on PATH, conflicting flags | A native feature or new flag Reidcc blocks, a tricky login, not knowing which command/account runs |

Both said the same thing in different words: **never get in the way of the native CLI.** Pass through what
you don't understand, show exactly what runs, and say up front what an engine can't do.

Other bigger bets they named: a profile switcher in the session bar (switch the live conversation without
typing `/reid`, Sam); a Monday view per project ("which agent last worked on it, what it left unfinished",
Jo); MCP servers registered once and ticked per profile like switches (Sam).

## Cleanup

Trial folders `C:\Temp\reidcc-trial-sam` and `-jo` deleted, plus `~/.claude/projects/C--Temp-reidcc-trial-sam-projects-kiln`
and the 3 Codex session files that ran in the trial folders. Reid's own `~/.claude` and `~/.codex` settings
were not changed (checked by modified time).
