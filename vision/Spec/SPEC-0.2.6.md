# SPEC: 0.2.6 beta (OpenCode as the third engine, and a full context switch)

Status: built on dev 2026-11-27 (OpenCode `d038f1a`, the switch `0dc93fb`), not released; see "Built" at
the end. Rev 1 2026-11-27. Builds on `SPEC-unified-interface.md` (chat, `--stream`, the
switch) and `SPEC-codex-opencode.md` (milestone 2: opening OpenCode in a session window).

Asked by Reid 2026-11-27:
> "The handoff.md that's not a full context switch this is 02.6"
> "O and the opencode engine"
> "Deterministic but I was thinking that you could just shove the context it self around"

## The idea in one line
Switching engines moves the conversation itself. Reidcc keeps one transcript per chat. On a switch it
writes that transcript into the next engine's own session format, as a new session, and resumes it. The
next engine then has the whole chat as its own history: no summary, and no model involved. OpenCode joins
as a third engine that works everywhere Claude Code and Codex do.

---

## Part 0: what's there now (read 2026-11-27)

- **The switch today** (`rs/core/src/handoff.rs`): `.reid/handoff.md` holds the folder, which profile it
  came from, `git status`, `git diff --stat HEAD`, and tests and a note when given. It's written by plain
  code and put before the next turn's prompt. It carries **none of the conversation**.
- **Sessions are per profile** (`rs/ui/src/chat.ts`: `sids[profile]`): a chat that goes Claude → Codex →
  Claude resumes Claude's own session and Codex's own thread. Each engine sees only its own turns plus a
  handoff. That is the gap Reid named.
- **Turns** run as `reid --stream <profile> [--resume ID] [--switch-from P]` children. The GUI chat and
  the TUI chat (`reid --chat`) both use it, so anything built into `--stream` reaches both.
- **OpenCode**: only researched (`SPEC-codex-opencode.md`, milestone 2, OpenCode 2.3.0). The installed
  version is still 2.3.0, so that research holds.

## Part 1: verified on this machine (2026-11-27)

Claude Code 2.1.332, codex-cli 0.172.0, OpenCode 2.3.0. Each probe was a scratch folder with a
hand-built session holding one exchange: the user gives the codeword `PERIWINKLE-42`, the assistant
says `ok`. Then the engine resumed it and was asked for the codeword. The probe files were deleted after.

| Engine | Where sessions live | Hand-built session resumed? |
|---|---|---|
| Claude Code | `~/.claude/projects/<folder slug>/<uuid>.jsonl` (slug: the folder path with every non-alphanumeric character → `-`) | **Yes.** Two records (`user`, `assistant`, each with `uuid`, `parentUuid`, `sessionId`, `cwd`, `version`, `timestamp`, `message`) → `claude -p --resume <uuid>` answered `PERIWINKLE-42`. The assistant record named another model; Claude didn't care. Resume appends to the same file. |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<uuid>.jsonl` | **Yes.** Three lines (`session_meta` with id, timestamp, cwd, originator, cli_version, source, model_provider; then two `response_item` messages: `input_text` for the user, `output_text` for the assistant) → `codex exec resume <uuid>` answered `PERIWINKLE-42`. No index entry was needed. |
| OpenCode | its own store | **Supported, not probed:** `opencode session import <file or URL>` and `opencode session export`, plus `opencode run --format json --session <id>` for headless turns. |

Also found: Codex 0.172 has its own importer for other agents' sessions (it had imported 15 Claude Code
sessions; `~/.codex/external_agent_session_imports.json`, with `external_agent_tool_call` /
`external_agent_tool_result` item types). It runs from Codex's onboarding and app server, not from a CLI
command, and only goes Claude → Codex, so Reidcc doesn't use it. It's a fallback to look at if
hand-built rollouts stop working.

---

## Part 2: the full context switch

### 2.1 One transcript per chat (Reidcc's own)
- Each chat gets a uuid when it opens. The GUI passes it to each turn as `reid --stream ... --chat <uuid>`;
  the TUI chat does the same.
- `--stream` appends every turn to `<REIDCC_HOME>/chats/<uuid>.jsonl`, from the events it already parses:
  - `{"role":"user","profile","engine","text"}` when the turn starts;
  - `{"role":"assistant","profile","engine","text"}` with the turn's streamed text;
  - one `{"role":"tool","name","input","output"}` per tool call, output cut to 4 KB (`… N KB cut`).
- It lives in Reidcc's folder, not the project, the way the engines keep theirs. Never committed (the
  repo's ignore list gains `chats/`). Deleting a chat in the UI doesn't exist yet; the file just stays,
  like engine sessions do.
- Thinking and reasoning are left out: Claude's thinking carries signatures and Codex's reasoning is
  encrypted, so neither can move to another engine.

