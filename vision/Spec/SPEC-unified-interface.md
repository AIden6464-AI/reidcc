# SPEC — Reidcc Unified Interface (GUI & TUI)

Status: Draft vision blueprint (Revision 4, grounded against `dev` at commit `f38e14f`, `0.2.2 beta`).
Saved 2026-11-25 as Reid gave it ("Save this"); the page version is `SPEC-unified-interface.html`.
Notes against today's `dev` are at the end, kept apart from Reid's text.

> **Prototype note:** The GUI and TUI layouts described here are directional prototypes — something like
> this, not a 1:1 of Reidcc — and the final UI/TUI craft still needs dedicated design work against
> Reidcc's real screens.

## Core Thesis

One direct interface (GUI and TUI) over Claude Code and Codex, with zero central boss AI ("no NVIDIA SLI").

- **One app, not two:** No separate Command Center desktop app (`rs/command`), no middleman conductor LLM,
  and no MCP delegation server.
- **Direct to real CLIs:** Your prompt goes straight to the active engine (`claude -p --output-format
  stream-json` or `codex exec --json`) using your existing Reidcc profile, sign-in env, persona, ACA
  memory, and prompt-cache proxy.
- **One-step context switch:** Flipping profiles in place writes a deterministic `.reid/handoff.md` (git
  diff summary, changed files, recent test output, optional note) and hands it straight into the next
  engine's turn.
- **Optional raw terminal hatch:** Whenever you want the native CLI TUI, `open terminal` launches or
  focuses that exact session in a live Reidcc window (`--resume <id>`), guarded by an OS-backed session lock.

## Part 1 — Why No Central Conductor AI

Forcing a master AI to orchestrate worker AIs adds heavy synchronization overhead, fragile recursion
guards, extra token latency, and a middleman playing telephone with your intent. Dropping the boss AI
removes an entire layer of complexity while keeping every day-to-day benefit:

| Layer | Dropped (Boss-AI / SLI Overhead) | Kept (Direct One-Interface Reidcc) |
|---|---|---|
| App topology | Second Tauri desktop app (`rs/command`) on top of Reidcc | One app (Reidcc) hosting GUI + TUI + optional raw terminal hatch |
| Delegation & MCP | Conductor LLM, 4-tool MCP server (ask/peek/handoff/sessions), recursion blocking, auto-mode loop caps | Direct profile picker (`main · claude` ↔ `review · codex`) + engine-enforced read-only |
| Context transfer | Transcript `peek()` scraping + LLM-summarized handoffs | Deterministic `.reid/handoff.md` + existing ACA memory & Persona |
| Visual language | Generic dark SaaS or separate terminal TUIs | Reidcc's own `tokens.css` engraved-stone GUI & TUI with zero AI looks |

## Part 2 — Visual & Voice Contract (Directional Prototype)

### Palette & Surface Rules (`rs/ui/src/tokens.css`, `vision/reidcc-palette.md`, `SPEC-one-look.md`)

"Engraved stone and blueprint linework on near-black, with one emerald signal." Zero blue-black
backgrounds, zero purple/AI gradients, zero drop shadows.

| Token | Exact Value | Role in Unified GUI & TUI |
|---|---|---|
| `--canvas` / `--s1` / `--s2` | `#040404` · `#0E0D0C` · `#171513` | Near-pure black ground, warm obsidian panels/composer, hover & diff blocks |
| `--stone` / `--line` / `--line2` | `#292723` · `#2A2724` · `#4A4540` | Full-width selected session row, 1 px hairlines, 1 px focus ring (no dotted boxes) |
| `--linework` | `#928A82` | 12 px RC mark, thin ring around status dot, crosshair ticks |
| `--text` / `--text2` / `--text3` | `#D6D0C8` · `#9F978E` · `#746F69` | Bone primary text & primary button fill, secondary labels/tags, muted telemetry & corner `+` marks |
| `--emerald` / `--bronze` / `--oxide` | `#00C463` · `#C99A45` · `#C0584B` | At most one emerald element visible at a time (live status dot); bronze for 75–89% context/busy; oxide for 90%+ / errors / `-lines` |

