# Ads: one post per subreddit

> "Is vision make a /ads and make .md for each subreddit" (Reid, 2026-11-24)

One file per subreddit, each with the post written for that sub. The rules for all of them are in
`vision\Spec\SPEC-reddit.md` Part 1 (say "I built this", say it was made with Claude Code, never call it open
source, the limits said once, one sub at a time a few days apart, nothing private in the media).

## Who posts

> "Na you post" (Reid, 2026-11-24, while away from his PC)

Claude may press Post now, but only after Reid has read the exact title, body and media on his phone and said
yes to that post. Claude still never votes, DMs, or comments without the same yes per comment.

## Order and status

| # | Sub | File | Rules read | Can post now? |
|---|---|---|---|---|
| 1 | r/ClaudeAI | [claudeai.md](claudeai.md) | **yes, 2026-11-24** | **no**: feed posts need more than 100 karma; the account has 3 |
| 2 | r/ClaudeCode | [claudecode.md](claudecode.md) | not yet | check karma and project rules |
| 3 | r/SideProject | [sideproject.md](sideproject.md) | not yet | likely; check |
| 4 | r/ChatGPTCoding | [chatgptcoding.md](chatgptcoding.md) | not yet | check |
| 5 | r/vibecoding | [vibecoding.md](vibecoding.md) | not yet | check |
| 6 | r/coolgithubprojects | [coolgithubprojects.md](coolgithubprojects.md) | not yet | check |
| 7 | r/tauri | [tauri.md](tauri.md) | not yet | "how I built it" only |
| 8 | r/rust | [rust.md](rust.md) | not yet | "how I built it" only; strict about self-promotion |

Not these: r/opensource (the license isn't open source), r/programming (bans LLM-made content).

## The account (u/Severe_Jackfruit_447, checked 2026-11-24)

- 3 karma, 1 year old, 14 contributions. Too low for r/ClaudeAI (100+) and likely for other big subs' filters.
- Public comments in r/Piracy and a free-Plex thread sit on the profile. Hide them ("Curate your profile") or
  post from a cleaner account before any of these go up.
- Display name won't save (fails on PC and phone, 2026-11-24); "Confirm your age" is pending on the account.

Building karma first: answer Claude Code questions in r/ClaudeAI and r/ClaudeCode for a while (real answers,
no links). That's also SPEC-reddit rule 8.

## Rewrites

> "Run each of thos Md though argon to wright the .mds" (Reid, 2026-11-24)

All 8 posts were rewritten by Gemini 4 Argon (`gemini-4-argon-high`, via agy) on 2026-11-24, using only facts
already in the drafts. Claude checked them: no new claims, no "open source", links unchanged; one line in
claudeai.md was corrected (Argon described the spec quotes as screen wording).

## Each file has

Rules (as read, with the date), the angle, title, body, media, and a checklist. Media is sample data only:
`docs/session-window.png` is ready; the launcher and settings shots are stale (SPEC-reddit Part 5).
