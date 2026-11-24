# Agentic Coding CLIs: Evidence-Based Research Report

**Date:** 2026-11-23  
**Scope:** Primary evaluation of Claude Code, OpenAI Codex CLI, OpenCode, Cursor CLI (`cursor-agent` / `agent`), Google Gemini CLI, and Google Antigravity CLI (`agy`), plus secondary evaluation of Aider, Amp, Kilo/Cline/Roo CLIs, Qwen Code, Qoder CLI, Freebuff, Factory Droid, Warp, Devin, DeepSeek harnesses, Goose, Pi, Crush, Auggie, and GitHub Copilot CLI.

---

## 1. Summary: Strongest Findings

1. **No single CLI dominates both interactive conducting and headless worker execution.** The best interactive conductors (Claude Code, Antigravity CLI, OpenCode) have rich permission hooks, subagent orchestration, and slash-command ergonomics, while the cleanest deterministic workers (Codex CLI `codex exec`, Claude Code `-p`, Antigravity `agy -p`, Aider `--message`) win on structured JSONL streaming, low startup overhead, and predictable file output.
2. **Context compaction is the #1 destroyer of multi-file coding quality across every major CLI.** Users across Claude Code ([r/Anthropic, Oct 2026](https://www.reddit.com/r/Anthropic/comments/1x2gl7e/claude_code_gets_worse_after_every_compactions/)), Codex CLI ([r/codex, Aug 2026](https://www.reddit.com/r/codex/comments/1w8sqon/codex_56_after_every_context_compaction_sorry/)), OpenCode ([GitHub #31764, 2026-06-17](https://github.com/anomalyco/opencode/issues/31764); [GitHub #55667, 2026-10-15](https://github.com/anomalyco/opencode/issues/55667)), and Antigravity CLI ([GitHub #878, 2026-08-26](https://github.com/google-antigravity/antigravity-cli/issues/878)) report severe post-compaction amnesia ("lobotomy"), dropped architectural constraints, and infinite compaction loops.
3. **The Discord signal on OpenCode's "favorite yet takes forever to say hi in a random folder" is 100% real and root-caused.** OpenCode is widely loved for supporting 75+ providers, local models, and an MIT codebase ([OpenCode Docs, 2026](https://docs.opencode.ai/docs/cli/)), but launching it in an unindexed or home directory triggers recursive `ripgrep --hidden --follow` scans ([GitHub #6741, 2026-01-03](https://github.com/anomalyco/opencode/issues/6741)), synchronous WASM ripgrep blocking ([GitHub #22784, 2026-04-16](https://github.com/anomalyco/opencode/issues/22784)), unindexed skill/plugin directory walks ([r/opencodeCLI, Apr 2026](https://www.reddit.com/r/opencodeCLI/comments/1t97d53/opencode_startup_is_painfully_slow_with_large/)), and multi-gigabyte SQLite `opencode.db` stalls requiring `VACUUM` ([r/opencodeCLI, Aug 2026](https://www.reddit.com/r/opencodeCLI/comments/1w95ltq/opencode_is_slow_and_my_simple_way_to_fix/); [GitHub #41477, 2026-08-10](https://github.com/anomalyco/opencode/issues/41477)).
4. **The Discord signal that Claude Code "doesn't lag" is only half true.** Its native tool-calling loop is fast, but its Node.js/Ink/Yoga TUI suffers from well-documented full-history redraw flicker ([GitHub #35987, 2026-03-18](https://github.com/anthropics/claude-code/issues/35987); [Hacker News, 2026-01-20](https://news.ycombinator.com/item?id=46699072)), high-refresh-rate display stutter ([GitHub #42045, 2026-04-01](https://github.com/anthropics/claude-code/issues/42045)), keystroke lag when the host CPU is busy compiling ([GitHub #68758, 2026-06-16](https://github.com/anthropics/claude-code/issues/68758)), and Windows ConPTY input deadlocks ([GitHub #23211, 2026-02-04](https://github.com/anthropics/claude-code/issues/23211)). By contrast, compiled Rust/Go TUIs (Codex CLI's Ratatui rewrite and Antigravity CLI's Go binary) start up and render noticeably faster.
5. **The Discord signal that Codex CLI has a "confusing UI" and "mid results" stems from silent sandbox failures and compaction loss.** Codex's default `workspace-write` sandbox blocks network calls (`npm`, `pip`), git hooks, and `gh` credentials without surfacing clear UI permission errors, causing frozen spinners or cryptic troubleshooting detours ([GitHub #41161, 2026-08-27](https://github.com/openai/codex/issues/41161); [GitHub #62088, 2026-11-17](https://github.com/openai/codex/issues/62088); [r/OpenaiCodex, Oct 2025](https://www.reddit.com/r/OpenaiCodex/comments/1oq5hv3/the_sandbox_is_kind_of_useless_i_often_use_full/)). On large projects, users report it wanders into "side quests" after compaction ([r/codex, Nov 2026](https://www.reddit.com/r/codex/comments/1y2900t/codex_is_freaking_terrible_on_a_large_project/)).
6. **Headless mode can burn 1.5x–1.8x more tokens than interactive TUI mode, and consumer OAuth spoofing is now actively policed.** In Claude Code, `claude -p` routes through `sdk-cli` and has been documented burning quota 1.5x–1.8x faster than interactive sessions due to prompt-cache initialization differences ([GitHub #97074, 2026-09-25](https://github.com/anthropics/claude-code/issues/97074)). Moreover, Anthropic blocked third-party harnesses (like OpenCode) from using Claude Pro/Max OAuth tokens between Jan and Mar 2026 ([ridakaddir.com, 2026-03-22](https://ridakaddir.com/blog/post/did-anthropic-kill-opencode-claude-subscription-ban)), and Google restricts consumer OAuth pooling in third-party orchestrators unless using official CLI flags or API keys ([Google AI Dev Forum, 2026-11-16](https://discuss.ai.google.dev/t/tos-clarification-official-agy-cli-driven-by-a-local-multi-agent-workflow-on-a-personal-google-ai-pro-account/200921)).
7. **Google deprecated the open-source Gemini CLI for consumer/Pro OAuth accounts on June 18, 2026, replacing it with the closed-source Go-based Antigravity CLI (`agy`).** While `google-gemini/gemini-cli` remains Apache-2.0 for API-key and enterprise Code Assist users ([GitHub Discussion #27274, 2026-06-18](https://github.com/google-gemini/gemini-cli/discussions/27274)), consumer and Google AI Pro/Ultra sign-ins were migrated to `agy` ([Hacker News, 2026-05-21](https://news.ycombinator.com/item?id=48222529)), which adds multi-vendor model selection (Gemini 4 Neon/Carbon/Argon/Hydrogen, Claude Opus/Sonnet 5.5, GPT-OSS 120B), native subagent swarms, and Python workflow orchestration (`agy --help`; `agy changelog`, v1.5.9–1.5.15, Nov 2026).
8. **Cursor CLI (`cursor-agent` / `agent`) is fast and shares editor MCP/rules, but its headless `-p` mode is plagued by indefinite hangs.** Users on Cursor's forum and Reddit report that `cursor-agent -p` frequently hangs after emitting a response or deadlocks on unapproved MCP servers unless `--trust`, `--approve-mcps`, `--force`, and `--output-format stream-json` are explicitly passed ([Cursor Forum #150246, 2026-01-29](https://forum.cursor.com/t/cursor-agent-p-print-headless-mode-hangs-indefinitely-and-never-returns/150246); [Cursor Forum #133509, 2025-09-15](https://forum.cursor.com/t/disappointing-bugs-first-impressions-of-headless-cli/133509)).
9. **The Discord signal on "DeepSeek harness" and "Devin for value" reflects two specific 2026 shifts, with a price inversion on DeepSeek.** DeepSeek harnesses—either the MIT-licensed `dsh` CLI ([Composio, 2026-09-01](https://composio.dev/content/deepseek-harness-vs-claude-code)) or routing Claude Code's `ANTHROPIC_BASE_URL` to `https://api.deepseek.com/anthropic` ([r/ClaudeCode, Jul 2026](https://www.reddit.com/r/ClaudeCode/comments/1w54ck5/just_realised_i_can_use_deepseek_inside_claude/))—are actually **far cheaper** ($0.03–$0.32/task), not higher priced; when developers report a "higher price" for frontend work, they either mean paying for a premium multi-model harness (like Factory Droid or Claude Code Max) or spending more iterative turns to match Claude's one-shot UI polish ([r/DeepSeek, Oct 2026](https://www.reddit.com/r/DeepSeek/comments/1xysywi/claude_20_is_better_than_deepseek_api/)). Devin's "value" reputation comes from **Devin 2.0 dropping from $500/mo to a $20/mo Pro tier**, where developers start in the local CLI and `/handoff` heavy tasks to cloud VMs ([r/DevinAI, Jul 2026](https://www.reddit.com/r/DevinAI/comments/1wkiqif/my_experience_with_the_20_devin_pro_plan_this/)), though sustained work quickly exhausts the $20 base quota ([r/DevinAI, Oct 2026](https://www.reddit.com/r/DevinAI/comments/1xsbcsv/i_tried_devin_on_real_work_6_hours_20_sub_200/)).
10. **JSONL (`stream-json` / `--json`) and Agent Client Protocol (ACP) over `stdio` have become the universal standards for multi-CLI wrappers.** Claude Code, Codex CLI, OpenCode, Cursor CLI, Gemini CLI, and Antigravity CLI all now emit newline-delimited JSON event streams in headless mode and support ACP (`stdio` JSON-RPC) either natively (`opencode acp`, `cursor-agent acp`, `gemini --experimental-acp`, `agy acp`) or via official bridge adapters (`claude-code-acp`, `codex-acp`).
11. **"Extras" beyond the core edit loop often decide which CLI developers actually pay for—especially bundled subscriptions, semantic indexing, LSP feedback, and subagents.** Users pick Codex CLI or `agy` because they come bundled with ChatGPT Plus ($20/mo) or Google AI Pro subscriptions they already pay for; stick with Cursor CLI for its semantic vector codebase indexing and cloud VM handoff ([r/cursor, May 2026](https://www.reddit.com/r/cursor/comments/1ur4t5o/so_is_indexing_the_only_feature_of_cursor/)); pick OpenCode for 75+ providers, built-in LSP error feedback, and $10/mo OpenCode Go ([r/LocalLLaMA, Nov 2025](https://www.reddit.com/r/LocalLLaMA/comments/1pb9q3q/how_many_of_you_are_using_opencode/)); and pick Claude Code or `agy` for hooks, subagents, and Python workflow orchestration ([DEV.to, 2026](https://dev.to/jennyouyang/best-claude-code-plugins-2026-11-tested-4-worth-keeping-1oal); `agy changelog` v1.5.9–1.5.15). Conversely, over-stacking plugin marketplaces causes severe token bloat ([r/ClaudeAI, Nov 2026](https://www.reddit.com/r/ClaudeAI/comments/1y3arht/which_cli_skill_or_tool_gateway_is_the_best_for/)).
12. **Engine-level extras survive headless wrapping, whereas UI-coupled extras die in `-p` mode.** Hooks, subagents, skills/plugins, LSP diagnostics, semantic codebase indexes, web search grounding, and bundled subscription quotas still work when a wrapper starts a CLI headlessly (`-p` / `exec` / `run`), whereas phone/browser Remote Control UIs, interactive `/review` or `/restore` pickers, voice dictation, and IDE diff views only work inside the CLI's own interactive TUI or server mode.

---

## 2. First Group: Full CLI Evaluations

---

### 2.1 Claude Code (Anthropic)

#### Good
- **Best-in-class multi-file reasoning and tool orchestration:** Universally treated as the baseline benchmark for complex multi-file refactors, architectural planning, test-fix loops, and frontend generation ([MarkTechPost, 2026-06-14](https://www.marktechpost.com/2026/06/14/claude-code-guide-2026-25-features-with-examples-demo/); [r/CLine, Sep 2026](https://www.reddit.com/r/CLine/comments/1x9p2rr/switching_to_cline_from_claude_codecodex_was_way/)).
- **Rich control and extensibility:** Supports granular permission rules (`allow`, `ask`, `deny`), lifecycle hooks (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` in `.claude/settings.json`), custom slash commands (`.claude/commands/`), subagents (`.claude/agents/`), skills (`SKILL.md`), and project instructions (`CLAUDE.md`) ([Claude Code Hooks Docs, 2026](https://code.claude.com/docs/en/hooks); [suprmind.ai, 2026](https://suprmind.ai/hub/claude/features/)).
- **Smart idle compaction for prompt cache preservation:** Added idle compaction (v2.1.299) that automatically compacts long idle sessions at ~54 minutes before the 1-hour Anthropic prompt cache expires, avoiding costly full re-caching ([Claude World, 2026-10-14](https://claude-world.com/articles/claude-code-21299-release/)).
- **Clean local JSONL transcripts and session branching:** Every session is stored as an append-only JSONL file in `~/.claude/projects/<munged-path>/<session-uuid>.jsonl` and supports non-destructive branching via `--fork-session` or `/branch` ([Aditya Bawankule, 2026-07-09](https://www.adityabawankule.io/blog/claude-code-session-jsonl-format); [GitHub sandcastle #523, 2026](https://github.com/mattpocock/sandcastle/issues/523)).
- **Mature automation & SDK ecosystem:** Offers bidirectional `stream-json` over stdin/stdout and the official **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk` in TypeScript and Python) ([Claude World Control Protocol, 2026](https://claude-world.com/tutorials/s13-control-protocol/)).

#### Bad
- **TUI rendering lag, screen flicker, and Windows ConPTY freezes (Disagrees with Discord "doesn't lag" claim):** Because the TUI uses React/Ink and the Yoga layout engine on Node.js, long sessions suffer from full-screen ANSI redraw flicker ([GitHub #35987, 2026-03-18](https://github.com/anthropics/claude-code/issues/35987); [Hacker News, 2026-01-20](https://news.ycombinator.com/item?id=46699072)), system-wide display stutter on 4K/high-refresh monitors ([GitHub #42045, 2026-04-01](https://github.com/anthropics/claude-code/issues/42045)), severe input lag when local compilers load the CPU ([GitHub #68758, 2026-06-16](https://github.com/anthropics/claude-code/issues/68758)), and complete keyboard input lockups on Windows Terminal/PowerShell/Git Bash ([GitHub #23211, 2026-02-04](https://github.com/anthropics/claude-code/issues/23211)).
- **Rapid 5-hour/weekly quota burn and unrefunded backend retry charges:** Pro ($20/mo) and Max ($100–$200/mo) users frequently report sudden 5x–10x quota depletion caused by runaway subagent/file-read tool spam, and Anthropic confirmed that automatic client retries during Anthropic backend errors count directly against user usage limits ([r/ClaudeAI, Oct 2026](https://www.reddit.com/r/ClaudeAI/comments/1xh3yyu/claude_code_usage_exploded_8x_today_anthropic/); [r/ClaudeCode, Mar 2026](https://www.reddit.com/r/ClaudeCode/comments/1s2kdl9/claude_suddenly_eating_up_your_usage_here_is_what/)).
- **Headless `-p` token penalty:** Running `claude -p` routes via `sdk-cli` and has been measured consuming context limits ~1.5x to 1.8x faster than equivalent interactive TUI turns due to caching/initialization differences ([GitHub #97074, 2026-09-25](https://github.com/anthropics/claude-code/issues/97074)).
- **Post-compaction quality drop:** Users consistently report that Claude Code becomes noticeably "dumber" after auto-compaction, dropping architectural constraints and re-introducing old bugs ([r/Anthropic, Oct 2026](https://www.reddit.com/r/Anthropic/comments/1x2gl7e/claude_code_gets_worse_after_every_compactions/)).
- **Closed-source proprietary lock-in and aggressive DMCA enforcement:** Distributed under a proprietary license; when an npm release (`v2.1.88`) accidentally shipped a JS source map on March 30–31, 2026, Anthropic filed immediate DMCA takedowns against thousands of GitHub mirrors ([TechCrunch, 2025-04-25](https://techcrunch.com/2025/04/25/anthropic-sent-a-takedown-notice-to-a-dev-trying-to-reverse-engineer-its-coding-tool/); [The Firewall Blog, 2026-04-02](https://thefirewall-blog.com/)).

#### Mixed
- **Speed on simple tasks:** Fast time-to-first-token and rapid tool calls, but often over-complicates simple fixes by spawning subagents and reading dozens of unrelated files unless constrained by `CLAUDE.md` ([r/ClaudeCode, Aug 2026](https://www.reddit.com/r/ClaudeCode/comments/1wu8zzp/claude_code_is_getting_very_very_slow_and_running/)).
- **Model choice:** Officially locked to Anthropic models (Claude Opus, Sonnet, Haiku), but easily redirected to DeepSeek, OpenRouter, or LiteLLM by overriding `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` in `~/.claude/settings.json` ([r/ClaudeCode, Jul 2026](https://www.reddit.com/r/ClaudeCode/comments/1w54ck5/just_realised_i_can_use_deepseek_inside_claude/); [r/DeepSeek, Jun 2026](https://www.reddit.com/r/DeepSeek/comments/1vrl0in/wtf_claude_code_is_using_deepseek_v4_flash/)).
- **Telemetry:** Collects usage/error telemetry by default, but supports enterprise opt-out (`DISABLE_TELEMETRY=1`) and user-configured OpenTelemetry export (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) ([MarkTechPost, 2026-06-14](https://www.marktechpost.com/2026/06/14/claude-code-guide-2026-25-features-with-examples-demo/)).

#### Best at
Complex multi-file refactoring, greenfield frontend/UI scaffolding, architectural reasoning across large repositories, and autonomous test-and-fix debugging loops.

#### Worst at
Maintaining constraints across multiple context compactions, staying within predictable token budgets on simple tasks without strict `CLAUDE.md` rules, and smooth TUI rendering on Windows ConPTY or under high local CPU load.

#### Automation Facts
- **Headless flags:** `claude -p "<prompt>"` (or `--print`), `--output-format text|json|stream-json`, `--input-format text|stream-json`, `--include-partial-messages`, `--verbose`, `--json-schema '<schema>'`, `--max-turns <n>`, `--max-budget-usd <amount>`, `--allowedTools "<tools>"`, `--disallowedTools "<tools>"`, `--permission-mode default|acceptEdits|plan|bypassPermissions`, `--dangerously-skip-permissions`, `--bare` (skips hooks/LSP/plugins for fast scripted runs) ([Claude World, 2026](https://claude-world.com/tutorials/s13-control-protocol/); [GitHub #1177, 2026-04-05](https://github.com/anthropics/claude-code-action/issues/1177)).
- **Output format:** `text` (plain stdout), `json` (single JSON result with `result`, `session_id`, `cost_usd`, `duration_ms`), or `stream-json` (real-time NDJSON events).
- **Exit codes:** `0` on success; non-zero (`1`) on execution/auth failure or hitting `--max-turns`.
- **Resume & fork:** `claude --continue` (`-c`), `claude --resume <session-id>` (`-r`), `claude --resume <id> --fork-session`.
- **Transcript location:** `~/.claude/projects/<munged-project-path>/<session-uuid>.jsonl` (append-only JSONL).
- **SDKs & ACP:** Official `@anthropic-ai/claude-agent-sdk` (TypeScript & Python); ACP supported via `@zed-industries/claude-code-acp` stdio adapter.

#### As Conductor / As Worker
- **As conductor:** **Top-tier.** Its combination of Opus/Sonnet planning, `PreToolUse`/`PostToolUse` hooks, subagent delegation, and custom skills makes it the strongest human-facing orchestrator—provided sessions are periodically reset or handed off before compaction degrades context.
- **As worker:** **Strong on quality, expensive on quota.** Bidirectional `--input-format stream-json --output-format stream-json` and `--allowedTools` make it easy to control programmatically, but the 1.5x–1.8x headless token burn on `-p` means a wrapper should keep long-lived worker processes alive over `stream-json` stdin rather than spawning fresh `claude -p` processes per micro-step.
- **What a wrapper must never block:** Its prompt-cache continuity (never mutate system prompts or injected prefixes mid-session), `.claude/settings.json` lifecycle hooks, `CLAUDE.md` discovery, and `ANTHROPIC_BASE_URL` overrides.

---

### 2.2 Codex CLI (OpenAI)

#### Good
- **Blazing startup and lean memory footprint after native Rust + Ratatui rewrite:** OpenAI rewrote Codex CLI from TypeScript/Node/Ink into native Rust (`codex-tui`, `codex-core`, `codex-exec`), eliminating Node/V8 startup overhead and delivering a zero-dependency binary ([InfoQ, 2025-06](https://www.infoq.com/news/2025/06/codex-cli-rust-native-rewrite/); [Hacker News, 2025-06-01](https://news.ycombinator.com/item?id=44150441)).
- **High-value inclusion in ChatGPT Plus ($20/mo) and Pro ($200/mo):** Works out-of-the-box with consumer and workspace ChatGPT OAuth subscriptions as well as API keys ([OpenAI Codex Docs, 2026](https://learn.chatgpt.com/docs/developer-commands)).
- **First-class OS-level sandboxing:** Uses Seatbelt on macOS, Bubblewrap/Landlock on Linux, and restricted tokens on Windows with explicit modes (`read-only`, `workspace-write`, `danger-full-access`) ([OpenAI Non-Interactive Docs, 2026](https://learn.chatgpt.com/docs/non-interactive-mode)).
- **Clean headless pipeline ergonomics (`codex exec -o`):** Built specifically for CI/CD with `--json` (JSONL event stream to stdout, progress to stderr) and `-o` / `--output-last-message <file>` to write the final answer cleanly to a file ([OpenAI Non-Interactive Docs, 2026](https://learn.chatgpt.com/docs/non-interactive-mode)).
- **Open-source Apache-2.0 license and automatic rollout JSONL logging:** Fully open source at `github.com/openai/codex` and writes detailed trajectory files to `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` ([DEV.to, 2026-10-29](https://dev.to/bargan/what-codex-cli-writes-to-disk-for-every-session-and-how-to-follow-it-live-1i04)).

#### Bad
- **Silent sandbox blocks create a confusing TUI and frozen spinners (Confirms Discord "UI is confusing" signal):** By default, `workspace-write` disables network access and blocks access outside the repo. When tools run `npm install`, `pip`, git hooks, or `gh auth status`, the sandbox silently blocks or fails them without a clear permission dialog, causing frozen status spinners or sending the model down bizarre debugging rabbit holes ([GitHub #41161, 2026-08-27](https://github.com/openai/codex/issues/41161); [GitHub #62088, 2026-11-17](https://github.com/openai/codex/issues/62088); [r/OpenaiCodex, Oct 2025](https://www.reddit.com/r/OpenaiCodex/comments/1oq5hv3/the_sandbox_is_kind_of_useless_i_often_use_full/)).
- **"Mid" results on large multi-file repos and severe post-compaction "lobotomy" (Confirms Discord "mid results" signal):** While fast at isolated code generation, users on `r/ChatGPTCoding` and `r/codex` heavily criticize its tendency to wander off on "side quests" in large codebases ([r/codex, Nov 2026](https://www.reddit.com/r/codex/comments/1y2900t/codex_is_freaking_terrible_on_a_large_project/)) and suffer immediate amnesia after context compaction—forgetting active tasks or inventing "fan fiction" architecture ([r/codex, Aug 2026](https://www.reddit.com/r/codex/comments/1w8sqon/codex_56_after_every_context_compaction_sorry/); [r/ChatGPTCoding, Aug 2026](https://www.reddit.com/r/ChatGPTCoding/comments/1wvg6su/codex_cli_is_cooked/)).
- **Windows execution and file-locking bugs:** Native Windows users hit `helper_unknown_error: setup refresh had errors`, `node_repl.exe` file lock (Error 32) failures, and `%APPDATA%` read denials inside the sandbox ([GitHub #53060, 2026-10-11](https://github.com/openai/codex/issues/53060); [GitHub #41161, 2026-08-27](https://github.com/openai/codex/issues/41161)).
- **Sandbox escape vulnerabilities required disruptive clamping:** High-profile sandbox escapes (`Heapjack` and `Overpatch`) disclosed in 2026 forced tighter memory and patch-path restrictions that broke some custom scripts ([r/pwnhub, Aug 2026](https://www.reddit.com/r/pwnhub/comments/1wlqqn9/openai_codex_sandbox_escapes_allow_remote_code/)).

#### Mixed
- **Model choice:** Optimized for OpenAI's Codex/GPT-5.x models via ChatGPT login, though `~/.codex/config.toml` allows defining custom OpenAI-compatible `model_provider` endpoints (including local Ollama/vLLM servers) ([OpenAI Codex Docs, 2026](https://learn.chatgpt.com/docs/developer-commands)).
- **Quota burn on ChatGPT Plus:** Great value for light-to-medium work included in the $20 Plus subscription, but a single deep debugging loop can exhaust the 5-hour Plus window ([r/ClaudeAI, Oct 2026](https://www.reddit.com/r/ClaudeAI/comments/1xl4bth/cs_student_dilemma_chatgpt_plus_codex_work_vs/)).

#### Best at
Fast, well-scoped single-module implementation, boilerplate removal, test writing, and deterministic CI/CD patch execution (`codex exec`).

#### Worst at
Long-horizon architectural refactoring across large monorepos, visual/frontend state debugging across compactions, and tasks requiring network/credential access inside the default sandbox on Windows.

#### Automation Facts
- **Headless flags:** `codex exec "<prompt>"`, `--json` (JSONL event stream to stdout), `-o <path>` / `--output-last-message <path>`, `--full-auto` (alias for `-a on-request --sandbox workspace-write`), `--sandbox read-only|workspace-write|danger-full-access`, `-a` / `--ask-for-approval untrusted|on-failure|on-request|never`, `--dangerously-bypass-approvals-and-sandbox` (alias `--yolo`), `--approve-for-me` (alias `--not-so-yolo`), `--ephemeral` (no session file persisted), `--output-schema <file>`, `--add-dir <dir>`, `-m` / `--model <model>`, `-C` / `--cd <dir>` ([OpenAI Non-Interactive Docs, 2026](https://learn.chatgpt.com/docs/non-interactive-mode)).
- **Output format:** Plain text final message to `stdout` (progress to `stderr`), or newline-delimited JSON events (`thread.started`, `turn.started`, `item.completed`, `turn.completed`) with `--json`.
- **Exit codes:** `0` on normal completion, non-zero on runtime/auth/sandbox errors (though bug `#19309` noted edge cases where silent early validation failures returned `0` without running tools: [GitHub #19309, 2026-04-24](https://github.com/openai/codex/issues/19309)).
- **Resume & fork:** `codex resume [--last | <session-id>] [--all]`, `codex fork [--last | <session-id>]`, `codex exec resume --last "<prompt>"` ([GitHub Codex Cheatsheet, 2026](https://github.com/rstacruz/cheatsheets/blob/master/codex.md)).
- **Transcript location:** `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` (respects `CODEX_HOME`).
- **SDKs & ACP:** Official `@openai/codex-sdk` (TypeScript) and `codex-app-server` JSON-RPC server; ACP supported via `agentclientprotocol/codex-acp` ([GitHub codex-acp, 2026](https://github.com/agentclientprotocol/codex-acp)).

#### As Conductor / As Worker
- **As conductor:** **Weak-to-mixed.** Its tendency to lose the big picture after compaction and its confusing silent sandbox denials make it frustrating as the primary conversational orchestrator for long sessions.
- **As worker:** **Strong.** Fast Rust binary startup, low RAM use, included ChatGPT Plus/Pro quota, `--json` streaming, and `-o <file>` output make `codex exec` an ideal headless worker for bounded coding subtasks handed off by a smarter conductor.
- **What a wrapper must never block:** `CODEX_HOME` and `~/.codex/config.toml` sandbox/network settings (`workspace_write.network_access = true`), hierarchical `AGENTS.md` discovery (up to 32 KiB), and `.codex/hooks.json`.

---

### 2.3 OpenCode (`sst/opencode` / `anomalyco/opencode`)

#### Good
- **Unmatched model freedom (75+ providers & local models) (Confirms Discord "most voted favourite" signal):** Supports Anthropic, OpenAI, Gemini, DeepSeek, Qwen, GitHub Copilot, OpenRouter, Ollama, LM Studio, and pooled low-cost services like **OpenCode Go** ($10/mo for Kimi, Qwen, DeepSeek, GLM) and **OpenCode Zen** ([OpenCode Docs, 2026](https://opencode.ai/docs/console/go/); [GitHub opencode-primer, 2026](https://github.com/wesammustafa/opencode-primer)).
- **Client-server architecture with native ACP, Web UI, and mobile companions:** The TUI is just a client talking to a local server (`opencode serve` / `opencode web`), enabling remote attachment (`--attach`), native ACP (`opencode acp`), and mobile monitoring ([OpenCode CLI Docs, 2026](https://docs.opencode.ai/docs/cli/)).
- **Polished, themeable TUI with built-in LSP intelligence:** Built with Bubble Tea, featuring custom themes, vim keybindings, and automatic Language Server Protocol (LSP) diagnostics fed back into the agent ([GitHub anomalyco/opencode, 2026](https://github.com/anomalyco/opencode/issues/14965)).
- **Fully open-source MIT license:** Permissive MIT license with full community inspectability and plugin hooks.

#### Bad
- **Severe startup hangs and "takes forever to answer hi in a random folder" (Confirms Discord complaint with exact bug evidence):**
  1. *Unbounded ripgrep crawl:* Launching OpenCode in a home directory or unindexed random folder runs `rg --hidden --follow` looking for config/files across `.cache`, `.local`, `node_modules`, and `.cargo`, burning 1000%+ CPU for up to 10 minutes ([GitHub #6741, 2026-01-03](https://github.com/anomalyco/opencode/issues/6741)) or blocking the main thread via synchronous WASM ripgrep ([GitHub #22784, 2026-04-16](https://github.com/anomalyco/opencode/issues/22784)).
  2. *Unindexed skill & git traversal:* Startup recursively scans `~/.config/opencode/skills/`, `.claude/skills/`, and child git repos with no caching layer ([r/opencodeCLI, Apr 2026](https://www.reddit.com/r/opencodeCLI/comments/1t97d53/opencode_startup_is_painfully_slow_with_large/); [r/opencodeCLI, Jul 2026](https://www.reddit.com/r/opencodeCLI/comments/1we510x/slow_startup_time_for_opencode_cli_each_time_it/)).
  3. *SQLite database bloat & locking:* Session history in `~/.local/share/opencode/opencode.db` bloats to multiple gigabytes over time, stalling startup until users prune old sessions and run `VACUUM` ([r/opencodeCLI, Aug 2026](https://www.reddit.com/r/opencodeCLI/comments/1w95ltq/opencode_is_slow_and_my_simple_way_to_fix/); [GitHub #41477, 2026-08-10](https://github.com/anomalyco/opencode/issues/41477)), and concurrent local+Docker runs corrupt or lock SQLite ([GitHub #14194, 2026-02-18](https://github.com/anomalyco/opencode/issues/14194)).
- **Infinite auto-compaction loops on "say hi" or large system prompts:** When MCP tools and system prompts approach a smaller model's context ceiling, auto-compaction fails to reduce tokens below the threshold and loops endlessly ([GitHub #55667, 2026-10-15](https://github.com/anomalyco/opencode/issues/55667); [GitHub oh-my-openagent #2225, 2026-03-01](https://github.com/code-yeongyu/oh-my-openagent/issues/2225)). Another bug (`#31764`) caused OpenCode to forget it had loaded `AGENTS.md` after compaction and re-read it on every turn ([GitHub #31764, 2026-06-17](https://github.com/anomalyco/opencode/issues/31764)).
- **Loss of Claude Pro/Max OAuth support:** In January–March 2026, Anthropic blocked third-party OAuth tokens and forced OpenCode (PR `#18186`, March 19, 2026) to remove Claude Pro/Max subscription login ([ridakaddir.com, 2026-03-22](https://ridakaddir.com/blog/post/did-anthropic-kill-opencode-claude-subscription-ban)).

#### Mixed
- **Results quality & tool reliability:** Entirely dependent on the chosen backend model. With Claude Sonnet/Opus API keys or DeepSeek V4/Qwen3-Coder, tool use is strong; with smaller local Ollama models, edit-failure loops occur frequently.
- **Windows support:** Runs natively on Windows, but terminal rendering lag and filesystem scan overhead are noticeably worse outside WSL2 or GPU-accelerated terminals like Ghostty ([r/opencodeCLI, Feb 2026](https://www.reddit.com/r/opencodeCLI/comments/1r24hlk/opencode_slow/)).

#### Best at
Multi-provider and local-model routing, cost-optimized open-weight coding (via OpenCode Go or BYOK), and editor/ACP integration where users want an MIT-licensed alternative to vendor-locked CLIs.

#### Worst at
Cold-starting in unindexed or large parent directories without a global `~/.ignore`, surviving long sessions without SQLite maintenance or compaction tuning, and zero-config consistency across weaker models.

#### Automation Facts
- **Headless flags:** `opencode run "<prompt>"`, `--format default|json` (raw JSON events), `-c` / `--continue`, `-s` / `--session <id>`, `--fork`, `-m` / `--model <provider/model>`, `--agent <name>`, `-f` / `--file <path>`, `--attach <server-url>`, `--port <port>`, `--auto` (auto-approve non-denied permissions), `opencode serve`, `opencode web`, `opencode acp` ([OpenCode CLI Docs, 2026](https://docs.opencode.ai/docs/cli/)).
- **Output format:** Streaming text (`default`) or newline-delimited JSON events (`--format json`); full export via `opencode export [sessionID] [--sanitize]`.
- **Exit codes:** `0` on success, non-zero on error/abort.
- **Resume & fork:** `opencode --continue` (`-c`), `opencode --session <id>` (`-s`), `opencode --session <id> --fork`, `opencode session list [--format json]`.
- **Transcript location:** SQLite database at `~/.local/share/opencode/opencode.db` (and JSON storage under `~/.local/share/opencode/storage/`), portable via `opencode export` / `opencode import <file>`.
- **SDKs & ACP:** Official `@opencode-ai/sdk` (TypeScript/JS REST & SSE client for `opencode serve`) and native `opencode acp` (JSON-RPC 2.0 over `stdio`).

#### As Conductor / As Worker
- **As conductor:** **Strong for model-agnostic power users, risky out-of-the-box.** Its client-server HTTP/ACP design and custom agent definitions (`opencode.json`) make it very hackable as a conductor, provided the user maintains a clean SQLite DB and `~/.ignore`.
- **As worker:** **Good if connected to a warm `opencode serve` daemon; poor if cold-spawned per task.** Cold-spawning `opencode run` in arbitrary folders incurs the filesystem/skill scan penalty, whereas attaching (`opencode run --attach http://localhost:4096`) to a warm daemon eliminates startup lag and gives cheap access to 75+ models.
- **What a wrapper must never block:** `~/.ignore` / watcher exclusions, `opencode.json` (`mcp` and `permission.skill` deny lists), LSP server child processes, and the `opencode serve` daemon socket.

---

### 2.4 Cursor CLI (`cursor-agent` / `agent`)

#### Good
- **Blazing token generation and seamless parity with the Cursor IDE:** Shares `.cursor/rules`, `.cursorrules`, `AGENTS.md`, `hooks.json`, and MCP server definitions directly with the Cursor desktop editor, and executes fast edits using Cursor's indexing and model routing ([Cursor CLI Overview, 2026](https://cursor.com/docs/cli/overview); [r/cursor, May 2026](https://www.reddit.com/r/cursor/comments/1u284g8/i_think_cursors_speed_is_hurting_my_saas/)).
- **Broad frontier model catalog under one subscription:** Gives terminal access to Claude Sonnet/Opus, GPT-5.x, Gemini, and Cursor's native fast models without juggling separate vendor API keys ([Cursor Models & Pricing, 2026](https://cursor.com/docs/models-and-pricing)).
- **Built-in worktree isolation (`-w` / `--worktree`):** Can automatically spin up isolated git worktrees under `~/.cursor/worktrees/` for parallel agent tasks without dirtying the active working tree ([Cursor CLI Parameters, 2026](https://cursor.com/docs/cli/reference/parameters)).
- **Native ACP mode and structured streaming flags:** Supports `cursor-agent acp` over stdio and `--output-format text|json|stream-json` with `--stream-partial-output` ([Cursor Headless Docs, 2026](https://cursor.com/docs/cli/headless)).

#### Bad
- **Headless `-p` / `--print` mode frequently hangs indefinitely:** A major, long-running complaint on the Cursor Forum is that `cursor-agent -p "prompt"` prints its output and then hangs forever instead of exiting, or stalls waiting for interactive MCP/workspace trust prompts ([Cursor Forum #150246, 2026-01-29](https://forum.cursor.com/t/cursor-agent-p-print-headless-mode-hangs-indefinitely-and-never-returns/150246); [Cursor Forum #133509, 2025-09-15](https://forum.cursor.com/t/disappointing-bugs-first-impressions-of-headless-cli/133509)).
- **Stdin piping and subshell parsing bugs:** Piping large diffs or file contents via `stdin` into `cursor-agent -p` often causes argument truncation or misinterpretation compared to passing string arguments ([Cursor Forum #133509, 2025-09-15](https://forum.cursor.com/t/disappointing-bugs-first-impressions-of-headless-cli/133509)).
- **Opaque SQLite blob transcript storage and lack of Desktop sync:** CLI sessions are stored in content-addressed SQLite blobs (`~/.cursor/chats/<workspace-hash>/<chat-uuid>/store.db`) rather than human-readable JSONL, and CLI chats do not automatically sync into the Cursor Desktop IDE's Agents Window ([Deja-Vu Registry, 2026](https://vshulcz.github.io/deja-vu/registry/cursor.html)).
- **Shifting subscription credit pools and "Auto" model quality regressions:** Users on `r/cursor` frequently complain about opaque fast-request credit depletion, tier changes, and periodic regressions when Cursor's router silently downgrades "Auto" mode quality ([r/cursor, Oct 2026](https://www.reddit.com/r/cursor/comments/1xk1jyf/ive_been_seeing_a_lot_of_complaints_about_ai/)).

#### Mixed
- **TUI UX & Windows support:** Runs on Windows PowerShell, WSL, macOS, and Linux, and is praised by terminal fans using wrappers like `agent-term`, though users note truecolor palette quirks and feel the TUI receives less engineering attention than the flagship GUI editor ([r/cursor, Aug 2026](https://www.reddit.com/r/cursor/comments/1wpco3b/cursor_cli_deserves_more_especially_with_terminal/)).
- **Speed vs. "vibe coding" tech debt:** Edits apply so rapidly that developers report falling into "accept-all" fatigue and accumulating architectural debt on long sessions ([r/cursor, May 2026](https://www.reddit.com/r/cursor/comments/1u284g8/i_think_cursors_speed_is_hurting_my_saas/)).

#### Best at
Fast iterative feature scaffolding, multi-file edits using Cursor's codebase index, and terminal workflows for developers who already pay for a Cursor subscription and maintain `.cursor/rules`.

#### Worst at
Unattended headless CI/CD pipelines (due to `-p` exit hangs and MCP approval blocks) and transparent transcript auditing (due to SQLite blob storage).

#### Automation Facts
- **Headless flags:** `cursor-agent -p "<prompt>"` (or `agent -p` / `--print`), `--output-format text|json|stream-json`, `--stream-partial-output`, `-f` / `--force` / `--yolo` (auto-approve commands unless denied), `--trust` (trust workspace headlessly), `--approve-mcps` (auto-approve MCP servers), `--sandbox enabled|disabled`, `--mode plan|ask`, `--model <model>`, `-w [name]` / `--worktree [name]`, `cursor-agent acp` ([Cursor CLI Parameters, 2026](https://cursor.com/docs/cli/reference/parameters); [Cursor Headless Docs, 2026](https://cursor.com/docs/cli/headless)).
- **Output format:** `text` (final answer string), `json` (`{"result": "...", "session_id": "..."}`), or `stream-json` (NDJSON events: `system`, `user`, `assistant`, `tool_call`, `result`).
- **Exit codes:** `0` on success, non-zero on error or when blocked by team policy (`Disable CLI headless mode`), though process-exit hangs in `-p` mode frequently require wrapper timeouts.
- **Resume & fork:** `cursor-agent create-chat` (returns `chatId`), `cursor-agent --resume <chatId>` (or `agent resume <chatId>`), `cursor-agent --continue`, `cursor-agent ls` ([Cursor CLI Parameters, 2026](https://cursor.com/docs/cli/reference/parameters)).
- **Transcript location:** `~/.cursor/chats/<workspace-hash>/<chat-uuid>/store.db` (SQLite database with `meta` and `blobs` tables) and `meta.json` ([Deja-Vu Registry, 2026](https://vshulcz.github.io/deja-vu/registry/cursor.html)).
- **SDKs & ACP:** No standalone public npm Agent SDK; native `cursor-agent acp` stdio JSON-RPC server.

#### As Conductor / As Worker
- **As conductor:** **Mixed.** Convenient if the user wants one subscription and `.cursor/rules` across IDE and terminal, but lacks the native multi-agent orchestration primitives of Claude Code or Antigravity CLI.
- **As worker:** **Fragile unless wrapped with strict watchdogs.** If used as a headless worker, the wrapper *must* pass `--trust --approve-mcps --force --model <explicit-model> --output-format stream-json` and kill the process as soon as the final `"type": "result"` JSON line arrives rather than waiting for EOF/exit ([Cursor Forum #150246, 2026-01-29](https://forum.cursor.com/t/cursor-agent-p-print-headless-mode-hangs-indefinitely-and-never-returns/150246)).
- **What a wrapper must never block:** `.cursor/rules`, `.cursorignore`, `hooks.json` (`beforeShellExecution`, `beforeMCPExecution`), and `-w` worktree paths.

---

### 2.5 Gemini CLI (Google — Legacy Open-Source `google-gemini/gemini-cli`)

#### Good
- **Fully open-source Apache-2.0 codebase with clean extensibility:** Remains open-source on GitHub (`google-gemini/gemini-cli`), making its TypeScript harness, TOML custom commands (`.gemini/commands/*.toml`), and synchronous lifecycle hooks (`BeforeTool`, `AfterTool` with exit code `2` emergency braking) easy to audit and customize ([Gemini CLI Hooks Reference, 2026](https://geminicli.com/docs/hooks/reference/); [GitHub Discussion #27274, 2026-06-18](https://github.com/google-gemini/gemini-cli/discussions/27274)).
- **Native 1M-token context window:** When backed by Gemini Pro/Flash API keys or enterprise Code Assist, it can ingest massive files and logs before needing `/compress` ([Gemini CLI Quotas Docs, 2026](https://geminicli.com/docs/resources/quota-and-pricing/)).
- **Well-structured headless and ACP modes:** Supports `-p` / `--prompt`, `--output-format text|json|stream-json`, `--approval-mode default|auto_edit|yolo|plan`, and `--experimental-acp` ([Gemini CLI Configuration Docs, 2026](https://geminicli.com/docs/reference/configuration/); [GitHub #20977, 2026-03-03](https://github.com/google-gemini/gemini-cli/issues/20977)).

#### Bad
- **Deprecated for consumer, free, and Google AI Pro/Ultra sign-ins on June 18, 2026:** Google shut down individual Google Account OAuth access ("Login with Google") on Gemini CLI on June 18, 2026, forcing non-enterprise OAuth users onto the closed-source Antigravity CLI (`agy`) or paid AI Studio API keys ([GitHub Discussion #27274, 2026-06-18](https://github.com/google-gemini/gemini-cli/discussions/27274); [Hacker News, 2026-05-21](https://news.ycombinator.com/item?id=48222529)).
- **"Stuck at Thinking" infinite retry loops on HTTP 429 rate limits:** Instead of failing fast or surfacing quota exhaustion, the CLI frequently hangs for 30–60+ minutes on "Thinking..." when hitting backend HTTP 429 capacity limits ([r/GeminiCLI, Apr 2026](https://www.reddit.com/r/GeminiCLI/comments/1thmkpe/gemini_cli_stuck_at_thinking/)).
- **Repetitive `replace`/`edit` tool failure loops:** Users frequently hit infinite loops where the agent fails an exact `old_string` replacement due to whitespace/indentation drift, apologizes, and retries the exact same failing edit without re-reading the file ([GitHub #6437, 2025-08-17](https://github.com/google-gemini/gemini-cli/issues/6437)).
- **Startup freezes on `GEMINI.md` and workspace memory discovery:** Scanning large repositories without a strict `.geminiignore` causes high memory consumption and startup hangs while crawling directories for hierarchical `GEMINI.md` files ([GitHub #12362, 2025-12-10](https://github.com/google-gemini/gemini-cli/issues/12362); [GitHub #22141, 2026-03-12](https://github.com/google-gemini/gemini-cli/issues/22141)).

#### Mixed
- **Cost & quotas:** Originally famous in mid-2025 for its 1,000 free requests/day via Google login; after the June 2026 cutoff, unpaid AI Studio API keys are heavily restricted (e.g., Flash-only low daily caps), while paid API keys and Vertex/Code Assist Enterprise remain supported ([Gemini CLI Quotas Docs, 2026](https://geminicli.com/docs/resources/quota-and-pricing/)).

#### Best at
Large-context log analysis, codebase Q&A, and scripted CI checks for teams using paid `GEMINI_API_KEY` or enterprise Gemini Code Assist licenses who require an auditable Apache-2.0 CLI binary.

#### Worst at
Multi-step surgical file editing (prone to string-replace loops), consumer subscription usage (now blocked), and graceful recovery from HTTP 429 rate limits.

#### Automation Facts
- **Headless flags:** `gemini -p "<prompt>"` (or `--prompt`), `-i` / `--prompt-interactive`, `--output-format text|json|stream-json`, `-y` / `--yolo`, `--approval-mode default|auto_edit|yolo|plan`, `-s` / `--sandbox`, `-m` / `--model <model>`, `--allowed-tools <list>`, `--allowed-mcp-server-names <list>`, `--include-directories <dirs>`, `--experimental-acp` ([Gemini CLI Configuration Docs, 2026](https://geminicli.com/docs/reference/configuration/)).
- **Output format:** `text`, `json` (final object with `response`, `stats`, `error`), or `stream-json` (NDJSON events: `init`, `message`, `tool_use`, `tool_result`, `result`).
- **Exit codes:** `0` success, `1` general error, `42` input/auth error, `53` turn limit exceeded (plus hook exit code `2` for emergency tool block) ([Gemini CLI Hooks Reference, 2026](https://geminicli.com/docs/hooks/reference/)).
- **Resume & fork:** `gemini --resume [latest | <index/UUID>]` (`-r`), `gemini --list-sessions`, `gemini --delete-session <id>`.
- **Transcript location:** `~/.gemini/tmp/<project_hash>/chats/session-*.json` (and settings in `~/.gemini/settings.json`).
- **SDKs & ACP:** Core package `@google/gemini-cli-core` (TypeScript); native `--experimental-acp` stdio JSON-RPC server.

#### As Conductor / As Worker
- **As conductor:** **Weak (legacy).** Superseded by `agy` for interactive conducting and prone to edit/429 loops.
- **As worker:** **Viable only for API-key/Enterprise users doing large-context read/review tasks.** A wrapper should enforce a hard timeout to catch silent HTTP 429 retry hangs.
- **What a wrapper must never block:** `.geminiignore` (mandatory to avoid startup hangs), `GEMINI.md`, and conflicting `GOOGLE_CLOUD_PROJECT` vs `GEMINI_API_KEY` environment variables ([Gemini CLI Troubleshooting, 2026](https://geminicli.com/docs/resources/troubleshooting/)).

---

### 2.6 Antigravity CLI (`agy`, Google)

#### Good
- **Fast, lightweight compiled Go binary ("Lag Killer" vs. IDE):** Unlike the heavier Antigravity desktop IDE or Node.js-based CLIs, `agy` is a compiled Go binary with snappy TUI response, low memory footprint (v1.5.10 added on-demand disk reloading of older conversation steps), and full-screen (`altscreen`) mouse/click support ([Antigravity Blog, 2026-05-19](https://antigravity.google/blog/introducing-google-antigravity-cli/); [r/google_antigravity, Aug 2026](https://www.reddit.com/r/google_antigravity/comments/1wqmd4n/why_is_the_antigravitycli_so_underrated/); [r/AntigravityGoogle, Oct 2026](https://www.reddit.com/r/AntigravityGoogle/comments/1xpq3ed/antigravity_slow_this_worked_for_me/); `agy changelog` v1.5.10–1.5.15).
- **Multi-vendor model catalog and built-in Planner/Executor `Orchestrator`:** Locally verified via `agy models` (v1.5.15, 2026-11-23), `agy` offers **Gemini 4 Neon, Carbon, Argon, and Hydrogen** (Low/Medium/High/XHigh), **Gemini 3.8 Flash**, **Claude Opus 5.5**, **Claude Sonnet 5.5**, **GPT-OSS 120B**, and dedicated **Orchestrator (Neon/Carbon/Argon)** modes that plan with a high-reasoning model and hand execution to a fast Executor model (`agy models`; `agy changelog` v1.5.10, v1.5.14, v1.5.15).
- **First-class multi-agent orchestration (`subagents`, `/swarm`, `run_workflow`):** Built-in support for asynchronous subagents (`invoke_subagent` with `inherit`, `branch`, or `share` workspaces), `/swarm` message boards, and `run_workflow` (which executes a bundled Python script to fan out and aggregate parallel agent pipelines) (`agy changelog` v1.5.9, v1.5.14).
- **Comprehensive Windows and cross-ecosystem polish:** Recent releases (v1.5.8–1.5.15) fixed Windows CRLF line-ending preservation on file append, UTF-8 BOM handling in `settings.json`/`hooks.json`/`plugin.json`, PowerShell/cmd quote preservation and `always-allow` command-injection prevention, UNC credential leak blocking, and direct plugin/skill import from Claude Code and Gemini CLI (`agy plugin import [claude|gemini]`; `agy changelog` v1.5.8–1.5.15).
- **Rich automation & remote surfaces:** Supports bidirectional `stream-json` input/output, `--json-schema` enforcement, native `agy acp` (with `--process-per-session`), and a browser-based Remote Control view (`agy remote-control start`, `--remote-control`) (`agy --help`; `agy acp --help`).

#### Bad
- **Aggressive default auto-compaction (~140k–150k tokens) caused mid-session amnesia (until v1.5.15 override):** A major complaint on GitHub (`#878`) was that `agy` compacted conversations around 140k–150k tokens instead of using Gemini's full 1M window, causing agents to forget architectural constraints and enter file re-read loops ([GitHub #878, 2026-08-26](https://github.com/google-antigravity/antigravity-cli/issues/878)). *(Note: v1.5.15 just added `AGY_CLI_AUTO_COMPACT_OVERRIDE` to let users raise this up to `800K` or `80%`: `agy changelog` v1.5.15).*
- **Community backlash over Gemini CLI deprecation, closed-source pivot, and shifting quota walls:** Developers on Hacker News and Reddit criticized Google for shutting down consumer OAuth on the Apache-2.0 `gemini-cli` and moving to the proprietary, closed-source `agy` binary ([Hacker News, 2026-05-21](https://news.ycombinator.com/item?id=48222529); [aq.dev, 2026](https://aq.dev/agents/antigravity/)), alongside complaints about opaque rolling quota limits on Google AI Pro/Ultra plans ([r/AntigravityGoogle, Sep 2026](https://www.reddit.com/r/AntigravityGoogle/comments/1x155rs/antigravity_usage_limits_are_absolute_shit/); [Hacker News, 2026-09-01](https://news.ycombinator.com/item?id=49517537)).
- **ToS friction when wrapping consumer accounts in third-party orchestrators:** Running consumer Google AI Pro OAuth sessions inside external multi-agent wrappers can trip automated account safety flags unless using `agy`'s native subagents or configuring `"modelProvider": "gemini"` with a `GEMINI_API_KEY` ([Google AI Dev Forum, 2026-11-16](https://discuss.ai.google.dev/t/tos-clarification-official-agy-cli-driven-by-a-local-multi-agent-workflow-on-a-personal-google-ai-pro-account/200921)).

#### Mixed
- **Results quality across model tiers:** Frontier tiers (Gemini 4 Argon/Neon/Carbon High, Claude Opus/Sonnet 5.5) and `Orchestrator` mode perform strongly on complex tasks, while lighter Flash tiers are ultra-fast ("virtually infinite" on Pro plans) but can lose track on deep multi-file refactors ([r/ChatGPTCoding, Nov 2026](https://www.reddit.com/r/ChatGPTCoding/comments/1y2bj0m/how_does_antigravity_new_gemini_models_compare/)).
- **Telemetry:** Enabled by default and tied to cloud account settings for OAuth sign-ins, though `agy acp --disable-telemetry` and local `settings.json` flags exist ([wezzard.com, 2026-11](https://wezzard.com/post/2026/11/making-antigravity-cli-usable-7276/); `agy acp --help`).

#### Best at
Multi-model orchestration (mixing Gemini 4, Claude 5.5, and GPT-OSS), parallel subagent/workflow fan-out (`run_workflow`), fast terminal TUI execution on Windows/Linux/macOS, and browser-attached remote terminal sessions (`--remote-control`).

#### Worst at
Open-source auditability (closed-source binary), unconfigured long-context sessions if `AGY_CLI_AUTO_COMPACT_OVERRIDE` is not set, and third-party consumer OAuth proxying.

#### Automation Facts
- **Headless flags (verified via `agy --help`, v1.5.15):** `agy -p "<prompt>"` (or `--print` / `--prompt`), `--output-format text|json|stream-json`, `--input-format text|stream-json` (reads NDJSON per line from stdin and runs a turn for each; requires `--output-format stream-json`), `--json-schema <schema-or-path>`, `--print-timeout <duration>` (default `0s`), `--mode accept-edits|auto|plan`, `--effort low|medium|high|xhigh|max`, `--model <model>`, `--agent <agent>`, `--sandbox`, `--dangerously-skip-permissions`, `--disable-slash-commands`, `--add-dir <dir>`, `--settings <json-or-path>`, `--project <id-or-name>`, `--remote-agent`.
- **Output format:** `text`, `json`, or `stream-json` (NDJSON).
- **Exit codes:** `0` on success, `1` on general/execution error, `2` on invalid flag/auth combination (e.g., `--remote-control` or `/usage` with `GEMINI_API_KEY`, per `agy changelog` v1.5.11–1.5.12).
- **Resume & fork:** `agy -c` / `--continue`, `agy --conversation <id>`, interactive `/resume <id>` and `/fork` (v1.5.12 optimized `/fork` to reference large artifact folders in seconds rather than copying).
- **Transcript location:** `~/.gemini/antigravity-cli/brain/<conversation-id>/.system_generated/logs/transcript.jsonl` (compact) and `transcript_full.jsonl` (full), plus saved conversation metadata in `~/.gemini/antigravity-cli/conversations` and settings in `~/.gemini/antigravity-cli/settings.json`.
- **SDKs & ACP:** Native `agy acp [--stdio] [--process-per-session] [--dangerously-skip-permissions] [--sandbox] [--disable-telemetry]` (`agy acp --help`), plus built-in Python `run_workflow` orchestration engine.

#### As Conductor / As Worker
- **As conductor:** **Top-tier.** Because `agy` already supports Claude Opus/Sonnet 5.5, Gemini 4 Argon/Neon/Carbon/Hydrogen, Planner/Executor `Orchestrator` mode, Python `run_workflow` scripts, and `/swarm`, it is arguably the most feature-complete native conductor installed on this system.
- **As worker:** **Strong with API key / Vertex ADC; requires ToS care on consumer OAuth.** Its `--input-format stream-json --output-format stream-json` persistent stdin loop and `--json-schema` validation make it a fast, structured worker, provided the user authenticates via `GEMINI_API_KEY` or Vertex ADC if driving it from an external third-party orchestrator ([Google AI Dev Forum, 2026-11-16](https://discuss.ai.google.dev/t/tos-clarification-official-agy-cli-driven-by-a-local-multi-agent-workflow-on-a-personal-google-ai-pro-account/200921)).
- **What a wrapper must never block:** `AGY_CLI_AUTO_COMPACT_OVERRIDE` environment variable, `~/.gemini/antigravity-cli/brain/<conversation-id>/` artifact/transcript directories, `~/.gemini/skills/`, and its native subagent/workflow tools.

---

## 3. Second Group: Brief Notes on Other Agentic Coding CLIs

- **Aider:** The veteran open-source (Apache-2.0) Git-native pair-programming CLI. Uses a tree-sitter AST **repo-map** for fast, low-token context and auto-commits every edit with a clean Git message ([r/ChatGPTCoding, Jul 2025](https://www.reddit.com/r/ChatGPTCoding/comments/1m7gq38/using_aider_vs_claude_code/)). Supports any model (Claude, OpenAI, DeepSeek, local Ollama) and deterministic headless scripting via `aider --message "<prompt>" --yes-always <files>`. Less autonomous at multi-step exploration than Claude Code, but faster and more surgical when you know which files to touch.
- **Amp (`@ampcode/cli`, Sourcegraph spinout):** Terminal-first TUI and cloud-runner platform built around isolated remote VMs called **"Orbs"** and specialized subagents (**Oracle** for deep reasoning, **Librarian** for code intelligence, Search) ([ampcode.com, 2026](https://ampcode.com/); [r/AmpCode, Jun 2026](https://www.reddit.com/r/AmpCode/comments/1vbax01/i_am_literally_so_happy_with_the_latest_updates/)). Early usage-based pricing drew complaints on Reddit for burning $10+ in hours ([r/AmpCode, Jul 2025](https://www.reddit.com/r/AmpCode/comments/1m5iuoe/cost/)), prompting Amp to add a ~$20/mo Megawatt tier and BYO model options.
- **Cline CLI / Roo Code / Kilo Code CLI:**
  - **Cline CLI:** Extends the popular open-source VS Code Plan/Act agent to the terminal with shadow-git checkpoints, MCP, and full BYOK support; praised for seamless IDE-to-headless CLI handoff, though unthrottled BYOK loops on large repos get expensive fast ([cline.bot, 2026](https://cline.bot/); [r/CLine, Sep 2026](https://www.reddit.com/r/CLine/comments/1x9p2rr/switching_to_cline_from_claude_codecodex_was_way/)).
  - **Roo Code:** Feature-packed Cline fork favored on Reddit for embedding-backed codebase indexing and "ping-pong" multi-model switching (e.g., Gemini Flash/DeepSeek for edits, Claude for architecture), primarily used in IDE with CLI companion workflows ([r/LocalLLaMA, Oct 2025](https://www.reddit.com/r/LocalLLaMA/comments/1o54lfc/roo_code_cline_opencode_codex_qwen_cli_claude/)).
  - **Kilo Code CLI (`@kilocode/cli`):** Open-source agentic CLI spanning 500+ models with specialized modes (*Architect*, *Code*, *Debug*, *Orchestrator*) and a praised TUI ([kilo.ai, 2026](https://kilo.ai/); [Hacker News, 2026-01-22](https://news.ycombinator.com/item?id=46719284)). Users like its Architect mode and TUI over OpenCode ([r/kilocode, May 2026](https://www.reddit.com/r/kilocode/comments/1ugvcdh/what_made_you_choose_kilo_code_over_opencode/)), but note high Bun/Node RAM usage and early scrutiny over data-processing terms.
- **Qwen Code & Qoder CLI (Alibaba):**
  - **Qwen Code:** Open-source fork of `gemini-cli` tailored for `Qwen3-Coder` and `Qwen3-Coder-Next`. Popular on `r/LocalLLaMA` for high token speed (~70 tok/s), generous free OAuth daily quotas, and strong local/MoE execution ([Qwen Blog, 2026](https://qwen.ai/blog?id=qwen3-coder); [r/LocalLLaMA, Oct 2025](https://www.reddit.com/r/LocalLLaMA/comments/1o54lfc/roo_code_cline_opencode_codex_qwen_cli_claude/)).
  - **Qoder CLI (`qoder`):** Alibaba's polished terminal agent with Quest mode, subagents, multi-modal screenshot-to-code input, and an embeddable Qoder Agent SDK ([Qoder CLI Docs, 2026](http://docs.qoder.com/cli/overview); [Qoder SDK Docs, 2026](http://docs.qoder.com/cli/sdk/overview)).
- **Freebuff (`npm i -g freebuff`):** Emerged in mid-2026 as a zero-cost, ad-supported terminal coding agent (displaying unobtrusive text ads in the TUI in exchange for free frontier model access) with multi-subagent and browser-use capabilities ([r/vibecoding, Jun 2026](https://www.reddit.com/r/vibecoding/comments/1vh7bjr/built_a_cli_dev_tool_with_freebuff_looking_for/)).
- **Factory Droid (`droid` / `droid exec`):** Enterprise-focused, model-agnostic agentic CLI and SDK by Factory AI ([factory.com, 2026](https://factory.com/product/droids)). Placed at the top of **Terminal-Bench** (~64.9%, beating standalone Codex CLI's 62.9% with the same base model) due to its "Missions" planning layer and programmatic tool-calling harness ([r/codex, Jan 2026](https://www.reddit.com/r/codex/comments/1q52mwr/gpt52_hits_629_codex_cli_and_649_droid_on/); [DevelopersDigest, 2026-06-10](https://www.developersdigest.tech/blog/factory-droid-review-setup-2026)). Trades raw speed on small tasks for high reliability on large migrations; priced at $20/mo Pro, $100–$200/mo Plus/Max, plus BYOK ([r/FactoryAi, Jun 2026](https://www.reddit.com/r/FactoryAi/comments/1vpq26z/factory_droid_vs_cursor_usage_quota/)).
- **Warp (`Warp Code` / `Oz` CLI):** GPU-accelerated Rust terminal that embeds an AI coding agent and acts as a multi-pane orchestrator for running Claude Code, Codex, and OpenCode side-by-side. While users love the terminal UI, Warp's removal of free AI credits and rapid credit burn on its $20/mo Build tier drew heavy backlash on `r/warpdotdev` ("detached from reality"), making Free + BYOK the community-recommended setup ([r/warpdotdev, May 2026](https://www.reddit.com/r/warpdotdev/comments/1ua35jh/warp_no_longer_has_ai_features_for_free/); [r/warpdotdev, Jan 2026](https://www.reddit.com/r/warpdotdev/comments/1qbrmdc/warp_is_detached_from_reality/)).
- **Devin (Devin 2.0 CLI & Cloud):** Cognition dropped Devin's entry price from $500/mo to a **$20/mo Pro plan**, shifting self-serve billing from complex ACUs to monthly quotas plus on-demand API top-ups. This explains the Discord "Devin for value" signal: users praise starting a task in the local Devin CLI and running `/handoff` to let a cloud VM finish asynchronously ([r/DevinAI, Jul 2026](https://www.reddit.com/r/DevinAI/comments/1wkiqif/my_experience_with_the_20_devin_pro_plan_this/)). However, sources disagree on overall cost efficiency: Artificial Analysis benchmarks show full autonomous Devin runs averaging ~$8.75+/task ([Artificial Analysis, 2026](https://artificialanalysis.ai/agents/coding-agents/comparisons/deepseek-harness-vs-devin-fusion-cli)), and Reddit users warn that 6 hours of real repo work can burn the $20 quota and rack up $200 in top-ups ([r/DevinAI, Oct 2026](https://www.reddit.com/r/DevinAI/comments/1xsbcsv/i_tried_devin_on_real_work_6_hours_20_sub_200/)).
- **"DeepSeek Harness" (`dsh` & Claude Code + DeepSeek API):** Refers to two setups in 2026: (1) the MIT-licensed open-source **DeepSeek Harness CLI (`dsh`)** where every component (loop, tools, sandbox) is a swappable plugin ([Composio, 2026-09-01](https://composio.dev/content/deepseek-harness-vs-claude-code)), and (2) pointing **Claude Code's harness** at `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` using DeepSeek V4 Pro/Flash ([r/ClaudeCode, Jul 2026](https://www.reddit.com/r/ClaudeCode/comments/1w54ck5/just_realised_i_can_use_deepseek_inside_claude/)). Contrary to the Discord rumor of a "much higher price," DeepSeek API harnesses are **10x–30x cheaper** ($0.03–$0.32/task); the only "higher cost" reported in wider evidence is either paying for a third-party premium harness subscription (like Factory Droid) or spending extra iterative turns on complex frontend states ([r/DeepSeek, Oct 2026](https://www.reddit.com/r/DeepSeek/comments/1xysywi/claude_20_is_better_than_deepseek_api/)).
- **Newer CLIs coming up often in 2026:**
  - **Pi (`pi-coding-agent`):** Ultra-minimalist terminal harness (just `read`, `write`, `edit`, `bash`) that strips away heavy scaffolding and trusts frontier/local model reasoning; huge following among minimalists ([r/GithubCopilot, Feb 2026](https://www.reddit.com/r/GithubCopilot/comments/1rpjq4l/which_terminal_coding_agent_wins_in_2026_pi/)).
  - **Goose CLI (`block/goose`, Linux Foundation AAIF):** Rust-powered local-first agent supporting 85+ providers, MCP extensions, and portable YAML "recipes" for repeatable CI tasks ([GitHub awesome-cli-coding-agents, 2026](https://github.com/bradagi/awesome-cli-coding-agents)).
  - **Crush CLI (`charmbracelet/crush`):** Go + Bubble Tea terminal agent by Charmbracelet with deep LSP integration and tmux-friendly ergonomics ([GitHub awesome-cli-coding-agents, 2026](https://github.com/bradagi/awesome-cli-coding-agents)).
  - **Auggie CLI (Augment Code) & GitHub Copilot CLI:** Auggie brings Augment's semantic codebase search engine into an interactive and `--print` CI CLI; GitHub Copilot CLI bridges local terminal sessions with GitHub Issues/PR fleet execution ([r/GithubCopilot, Feb 2026](https://www.reddit.com/r/GithubCopilot/comments/1rpjq4l/which_terminal_coding_agent_wins_in_2026_pi/)).

---

## 4. Comparison Table: First Group

| Dimension | Claude Code | Codex CLI | OpenCode | Cursor CLI | Gemini CLI | Antigravity CLI (`agy`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Speed** | mixed | strong | weak | strong | weak | strong |
| **Tool use** | strong | mixed | mixed | strong | weak | strong |
| **Results quality** | strong | mixed | mixed | strong | mixed | strong |
| **Context handling** | mixed | weak | weak | mixed | mixed | mixed |
| **Cost and plans** | mixed | strong | strong | mixed | weak | mixed |
| **Model choice** | weak | mixed | strong | strong | weak | strong |
| **UI/UX of the TUI** | mixed | weak | strong | mixed | mixed | strong |
| **Control** | strong | strong | strong | strong | strong | strong |
| **Sessions** | strong | strong | mixed | mixed | strong | strong |
| **Automation** | strong | strong | strong | mixed | strong | strong |
| **Trust** | mixed | strong | strong | weak | mixed | mixed |

---

## 5. Patterns: What Loved vs. Hated CLIs Share

### What the Loved CLIs Share
1. **Compiled native TUI responsiveness:** Tools compiled to native Rust or Go binaries (Codex CLI's Ratatui TUI, Antigravity CLI's Go TUI, Crush) avoid the event-loop stalls, high memory footprint, and full-screen ANSI flicker that plague Node.js/Ink TUIs.
2. **Pre-execution Planning ("Plan" / "Architect" / "Orchestrator" modes):** Separating read-only architectural discovery from file mutation (`--mode plan`, Kilo's Architect mode, Factory Droid's Missions, `agy`'s Planner/Executor Orchestrator) consistently prevents runaway multi-file breakage.
3. **Deterministic verification hooks:** Allowing users to wire fast local linters, typecheckers, or test runners into `PostToolUse` / `AfterTool` hooks forces immediate self-correction without relying on the LLM to remember prose instructions in `CLAUDE.md` or `AGENTS.md`.
4. **Append-only JSONL transcripts and zero-copy session forking:** Storing plain JSONL on disk (`~/.claude/projects/`, `~/.codex/sessions/`, `~/.gemini/antigravity-cli/brain/`) and allowing instant `/fork` or `--fork-session` lets developers try risky refactors without corrupting their main context.
5. **Model routing flexibility:** Letting users pair an elite reasoning model (Claude Opus/Sonnet, Gemini 4 Argon/Neon, GPT-5.x) for planning with a cheap/fast model (DeepSeek V4 Flash, Gemini Flash, Qwen3-Coder, or included ChatGPT Plus/Google Pro quota) for execution.

### What the Hated CLIs Share
1. **Opaque, lossy auto-compaction ("The Lobotomy"):** Compacting context silently without preserving pinned architectural rules or active task state causes every CLI to forget constraints, repeat broken edits, or re-read the entire repository.
2. **Unbounded synchronous startup scans:** Crawling the filesystem via `ripgrep --hidden`, walking hundreds of skill folders, or indexing git trees on startup makes a CLI unusable when launched in a home directory, monorepo root, or unindexed folder (OpenCode `#6741`, Gemini CLI `#12362`).
3. **Silent sandbox or rate-limit stalls:** Failing to distinguish between "model is thinking," "HTTP 429 rate-limit retry loop" (Gemini CLI), "sandbox blocked network/credentials" (Codex CLI `#41161`), and "waiting on unapproved MCP server" (Cursor CLI `#133509`) destroys user trust.
4. **Monolithic SQLite state without auto-pruning:** Storing all chat history or content blobs in a single SQLite database (`opencode.db`, Cursor `store.db`) causes startup slowdowns, multi-GB disk bloat, and concurrency lock errors across terminals/containers.
5. **Hidden token burn and quota hostility:** Charging user quotas for backend 5xx retries (Claude Code), burning 1.5x–1.8x more tokens in `-p` headless mode, or retroactively tightening monthly subscription limits mid-cycle.

---

## 6. What a Multi-CLI Wrapper ("Conductor + Workers") Should Copy, Avoid, and Never Block

### What to Copy
1. **Explicit Planner $\rightarrow$ Worker Role Separation (from Antigravity `Orchestrator` & Factory Droid):** Keep the human talking to a high-reasoning Conductor that maintains a compact, structured task state, and dispatch bounded, file-scoped implementation prompts to headless Workers (`codex exec`, `claude -p`, `agy -p`, `opencode run --attach`).
2. **Persistent `stream-json` Worker Pools & Daemon Attachment:** Instead of spawning a cold CLI process for every micro-prompt—which breaks prompt caching in `claude -p` (`#97074`) and triggers startup scans in `opencode`—keep long-lived worker sessions open via `--input-format stream-json --output-format stream-json` (supported by both `claude` and `agy`) or attach to a warm `opencode serve` / ACP stdio process.
3. **Externalized Pinned Memory Outside CLI Compaction:** Maintain the shared project memory, active architectural constraints, and "definition of done" in the wrapper's own state (or a dedicated file/MCP server) and re-inject a concise task brief whenever a worker compacts or starts a new turn.
4. **Unified Real-Time Usage & Quota Bar:** Parse the token/cost usage summaries emitted in the final `result` / `turn.completed` JSON events from each worker (`cost_usd` in Claude Code, token stats in Codex/Gemini/Antigravity) into one unified burn-rate indicator so the user can route boilerplate away from a depleting 5-hour quota.
5. **Git Worktree Isolation per Parallel Worker (from `cursor-agent -w` and `agy` `workspace:"share"`):** When fanning tasks out to multiple headless workers simultaneously, assign each worker an isolated git worktree or shared working copy so concurrent file edits and test runs never collide.

### What to Avoid
1. **Never rely on EOF / process exit alone for headless workers:** Because tools like `cursor-agent -p` (`#150246`) and `gemini -p` (on HTTP 429) can hang indefinitely after finishing or hitting a rate limit, parse the `stream-json` / `--json` event stream line-by-line, treat the terminal `"type": "result"` / `"turn.completed"` event as completion, and enforce an inactivity watchdog timer.
2. **Never launch workers in unindexed parent or home directories:** Always validate that the worker's working directory (`cwd`) is a scoped project/worktree root with proper ignore files (`.gitignore`, `.ignore`, `.geminiignore`, `.cursorignore`) before spawning.
3. **Never spoof consumer OAuth headers across third-party APIs:** Both Anthropic (Jan–Mar 2026 crackdown) and Google actively detect and block third-party harnesses that extract or spoof consumer OAuth tokens. Always invoke the official CLI binaries (`claude`, `codex`, `agy`, `cursor-agent`, `opencode`) as subprocesses using their sanctioned CLI flags or explicit API keys.
4. **Never pass large prompts or diffs via raw `stdin` pipes when flags or files exist:** To avoid stdin truncation and subshell parsing bugs (especially on Windows PowerShell/cmd and `cursor-agent`), either use structured `--input-format stream-json` over stdin or write large context to a scratch file inside the workspace and instruct the worker to read that file path.

### What to Never Block or Interfere With
1. **Prompt Cache Prefix Stability:** Never inject changing timestamps, random UUIDs, or shifting system instructions at the top of a worker's prompt history; breaking the prefix invalidates Anthropic, OpenAI, and Google prompt caches and multiplies token burn 5x–10x.
2. **Native Project Instruction & Hook Files:** Never overwrite or shadow the user's `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules`, or `.claude/settings.json` / `.codex/hooks.json` / `hooks.json`. If the wrapper shares a unified persona/memory, synchronize it cleanly via a dedicated section or `@import` link rather than clobbering native config files.
3. **Explicit Sandbox & Permission Flags in Headless Mode:** A headless worker waiting on a `y/N` prompt on an unattached TTY will deadlock the entire pipeline. The wrapper must always pass explicit non-interactive permission flags (`--allowedTools` / `--permission-mode` for Claude, `--sandbox workspace-write -a never` or `--full-auto` for Codex, `--mode accept-edits` or `--dangerously-skip-permissions` for `agy`, `--trust --approve-mcps --force` for Cursor) matched to the user's wrapper-level approval policy.
4. **Environment Variable Overrides:** Never strip `ANTHROPIC_BASE_URL`, `CODEX_HOME`, `AGY_CLI_AUTO_COMPACT_OVERRIDE`, `GEMINI_API_KEY`, or proxy/certificate variables (`HTTP_PROXY`, `NODE_EXTRA_CA_CERTS`) from the worker subprocess environment.

---

## 7. Gaps: What Could Not Be Verified

1. **Exact cold start-up time and time-to-first-token (TTFT) in milliseconds on identical hardware across all six CLIs:** Only `agy` (`v1.5.15`) was installed locally on this test machine (where read-only commands were allowed, but no paid prompts could be executed to measure live TTFT). While architectural differences (compiled Rust in Codex and Go in Antigravity vs. Node.js/Bun in Claude Code and OpenCode) and startup hang bugs are well-documented in GitHub issues, controlled sub-second millisecond benchmarks across identical prompts were not independently runnable under the read-only constraint.
2. **Internal proprietary compaction prompts and exact token multipliers for closed-source CLIs:** Because Claude Code, Cursor CLI, and Antigravity CLI are closed-source binaries, their exact internal summarization prompts and server-side quota weighting formulas (e.g., how Google AI Pro or Cursor Plus translates specific model calls into rolling quota percentages) cannot be verified from public source code and are known only through black-box user diagnostics and changelog notes.
3. **Origin of the Discord rumor that a "DeepSeek harness" has a "much higher price" for frontend work:** Every public benchmark and Reddit thread from 2025–2026 shows DeepSeek API harnesses (`dsh` or Claude Code pointed at DeepSeek's API) costing **far less** per task ($0.03–$0.32) than native Claude or Devin runs. We could not verify whether the Discord commenter confused DeepSeek with an expensive multi-model harness (like Factory Droid or Amp), was paying per-token API rates after coming from a flat $20 subscription, or meant higher time/turn cost.

---

## 8. The extras: what changes why you'd pick each one

Beyond the baseline "chat + edit files + run shell commands" loop, each CLI ships extra capabilities that either lock users in or drive them away. Below is the evidence on what each extra does, whether developers actually value it or treat it as bloat/marketing, and whether it survives when an external wrapper runs the CLI headlessly.

---

### 8.1 Claude Code (Anthropic)

- **Subagents & Parallel Worktrees (`.claude/agents/`, `Task` tool, `--worktree` / `-w`):**
  - *What it is:* Spawns isolated child agent contexts (with separate prompts/tool allowlists or isolated git worktrees) to research or implement subtasks in parallel ([MarkTechPost, 2026-06-14](https://www.marktechpost.com/2026/06/14/claude-code-guide-2026-25-features-with-examples-demo/)).
  - *Valued or marketing?* **Heavily valued, with a cost caveat.** Power users rely on subagents to keep main-thread context clean during codebase exploration, though Reddit users warn that unconstrained subagent spawning can drain a 5-hour Pro/Max quota in minutes ([r/ClaudeCode, Aug 2026](https://www.reddit.com/r/ClaudeCode/comments/1wu8zzp/claude_code_is_getting_very_very_slow_and_running/)).
  - *Works headless?* **Yes.** Subagent tool calls and `--worktree` operate normally inside `claude -p` unless `--bare` or `--disallowedTools "Task"` is passed.
- **Lifecycle Hooks (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` in `.claude/settings.json`):**
  - *What it is:* Deterministic shell commands or HTTP webhooks that fire before/after tool calls to auto-run linters/formatters or block dangerous commands ([Claude Code Hooks Docs, 2026](https://code.claude.com/docs/en/hooks)).
  - *Valued or marketing?* **Highly valued.** Developers cite hooks as the single most reliable way to enforce code quality (e.g., running Prettier/ESLint/typecheck on every file edit) because LLMs routinely ignore prose rules in `CLAUDE.md` ([Firecrawl Blog, 2026](https://www.firecrawl.dev/blog/best-claude-code-plugins)).
  - *Works headless?* **Yes.** Hooks execute in `claude -p` runs (unless bypassed via `--bare`).
- **Skills, Plugins & Plugin Marketplace (`/plugin`, `.claude/skills/SKILL.md`):**
  - *What it is:* Installable bundles packaging slash commands, `SKILL.md` instructions, hooks, and MCP servers from community or enterprise marketplaces ([DEV.to, 2026-05](https://dev.to/jennyouyang/best-claude-code-plugins-2026-11-tested-4-worth-keeping-1oal)).
  - *Valued or marketing?* **Mixed (selective value vs. "plugin bloat" backlash).** While specific plugins like LSP code navigation, Context7 docs, and Firecrawl are praised for cutting blind grepping ([r/ClaudeAI, Jul 2026](https://www.reddit.com/r/ClaudeAI/comments/1whsbju/i_tested_3_more_claude_code_plugins_to_cut_costs/)), testers report that most marketplace plugins bloat the system prompt and burn context tokens rapidly ([DEV.to, 2026-05](https://dev.to/jennyouyang/best-claude-code-plugins-2026-11-tested-4-worth-keeping-1oal); [r/ClaudeAI, Nov 2026](https://www.reddit.com/r/ClaudeAI/comments/1y3arht/which_cli_skill_or_tool_gateway_is_the_best_for/)).
  - *Works headless?* **Yes.** Installed skills and plugins load automatically in headless `-p` mode unless `--bare` is set.
- **Browser / Computer Use (`--chrome` / `/chrome` & Playwright MCP):**
  - *What it is:* Connects Claude Code to a live Chrome instance or headless browser so the agent can inspect DOM elements, read console errors, and visually verify UI changes ([r/ClaudeAI, Nov 2026](https://www.reddit.com/r/ClaudeAI/comments/1y0kjxk/what_claude_code_plugins_are_you_guys_using/)).
  - *Valued or marketing?* **Valued by frontend developers.** Praised for closing the loop on live frontend debugging without manually copy-pasting browser console errors ([r/ClaudeAI, Nov 2026](https://www.reddit.com/r/ClaudeAI/comments/1y0kjxk/what_claude_code_plugins_are_you_guys_using/)).
  - *Works headless?* **Yes** (when passed `--chrome` or configured via a Playwright/DevTools MCP server in `.claude/settings.json`).
- **Remote Control, Cloud Handoff & Teleport (`claude remote-control`, `--remote`, `--teleport`):**
  - *What it is:* Lets users steer a local terminal session from a phone/web browser (`remote-control`) or hand off cloud tasks (`--remote`) and pull them back locally (`--teleport`) ([r/ClaudeAI, May 2026](https://www.reddit.com/r/ClaudeAI/comments/1ubiulc/claude_code_desktop_vs_claude_cli/); [r/ClaudeCode, Apr 2026](https://www.reddit.com/r/ClaudeCode/comments/1tci1dr/so_are_people_using_claude_code_cli_claude_code/)).
  - *Valued or marketing?* **Valued for away-from-desk monitoring, but secondary to the local CLI.** Users like checking long tasks from a phone, though security-conscious devs express caution about remote execution bridges ([r/ClaudeCode, Apr 2026](https://www.reddit.com/r/ClaudeCode/comments/1tci1dr/so_are_people_using_claude_code_cli_claude_code/)).
  - *Works headless?* **No** (tied to Anthropic's interactive web/mobile UI and interactive TUI daemon).
- **GitHub / PR / CI Integration (`anthropics/claude-code-action`, `/install-github-app`, `/pr-comments`):**
  - *What it is:* Official GitHub Action and slash commands that let `@claude` review PRs, respond to inline PR comments, and push fixes in CI ([GitHub claude-code-action #1177, 2026-04-05](https://github.com/anthropics/claude-code-action/issues/1177)).
  - *Valued or marketing?* **Highly valued by teams.** Widely adopted for automated PR review and CI auto-fixes, though senior devs warn it can breed review laziness ([r/ClaudeAI, Oct 2026](https://www.reddit.com/r/ClaudeAI/comments/1xpz4o7/claude_code_built_my_opensource_ai_voice_studio/)).
  - *Works headless?* **Yes** (the GitHub Action itself runs `claude -p` headlessly).
- **Web Search Grounding, Image Input & Voice Dictation (`WebSearch`/`WebFetch`, image paste, `/voice`):**
  - *What it is:* Built-in web search/doc fetching, multimodal screenshot analysis, and push-to-talk `/voice` dictation ([suprmind.ai, 2026](https://suprmind.ai/hub/claude/features/)).
  - *Valued or marketing?* **WebSearch and screenshots are heavily used; `/voice` is niche.** Developers use image attachments constantly for UI bugs, while `/voice` in the terminal is mostly treated as a novelty ([r/ClaudeAI, Oct 2026](https://www.reddit.com/r/ClaudeAI/comments/1xpz4o7/claude_code_built_my_opensource_ai_voice_studio/)).
  - *Works headless?* **Partly.** `WebSearch`/`WebFetch` and file-path images (`Read` tool on `.png`/`.jpg`) work in headless `-p` mode; `/voice` and clipboard image paste are TUI-only.
- **Scheduled / Recurring Loops (`/loop`):**
  - *What it is:* In-session recurring prompt scheduler (e.g., `/loop 5m check build`) ([Firecrawl Blog, 2026](https://www.firecrawl.dev/blog/best-claude-code-plugins)).
  - *Valued or marketing?* **Mixed.** Used by "Ralph loop" enthusiasts for unattended iteration, but notorious for runaway token burn if left unwatched ([Firecrawl Blog, 2026](https://www.firecrawl.dev/blog/best-claude-code-plugins)).
  - *Works headless?* **No** (`/loop` is an interactive session slash command; headless wrappers must run their own cron/loop).

---

### 8.2 Codex CLI (OpenAI)

- **Bundled with Existing ChatGPT Plus ($20/mo) / Pro / Team Subscriptions:**
  - *What it is:* Authenticates directly with a user's existing ChatGPT web subscription at no extra API cost ([OpenAI Codex CLI Docs, 2026](https://learn.chatgpt.com/docs/codex/cli)).
  - *Valued or marketing?* **The #1 reason developers try and keep Codex CLI.** Reddit threads consistently cite "it's already included in my $20 ChatGPT Plus plan" as its biggest advantage over paying for a separate coding subscription ([r/ClaudeAI, Oct 2026](https://www.reddit.com/r/ClaudeAI/comments/1xl4bth/cs_student_dilemma_chatgpt_plus_codex_work_vs/)).
  - *Works headless?* **Yes.** `codex exec` uses the same cached `~/.codex/auth.json` ChatGPT OAuth session.
- **Built-in Local Code Review (`/review`) & GitHub Action (`openai/codex-action`):**
  - *What it is:* Dedicated `/review` mode that audits uncommitted diffs, branch diffs, or specific commits for bugs, plus an official GitHub Action for PR reviews ([OpenAI Codex CLI Docs, 2026](https://learn.chatgpt.com/docs/codex/cli); [GitHub openai/codex-action, 2026](https://github.com/openai/codex-action)).
  - *Valued or marketing?* **Highly valued.** Even developers who prefer Claude Code for writing code frequently praise Codex's `/review` and `codex-action` as a second-opinion bug catcher before pushing PRs ([r/ChatGPTCoding, Aug 2026](https://www.reddit.com/r/ChatGPTCoding/comments/1wvg6su/codex_cli_is_cooked/)).
  - *Works headless?* **Partly.** The interactive `/review` menu is TUI-only, but `codex exec` and `openai/codex-action` run equivalent diff reviews headlessly.
- **Codex Cloud Handoff (`codex cloud` / Web Tasks):**
  - *What it is:* Launches or pulls asynchronous cloud container tasks running on `chatgpt.com/codex` from the local CLI ([r/codex, Oct 2026](https://www.reddit.com/r/codex/comments/1xvmspk/the_new_codex_cloud_ui_and_workflow_are_inferior/)).
  - *Valued or marketing?* **Mixed-to-negative after the 2026 UI redesign.** Power users loved the original dense task dashboard for fire-and-forget PRs, but heavily criticized OpenAI's newer chat-centric Cloud UI for hiding multi-file diff summaries ([r/codex, Oct 2026](https://www.reddit.com/r/codex/comments/1xvmspk/the_new_codex_cloud_ui_and_workflow_are_inferior/)).
  - *Works headless?* **Partly** (`codex cloud` subcommands can trigger cloud runs from scripts, but review/PR management lives in OpenAI's web UI).
- **Live Web Search (`--search`) & Image Input (`-i` / `--image <file>`):**
  - *What it is:* Enables live web search grounding via `--search` and attaches screenshots/mockups via `-i <path>` ([r/CodexAutomation, Aug 2026](https://www.reddit.com/r/CodexAutomation/comments/1wsgjhu/codex_cli_01580_is_out_stronger_approvals_mcp/); [r/AISEOInsider, May 2026](https://www.reddit.com/r/AISEOInsider/comments/1ub1v79/new_codex_update_just_changed_coding_forever/)).
  - *Valued or marketing?* **Valued.** Passing `-i screenshot.png` directly on the command line is praised for quick UI fixes and image-generation pipelines ([r/CodexAutomation, Aug 2026](https://www.reddit.com/r/CodexAutomation/comments/1wsgjhu/codex_cli_01580_is_out_stronger_approvals_mcp/)).
  - *Works headless?* **Yes.** Both `--search` and `-i` / `--image` work directly with `codex exec`.
- **`codex app-server` & TypeScript SDK (`@openai/codex-sdk`):**
  - *What it is:* A built-in JSON-RPC server (`codex app-server`) and Node SDK designed to power IDE extensions (VS Code, Cursor, Xcode) and custom wrappers ([DeepWiki openai/codex, 2026](https://deepwiki.com/)).
  - *Valued or marketing?* **Valued by tool builders.** Gives wrapper authors a stable bidirectional protocol instead of scraping TUI stdout.
  - *Works headless?* **Yes** (explicitly built for headless programmatic control).

---

### 8.3 OpenCode (`sst/opencode` / `anomalyco/opencode`)

- **75+ Model Providers, Local Models & $10/mo "OpenCode Go" / GitHub Copilot Reuse:**
  - *What it is:* Connects to 75+ LLM providers, local Ollama/LM Studio models, existing GitHub Copilot subscriptions, or the $10/mo OpenCode Go pooled open-model plan ([OpenCode Go Docs, 2026](https://opencode.ai/docs/console/go/); [r/opencode, Aug 2026](https://www.reddit.com/r/opencode/comments/1wvkbm2/is_opencode_go_worth_it_now/)).
  - *Valued or marketing?* **The #1 reason people choose OpenCode.** Developers love not being locked into one vendor and using cheap/open models (DeepSeek, Qwen, Kimi, GLM) or an existing GitHub Copilot seat, though some Redditors debate whether OpenCode Go's backend models experience cache/quantization slowdowns under peak load ([r/opencode, Aug 2026](https://www.reddit.com/r/opencode/comments/1wvkbm2/is_opencode_go_worth_it_now/); [r/opencode, Oct 2026](https://www.reddit.com/r/opencode/comments/1xpylm3/i_love_opencode/)).
  - *Works headless?* **Yes.** `opencode run -m <provider/model>` supports every configured provider and local model headlessly.
- **Built-in LSP (Language Server Protocol) Diagnostic Feedback Loop:**
  - *What it is:* Automatically spawns language servers (TypeScript, Pyright, gopls, rust-analyzer) and feeds compiler/type errors straight back to the agent after every file edit ([r/LocalLLaMA, Nov 2025](https://www.reddit.com/r/LocalLLaMA/comments/1pb9q3q/how_many_of_you_are_using_opencode/)).
  - *Valued or marketing?* **Highly valued.** Frequently cited on Reddit as a huge quality boost that lets cheaper models self-correct syntax and type errors without running a full slow build command ([r/LocalLLaMA, Nov 2025](https://www.reddit.com/r/LocalLLaMA/comments/1pb9q3q/how_many_of_you_are_using_opencode/)).
  - *Works headless?* **Yes.** The internal `opencode` engine runs LSP diagnostics during `opencode run` and `opencode serve`.
- **Client/Server Architecture (`opencode serve`, `opencode web`, `--attach`, Mobile Apps):**
  - *What it is:* Decouples the agent backend into an HTTP/SSE server (`opencode serve` / `opencode web`) that any TUI, browser, or mobile app can attach to remotely ([OpenCode CLI Docs, 2026](https://docs.opencode.ai/docs/cli/); [r/opencodeCLI, Feb 2026](https://www.reddit.com/r/opencodeCLI/comments/1rkm551/thank_you_opencode/)).
  - *Valued or marketing?* **Valued by multi-device and homelab users.** Users praise running the server on a workstation and checking or steering sessions from a laptop or Android phone ([r/opencodeCLI, Feb 2026](https://www.reddit.com/r/opencodeCLI/comments/1rkm551/thank_you_opencode/)).
  - *Works headless?* **Yes.** A wrapper can talk directly to `opencode serve` via `@opencode-ai/sdk` or `opencode run --attach http://localhost:4096`, avoiding cold-startup scans.
- **Shareable Session Links (`/share`, `opencode run --share`) & GitHub App (`opencode github`):**
  - *What it is:* Generates a public read-only web link (`opencode.ai/s/<id>`) of a session transcript, and provides a GitHub Actions agent triggered by `/opencode` or `/oc` comments on issues/PRs ([OpenCode CLI Docs, 2026](https://docs.opencode.ai/docs/cli/)).
  - *Valued or marketing?* **Valued for team debugging and OSS collaboration.** Users frequently share `/share` links on Reddit and GitHub issues to show exact prompt/tool trajectories.
  - *Works headless?* **Yes** (`opencode run --share` prints the share URL in headless mode).

---

### 8.4 Cursor CLI (`cursor-agent` / `agent`)

- **Shared Semantic Codebase Indexing & IDE Rules/MCP Tie-In:**
  - *What it is:* Reuses Cursor's cloud-synced vector codebase index, `.cursor/rules`, `hooks.json`, and MCP configurations from the Cursor Desktop IDE ([Cursor CLI Overview, 2026](https://cursor.com/docs/cli/overview); [r/cursor, Oct 2025](https://www.reddit.com/r/cursor/comments/1othdrc/is_cursors_codebase_indexing_the_best_compared_to/)).
  - *Valued or marketing?* **The #1 moat keeping users on Cursor.** Reddit threads repeatedly state that Cursor's fast, accurate semantic vector indexing is the main reason developers keep paying for Cursor even when they prefer terminal workflows ([r/cursor, May 2026](https://www.reddit.com/r/cursor/comments/1ur4t5o/so_is_indexing_the_only_feature_of_cursor/)).
  - *Works headless?* **Yes.** `cursor-agent -p` queries the same semantic codebase index and applies `.cursor/rules` and `hooks.json`.
- **Cloud Agents & Mobile/Web Handoff (`-c` / `--cloud`, `cursor.com/agents`):**
  - *What it is:* Pushes a task (via `-c` or prefixing `&`) to an isolated Cursor Cloud VM that can run background builds, open browsers, and open PRs controllable from a phone at `cursor.com/agents` ([r/cursor, Feb 2026](https://www.reddit.com/r/cursor/comments/1rnfchm/cloud_agents_ai_code_review_have_completely/); [r/cursor, Jun 2026](https://www.reddit.com/r/cursor/comments/1vtaosn/anyone_tried_cursor_cloud_agents_lately/)).
  - *Valued or marketing?* **Valued by Premium ($30+/mo) teams, criticized for high token burn.** Teams love firing off Slack/Linear/CLI tasks to Cloud Agents + Bugbot while away from their laptops ([r/cursor, Feb 2026](https://www.reddit.com/r/cursor/comments/1rnfchm/cloud_agents_ai_code_review_have_completely/)), but solo devs complain that cloud sessions burn usage quotas much faster and require higher subscription tiers ([r/cursor, Jun 2026](https://www.reddit.com/r/cursor/comments/1vtaosn/anyone_tried_cursor_cloud_agents_lately/)).
  - *Works headless?* **Partly.** Can be triggered via CLI flags, but execution moves off the local machine into Cursor's proprietary cloud UI rather than returning local workspace edits to a wrapper.
- **Automatic Git Worktree Isolation (`-w` / `--worktree [name]`):**
  - *What it is:* Spins up a separate git worktree under `~/.cursor/worktrees/` for the CLI run so parallel agents never clobber each other's files ([Cursor CLI Parameters, 2026](https://cursor.com/docs/cli/reference/parameters)).
  - *Valued or marketing?* **Highly valued.** Eliminates manual `git worktree add` boilerplate when running multiple agents on the same repo.
  - *Works headless?* **Yes** (`cursor-agent -p -w <name>` works directly in headless calls).

---

### 8.5 Gemini CLI (Google — Legacy Open-Source `google-gemini/gemini-cli`)

- **Native Google Search Grounding (`google_web_search`):**
  - *What it is:* Built-in first-party tool that queries live Google Search and injects grounded results and citations into the agent context ([Gemini CLI Web Search Docs, 2026](https://geminicli.com/docs/tools/web-search/)).
  - *Valued or marketing?* **Heavily valued.** Consistently praised on Reddit as Gemini CLI's strongest built-in tool for looking up fresh SDK docs and breaking package changes without external MCP setup ([r/GeminiAI, Mar 2026](https://www.reddit.com/r/GeminiAI/comments/1svru9p/genuine_question_how_is_gemini_cli_still_so_far/)).
  - *Works headless?* **Yes.** `google_web_search` executes normally during `gemini -p` runs.
- **Gemini Extensions Packaging (`gemini extensions install`) & GitHub Action (`run-gemini-cli`):**
  - *What it is:* Self-contained extension bundles (packaging MCP servers, `.toml` slash commands, and `GEMINI.md` playbooks for BigQuery, Cloud SQL, GitHub, Datadog) plus an official GitHub Action ([Google Codelabs, 2026](https://codelabs.developers.google.com/getting-started-gemini-cli-extensions); [GitHub gemini-cli-extensions, 2026](https://github.com/gemini-cli-extensions)).
  - *Valued or marketing?* **Valued by Google Cloud / enterprise users.** Praised for replacing fragile manual `settings.json` edits with one-command installs ([Google Codelabs, 2026](https://codelabs.developers.google.com/getting-started-gemini-cli-extensions)).
  - *Works headless?* **Yes** (extensions load in `-p` mode and can be filtered via `--extensions`).
- **Shadow-Git Checkpointing & `/restore` (`--checkpointing`):**
  - *What it is:* Automatically snapshots workspace files in a hidden shadow Git repo (`~/.gemini/history/`) before every file edit so `/restore` can roll back bad changes without polluting project Git history ([Gemini CLI Checkpointing Docs, 2026](https://google-gemini.github.io/gemini-cli/docs/cli/checkpointing.html)).
  - *Valued or marketing?* **Valued as a safety net, though hidden paths confuse newcomers.** Users appreciate instant undo when Gemini's `replace` tool mangles a file ([r/GeminiAI, Aug 2025](https://www.reddit.com/r/GeminiAI/comments/1na8c6v/gemini_cli_supports_several_builtin_commands_to/)).
  - *Works headless?* **Partly.** `--checkpointing` still creates snapshots on disk during headless runs, but the `/restore` picker is an interactive TUI slash command.
- **1M-Token Context Window & Free Tier (Pre-June 2026 OAuth / Post-June 2026 AI Studio Key):**
  - *What it is:* Native 1M-token window across Gemini models, originally paired with 1,000 free requests/day via Google Sign-In until Google shut off consumer OAuth on June 18, 2026 ([GitHub Discussion #27274, 2026-06-18](https://github.com/google-gemini/gemini-cli/discussions/27274)).
  - *Valued or marketing?* **The free 1M window was the #1 reason people used Gemini CLI; its removal caused a mass exodus.** Losing consumer OAuth forced most individual users to switch to `agy`, Qwen Code, or OpenCode ([Hacker News, 2026-05-21](https://news.ycombinator.com/item?id=48222529)).
  - *Works headless?* **Yes** (1M context still works headlessly via `GEMINI_API_KEY` or Vertex ADC).

---

### 8.6 Antigravity CLI (`agy`, Google)

- **Multi-Vendor Frontier Model Catalog + Dual-Model `Orchestrator` Mode:**
  - *What it is:* Runs Gemini 4 (Neon, Carbon, Argon, Hydrogen), Gemini 3.8 Flash, Claude Opus 5.5, Claude Sonnet 5.5, and GPT-OSS 120B under one Google AI Pro/Ultra or Enterprise subscription, plus an `Orchestrator` mode that pairs a high-thinking Planner model with a fast Executor model (`agy models`; `agy changelog` v1.5.10–1.5.15).
  - *Valued or marketing?* **Heavily valued.** Reddit users highlight having both Claude 5.5 and "virtually infinite" fast Gemini models inside one fast Go CLI as `agy`'s biggest draw ([r/ChatGPTCoding, Nov 2026](https://www.reddit.com/r/ChatGPTCoding/comments/1y2bj0m/how_does_antigravity_new_gemini_models_compare/)).
  - *Works headless?* **Yes.** `agy -p --model <model>` and `--effort <level>` work headlessly (including `gemini-pro-orchestrator-neon|carbon|argon`).
- **Subagents (`inherit|branch|share`), `/swarm` Board & Python `run_workflow` Engine:**
  - *What it is:* Native subagents with isolated or git-worktree-like shared workspaces, a multi-agent `/swarm` board, and `run_workflow` (a bundled Python interpreter that orchestrates parallel/staged multi-agent pipelines in code) ([Antigravity CLI Product Page, 2026](https://antigravity.google/product/antigravity-cli/); `agy changelog` v1.5.9, v1.5.13, v1.5.14).
  - *Valued or marketing?* **Valued by power users, with a quota warning.** `run_workflow` and subagents are praised for deterministic fan-out tasks, though v1.5.13 had to stop agents from starting a `/swarm` unprompted because swarms burned user quota much faster than a single agent (`agy changelog` v1.5.13).
  - *Works headless?* **Partly.** Standard subagents (`invoke_subagent`) and `run_workflow` Python orchestration run inside headless `agy -p` turns; `/swarm` requires explicit user `/swarm` invocation or an active swarm session.
- **Remote Control Browser View (`--remote-control`), Cloud `--remote-agent` & `agy mic-serve`:**
  - *What it is:* A full side-panel web/mobile browser UI attached to the local CLI (`agy remote-control start` with split view, artifact review comments, and file tabs), cloud execution via `--remote-agent`, and `agy mic-serve` to stream a local microphone over SSH to a remote CLI ([Antigravity Remote Agents Docs, 2026](https://antigravity.google/docs/remote-agents/); `agy --help`; `agy changelog` v1.5.10–1.5.15).
  - *Valued or marketing?* **Valued for SSH/mobile and artifact review.** The Remote Control browser view gets heavy engineering attention in every release (v1.5.8–1.5.15) because it solves terminal table/artifact review without needing the heavy desktop IDE.
  - *Works headless?* **Partly.** `--remote-agent` works with `-p` (when signed in with Google OAuth, exiting with code `2` on `GEMINI_API_KEY`), while the Remote Control browser UI and `mic-serve` are for human interactive sessions (`agy changelog` v1.5.12).
- **Built-in `/browser` Subagent (with `.mp4` Screen Recording), Image Generator & Cross-CLI Plugin Importer (`agy plugin import`):**
  - *What it is:* Automated Chrome DevTools `/browser` subagent that records `.mp4` verification videos, an `image-generator` subagent, and one-command import of existing Claude Code or Gemini CLI plugins/skills (`agy plugin import [claude|gemini]`) ([Antigravity Features Docs, 2026](https://antigravity.google/docs/features/); `agy plugin --help`; `agy changelog` v1.5.9).
  - *Valued or marketing?* **Valued.** `agy plugin import claude` removes migration friction by letting users keep their existing `.claude` skills, MCPs, and hooks.
  - *Works headless?* **Yes.** Imported plugins, skills, hooks, and subagents work in `agy -p` (unless `--disable-slash-commands` or enterprise `pluginsDisabled` is set).

---

### 8.7 Notable Extras in the Second Group (Where It Changes Why You'd Pick Them)

- **Aider — Tree-Sitter AST Repo-Map & Automatic Git Commits:** Creates a compact structural call-graph index of the repository using tree-sitter and auto-commits every edit with a clean commit message ([r/ChatGPTCoding, Jul 2025](https://www.reddit.com/r/ChatGPTCoding/comments/1m7gq38/using_aider_vs_claude_code/)). **Highly valued** (developers even hack Aider's repo-map into Claude Code) and **100% survives headless wrapping** (`aider --message`).
- **Amp — Cloud "Orbs" & "Oracle" Deep-Reasoning Subagent:** Runs each thread on an isolated cloud VM ("Orb") that stays alive when you close your laptop, backed by Sourcegraph's Librarian and the high-compute Oracle subagent ([ampcode.com, 2026](https://ampcode.com/); [r/AmpCode, Jun 2026](https://www.reddit.com/r/AmpCode/comments/1vbax01/i_am_literally_so_happy_with_the_latest_updates/)). **Valued for unattended cloud runs**; Oracle/subagents survive headless CLI calls, while Orb cloud persistence bypasses local workspace state.
- **Factory Droid — "Missions" Planning Harness & Programmatic Tool Calling:** Uses a multi-stage verification harness that boosted GPT-5.2 from 62.9% (Codex CLI) to 64.9% on Terminal-Bench ([r/codex, Jan 2026](https://www.reddit.com/r/codex/comments/1q52mwr/gpt52_hits_629_codex_cli_and_649_droid_on/)). **Valued for complex migrations** and **survives headless wrapping** via `droid exec`.
- **Devin 2.0 — Local CLI `/handoff` to Asynchronous Cloud VMs ($20/mo entry):** Lets you start steering locally and `/handoff` to a cloud VM with browser/shell access ([r/DevinAI, Jul 2026](https://www.reddit.com/r/DevinAI/comments/1wkiqif/my_experience_with_the_20_devin_pro_plan_this/)). **Valued for async cloud offloading**, though **does not fit a local headless worker wrapper** once handed off to the cloud.
- **Qwen Code & Freebuff — Zero-Cost Frontier Access (OAuth Free Tier / Ad-Supported TUI):** Qwen Code offers generous free daily OAuth quotas at ~70 tok/s ([r/LocalLLaMA, Oct 2025](https://www.reddit.com/r/LocalLLaMA/comments/1o54lfc/roo_code_cline_opencode_codex_qwen_cli_claude/)), and Freebuff offers free multi-subagent coding funded by terminal text ads ([r/vibecoding, Jun 2026](https://www.reddit.com/r/vibecoding/comments/1vh7bjr/built_a_cli_dev_tool_with_freebuff_looking_for/)). Qwen Code's free OAuth **survives headless wrapping** (`qwen -p`); Freebuff's ad-supported TUI is **not meant for headless wrapping**.

---

### 8.8 Summary Table: Key Extras & Whether They Survive Headless Wrapping

| CLI | The 2–3 extras that most change why you'd pick it | Survives being wrapped? |
| :--- | :--- | :--- |
| **Claude Code** | 1. Deterministic lifecycle hooks (`PreToolUse`/`PostToolUse` in `.claude/settings.json`)<br>2. Subagents & parallel git worktrees (`.claude/agents/`, `--worktree`)<br>3. Plugin/skill ecosystem & GitHub/Chrome integrations (`--chrome`, `claude-code-action`) | **partly** (Hooks, subagents, skills, `--worktree`, `--chrome`, and `WebSearch` **yes**; phone Remote Control, `--teleport`, `/voice`, and `/loop` **no**) |
| **Codex CLI** | 1. Bundled at no extra cost with ChatGPT Plus ($20/mo) & Pro subscriptions<br>2. Built-in diff code reviewer (`/review` & `openai/codex-action`)<br>3. Direct CLI flags for live web search (`--search`) and screenshot input (`-i`) | **partly** (Bundled ChatGPT Plus auth, `--search`, `-i` images, and `codex-app-server` **yes**; interactive `/review` UI and Codex Cloud web dashboard **no**) |
| **OpenCode** | 1. 75+ model providers, local models, GitHub Copilot reuse & $10/mo OpenCode Go<br>2. Automatic LSP compiler/type error feedback loop into the agent<br>3. Client/server daemon (`opencode serve`/`web`, `--attach`) & `/share` links | **yes** (All three—multi-provider routing, automatic LSP diagnostics, `--share`, and attaching to a warm `opencode serve` daemon—work headlessly) |
| **Cursor CLI** | 1. Shared Cursor semantic vector codebase index & `.cursor/rules` / MCPs<br>2. Automatic git worktree isolation (`-w` / `--worktree`)<br>3. Cloud Agent VM handoff (`--cloud` / `cursor.com/agents`) | **partly** (Semantic codebase index, `.cursor/rules`, hooks, and `-w` worktrees **yes**; Cloud Agents move execution off-machine and `-p` requires watchdog timeouts) |
| **Gemini CLI** | 1. Native first-party Google Search grounding (`google_web_search`)<br>2. 1M-token native context window + packaged `gemini extensions`<br>3. Shadow-git file checkpointing (`--checkpointing` & `/restore`) | **partly** (`google_web_search`, 1M context, and extensions **yes**; interactive `/restore` picker **no**, and consumer Google OAuth was shut off June 18, 2026) |
| **Antigravity CLI (`agy`)** | 1. Multi-vendor frontier models (Gemini 4, Claude 5.5, GPT-OSS) + Planner/Executor `Orchestrator`<br>2. Native subagents, Python `run_workflow` fan-out engine & `agy plugin import claude`<br>3. Remote Control browser view (artifact review/split view) & `/browser` video subagent | **partly** (Multi-vendor models, `Orchestrator`, subagents, `run_workflow`, `/browser`, and imported plugins **yes**; Remote Control browser UI, `/swarm` board, and `mic-serve` **no**) |
| **Aider** *(2nd group)* | 1. Tree-sitter AST repo-map<br>2. Automatic Git commits per edit + any-model BYOK/local support | **yes** (Both repo-map and auto-commits work identically in `aider --message` headless mode) |
| **Factory Droid** *(2nd group)* | 1. Top-scoring "Missions" planning/verification harness on Terminal-Bench<br>2. Multi-model switching with enterprise governance | **yes** (`droid exec` runs the full harness headlessly in CI and scripts) |
| **Devin 2.0** *(2nd group)* | 1. $20/mo Pro entry plan (down from $500/mo)<br>2. Local CLI `/handoff` to autonomous Cloud VMs | **no** (Value comes from handing tasks off to Cognition's remote cloud VMs and web UI, not running as a local headless worker) |