- **Top bar:** 36 px borderless bar (`RC` mark, `folder · profile · engine`, `gui` / `tui` surface
  toggle, single emerald dot ringed in `--linework`, session timer, `context %` or `context unknown`,
  `limit %`, and `- □ ×`).
- **GUI layout (4 flat zones):** Top telemetry bar, unified message + collapsible diff stream with inline
  `.reid/handoff.md` switch dividers, collapsible right sidebar (`SESSIONS`, `CONTEXT`,
  `.REID/HANDOFF.MD`), and bottom composer (`--s1`, 1 px `--line2` focus ring, profile dropdown, `✓`/`·`
  `read-only` toggle, `switch →` button, bone `send` button).
- **TUI counterpart (`rs/cli`):** Same `#040404` / 16-color Reidcc palette, synced session/message state,
  toggleable right sessions pane, `profile·engine>` prompt supporting slash commands (`/switch`, `/ro`,
  `/terminal`, `/gui`), and bottom keybind strip (`^S switch`, `^R read-only`, `^O open terminal`,
  `^L sessions`, `^T gui view`).

### Voice Rules (`vision/reidcc-voice.md`)

- **Feeling:** Calm control — short, declarative, numbers over adjectives, zero emoji, zero exclamation
  marks, zero hype.
- **Formatting:** Lowercase UI labels and buttons (`open terminal`, `read-only`, `switch → codex`,
  `send`); 11 px uppercase mono system tags (`PROFILE · MAIN`, `PERSONA · PLAIN`, `MEMORY · ON`,
  `HANDOFF · READY`); on/off marks `✓` and `·`.
- **Exact vocabulary:** `folder`, `profile`, `persona`, `memory`, `session`, `context`, `limit`,
  `changed`, `paste`, `open gate`.

## Part 3 — Four Code-Verified Rust Contracts (from `dev` @ `f38e14f`)

1. **Unblock Codex resume in all 3 layers (Step 0):**
   - *Code reality:* Codex resume is currently blocked in the Codex adapter (leading `resume`/`fork`
     args), `rs/core` (non-Claude profile guard), and GUI launch.
   - *Requirement:* Capture Codex's `thread_id` on both interactive and streamed runs, unblock resume
     across all three layers, and preserve existing `reid --resume [profile]` CLI behavior.
   - *The hard part (Reid, 2026-11-25):* "The hard part is identifying which Codex thread a fresh Reidcc
     window created. Removing the guards only gets you partway." The ID must be tied to that window's own
     Codex process, never found by a "most recent thread" lookup.
2. **Normalized `StreamEngine` adapter (`rs/core`):**
   - *Requirement:* Map Claude Code (`-p --output-format stream-json`) and Codex (`exec --json`) into one
     Rust event enum (`started`, `text`, `tool_call`, `diff`, `usage`, `done`, `error`) with an explicit
     `mode: write | read_only` enforced at the CLI level, shared by both GUI and TUI.
3. **OS-backed per-session & folder locks:**
   - *Code reality:* Atomic JSON replacement prevents torn reads, not TOCTOU races across multiple
     `Reidcc.exe` instances or between the unified UI and an opened raw terminal hatch. Headless/streamed
     workers also have no `hwnd`.
   - *Requirement:* Acquire an OS-backed per-session lockfile before streaming or attaching a raw
     terminal, store metadata in `REIDCC_HOME/sessions/<id>.json` with `pid` tracked independently of
     optional `hwnd`, and enforce a per-folder write lock across different sessions.
4. **Honest optional usage & resilient errors:**
   - *Code reality:* `reidcc-core` already parses Claude's status line, but missing context currently
     becomes `0%`.
   - *Requirement:* Extract the parser in place, make context % and cost `Option<T>` rendered as
     `unknown` when unreported, and include `unknown { exit_code, raw }` on the error enum so CLI wording
     changes never break error handling.

## Part 4 — Context Switch Flow

Persona and ACA memory stay active across every step. Switching is deterministic and human-triggered.

Claude Code (write · stream) → **Switch ⇄** (`.reid/handoff.md`) → Codex (read-only · stream) → Raw PTY
(optional). Persona + ACA memory stay active across every step · OS lock guards raw PTY takeover.

