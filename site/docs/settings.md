<span class="tag">the launcher</span>

# Settings

The few things that aren't part of a profile. Open it with **settings** at the bottom of the launcher; `Esc` or **back** returns.

![The settings page](/shots/settings.webp)

| Section | What it holds |
|---|---|
| **sessions open in** | A Reidcc session window (the default), or Windows Terminal |
| **terminal colours** | Reidcc's palette (the default), or the engine's own colours untranslated. Sessions opened after a change use it |
| **default engine** | The engine a new profile starts on: `claude` or `codex` |
| **default size** | The size the launcher opens at: `main`, `medium` or `small` |
| **updates** | The version, and **check for updates**. Installed copies only |
| **locations** | Where your data, temp files and the AI's temp work live, each with **open** and **change** |
| **plugins** | Claude Code's installed plugins. Turn them on or off per profile with **tune**, or with `/plugin` in a session |

Settings save to `reid.json` (`open_in`, `colors`, `default_engine`, `start_size`) as you change them. A setting left at its default isn't written.

Settings also opens from inside a session window: click **RC** on the bar, then **settings**.
