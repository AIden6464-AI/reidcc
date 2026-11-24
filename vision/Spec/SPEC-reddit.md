# SPEC: posting Reidcc on Reddit, the right way (Claude drives the browser, Reid posts)

Status: SPEC 2026-11-23. Nothing posted. Each post goes out only on Reid's word for that post.

> "Wait can you use remote control and post on Reddit about Reidcc the right way.  Spec that" (Reid, 2026-11-23)

> "Get a better photo for the Reidcc terminal then the other fix's for the spec" (Reid, 2026-11-23, after a
> review of this spec by Gemini 4 Argon via agy; the findings that held up against the code are applied below)

"The right way" means Reddit's own norms, not a growth trick: Reid's real account, said plainly that he
built it, each subreddit's rules read and followed, one honest post at a time, and Reid in the comments.
Done any other way, a post gets removed, the account gets flagged, and Reidcc's name goes with it.

## Part 1: the rules this follows

1. **Reid's own account, nobody else's.** No alt accounts, no friends asked to upvote, no asking for votes in
   the post. Vote manipulation breaks Reddit's sitewide rules and gets accounts banned.
2. **Say who made it.** The first lines say "I built this". Undisclosed self-promotion is the main reason
   these posts get removed.
3. **Say how it was made.** Reidcc was built mostly with Claude Code. Many AI subs ask for this; others ban AI
   content. Say it either way and skip subs that don't allow it.
4. **Read the subreddit's rules on the day of posting**, since they change: the sidebar, the wiki, any pinned
   post. Check whether self-promotion is allowed, whether it goes in a weekly thread or on a certain day,
   which flair to use, and whether links or images are allowed. If a sub sends projects to a weekly thread,
   post there or skip the sub.
5. **One sub at a time, a few days apart, each post written for that sub.** Don't crosspost the same text to
   five subs in one day; that reads as spam and trips Reddit's filters.
6. **Honest about the license.** Reidcc is **source-available, free for personal use** (PolyForm
   Noncommercial 1.0.0). It is **not "open source"**, because that term means a license that allows commercial
   use. So: no r/opensource, and never call it open source.
7. **Lead with what it does; say the limits once, in one short line.**

   > "Ya but don't say the down sides over and over" (Reid, 2026-11-23)

   The post is about what Reidcc gives you. The facts a reader needs before downloading (Windows, beta, uses
   your Claude Code) go in one line near the end, said once, with no apology and no list of caveats.
8. **Give more than you take.** The guideline people cite is 90/10: mostly normal participation, a little
   self-promotion. It works best if Reid's account already takes part in the sub. A brand-new account
   posting only its own link looks like spam.
9. **Nothing private in the post.** Screenshots and GIFs use sample data only (profile `main`, folder
   `~/projects/kiln`): no Windows username, no real paths, memory or personas. No email address.

## Part 2: who does what ("remote control")

The browser is Reid's own Chrome, driven through the **Claude in Chrome** extension. Reid signs in to Reddit
himself; Claude never sees or types a password.

| Step | Who |
|---|---|
| Read the sub's rules, flair list and recent showcase posts | Claude, in a new tab |
| Write the post for that sub (title, body, flair) | Claude drafts in this spec's Part 4; Reid edits |
| Make the screenshot and GIF from sample data | Claude |
| Fill the submit form: title, body, flair, images | Claude, then stops |
| Read the filled form and press **Post** | **Reid**, always, with his own click |
| Replies to comments | Reid. When asked, Claude reads the thread and drafts replies; Reid posts them |

Claude never presses Post, comments, votes, DMs, joins subs or changes the account. Reid pressing Post himself
is simpler and leaves nothing for Reddit to read as automated.
If Reddit shows a captcha, a login or a warning, Claude stops and hands it to Reid.

## Part 3: where (check each sub's rules on the day; this list is not a promise they allow it)

| Sub | Fit | Angle |
|---|---|---|
| r/ClaudeAI | best | a launcher for Claude Code: profiles, persona, memory, usage in sight. Check its current rule and flair for projects |
| r/ClaudeCode (if it exists and allows projects) | best | same, more hands-on: profiles, `/reid`, resume |
| r/SideProject | good | the story: a solo dev's launcher, the gate opening |
| r/coolgithubprojects | good | short, link to the repo |
| r/tauri, r/rust | only as a "how I built it" post | Tauri 2 + Rust; these subs want technical detail, not an ad |
| r/opensource | **no** | the license isn't open source (rule 6) |
| r/programming | **no** | reportedly bans LLM-made content; not worth it |

