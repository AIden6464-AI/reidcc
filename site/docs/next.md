<span class="tag">releases</span>

# What's next

The plan after 0.2.5. Plans can change.

## 0.2.6 beta

OpenCode becomes a third engine beside Claude Code and Codex. It works the same way they do: in chat,
`reid --stream`, resume and tune, and as a turn to switch to or from through `.reid/handoff.md`.

Switching engines becomes a full context switch. Today `.reid/handoff.md` carries the changed files and
the diff stat. In 0.2.6 the next engine gets the conversation so far as well.

## 0.2.7

Cleanup under the hood: one engine interface for all three, a typed profile model, and the old Python copy
and the tracked test screenshots retired. Nothing changes in how you use Reidcc.

## 0.3.0

Planned.

---

What each release changed: [changelog](/changelog).
