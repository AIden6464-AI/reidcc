<span class="tag">reference</span>

# reid in a terminal

`reid` is the same launcher in a terminal. Typed with no arguments it opens the TUI; with arguments it's a command.

```text
reid                      open the Reidcc TUI (pick, edit, open gate, resume)
reid <profile> [args]     start a session with that profile; extra args go to its engine
reid -c / reid "do X"     anything that isn't a profile goes to the default profile's engine
reid --resume [profile]   continue the last session (that profile, or the one it had)
reid --resume <profile> --id ID   continue that session, in this folder
reid -l                   list profiles
reid --chat [profile]     chat with Claude Code and Codex in this folder, in the terminal
reid --stream <profile> [--read-only] [--resume ID] [--with JSON] [--switch-from P] PROMPT
                          one headless turn, its events as JSON lines
reid --version            show the Reidcc version
reid --update             install the latest Reidcc (installed copies only)
reid --dry [profile]      print what would run, don't run it
reid --dry -v [profile]   ... and the prompt and settings files it adds
reid --edit / --mem       open reid.json / the memory file
reid --tui / --gui        force the TUI or the window
```

## Inside Claude Code

| Command | Does |
|---|---|
| `/reid` | Ends the session and returns to Reidcc: the TUI in a terminal, the launcher in a session window. The conversation is kept: press `r` there to resume it, with any profile |
| `/exit` | Leaves as usual, back to your shell |

## Examples

```powershell
cd ~/projects/kiln
reid main            # start main in this folder
reid --dry review    # show the exact command review would run
reid --dry -v review # ... and the persona / memory prompt and settings it adds
reid --dry --resume  # what reid --resume would run, and in which folder
reid --resume main --verbose   # continue the last session with main; extra args go along
```

A dry run of a Codex profile writes its prompt file (`codex\prompts\<profile>.md`) and asks Codex for its
sign-in, because the prompt file's size depends on Codex's own prompt. Claude dry runs write nothing that stays.
