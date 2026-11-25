<span class="tag">reference</span>

# reid in a terminal

`reid` is the same launcher in a terminal. Typed with no arguments it opens the TUI; with arguments it's a command.

```text
reid                      open the Reidcc TUI (pick, edit, open gate, resume)
reid <profile> [args]     start a session with that profile; extra args go to its engine
reid -c / reid "do X"     anything that isn't a profile goes to the default profile's engine
reid --resume [profile]   continue the last session, with that profile or the one it had
reid -l                   list profiles
reid --version            show the Reidcc version
reid --update             install the latest Reidcc (installed copies only)
reid --dry [profile]      print what would run, don't run it
reid --edit / --mem       open reid.json / the memory file
reid --tui / --gui        force the TUI or the window
```

## Inside Claude Code

| Command | Does |
|---|---|
| `/reid` | Ends the session and returns to the TUI. The conversation is kept: press `r` there to resume it, with any profile |
| `/exit` | Leaves as usual, back to your shell |

## Examples

```powershell
cd ~/projects/kiln
reid main            # start main in this folder
reid --dry review    # show the exact command review would run
```
