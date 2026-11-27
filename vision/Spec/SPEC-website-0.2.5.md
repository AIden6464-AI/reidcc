# SPEC: the website for 0.2.5 (landing page, changelog, shots)

Status: built on dev, not published (Rev 2 2026-11-27: decisions, roadmap, as built). Rev 1 2026-11-27. Updates the site that `SPEC-github-pages.md` built.

Asked by Reid 2026-11-27:
> "Well ok spec doc a update to the Website and pull for other website for details"

## The idea in one line
The site still describes 0.2.1: folder → profile → gate. 0.2.5 adds chat, tune, one window, four sizes
and Codex parity. The docs already cover all of it, but the landing page shows none of it, and
`changelog` sends you to GitHub. Add three things: one section per new feature, a real changelog page,
and fresh shots.

---

## Part 0: what's there now (read 2026-11-27)

| Part | Now | 0.2.5 needs |
|---|---|---|
| Hero | `Folder. Profile. Gate.` + "A launcher for Claude Code and Codex…" | keep as is |
| the flow | 01 folder · 02 profile · 03 open gate | keep; add `open chat` beside 03 |
| every session | context / limit meter | keep; show RC beside |
| yours | profile · persona · memory | keep |
| chat | **missing** | new section (Part 2.2) |
| tune | **missing** | inside the chat section |
| sizes / one window | **missing** | new strip (Part 2.3) |
| what's new | **missing** | one line under the hero (Part 2.1) |
| changelog | nav links to GitHub releases | its own page, built from `CHANGELOG.md` (Part 3) |
| shots | `launcher.webp`, `session-window.webp`, `settings.webp` (Nov 21–25) | retake + 4 new (Part 4) |
| docs | 18 pages, all 0.2.5 features covered (chat, tune, RC, rigs, pod, `--stream`, `/quit`, slim) | no new pages; Part 6 |

First load is 391 KB of a 700 KB budget (SPEC-github-pages). There is room, but only below the fold.

---

## Part 1: what other sites do (read 2026-11-27)

| Site | What it does | Take | Leave |
|---|---|---|---|
| **Conductor** (conductor.build): Claude Code + Codex agents in parallel, the closest product | Name, one line, two sentences, then `Docs · Changelog · Blog` and **"See what's new in 0.101.0: /changelog"**. No media. Changelog: one page per release, `version: title — date` | the what's-new line, read from the version at build time; a short title per release | a page with no shots (we sell a look) |
| **OpenCode** (opencode.ai): one agent over 200+ providers | Hero, product cards (desktop / terminal / mobile / SDK), a grid of 10 one-line feature cards, 3 numbered get-started steps, changelog link in the nav and the footer | **one-line feature cards** for the small features (tune, rigs, `--stream`); the changelog in the footer too | trust counters ("22M+ developers"), star counts, contributor wall, 18 languages, pricing |
| **Warp** (warp.dev): "any agent, any model" | A live roster shows several agents at once, labelled by model and harness (`Opus with Claude Code`, `GPT 5.2 Codex`), each with a status | label each engine the way the app does: `main · claude ›`, `cx · codex ›`, and show both in one shot | factory/enterprise copy, logo bars, FAQ, sales CTA, live status badge |
| **Zed** (zed.dev/releases): weekly releases | Releases page: month heading, version + date, an optional intro paragraph, then **Features** (grouped by area) / **Bug Fixes** / **Breaking Changes**, one bullet per change | the page shape: version + date, `###` areas as they are in CHANGELOG.md, newest first, one bullet per change | PR links and per-release download buttons (one installer, linked once) |

Ghostty (ghostty.org) didn't come through the fetch, so it isn't used.

**What all four share:** the changelog sits one click from the home page, and each release reads in one
screen. None of them puts a changelog on the landing page itself; a single "what's new" line points to it.

---

## Part 2: the landing page

Order after the change: hero → what's new line → the flow → **one chat** → every session → **four sizes**
→ yours → download → footer. The new sections reuse the existing section markup and tokens in `Home.vue`
and `home.css`. Motion and reveals stay as they are (Part 2b of SPEC-github-pages).

### 2.1 What's new (Conductor)
One mono line under the hero's buttons, read at build time like the version tag:

> `0.2.5 beta · one chat over Claude Code and Codex ›` → `/changelog`

The text after the version is the release's title (Part 3). When a release has no title, the line reads
only `0.2.5 beta · what's new ›`.

### 2.2 One chat (new section, after the flow)
- Kicker: `chat`
- Heading: **One chat over Claude Code and Codex.**
- Body: Each turn streams its text and tool lines. After a turn that edits files, you see which files
  changed, and each one opens to its diff. Pick the other engine and it picks up from a handoff.
