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