## Part 5 — Build Order & CLI Naming Candidates

- **CLI naming options (matching `reidcc-voice.md`):** Keep `reid` (cleanest zero-friction choice since
  it is one unified tool), or choose a stone/blueprint name such as `gate`, `slate`, `kiln` (already
  referenced in `reidcc-voice.md`), or `bench`.

| Stage | Scope | Acceptance Test |
|---|---|---|
| Pre-flight | Stabilize dev baseline (main stays untouched via manual publish workflow) | Fix background/minimized session-exit window jump, test docking in snapped frames, clear quick SPEC-user-trial fixes 1–4. |
| Step 0 | Unblock Codex resume (adapter, core, GUI) | Prove both directions on Windows: (1) open a known headless thread in a Reidcc window; (2) open a fresh Codex session in Reidcc and have the headless runner continue that exact thread. Run (2) with two Codex windows in the same folder, so a "most recent thread" lookup can't pass by accident. Keep `reid --resume [profile]` intact. |
| Milestone 1 | Direct StreamEngine + Context Switch (`rs/core`) | Run Claude Code edit → trigger Switch (writes `.reid/handoff.md`) → run Codex read-only review in the same folder with OS locks guarding raw terminal takeover. |
| Milestone 2 | Unified GUI (`rs/app` + `rs/ui`) & TUI (`rs/cli`) | Build the engraved-stone GUI and matching TUI over the proven Milestone 1 backend, refining visual craft into a true 1:1 Reidcc experience. |
| Deferred | Explicitly out of scope | Central boss AI / conductor LLM, MCP delegation server, second desktop app, OpenCode backend/engine, agy, crons, and messaging gateways. |

## Part 6 — Milestone 2 Decisions (Reid, 2026-11-25)

Given after Milestone 1 was built, in answer to the open questions it left. His words are quoted.

- **Shape:** "GUI first as a new window type spawning reid --stream as a child process, TUI second." The
  chat window sits beside the existing session windows; it replaces nothing. A turn is a
  `reid --stream` child, so a crash in a turn can't take Reidcc down, and `stop` kills that child (its
  kill-on-close job takes the engine with it).
- **Acceptance test:** "disposable repo → Claude stream + stop → switch → codex read-only with
  .reid/handoff.md divider and context unknown → open terminal with --resume <id> and composer lock
  state." Spelled out: open the chat window on a disposable git repo; send a Claude prompt and watch it
  stream; stop a turn; flip `switch → codex` with `read-only` on and see the `.reid/handoff.md` divider,
  then the Codex review with `context unknown`; press `open terminal` (`--resume <id>`) and see the
  composer show the lock cleanly until the terminal closes.
- **Write turns:** "Keep Claude write turns edit-only (acceptEdits) for Milestone 2 and use open
  terminal for shell/tests. Defer --permission-prompt-tool." A per-profile opt-in to allow the shell
  may come later.
- **Folder lock:** "Keep exclusive folder locks for write turns, allow read-only turns to share the
  folder lock, and show a clean composer refusal with a focus window / read-only option when blocked."
- **Tags:** "Match built SPEC-one-look (lowercase tags)." This settles the Part 2 conflict: lowercase.
- **Diff:** "compute collapsible diff summary from git diff on Done." No engine-specific `diff` event:
  `git diff --stat` (and the full diff on expand) after each turn, the same for Claude and Codex.
- **History:** "defer loading old Claude/Codex transcripts to Milestone 2.1." Milestone 2 shows the
  live turns and the handoff.
- **Codex writes:** "add one Codex write check to milestone1_flow.py."
- **Next:** "do the short design pass for the chat window composer and stream against the real
  launcher before writing UI code."

## Sources

1. `rs/ui/src/tokens.css` — Exact hex palette, font stacks, and motion curve.
2. `vision/reidcc-palette.md` and `vision/Spec/SPEC-one-look.md` — Engraved-stone aesthetic,
   single-emerald rule, 36 px borderless bar, 1 px focus rings, and 16-color terminal mapping.