Order: r/ClaudeAI first (the core users), then the others a few days apart, using what the first post's
comments taught.

## Part 4: the first post (draft, r/ClaudeAI)

**Title:** I built a Windows launcher for Claude Code and Codex: profiles for persona, model, login and memory,
with live context and usage limits in sight

(No "free" in the title: work and client use need a commercial license, so the body says "free for personal
use". No "open the gate" either: it means nothing before someone has seen the app.)

**Body:**

> I'm a solo dev and I run Claude Code all day with different setups: different personas, models, logins
> and memory. Switching meant editing configs and retyping flags, so I built **Reidcc**.
>
> **Folder. Profile. Gate.** Pick a project folder, pick a profile, press open gate. Each profile keeps its
> own model, sign-in (your subscription or an API key), persona, tools, MCP config and switches, plus a
> long-term memory file you can switch on. Sessions open in a Reidcc window (or Windows Terminal) with a bar
> showing the folder, the profile, and live context and usage-limit %. There's a window app and a terminal UI
> (`reid`); `/reid` inside a Claude session takes you back, so you can resume the same conversation with any
> profile. Codex profiles run from the same launcher, so both engines are one click apart.
>
> Free for personal use, with an installer that updates itself. Runs on Windows with your own Claude Code.
> Built mostly with Claude Code, which felt fitting.
>
> Site: https://aiden6464-ai.github.io/reidcc/ · Source: https://github.com/AIden6464-AI/reidcc
>
> I'd like to know what's confusing in the first minute, and what you'd want a profile to hold that it doesn't.

**Media:** the session window (`docs/session-window.png`: a real Claude session on the sample project, with the
context and limit meters), one screenshot of the launcher (sample data), and a short GIF of the gate opening. Video and GIF
only if the sub allows images in text posts; otherwise links.

Rewrite it for each later sub (Part 3's angle), never paste it unchanged.

## Part 5: before the first post

- Done 2026-11-23: `docs/session-window.png` (and the site's `session-window.webp`) retaken: a real Claude
  session on the sample project `E:/projects/kiln`, profile `main`, `context 5% · limit 12%` in the bar,
  plugins off for that session, no username or real paths. Made by a script that runs the app against a temp
  Reidcc folder and removes the sample folder and its transcripts after.
- Retake `docs/launcher.png` with the new tagline and sample data (SPEC-review-0.2.1.md item 4); the site's
  shot comes from it.
- Retake the settings shot (`site/public/shots/settings.webp`, from `rs/tests/gui_shots/settings.png`): it's
  from 0.2.0 (no `default size`) and lists Reid's own plugins. Take it with no personal plugins, after the
  plugins list is fixed.
- Fix the plugins list (it fails since a Claude Code update; palette §5) so a new user's settings page works.
- Ship the open review fixes worth having first (SPEC-review-0.2.1.md), as 0.2.2, so the first download is the
  best one.
- Check that the latest release downloads and installs on a clean machine or account.
- Reid checks that his account has some normal history in the sub (rule 8).

## Part 5b: parked 2026-11-23

> "Ok start the Reddit post and watch them" ... "Ok save that for later" (Reid, 2026-11-23)

Tried and stopped: the Claude in Chrome extension wasn't connected, and Reddit refuses plain downloads
(403), so the rules couldn't be read without it. Nothing filled in, nothing posted.

When Reid says go again:
1. Reid opens Chrome with Claude in Chrome connected (same account as Claude Code) and signs in to Reddit.
2. Claude reads r/ClaudeAI's rules, flair and recent project posts that day; if projects go in a weekly
   thread, post there.
3. Claude fits Part 4 to the rules, fills title, body, flair and `docs/session-window.png` only (the
   launcher and settings shots are stale, Part 5), and stops. Reid presses **Post**.
4. Watch: Claude checks the thread in the browser every 20–30 min, lists new comments and drafts
   replies; Reid posts them. Log the link in Part 6.

## Part 6: log

| Date | Sub | Link | Notes |
|---|---|---|---|
| | | | |