### 2.2 On a switch: a new native session from the transcript
`--switch-from P --chat <uuid>` on a turn for another engine:
1. Writes `.reid/handoff.md` as today (file state).
2. Builds a **new** session for the target engine from the whole transcript, in that engine's format
   (Part 1), with a fresh id. It never edits an engine's existing session file.
   - user and assistant text become native user and assistant messages, in order;
   - each tool call becomes plain text inside the assistant message:
     `[ran in codex] shell: npm test → exit 0 · 12 lines` plus the cut output. Not native tool calls:
     tool names and ids differ per engine, and Claude checks that every tool call has its result;
   - each assistant message starts with its source, e.g. `[codex · gpt-5.5]`, so the model knows another
     agent said it.
3. Resumes that session with the handoff in front of the prompt (today's `handoff::prompt`).
4. The chat's `sids[profile]` becomes the new id. `open terminal` then resumes a session that holds the
   whole chat.

Switching back builds again from the transcript, so every switch carries every turn so far.

### 2.3 Size
- The target engine's window is known per model (the context numbers the chat already shows). The
  carried conversation is held to **60%** of it, counted at 4 characters per token.
- When it doesn't fit, Reidcc keeps the first user message and the newest turns that fit, and puts one
  line where the gap is: `[N earlier turns left out: they're in Reidcc's chat transcript]`. It's
  deterministic: the same transcript always gives the same session.

### 2.4 When it fails
If writing the session or resuming it fails (an engine version changed its format, or the file isn't
accepted), the turn falls back to a new session with the transcript **as text** in front of the prompt,
cut to the same 60%. The chat shows one line: `context passed as text: <engine> didn't take the session`.
The turn never fails because of the switch.

### 2.5 Where the code goes
- `rs/core/src/transcript.rs`: append and read the chat transcript; the size cut.
- `rs/core/src/handoff.rs`: gains `native(engine, transcript, folder) -> R<String>` (writes the session,
  returns its id), one small writer per engine.
- `rs/core/src/stream.rs`: `--chat`; on a switch, `native` first, then the fallback.
- `rs/ui/src/chat.ts` and `rs/cli/src/chat.rs`: make the uuid, pass `--chat`, take the new id.

---

## Part 3: OpenCode, the third engine

Milestone 2 of `SPEC-codex-opencode.md` (session windows: `--standalone`, model and persona through
`OPENCODE_CONFIG_CONTENT`, sign-in through `OPENCODE_CONFIG`, Reid's own `opencode.json` untouched) is
built as specced. On top of it:

| Where | OpenCode |
|---|---|
| launcher | `opencode` in the engine box; the model list from `opencode models`; Claude-only rows greyed like Codex's |
| session window | `opencode --standalone` in the folder (milestone 2) |
| `reid --stream` | `opencode run --standalone --format json [--session ID] PROMPT`; its JSON lines mapped to Reidcc's events (`started`, `text`, `tool`, `tokens`, `done`) like `codex_line` |
| resume | `--session <id>` (stream) and `opencode --standalone --session <id>` (session window); `reid --resume <profile> --id ID` finds it |
| read-only | OpenCode's own permissions, passed in the config layer: edit, write and bash set to `deny`. A profile whose args turn them back on is refused for read-only, as for Claude and Codex |
| tune | model `provider/model#variant` (the variant is OpenCode's effort); MCP servers on or off through the config layer's `mcp` entries; saved per profile like Codex's |
| switch | to and from OpenCode, through `session import` (Part 2) |
| proxy | not in 0.2.6: OpenCode talks to many providers, and the proxy only knows Anthropic's and OpenAI's APIs |

## Part 4: verify at build (not checked yet)
1. OpenCode: what `run --format json` prints (event names, tokens, cost), and that `--standalone` works
   with `run`.
2. OpenCode: the permission keys and values that make a read-only turn, tested the way Codex's guards
   were. That means a turn that tries to write and is refused, with Reid's own config loaded.
3. OpenCode: the `session export` JSON shape, and that an imported session resumes with its history
   (the codeword probe).
4. Claude: a hand-built session whose assistant text holds `[ran in codex] …` tool text resumes and is
   understood. Also check a longer session (100+ messages).
5. Codex: the same with a longer rollout. Check that `codex resume <id>` (the interactive one, for
   `open terminal`) opens a hand-built thread too, not only `exec resume`.
6. That the hand-built sessions show up sensibly in each engine's own resume list (title, folder). This
   is cosmetic, but Reid will see them there.

## Part 5: done when
1. The codeword test, through the chat, for every pair: Claude → Codex, Codex → Claude, Claude → OpenCode,
   OpenCode → Codex, and back. Give the codeword to engine A, switch to B, and B answers it.
2. A three-engine chat (Claude → Codex → OpenCode → Claude): the last turn can quote something said to
   Codex.
3. A transcript over 60% of the target window carries the newest turns, the first message and the gap
   line, and the turn still runs.
4. A broken session file (forced in a test) falls back to text, shows the one line, and the turn runs.
5. OpenCode in chat: streams, stops, edits with a **changed** block, read-only refuses a write, tune
   changes model and effort, `open terminal` resumes it.
6. Claude and Codex chat turns without a switch are unchanged. `cargo test --workspace`,
   `milestone1_flow`, `chat_flow` and `tui_chat_flow` pass.
7. Docs:
   - `chat.md` (switching carries the conversation);
   - `engines.md` (OpenCode);
   - `next.md` (moves to the changelog);
   - CHANGELOG `## 0.2.6 beta`.

## Built (2026-11-27)

Where the build differs from the spec:
- The transcript is written at turn end, only for a turn that ran (a refused one leaves nothing). Records are
  `{role, profile, engine, model, text}` and `{role:"assistant", …, parts:[{text}|{tool, summary, output}]}`.
  `output` is the end of the tool's output: terminal escapes out (a shell profile's colours and sixel logo
  reach Codex's output), each line as last redrawn, the last 2 KB cut on a char boundary. It goes along
  indented under its `[ran in …]` line. No `→ exit 0 · 12 lines`: the end of a failed run shows the failure,
  and the engines report exit codes three ways. Each engine's output finds its call by id (Claude's
  parallel calls answer in any order); it's kept out of `--stream`.
- The native writers live in `transcript.rs` with the transcript, not in `handoff.rs`.
- The window is per engine, not per model: Claude 200k, Codex 272k, OpenCode 128k (tokens).
- The fallback covers a session that can't be written, one the engine doesn't list after writing, and one it
  then won't resume: the resume errors before any text or tool call, or names another session as it starts
  (Codex `exec resume` of an id it can't load starts an empty thread; Reidcc stops it at that first event).
  The turn then runs once more as a new session with the text; one retry, so a sign-in or network failure
  shows at once. The chat never sees the dead session's id; the next turn resumes the new one.
- OpenCode `run --session <unknown id>` makes a session with that id, so a dead resume there can't be seen;
  only the `session export` check after the import covers it.
- A writing switch takes the folder lock before it carries, so a busy folder refuses before a session is made.
- OpenCode tune: effort only. MCP servers and plugins on or off for OpenCode aren't built.

Part 4 at build:
1. Verified: `run --format json` events (`step_start`, `text`, `tool_use`, `step_finish` with tokens and cost,
   `error`; no end event), `--standalone` with `run`.
2. Verified: a turn agent with `*: deny` plus read, glob, grep, list, lsp, webfetch and websearch refuses
   writes and shell with Reid's own config loaded (`opencode_flow`).
3. Verified: `session import` of an export-shaped file (it needs the folder's project id, read from a
   throwaway `session.create`), then `run --session` answers from it.
4. Verified: Claude resumes a hand-built 240-message session with `[ran in …]` text.
5. Verified: Codex `exec resume` of a 240-message rollout, and interactive `codex resume <id>` of a thread
   built from a switch, in a Reidcc session window (`codex_resume_flow` D): it answers from the Claude turn.
6. Checked 2026-11-27, each engine's own list for a chat carried across all three:
   - OpenCode `session list`: every Reidcc session read "Untitled session", carried or not: a `--standalone`
     run or an import makes no title (OpenCode's server does). Reidcc now names a new session after its ask
     and a carried one after the chat's first ask (`session.update`; `opencode_flow` 2 checks it).
   - Codex `codex resume` picker: lists no `exec` thread, a plain `codex exec` one included, so neither chat
     turns nor carried threads show. Codex's choice; `open terminal` resumes by id.
   - Claude `claude --resume` picker: lists no `-p` session, carried or not ("No sessions in this project
     yet"). Claude's choice; `open terminal` resumes by id.

Part 5 at build:
1-3. `switch_flow` 48/48: every direction, a three-engine chat, 240-message sessions, a transcript over
   OpenCode's 60% with the gap line.
4. The write fallback is a unit test (a writer that fails). The resume fallback is end-to-end: `switch_flow`
   part 9 (debug build, `REIDCC_TEST_DEAD_RESUME`) for Claude and Codex.
5. OpenCode through `reid --stream` (`opencode_flow` 18/18), in a session window (`session_flow`) and in the
   GUI chat (`chat_flow` 5): a carried switch, a write without a shell, an answer from a turn it never saw.
6. `cargo test --workspace`, `milestone1_flow` 31/31, `chat_flow` 53/53, `tui_chat_flow` 43/43,
   `codex_resume_flow` 14/14.
7. Docs done.

## Part 6: left out
- Moving thinking or reasoning (it can't be moved, Part 2.1).
- Summaries by a model (Reid chose deterministic).
- Context switching for session windows that weren't started from a chat. Their transcripts are the
  engines' own, and reading those is a separate step.
- OpenCode through the proxy.
- Codex's own external-agent importer (Part 1).