- Shot: `chat.webp`. The chat window after a Claude turn that wrote a file: a streamed reply, a folded
  `ran N commands ›` line, the **changed** block, and the composer reading `edits · no shell`. The
  profile labels read `main · claude ›` (Warp's engine labels).
- Three one-line cards under the shot (OpenCode's cards):
  - `switch → codex`: the next turn gets `.reid/handoff.md`: changed files and the diff stat.
  - `read-only`: each engine's own guards. Claude loses its write tools and every MCP tool.
  - `tune`: effort, servers and plugins for this chat only. Or type `/effort high`.
- Under the cards, in mono: `c` in the TUI, or `reid --chat`.

The voice guide allows "which files changed" in the pitch once Reidcc shows it. The chat shows it now, so
the voice guide's short pitch gains it in the same change (Part 5).

### 2.3 Four sizes (new strip, after every session)
- Kicker: `one window`
- Heading: **One launcher, four sizes.**
- Four thumbnails in a row, two by two at 390px: **main** `Alt+1` · **medium** (drag it narrow) ·
  **small** `Alt+2` · **pod** `Alt+3`.
- One line under them: Click **RC** on a session window and the launcher opens beside it. Again: full.
  Again: closed.
- Shots: `size-main.webp`, `size-medium.webp`, `size-small.webp`, `size-pod.webp`, cut to the window, 480px wide.

### 2.4 Kept as they are
The hero, the flow (its step 03 gains `or open chat` in its small line), every session, yours, download
(still decided at build time from the latest release) and the footer (gains `changelog` → the new page).

---

## Part 3: a changelog page (Zed, Conductor)

- **One source:** `site/.vitepress/config.ts` reads `../../CHANGELOG.md` at build time, the way it reads
  `rs/Cargo.toml`. A new `site/changelog.md` renders it. Nothing is typed twice, so the page can't go stale
  (the truth rule).
- **Heading per release:** `## 0.2.5 beta · 2026-11-xx: one chat over Claude Code and Codex`. The date
  and title go into `CHANGELOG.md` by hand at publish time. A release without them shows just the version.
- **Inside a release:** the `###` areas CHANGELOG.md already has (Chat, Tune, One window, Launcher,
  Engines, Fixes) and one bullet per change, as Zed does. No PR links.
- **Nav:** `changelog` → `/changelog` (was GitHub releases). The page ends with `every release on GitHub ›`.
- **Search:** the page is in local search like the docs.

---

## Part 4: shots

| File | Shows | Width |
|---|---|---|
| `launcher.webp` | retake: main with `open chat` beside resume and **tune** beside the model | 1120 |
| `session-window.webp` | retake: a session window with the launcher docked beside it (RC) | 1120 |
| `settings.webp` | retake: terminal colours, the **change** buttons | 1120 |
| `chat.webp` | new: Part 2.2 | 1120 |
| `size-main/medium/small/pod.webp` | new: Part 2.3 | 480 |

- **Clean capture:** a temp `REIDCC_HOME` with demo profiles `main` (claude) and `cx` (codex), a demo
  folder `~/kiln` (the name the site already uses) and no real sessions. Test names like `m2cl`, real
  paths, account emails and Reid's personas never appear. The test galleries (`rs/tests/*_shots`, the
  2026-11-27 gallery) are the reference for framing only; nothing is copied from them.
- WebP at quality 80, `loading="lazy"` on everything below the hero. Budget: first load stays under
  **700 KB** (it's 391 KB now; the new shots load after it).
- A capture script beside `make_assets.py --site` makes them again for the next release. The capture
  backs up `rs/tests/*_shots` first.

---

## Part 5: copy

- **Tagline unchanged:** Folder. Profile. Gate.
- **Short pitch** (`reidcc-voice.md` §1, README, about screen) gains one sentence: *"In a chat, Claude Code
  and Codex share one composer, and you see which files each turn changed."* "Paste screenshots straight
  in" stays out until Reidcc shows it.
- Every new line follows the voice guide: plain words, numbers not adjectives, keys in mono. No
  "seamless", "powerful" or "AI-powered".
- The proxy's numbers (slim −12%, ultra −13% input tokens on Codex, with no cache on a fresh slimmed
  thread) stay on the proxy page. They come with a caveat, so they don't go on the landing page.

---

## Part 6: docs

No new pages: the sidebar covers 0.2.5. Two touch-ups:
- `install.md` and `first-session.md`: one line each, "open chat sits beside resume", with a link to `chat`.
- `updates.md`: link the new changelog page.

---

## Part 7: left out (from Part 1)
Trust counters, star counts, logo bars, contributor walls, pricing, FAQ, a live status badge, language
selection, mobile, a demo video (it would blow the budget; the gate animation already moves), PR links,
and per-release downloads.

---

## Part 8: done when
1. `npm run build` in `site\` is clean. The home page, `/changelog` and every doc page render.
2. First load ≤ 700 KB, measured as in SPEC-github-pages. 390px: no sideways scroll. Reduced motion: no
   hidden content.
3. The what's-new line and the changelog's top entry match `rs/Cargo.toml`'s version.
4. `dist\` scanned clean for personal paths, emails, keys and test profile names (`m2cl`, `m2cx`).
5. Every link works, including `/changelog` from the what's-new line.
6. Shots of the built pages at 1440 and 390, put in `vision/Spec/website-0.2.5/` for Reid.

## Part 9: going live
The site deploys from main (`pages.yml` after `publish main`), so none of this is public until Reid
publishes 0.2.5. Build it on dev, check it locally (`npm run preview`), and it goes out with the release.

## Decisions (Reid, 2026-11-27)
> "All three choices are approved: 1. Release title: 'one chat over Claude Code and Codex' 2. Release
> date: set in CHANGELOG.md on publish day. 3. Section order: chat before sizes."

1. Release title: **one chat over Claude Code and Codex**. It's in CHANGELOG.md's heading now.
2. Release date: added on publish day, as `## 0.2.5 beta · YYYY-MM-DD: one chat over Claude Code and Codex`.
   config.ts reads the heading with or without it.
3. Section order: chat first, then every session, then four sizes.

## Part 10: after 0.2.5 (roadmap)
Asked by Reid 2026-11-27:
> "Also record the post-0.2.5 roadmap in the spec (and add a short, plain Next / Roadmap note on the docs
> or bottom of the site—zero hype, no dates)"

