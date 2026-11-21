<span class="tag">reference</span>

# Troubleshooting

## "Can't find Claude Code"

Reidcc runs the `claude` on your PATH. Check `claude --version` in a new terminal. If Claude Code is updating itself, this clears in a moment.

## A file is "missing"

A profile's summary says `(missing)` when its persona or sign-in file isn't there. Paths are relative to your Reidcc folder; fix the field, or put the file back.

## "isn't valid JSON"

A sign-in file or `reid.json` has a typo. The message names the file. Fix it and try again.

## Windows protected your PC

The installer isn't code-signed yet. Click *More info*, then *Run anyway*.

## The session failed

The session window says `failed · code N`; the engine's own output above it says why. Any key closes the window.

## Still stuck

Open an issue on [GitHub](https://github.com/AIden6464-AI/reidcc/issues) with what you did and what you saw. Leave out keys and personal paths.
