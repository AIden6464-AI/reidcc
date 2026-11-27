<span class="tag">extras</span>

# Proxy

::: tip
The proxy is in the source repo, not the installer. It needs Python and mitmproxy.
:::

A profile's `proxy` field runs its session through a private request proxy, to trim what's sent or to capture it. It works for Claude Code and Codex profiles; each engine has its own add-ons.

| Value | Does |
|---|---|
| `slim` | Shortens the long built-in tool descriptions the engine sends |
| `ultra` | Trims further |
| `optimize` | Rewrites requests to use fewer tokens (Claude Code only) |
| `capture` | Logs the requests, for study |

Values combine, for example `"proxy": ["slim", "capture"]`. Each session starts a hidden `mitmdump` on a free port, closed with the session, and logs to `proxy\logs\<profile>.log`.

::: warning
`slim` and `ultra` rewrite requests and can break when Claude Code or Codex updates.
:::

## Codex: measured

Real runs on 2026-11-26, codex-cli 0.172.0, default model, a one-line prompt (`Reply with just OK.`), each in a
fresh thread. Input tokens come from Codex's own `turn.completed` usage. `optimize` is Claude Code only, so it isn't here.

| Mode | Input tokens, one turn | vs none | Cached by the server | Two turns in one thread |
|---|---|---|---|---|
| none | 20,012 | | 7,552 to 15,488 | 40,716 |
| `slim` | 17,606 | −12.0% | 0 (all 7 runs) | 36,447 (−10.5%) |
| `ultra` | 17,390 | −13.1% | 0 (all 3 runs) | not measured |

`slim` and `ultra` send fewer tokens, but on a fresh thread the server cached none of the slimmed prompt, while
plain Codex reused 7.5k to 15.5k cached tokens. So a short thread can cost more uncached input with them than
without. From the second turn in a thread, `slim` was cached again (17.5k to 30.5k). `capture` alone changes
nothing sent and kept its cache.

Why: Codex sends its tools first, as input item 0, so `slim` changes the very first tokens of the prompt. The
rewrite is the same every time (17,606 tokens on every run), but plain Codex's opening is the one every other
Codex request on your account sends, so it's already in the server's cache. The slimmed opening only gets
cached once a thread has sent it. `slim` pays off on long threads, not one-shot runs.

## Setup

From the repo's `dev` branch: create `proxy\.venv` with mitmproxy, then add `proxy` to a profile in `reid.json`. See `proxy\README.md` there.