| Release | What | On the site |
|---|---|---|
| 0.2.6 beta | OpenCode as a third native engine, wired into chat, `--stream`, resume, tune and `.reid/handoff.md` switching, the same as Claude Code and Codex. **And** the switch becomes a full context switch (Reid, 2026-11-27: "The handoff.md that's not a full context switch this is 02.6"): today the handoff carries only folder, from, `git status`, diff stat, tests and note (`rs/core/src/handoff.rs`), none of the conversation | `docs/next.md`, two paragraphs |
| 0.2.7 | Cleanup under the hood: a symmetric Engine trait, a typed Profile model, retiring the legacy `python/` parity code and the tracked test shots | `docs/next.md`, two lines; not on the landing page |
| 0.3.0 | The next major milestone, not announced | `docs/next.md` says only `Planned.` |

The page is `site/docs/next.md` ("what's next"), linked from the sidebar's **releases** group, the changelog
page and the landing page's footer. No dates, no adjectives. It says plans can change.

## As built (2026-11-27, on dev, not published)
- **Shots** (`site/public/shots/`, 185 KB in all):
  - `launcher` 1000×916, `settings` 1000×652 (cut above the plugins row so no plugin list shows),
    `chat` 1120×720, `session-window` 1000×514.
  - `beside` 1120×384 (new).
  - `size-main` 500×458, `size-medium` 250×418, `size-small` 190×218, `size-pod` 184×56.
- **Session shot:** `session-window.webp` stays a plain session window. The RC-beside view is its own
  shot, `beside.webp`, under the four sizes, captioned by the RC line.
- **Sizes:** shot at half their real pixels, so the four stay to scale. At 390px they keep the same
  scale: main and medium fill the first row.
- **Chat fold:** the shot's fold reads `4 tool calls ›`, because the turn mixed reads and a write. The app
  says `ran N commands ›` only when every line is a shell call. CHANGELOG.md now names both.
- **What's-new link:** goes to `/changelog` with no anchor. VitePress makes the anchor from the whole
  heading, so an anchor would break whenever a title or date is added.
- **Footer:** docs · changelog · what's next · github · license.
- **Capture script:** `rs/tests/site_shots.py`, not beside `make_assets.py`. It does the following:
  - makes the demo project in `E:\projects\kiln` and empties it again afterwards;
  - uses a fixed temp home at `%TEMP%\reidcc-demo`;
  - shows the title as an installed copy would (no `dev`);
  - removes the inherited `CLAUDE_CODE_*` variables;
  - for the session shot only, runs `main` with `--setting-sources project,local --permission-mode default`,
    so no user plugins, hooks or auto-mode dialog show;
  - deletes the demo session files it made.
  
  Its supporting change: `guihome.Tauri` takes `cwd`.
- **Measured:**
  - first load: 281 KB at 1440 and 242 KB at 390;
  - after load: the gate frames, as before;
  - no sideways scroll at 390;
  - nothing hidden under reduced motion;
  - 37 internal links resolve;
  - `dist\` is clean of personal paths, emails, keys and `m2cl`/`m2cx`.
  
  Page shots are in `website-0.2.5/`.
- **The hand first** (Reid, 2026-11-27: "Make the hand like thoughting the house be on the first page with
  its animation then the gate one"):
  - The hero plays medium's emblem opening (the hand grows, leaves, emerald ignites, zoom to dark, ~2.5s at
    the app's PACE), then the gate rises and ignites as before. Scrolling still opens the gate.
  - The frames are `site/public/frames/e{r,g,l,i,o}NN.webp`: 71 frames, 640×563 (cut to the gate's ratio),
    1.9 MB. They load after the page's load event; only `er00` is in the first load, which is now 235 KB.
  - Reduced motion skips the hand.
  - `make_assets.py --site` makes them and no longer overwrites the shots.
- **Not done (Part 5):** the short-pitch sentence. It belongs in `reidcc-voice.md` (a vision note), the
  README and the about screen together, and needs Reid's OK on the note first.
