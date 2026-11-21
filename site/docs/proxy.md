<span class="tag">extras</span>

# Proxy

::: tip
The proxy is in the source repo, not the installer. It needs Python and mitmproxy.
:::

A profile's `proxy` field runs its Claude Code session through a private request proxy, to trim what's sent or to capture it.

| Value | Does |
|---|---|
| `slim` | Drops parts of the request Claude Code doesn't need |
| `ultra` | Trims further |
| `optimize` | Rewrites requests to use fewer tokens |
| `capture` | Logs the requests, for study |

Values combine, for example `"proxy": ["slim", "capture"]`. Each session starts a hidden `mitmdump` on a free port, closed with the session, and logs to `proxy\logs\<profile>.log`.

::: warning
`slim` and `ultra` rewrite requests and can break when Claude Code updates.
:::

## Setup

From the repo's `dev` branch: create `proxy\.venv` with mitmproxy, then add `proxy` to a profile in `reid.json`. See `proxy\README.md` there.
