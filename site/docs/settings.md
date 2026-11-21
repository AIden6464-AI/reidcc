<span class="tag">the launcher</span>

# Settings

The few things that aren't part of a profile. Open it with **settings** at the bottom of the launcher; `Esc` or **back** returns.

![The settings page](/shots/settings.webp)

| Section | What it holds |
|---|---|
| **sessions open in** | A Reidcc session window (the default), or Windows Terminal |
| **default engine** | The engine a new profile starts on: `claude` or `codex` |
| **updates** | The version, and **check for updates**. Installed copies only |
| **plugins** | Claude Code's installed plugins. Turn them on or off with `/plugin` in a session |
| **locations** | Where your data, temp files and the AI's temp work live, each with **open** |

Settings save to `reid.json` (`open_in`, `default_engine`) as you change them. A setting left at its default isn't written.
