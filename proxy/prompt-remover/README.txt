Claude System Prompt Remover
============================

Starts Claude Code with its built-in system prompt replaced by one line
("You are a helpful assistant.") and with all tools turned off: no file
access, no shell, no MCP servers, no Claude in Chrome.

You get a plain chat with Claude in your terminal that uses far fewer tokens
per message (about 570 instead of about 25,000).

It uses only official Claude Code command-line flags. It does not modify
Claude Code, intercept traffic, or need a proxy.


REQUIREMENTS
------------
- Claude Code installed, with the `claude` command working in a terminal.
  Install guide: https://docs.claude.com/en/docs/claude-code/setup
- Logged in, either with a Claude subscription or an API key. Run `claude`
  once on its own first if you never have.
- Tested with Claude Code 2.1.325. Older versions may not support the
  --tools or --no-chrome flags; run `claude update` if you get an
  "unknown option" error.


HOW TO USE
----------
Windows:
  - Double-click claude-stripped.cmd, or
  - In a terminal opened in this folder, run:
        Command Prompt:  claude-stripped
        PowerShell:      .\claude-stripped.cmd

macOS / Linux, in a terminal opened in this folder:
    chmod +x claude-stripped.sh     (only needed once)
    ./claude-stripped.sh

To use it from any folder, copy the script into a folder that is on your PATH.


EXTRA OPTIONS
-------------
Anything you type after the script name goes to Claude Code. Examples:

    claude-stripped --model sonnet            use a different model
    claude-stripped -p "Explain recursion"    ask one question, print the answer, exit
    claude-stripped --continue                resume your last conversation


CHANGING THE REPLACEMENT PROMPT
-------------------------------
Open the script in a text editor and change the text after --system-prompt.
For example:

    --system-prompt "You are a concise expert programmer."


GOOD TO KNOW
------------
- Because all tools are off, Claude cannot read or change your files or run
  commands. It can only chat. That is the point, but paste in any code or
  text you want it to see.
- Your normal `claude` command is unchanged. This script affects only the
  session it starts.
