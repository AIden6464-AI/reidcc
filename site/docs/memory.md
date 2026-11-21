<span class="tag">the launcher</span>

# Memory

Memory is what sessions remember from before: one Markdown file of pinned facts and a dated journal, added to every session whose profile has memory on.

## The file

It's `reidcc_memory.md` in your Reidcc folder, made the first time a profile with memory starts:

```md
# Long-term memory

## Pinned facts
- The kiln project builds with `cargo build`; tests live in `tests/`.

## Journal
- 2026-11-20 - memory init
```

The session is told where the file is, and adds to it with its file tools when you ask it to remember something: facts under `## Pinned facts`, dated one-liners under `## Journal`. You can edit it by hand at any time (**open memory** in the launcher, or `reid --mem`).

## Turning it on

Switch **memory** on in a profile. In `reid.json`: `"memory": true`.

## Size

Memory is sent with every request, so it's kept to 6,000 characters. When the file is longer, the pinned facts are kept and the oldest journal lines are left out. A profile can set its own limit with `"memory_limit"`, or read a different file with `"memory_file"`.