3. `vision/reidcc-voice.md` — Tagline, calm-control voice rules, formatting, and vocabulary.
4. `AIden6464-AI/reidcc` (`dev` branch), commits at `f38e14f`, and `vision/Spec/SPEC-agent-cli.md` —
   Rust workspace structure, `.reid/handoff.md` contract, and manual publish workflow.

---

## Notes against `dev` (2026-11-25, not part of Reid's text)

- **It replaces SPEC-agent-cli's command center.** That spec plans a separate app on top of Reidcc with
  a conductor; this one drops both. Its Part 7 plumbing (locks, `sessions/<id>.json`, typed errors,
  `--resume`) carries over as contracts 1, 3 and 4 here.
- **Pre-flight is done on dev** (commits after `f38e14f`): the session-exit jump is fixed (`b695a97`),
  docking in frames is tested (dock_flow 43/43), and trial fixes 1–13 are in, not only 1–4.
- **Tags disagree with what's built.** Part 2 asks for uppercase tags (`PROFILE · MAIN`), but
  SPEC-one-look Part 2, built 2026-11-25 on the launcher, TUI and session bar, made them lowercase
  (`main · claude · persona plain · memory`). One of the two has to give.
- **Step 0 built on dev (2026-11-25).** The three refusals are gone (adapter, `session::run`, GUI/TUI).
  A Codex session's id is found while it runs: the thread file Windows' Restart Manager says is held open
  by that session's own `codex.exe` (`codex::thread_of`), never the newest file; subagent threads are
  skipped. It goes into `reid_state.json`'s `last` with its engine, as soon as it's found and again when
  the session ends. Resume hands Codex `resume <id>`, or `resume --last` when there's no Codex id (like
  Claude's `-c`). The headless runner is `reid <profile> exec --json …` / `exec resume <id> …`.
  Proof: `rs/tests/codex_resume_flow.py` 9/9 (real Codex, two windows in one folder; it deletes its
  threads afterwards).
- **Milestone 1 built on dev (2026-11-25), core and CLI only; no UI yet.**
  - `reid --stream <profile> [--read-only] [--resume ID] [--switch-from P [--tests T] [--note N]] PROMPT`
    runs one headless turn and prints events as JSON lines (`rs/core/src/stream.rs`). The events are
    `started`, `text_delta`, `tool_call`, `usage {context_pct, cost_usd}`, `done` and `error`.
    `error` is one of three kinds:
    - `engine`: the engine reported the error.
    - `refused`: a lock or a bad profile stopped the turn before it started.
    - `unknown`: a nonzero exit with nothing reported; it carries the exit code and the end of stderr.
  - Contract 2 also names a `diff` event; it isn't built, because Reid's Milestone 1 handoff left it out.
  - Context: Claude's comes from its last request's tokens against `modelUsage.contextWindow`.
    Codex exec reports neither context nor cost, so both stay `null`. The statusline shows a missing
    figure as `context unknown`, never 0%.
  - **Read-only, checked against the installed binaries:**
    - Claude: `--permission-mode default --disallowedTools Write Edit NotebookEdit Bash PowerShell
      EnterWorktree`. Those tools leave the session, including for subagents. Plan mode alone only
      made the model hold back by choice.
    - Codex: `-c sandbox_mode="read-only" -c approval_policy="never"`. With `-s read-only` alone,
      Codex's auto-reviewer approved a patch past the sandbox, because Reid's `approval_policy` is
      `on-request`. `exec resume` has no `-s`, so `-c` covers new and resumed threads alike.
    - A profile whose own args set these guards, or turn them off, is refused for read-only.
  - **Switch** writes `.reid/handoff.md` (`rs/core/src/handoff.rs`) with no model involved. It
    records the folder, `profile · engine`, `git status` and `git diff --stat HEAD` (both leaving
    `.reid/` out), plus the tests and note when given. The text goes before the next turn's prompt.
  - **Locks** (`rs/core/src/locks.rs`) are files held open. The OS releases them when the process
    dies, so no lock is ever stale.
    - `sessions/<id>.lock` and `sessions/<id>.json` record pid, hwnd when a window sets
      `REIDCC_HWND`, mode, folder and engine. They're taken by stream turns and by interactive
      sessions (`session::run`) once the id is known.
    - `locks/<folder hash>.lock` is the folder lock, shared or exclusive (Reid's choice, 2026-11-25:
      "Windows share, headless excludes"). Interactive windows hold it shared, so any number of them
      can be open in one folder (the Step 0 test needs two). A headless writing turn needs it alone:
      it's refused while a window or another writing turn is in the folder, and a new window is
      refused while one runs. Read-only turns take nothing.
    - The engine runs in a kill-on-close job, so killing `reid.exe` also takes the engine down.
  - Proof: `rs/tests/milestone1_flow.py` 25/25 (real Claude haiku and Codex; it deletes its sessions
    afterwards).
  - **Hardened (`74e8484`):**
    - The prompt is written on its own thread, so a long one can't deadlock on a full pipe.
    - The handoff lists a new folder as one line.
    - `.reid\.gitignore` holds `*`.
    - A lock's records are removed while it's still held.
    - A Codex `resume --last` onto a thread open elsewhere is stopped.
    - Claude `-c` says it can't be locked.
  - **Tests now:** 29 checks, adding a 22 KB prompt on stdin, `.reid` hidden from git, and a Codex
    write turn (Part 6).
