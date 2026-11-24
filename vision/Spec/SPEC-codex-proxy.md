# Spec: the proxy for Codex profiles

Status: **BUILT 2026-11-23** (both build steps; see "As built" at the end). Follows `SPEC-proxy.md`
(Claude's proxy, built) and `SPEC-codex-signin-persona.md` (built).

> "All of the build proxy's for Claude code that's in Reidcc needs to be ported/updated support for codex"
> (Reid, 2026-11-23)

> "persona's don't work? what man" (Reid, 2026-11-19, on his `claude` profile: engine codex, memory on,
> `proxy: capture`, refused with `Codex can't use the proxy.`)
>
> "ok spec doc proxys for codex that fit the idea of the claude" (Reid, 2026-11-19)

## The idea, same as Claude's

Claude's proxy is one field on the profile: pick `slim`, `ultra`, `optimize` or `capture`. Reidcc starts a
private mitmproxy for that one session, points Claude at it, and stops it when the session ends. No second
window, no ports. Codex gets the same field, the same picker, the same lifecycle and the same log, with
add-ons written for Codex's traffic:

| Choice | Claude | Codex |
|---|---|---|
| `capture` | saves each distinct prompt setup to `proxy\claude_prompts\` | saves each distinct prompt setup to `proxy\codex_prompts\` |
| `slim` | short descriptions for Claude Code's built-in tools | short descriptions for Codex's built-in tools |
| `ultra` | `slim`, terser, more tools | `slim`, terser, more tools |
| `slim+capture`, `ultra+capture` | both | both |
| `optimize` | reorders the request for Anthropic's prompt cache | **not offered.** Codex's cache works differently (below). |
| `proxy_drop` | removes whole tools | removes whole tools or whole tool namespaces |

Reid's `claude` profile (`proxy: capture`) launches as it is once this is built.

## What Codex 0.170.0 sends (measured 2026-11-19)

Measured through a private mitmdump with a logging add-on that records only methods, hosts, paths,
sizes, JSON keys and message types (no headers, no prompt text): `codex doctor --network-only`, then two
throwaway `codex exec --ephemeral -s read-only` runs ("reply ok", and one `echo hi` tool call).

- **Proxy and CA:** Codex honours `HTTPS_PROXY` / `NO_PROXY` and trusts an extra CA from
  `CODEX_CA_CERTIFICATE` (or `SSL_CERT_FILE`). With `CODEX_CA_CERTIFICATE=~\.mitmproxy\mitmproxy-ca-cert.pem`,
  doctor passes (4 ok) and every request goes through mitmdump.
- **The model call is a WebSocket**, not an HTTP POST: `GET chatgpt.com/backend-api/codex/responses`
  upgraded to `101`. Each request is one client text message `{"type": "response.create", ...}`.
  The answer streams back as server messages (`response.created`, `response.output_text.delta`,
  `response.completed` with usage, `codex.rate_limits`). With an API key the host is
  `api.openai.com/v1/responses`.
- **No top-level `instructions` or `tools`.** In a `response.create`, the `input` list holds everything:

  | input item | size | what |
  |---|---|---|
  | `additional_tools` (role developer) | 48.5 KB | the tools, in 4 namespaces: `functions` 35.5 KB, `mcp__cua_repl` 6.7 KB, `collaboration` 5.6 KB, `clock` 0.5 KB |
  | `message` developer | 28.4 KB | Codex's own prompt ("You are Codex…"), or the persona file in replace mode |
  | `message` developer ×3 | 10.9 KB, 2.6 KB, 0.7 KB | permissions, collaboration mode, other `<…>` blocks |
  | `message` user | 1.0 KB | `<environment_context>`, AGENTS.md |
  | `message` user | — | what you typed |

- **Only the first request carries the setup.** Codex first sends warm-up messages (`"generate"` set,
  empty `input`, one for the model and one for `codex-auto-review`). The real request names the warm-up in
  `previous_response_id`. After a tool call, the next request carried **only** the new item
  (`custom_tool_call_output`) plus `previous_response_id`: the server keeps the rest for that connection
  (`store: false`, `reasoning.context: "all_turns"`).
- **Other traffic through the same proxy:** `codex/models`, plugin and MCP listings (`ps/…`), account and
  settings checks (`wham/…`), `codex/analytics-events/events` and `ab.chatgpt.com/otlp/v1/metrics`.
  The add-ons pass all of it through untouched.

## Lifecycle: Claude's, unchanged

Everything in "Proxy lifecycle" of `SPEC-proxy.md` holds for Codex. One mitmdump per session from
`proxy\.venv`, a free port, hidden, logging to `proxy\logs\<profile>.log`, killed with the session
(job object), the 15 s start-up wait, and no Codex launch if the proxy doesn't come up. The launch banner
shows `proxy capture on 127.0.0.1:<port> · log proxy/logs/<profile>.log` the same way.

Only the environment differs:

| Claude gets | Codex gets |
|---|---|
| `HTTPS_PROXY=http://127.0.0.1:<port>` | the same |
| `NODE_EXTRA_CA_CERTS=~\.mitmproxy\mitmproxy-ca-cert.pem` | `CODEX_CA_CERTIFICATE=` the same file |
| `NO_PROXY=localhost,127.0.0.1,::1` | the same, so LM Studio / Ollama provider files on localhost go direct |

**The proxy needs embedded mode.** Without any `-c`, Codex may hand the session to its shared background
server, a separate long-running process that doesn't have the proxy's environment. Every Reidcc Codex launch
already runs embedded, because the tab title (`-c tui.terminal_title=[]`) is always passed. A Codex profile
with a proxy keeps at least one `-c` even if the status line and title are ever made optional.

## The add-ons

New files next to Claude's. Claude's add-ons don't change, so Claude profiles stay byte-identical.

**Only Codex's model endpoints are modified:** client WebSocket messages of type `response.create` on
`chatgpt.com/backend-api/codex/responses` and `api.openai.com/v1/responses`. Codex can fall back to plain
HTTP, so a JSON `POST` with the same body on those paths is handled the same way. Provider files that point
somewhere else pass through unmodified, like Claude's relay profiles.

### `capture` → `proxy\codex_capture_addon.py`

Read-only, like `capture_addon.py`. For each `response.create` that carries the setup (an
`additional_tools` item), it saves one folder per distinct setup:
`proxy\codex_prompts\<time>_<model>_<hash>\`

| file | holds |
|---|---|
| `instructions.txt` | the developer messages, in order, verbatim (Codex's prompt or the persona, permissions, mode blocks) |
| `tools.json` | the `additional_tools` item, verbatim |
| `context.txt` | the user messages Codex injected (`<environment_context>`, AGENTS.md) |
| `messages.json` | the whole `input` verbatim, including what you typed in that request (local file only) |
| `summary.md` | size per part in characters, and tokens from that response's `response.completed` usage |

- The hash covers the developer messages + tools + context, so an identical setup isn't saved twice (the same
  rule as Claude's capture).
- Warm-ups (empty `input`) and follow-up deltas (no `additional_tools`) aren't saved.
- Never saved: headers (auth tokens), server messages other than the usage numbers.

### `slim` / `ultra` → `proxy\codex_slim_addon.py`

Same rules as `slim_tools_addon.py`:
- Inside `additional_tools`, replace the long descriptions of the tools it knows with short ones. Tool names,
  namespaces, parameter names, types, required fields and every other key stay exactly as sent, so Codex
  still runs its own tools.
- Tools and namespaces it doesn't list (MCP tools, anything a future Codex adds) pass through unchanged.
- `SLIM_LEVEL=ultra` adds terser text and covers more tools.
- `proxy_drop` (`SLIM_DROP`) removes whole tools by name, or a whole namespace (e.g. `mcp__cua_repl`,
  `collaboration`).
- The rewrite is deterministic: the same input always gives the same bytes, so the server's prompt cache still
  hits across sessions.
- It rewrites only the setup-carrying request. Follow-up deltas refer to what the server already holds, so they
  need nothing.
- The short descriptions are written from a `capture` of the real tools, the same way Claude's were. That's
  build step 2, after capture exists.

### Why no `optimize`

Claude's optimizer reorders `/v1/messages` bodies so Anthropic's cache prefix lines up. Codex already sends a
stable prefix with `prompt_cache_key`, and after the first request it sends only deltas against server-held
state, so there's nothing to reorder. Picking `optimize` on a Codex profile is refused:
`optimize is Claude's. Pick slim, ultra or capture for Codex.`

## Screens and words

- The `proxy` row goes live on a Codex profile. Its list is Codex's own: `off`, `slim`, `ultra`, `capture`,
  `slim+capture`, `ultra+capture`. The TUI editor uses the same list.
- The greyed set on a Codex profile shrinks to `tools`, `mcp` and the switches. The tag
  `CODEX · GREYED FIELDS ARE CLAUDE'S` stays.
- The command preview reads `via proxy capture · codex …`, as it does for Claude.
- Switching a profile's engine keeps `capture`, `slim` and `ultra`. It clears `optimize` when switching to
  Codex: `Engine is now codex. Model and sign-in reset to its defaults; optimize is Claude's, so the proxy is off.`

## Build order

1. Lifecycle + env + `capture` (read-only, low risk). Reid's `claude` profile launches.
2. `slim` / `ultra` from a real capture of Codex's tools.

## Acceptance checks

1. A Codex profile with `proxy: capture` starts mitmdump on a free port. Codex runs with `HTTPS_PROXY`,
   `CODEX_CA_CERTIFICATE` and `NO_PROXY`, and with no TLS errors. Quitting Codex stops the proxy, and so does
   closing the terminal (no orphan mitmdump).
2. One prompt in Reidcc's Codex TUI saves exactly one folder in `proxy\codex_prompts\`, with all five files.
   A second identical session saves nothing new. A persona change saves a new folder.
3. The capture is byte-identical to what Codex sent: `instructions.txt` contains the persona file from
   `codex\prompts\<profile>.md`, and `tools.json` parses to the same JSON as the item in flight.
4. No auth header or token appears in any saved file or in the log.
5. `slim`: Codex still calls `shell` / `apply_patch` normally. Tool names and schemas are identical before and
   after, only descriptions shrink. The same input gives the same bytes on two runs. `proxy_drop` of a
   namespace removes it.
6. A provider file on `localhost` (LM Studio) never touches the proxy. A remote provider passes through
   unmodified.
7. `optimize` on a Codex profile is refused with the message above, before the proxy starts.
8. Claude profiles: `--dry` is byte-identical to the build before this change, and `proxy\tests` still pass.
9. Reid's `claude` profile (codex, memory, `proxy: capture`) launches with its memory and saves its capture.

## Risks

- **Unsupported, like Claude's slim:** `slim` / `ultra` rewrite requests to ChatGPT's backend. A Codex update
  can change the message shape (it already moved tools from `tools` into `additional_tools`). The add-ons then
  pass anything they don't recognise through unchanged, and `capture` shows what changed.
- **Shell commands inherit the proxy.** Commands Codex runs (git, npm, curl) see `HTTPS_PROXY` too, and tools
  that don't trust mitmproxy's CA fail TLS through it. Claude's proxy has the same exposure. To check at build:
  whether Codex's `shell_environment_policy` passes the variables on, and if it does, keep them out of the
  shell environment.
- **WebSocket compression:** the logging add-on read the messages as plain text through mitmproxy. Rewriting
  them is the step to prove first in build step 2.

## Not in this spec

- Blocking Codex's analytics or metrics (`analytics-events`, `ab.chatgpt.com`): a different idea from Claude's
  proxy. Ask first.
- A long-lived shared proxy (per-session, like Claude).
- Routing the Codex desktop app.

## As built (2026-11-23)

- **Core** (`rs/core/src/proxy.rs`): `CODEX_ADDONS` (slim/ultra → `codex_slim_addon.py`, capture →
  `codex_capture_addon.py`) picked by engine; `choices(codex)` gives each picker its own list; `optimize` on a
  Codex profile is refused with `optimize is Claude's. Pick slim, ultra or capture for Codex.`;
  `drop_optimize` runs when a profile switches to Codex. `env()` gives Codex `CODEX_CA_CERTIFICATE`, Claude keeps
  `NODE_EXTRA_CA_CERTS`. `proxy` is no longer in `CLAUDE_ONLY`.
- **Screens:** the proxy row is live on Codex profiles in the GUI and TUI, with Codex's list (no optimize).
  Switching to Codex with optimize on says `... optimize is Claude's, so it's off.`
- **The exec tool.** Codex 0.170.0 puts most of its tool docs in one place: `functions.exec`'s description
  (28,887 chars), a "### `name`" section per nested tool, each ending in an `exec tool declaration:` TypeScript
  block. Slim replaces only the prose of listed sections (web__run, update_goal, image_gen, create_goal,
  request_plugin_install, the MCP resource listers; ultra adds exec_command, write_stdin, read_mcp_resource,
  view_image) and keeps every declaration byte for byte. The rules in the prose are kept, shorter (exec_command's
  Windows safety rules, web__run's browse/citation/quote limits). `collaboration.spawn_agent` is left whole: its
  model list changes with the account.
- **Measured** (Codex 0.170.0, `codex exec "reply ok"`): tools 48,493 → 36,782 chars (slim), 35,544 (ultra);
  input 19,013 → 16,612 tokens. A shell + `apply_patch` task through `ultra` worked, and the proxy stopped with the
  session. WebSocket rewriting through mitmproxy works as is (the compression risk didn't bite).
- **Checks:** `proxy\tests\test_codex_addons.py` (names, schemas and declarations unchanged, deterministic,
  deltas untouched, drop by namespace or tool, one capture folder per setup, id-insensitive hash);
  proxy tests 87 passed, 2 xfailed. Parity against the Python app, where every difference is this change on purpose:
  CLI 151/154 + 2 known (Codex+proxy no longer refused); TUI 30/48, the other 18 differ only in the proxy row
  (live, not greyed) and the refusal wording, now listed in `KNOWN`; GUI 162/175 reid.json identical, the other 13
  all `optimize+capture` → `capture` after switching a profile to Codex (the GUI suite has no `KNOWN`, it reports). Captures go to `proxy\codex_prompts\` (gitignored).
- **Not done:** the `shell_environment_policy` check (risk above): commands Codex runs still inherit
  `HTTPS_PROXY`, the same exposure as Claude's proxy. The Python app still refuses a proxy on Codex.