- **Read-only turns and the folder lock (Part 6).** Reid's call says read-only turns share the folder
  lock. As built they take no folder lock at all, which already gives what he asked for: a Codex review
  runs with a terminal open. It is looser than sharing, though. A read-only turn also runs beside a
  headless write turn, where a shared lock would refuse it, and a review never blocks a write.
  Default: keep it as built. Say if reviews should wait for a running write instead.
- **Milestone 2 design pass (proposal, 2026-11-25; Reid approved it and its four defaults on 2026-11-26).** The mock is
  `unified-interface/mock/chat.html`, with the composer states at `chat.html#composer`. Screenshots sit
  next to it (`chat.png`, `composer.png`).
  - **Frame:** the session window's own frame, unchanged.
    - Left of the bar: the RC mark, the folder in bone, then `profile · engine · read-only` in text-2.
    - Right of the bar: `● 04:12 · context 41% | context unknown · limit 61%`, then `– ☐ ×`.
    - The emerald dot shows only while a turn runs. An idle window shows `ready` in text-2.
    - The `gui · tui` toggle waits for the TUI.
  - **Stream:** one column, at most 760 px wide, with no bubbles.
    - A prompt is an `--s1` band with a 1 px `--line2` left rule. It starts with
      `main · claude ›` in text-3 mono, matching the TUI's prompt.
    - Tool calls are one mono line each: a verb in text-2 (`read`, `edit`, `shell`, `patch`), then the
      summary in text-3.
    - Replies are bone sans text.
    - Each turn ends with a text-3 meta line: `00:38 · context 41% · $0.04 · edit-only`, or `stopped`.
  - **Changed:** after a write turn ends, a `--s2` block shows `git diff --stat` plus new files,
    leaving `.reid` out. It's collapsed to one line (`▾ changed · 1 file · +14 −3`), opens to show each
    file, and each file opens to its full diff.
    - Added lines and the `+` count are bone. Removed lines and the `−` count are oxide, never emerald.
    - Read-only turns get no block, and neither does a folder that isn't a git repo.
  - **Switch divider:** a `--line2` hairline with `switch · main · claude → review · codex · read-only`
    in linework in its middle, then a `.reid/handoff.md` link that opens the file.
  - **Sidebar (272 px, collapsible):**
    - `sessions` lists this folder's sessions: the chat window's own, plus session windows read from
      `sessions\*.json` (`terminal`). The selected row is the `--stone` bar.
    - `context` shows each profile's last figure, the limit and the cost.
    - `.reid/handoff.md` shows from, when written, the changed count and `open`.
    - Headers are lowercase.
  - **Composer:**
    - An `--s1` field with a 1 px `--line2` border on focus.
    - Under it: the profile picker (`main · claude ▾`), `✓ read-only` (or `·` when off),
      `open terminal`, then the window's one bone button.
    - The bone button is `send`. While a turn runs it becomes `stop` in oxide text. When the picker
      names another profile, it reads `switch → codex`.
  - **Switch, step by step:** picking another profile and pressing `switch → codex` writes the handoff
    from the current profile, draws the divider, and sends the typed prompt as the new profile's first
    turn.
    - No separate note box: the prompt is the ask. `--tests` stays unused in Milestone 2.
    - Each profile keeps its own session inside the window (`--resume <id>` per profile). Switching back
      continues Claude's session, with Codex's handoff in front.
  - **Refusals** take one line above the field, with a bronze label (busy, not an error) and actions,
    and `send` takes the disabled look:
    - `locked · A Reidcc window is open in this folder. · focus window · send read-only`
    - `in terminal · main · claude is open in a terminal. It comes back here when that closes. · focus terminal`
    - Engine errors go into the stream as an oxide line.
  - **Open questions (defaults if Reid doesn't say):**
    1. Where the chat window opens from. Default: a secondary `open chat` button beside `resume` on
       the launcher; `open gate` doesn't change.
    2. `send` as the window's bone primary. One-look keeps bone for `open gate`, but that rule is about
       the launcher. Default: one bone button per window.
    3. Should the folder refusal name the window's pid? The core names a writer's pid, not a window's.
       Default: no pid for windows.

- **Milestone 2 chat window, built (2026-11-26).** `rs/ui/chat.html` with `src/chat.ts` and `src/chat.css`
  holds the page. `rs/app/src/chat.rs` runs each turn as a `reid --stream` child. `rs/core/src/changes.rs`
  computes the per-turn git diff from scratch-index trees, so the real index is never touched.
  - **Launcher:** `open chat` sits beside `resume`. In the 500 px form the bar's first two buttons now
    read `memory` and `reid.json`, which keeps the bar on one line with 10 px spare (sizes_flow checks it).
  - **Open terminal:** runs `reid --resume <profile> --id <id>` in a session window over the chat. That
    `--id` is new in the CLI: that session, in this folder.
  - **Refusals** become the composer note:
    - `in terminal` with `focus terminal`. It clears once the terminal lets go, polled through
      `locks::holder`.
    - `locked · A Reidcc window is open in this folder.` (no PID) with `focus window` and `send read-only`.
    - A refused switch leaves no divider, and the ask stays in the field.
  - **Left out for now:**
    - The bar's `limit` figure: `reid --stream` doesn't report one yet.
    - Session windows listed in the sidebar: it shows only the chat's own sessions.
    - The `gui · tui` toggle, which waits for the TUI.
  - **Tests:** `rs/tests/chat_flow.py` runs the acceptance test above, 31/31.
- **Milestone 2B TUI chat, built (2026-11-26).** `rs/cli/src/chat.rs` is the chat window in text, on the
  SPEC-one-look 16-colour palette. Each turn is the same `reid --stream` child, and stop kills it (its job
  takes the engine down).
  - **Entry:** `c chat` beside `r resume` in the profile list, on the selected profile and the TUI's folder;
    and `reid --chat [profile]` (the default profile without one). Esc leaves.
  - **Keys:** ↵ send (or `switch → <engine>` once tab has picked another profile), esc stop, tab profile,
    ctrl+r read-only (`✓`/`·`), ctrl+t open terminal (`reid --resume <profile> --id <id>` in a console of its
    own), ctrl+d the last turn's diff, ctrl+o the handoff, pgup/pgdn scroll.
  - **Replies** follow md.ts: fences (an open one too) on the value ground, `code`, **bold**, link text
    underlined, headings bold. Engine text loses its control characters, so a reply can't drive the terminal.
  - **Refusals:** the same `in terminal` and `locked` notes; `ctrl+r sends it read-only` stands in for the
    button. A refused ask stays in the field and a refused switch leaves no divider.
  - **Left out:** multi-line prompts (a pasted line break sends); the sidebar (the bar carries context).
  - **Tests:** `rs/tests/tui_chat_flow.py` runs chat_flow's round trip in a pseudo-terminal, 33/33.
    `tui_parity.py` still shows 0 differ.
