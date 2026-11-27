<script setup lang="ts">
// The landing page, ported from vision\Spec\github-pages\mock (index.html + motion.js). Motion rules: every
// timed step is 120-240ms on one curve; longer moves follow the scroll position. Reduced motion turns it all off.
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useData, withBase } from "vitepress";

const { theme } = useData();
const { version, release, repo, news } = theme.value.reidcc as {
  version: string; repo: string; release: { version: string; setup: string; url: string } | null;
  news: { release: string; title: string } | null; // CHANGELOG.md's newest heading (config.ts)
};
const docs = withBase("/docs/install");
const build = withBase("/docs/build-from-source");
const flowSrc = withBase("/art/flow-1120.webp");
const shotSrc = withBase("/shots/session-window.webp");
const chatSrc = withBase("/shots/chat.webp");
const besideSrc = withBase("/shots/beside.webp");
const changes = withBase("/changelog");
const next = withBase("/docs/next");
const chatDoc = withBase("/docs/chat");
// the launcher's four sizes, shot at half their real pixels so they stay to scale (rs\tests\site_shots.py)
const sizes = [
  { name: "main", key: "Alt+1", w: 500, h: 458 },
  { name: "medium", key: "drag it narrow", w: 250, h: 418 },
  { name: "small", key: "Alt+2", w: 190, h: 218 },
  { name: "pod", key: "Alt+3", w: 184, h: 56 },
].map((z) => ({ ...z, src: withBase(`/shots/size-${z.name}.webp`) }));
const emblemSrc = withBase("/art/emblem-144.webp");
// the hand (assets\emblem.json, medium's opening in the app): [frame prefix, frames, start ms, ms], at the app's
// PACE (rs\ui\src\gate.ts). Frames cut by make_assets.py --site.
const HAND: [string, number, number, number][] = [["er", 8, 0, 250], ["eg", 20, 250, 500], ["el", 13, 750, 330], ["ei", 10, 1080, 250], ["eo", 20, 1330, 490]];
const PACE = 1.375;

const root = ref<HTMLElement>();
let stop = () => {};

onMounted(() => {
  const el = root.value!;
  const ac = new AbortController(), sig = { signal: ac.signal };
  const on = (t: EventTarget, ev: string, fn: (e: any) => void, o: AddEventListenerOptions = {}) =>
    t.addEventListener(ev, fn, { ...o, signal: ac.signal });
  let alive = true;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const $ = <T extends Element = HTMLElement>(s: string) => el.querySelector(s) as T;
  const $$ = (s: string, r: ParentNode = el) => [...r.querySelectorAll(s)] as HTMLElement[];
  const raf = (fn: FrameRequestCallback) => requestAnimationFrame((t) => alive && fn(t));
  el.classList.add("js");

  // ---- reveal: each section draws in once, when it comes into view
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    io.unobserve(e.target);
    $$("[data-count]", e.target).forEach(count);
  }), { rootMargin: "0px 0px -12% 0px" });
  $$("[data-reveal]").forEach((s) => io.observe(s));

  // telemetry ticks up from 0 in one 240ms step, after its line lands
  function count(b: HTMLElement) {
    const to = +b.dataset.count!, lim = b.closest(".lim");
    if (reduced) { b.textContent = String(to); lim?.classList.toggle("warn", to >= 75); return; }
    b.textContent = "0";
    setTimeout(() => {
      const t0 = performance.now();
      const step = (now: number) => {
        const v = Math.round(to * clamp((now - t0) / 240));
        b.textContent = String(v);
        lim?.classList.toggle("warn", v >= 75); // the app's bronze threshold
        if (v < to) raf(step);
      };
      raf(step);
    }, 240);
  }

  // ---- the hand, then the gate. The hand grows, its leaves come out, the emerald ignites and the view zooms
  // into it, to dark (~2.5s); then the gate rises out of the lines and ignites (assets\gate.json: rise 6 /
  // ignite 8 in 360ms, open 30 in 480ms). Only the first frame is in the first load; the rest are fetched
  // after the page has loaded (the 700 KB budget). Reduced motion: the ready gate, no hand.
  const hero = $("#hero"), canvas = $<HTMLCanvasElement>("#gate");
  const g = canvas.getContext("2d")!, tag = $("#gatetag"), copy = $(".copy"), stage = $(".stage");
  const load = (pre: string, n: number) => Array.from({ length: n }, (_, i) => {
    const im = new Image(); im.src = withBase(`/frames/${pre}${String(i).padStart(2, "0")}.webp`); return im;
  });
  const draw = (im: HTMLImageElement) => im.complete ? g.drawImage(im, 0, 0, 800, 704)
    : im.addEventListener("load", () => alive && g.drawImage(im, 0, 0, 800, 704), { once: true, ...sig });
  let rise: HTMLImageElement[] = [], ignite: HTMLImageElement[] = [], open: HTMLImageElement[] = [];
  let risen = false, p = 0, forced: number | null = null, peek = 0, peekTo = 0, peekRaf = 0;

  const setTag = (s: string) => {
    tag.textContent = s === "open" ? "reidcc · opening" : "reidcc · ready";
    tag.classList.toggle("opening", s === "open");
    tag.classList.toggle("gone", s === "gone");
  };

  hero.classList.add("in");
  const first = new Image(); first.src = withBase(reduced ? "/frames/r00.webp" : "/frames/er00.webp"); draw(first);
  const afterLoad = (fn: () => void) => document.readyState === "complete" ? fn() : on(window, "load", fn, { once: true });
  // draws each frame from its start time, resolves after ms
  const play = (frames: { im: HTMLImageElement; at: number }[], ms: number) => new Promise<void>((done) => {
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = now - t0;
      draw((frames.findLast((f) => f.at <= t) ?? frames[0]).im);
      t < ms ? raf(tick) : done();
    };
    raf(tick);
  });
  afterLoad(() => {
    if (!alive) return;
    rise = load("r", 6); ignite = load("i", 8);
    const ready = ignite[7];
    if (reduced) { draw(ready); risen = true; open = load("o", 30); return; }
    const hand = HAND.flatMap(([pre, n, start, ms]) => load(pre, n).map((im, i) => ({ im, at: (start + ms * i / n) * PACE })));
    const handEnd = (HAND[4][2] + HAND[4][3]) * PACE;
    // rise out of the lines, ignite the keystone (one frame per ~26ms, as in the app)
    const gate = [...rise, ...ignite].map((im, i, a) => ({ im, at: 360 * i / a.length }));
    Promise.all([...hand, ...gate].map((f) => f.im.decode().catch(() => {}))).then(async () => {
      if (!alive) return;
      setTag("open");
      await play(hand, handEnd);
      await play(gate, 360);
      risen = true; open = load("o", 30); render();
    });
  });

  // scroll: the doors swing and the view goes through, frame by frame with the scroll position
  const navH = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--vp-nav-height")) || 64;
  function heroProgress() {
    const r = hero.getBoundingClientRect();
    const sticky = getComputedStyle(stage).position === "sticky";
    const range = sticky ? hero.offsetHeight - stage.offsetHeight : hero.offsetHeight * 0.8;
    return clamp(((sticky ? navH() : 0) - r.top) / range);
  }
  function render() {
    if (!risen) return;
    const q = forced ?? p;
    const im = q > 0 ? open[Math.min(29, Math.round(q * 29))] : peek > 0 ? open[Math.round(peek * 7)] : ignite[7];
    if (im) draw(im);
    setTag(q <= 0 ? "ready" : q >= 0.97 ? "gone" : "open");
    hero.classList.toggle("moved", q > 0);
    const fade = clamp((q - 0.55) / 0.45); // the copy steps back as the light fills the passage
    copy.style.opacity = String(1 - 0.8 * fade);
    copy.style.transform = `translateY(${-14 * fade}px)`;
  }
  const heroFrame = () => { p = reduced ? 0 : heroProgress(); render(); };

  // hover the hero button: the doors part a hand's width (open frames 0-7 in 150ms), and close again on leave
  const peekStep = () => {
    peek = peekTo > peek ? Math.min(peekTo, peek + 1 / 9) : Math.max(peekTo, peek - 1 / 9); // ~150ms at 60fps
    render();
    peekRaf = peek !== peekTo ? requestAnimationFrame(() => alive && peekStep()) : 0;
  };
  const peekAt = (v: number) => { if (reduced) return; peekTo = v; if (!peekRaf) peekRaf = requestAnimationFrame(() => alive && peekStep()); };
  const openBtn = $("#open");
  on(openBtn, "pointerenter", () => peekAt(1));
  on(openBtn, "pointerleave", () => peekAt(0));

  // click: the gate opens all the way (480ms), the view goes through, and lands on download
  on(openBtn, "click", (e: MouseEvent) => {
    const land = () => $("#download").scrollIntoView({ behavior: "instant" as ScrollBehavior, block: "start" });
    e.preventDefault();
    if (reduced || !risen) { land(); return; }
    const from = p, t0 = performance.now(), ms = 480 * (1 - from);
    let done = false;
    const skip = new AbortController();
    const finish = () => {
      if (done) return; done = true;
      skip.abort();
      forced = null;
      land();
    };
    setTimeout(() => { // any key or click skips, like the app
      if (done) return;
      window.addEventListener("keydown", finish, { signal: skip.signal });
      window.addEventListener("pointerdown", finish, { signal: skip.signal });
    }, 0);
    const tick = (now: number) => {
      if (done) return;
      forced = from + (1 - from) * clamp((now - t0) / ms);
      render();
      forced < 1 ? raf(tick) : finish();
    };
    raf(tick);
  });

  // ---- the flow: art revealed along its line; steps light as the line reaches them; the signal lights last
  const flow = $("#flow"), steps = $("#steps");
  const nodes = [0.188, 0.501, 0.813]; // folder, persona, signal along the art's line (measured on the image)
  let lastFlow = -1;
  steps.classList.add("track");
  function flowFrame() {
    const r = flow.getBoundingClientRect(), vh = innerHeight;
    const q = reduced ? 1 : clamp((vh * 0.85 - r.top) / (vh * 0.3 + r.height * 0.5));
    flow.style.setProperty("--p", q.toFixed(4));
    flow.classList.toggle("idle", q <= 0);
    flow.classList.toggle("done", q >= 1);
    $$(":scope > div", steps).forEach((d, i) => d.classList.toggle("on", q >= nodes[i]));
    if (lastFlow < nodes[2] && q >= nodes[2] && !reduced) { // the signal lights: one 240ms flare
      flow.classList.remove("ignite"); void flow.offsetWidth; flow.classList.add("ignite");
    }
    lastFlow = q;
  }

  // ---- top bar: how far down the page you are
  const bar = $(".progress");
  function barFrame() {
    const max = document.documentElement.scrollHeight - innerHeight;
    bar.style.setProperty("--s", max > 0 ? (scrollY / max).toFixed(4) : "0");
  }

  // one rAF per scroll, whatever the event rate
  let queued = false;
  const frame = () => { queued = false; heroFrame(); flowFrame(); barFrame(); };
  const queue = () => { if (!queued) { queued = true; raf(frame); } };
  on(window, "scroll", queue, { passive: true });
  on(window, "resize", queue);

  // ---- press: a 160ms ring (emerald on the primary button only: emerald means go)
  on(el, "pointerdown", (e: PointerEvent) => {
    const b = (e.target as HTMLElement).closest(".btn");
    if (!b || reduced) return;
    b.classList.remove("press"); void (b as HTMLElement).offsetWidth; b.classList.add("press");
  });

  // ---- measuring crosshair over art: coordinates in the art's own pixels
  if (!matchMedia("(hover: none)").matches) $$("[data-measure]").forEach((m) => {
    const mx = document.createElement("span"), my = document.createElement("span"), ro = document.createElement("span");
    mx.className = "mx"; my.className = "my"; ro.className = "readout";
    m.append(mx, my, ro);
    const media = m.querySelector("img, canvas") as HTMLImageElement | HTMLCanvasElement;
    on(m, "pointerenter", () => m.classList.add("measuring"));
    on(m, "pointerleave", () => m.classList.remove("measuring"));
    on(m, "pointermove", (e: PointerEvent) => {
      const r = m.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      m.style.setProperty("--x", x + "px"); m.style.setProperty("--y", y + "px");
      const nw = (media as HTMLImageElement).naturalWidth || media.width, nh = (media as HTMLImageElement).naturalHeight || media.height;
      const pad = (v: number) => String(Math.round(v)).padStart(4, "0");
      ro.textContent = `x ${pad(x / r.width * nw)} · y ${pad(y / r.height * nh)}`;
    });
  });

  frame();
  stop = () => { alive = false; ac.abort(); io.disconnect(); };
});
onBeforeUnmount(() => stop());
</script>

<template>
  <div class="rc-home" ref="root">
    <div class="progress" aria-hidden="true"></div>

    <!-- The hand, then the gate: on load the hand's opening plays and the gate rises after it (the app's frames);
         the gate opens as you scroll (its open frames). -->
    <section class="hero" id="hero">
      <div class="stage"><div class="wrap">
        <div class="copy" data-reveal>
          <span class="tag" style="--i:0">reidcc · ready</span>
          <h1 style="--i:1">Folder.<br> Profile.<br> Gate.</h1>
          <p class="lead" style="--i:2">A launcher for Claude Code and Codex. Pick a folder and a profile, and your persona, memory and settings are already there.</p>
          <div class="ctas" style="--i:3">
            <a class="btn primary" id="open" href="#download">{{ release ? "download for windows" : "build from source" }}</a>
            <a class="btn" :href="docs">read the docs</a>
          </div>
          <a class="news" v-if="news" :href="changes" style="--i:4">{{ news.release }} · {{ news.title || "what's new" }}&nbsp;<span class="sep">›</span></a>
          <div class="hint" style="--i:5">folder <span class="sep">→</span> profile <span class="sep">→</span> open gate <span class="scrollcue">· scroll to open</span></div>
        </div>
        <div class="frame gate" data-measure>
          <canvas id="gate" width="800" height="704" role="img" aria-label="A marble hand over an engraved compass, then the gate: an engraved stone arch with lion doors and one emerald point"></canvas>
          <span class="tag cap" id="gatetag">reidcc · ready</span>
        </div>
      </div></div>
    </section>

    <section class="band" data-reveal><div class="wrap">
      <span class="tag" style="--i:0">the flow</span>
      <h2 style="--i:1">Three steps. Nothing to hunt for.</h2>
      <p class="sub" style="--i:2">Everything sits on one screen: the profile list, the profile's fields, your folder and the command it will run.</p>
      <!-- dim copy under, the art revealed over it along the flow line as you scroll -->
      <div class="flowart" id="flow" style="--i:3" data-measure>
        <img class="base" :src="flowSrc" alt="" width="1120" height="630" loading="lazy">
        <img class="lit" :src="flowSrc" alt="folder → persona → ready" width="1120" height="630" loading="lazy">
        <span class="scan"></span>
      </div>
      <div class="steps" id="steps">
        <div style="--i:4"><span class="tag">01 · folder</span><h3>pick folder</h3><p>Or open a recent one. <span class="mono">ctrl+o</span></p></div>
        <div style="--i:5"><span class="tag">02 · profile</span><h3>pick a profile</h3><p>Engine, model, sign-in, persona, memory and switches, saved in <code>reid.json</code>.</p></div>
        <div style="--i:6"><span class="tag">03 · open gate</span><h3>open gate</h3><p>The session starts in its own window with your setup in place. <span class="mono">ctrl+↵</span> Or open chat.</p></div>
      </div>
    </div></section>

    <section class="band" data-reveal><div class="wrap">
      <span class="tag" style="--i:0">chat</span>
      <h2 style="--i:1">One chat over Claude Code and Codex.</h2>
      <p class="sub" style="--i:2">Each turn streams its text and tool lines. After a turn that edits files, you see which files changed, and each one opens to its diff. Pick the other engine and it picks up from a handoff.</p>
      <div class="frame wide" style="--i:3" data-measure><img :src="chatSrc" alt="Reidcc's chat after a Claude turn that wrote a file: the reply, the changed block and the composer" width="1120" height="720" loading="lazy"></div>
      <div class="steps">
        <div style="--i:4"><span class="tag">switch → codex</span><p>The next turn gets <code>.reid/handoff.md</code>: the changed files and the diff stat.</p></div>
        <div style="--i:5"><span class="tag">read-only</span><p>Each engine's own guards. Claude loses its write tools and every MCP tool.</p></div>
        <div style="--i:6"><span class="tag">tune</span><p>Effort, servers and plugins for this chat only. Or type <code>/effort high</code>.</p></div>
      </div>
      <p class="mono after" style="--i:7"><a :href="chatDoc">c in the TUI, or reid --chat ›</a></p>
    </div></section>

    <section class="band" data-reveal><div class="wrap split">
      <div>
        <span class="tag" style="--i:0">every session</span>
        <h2 style="--i:1">You always know where you stand.</h2>
        <p class="sub" style="--i:2">Each session shows its folder, its profile, and how much context and limit you've used. Numbers, not adjectives.</p>
        <div class="tele" style="--i:3"><span>~/kiln</span><span>PROFILE · <b>MAIN</b></span><span>context <b data-count="42">42</b><b>%</b></span><span class="lim">limit <b data-count="81">81</b><b>%</b></span></div>
      </div>
      <div class="frame" style="--i:2" data-measure><img :src="shotSrc" alt="A Reidcc session window" width="1000" height="514" loading="lazy"></div>
    </div></section>

    <section class="band" data-reveal><div class="wrap">
      <span class="tag" style="--i:0">one window</span>
      <h2 style="--i:1">One launcher, four sizes.</h2>
      <div class="sizes" style="--i:2">
        <figure v-for="z in sizes" :key="z.name" :style="{ flexGrow: z.w, '--w': z.w }">
          <img :src="z.src" :alt="`The launcher at ${z.name} size`" :width="z.w" :height="z.h" loading="lazy">
          <figcaption><b>{{ z.name }}</b> <span class="mono">{{ z.key }}</span></figcaption>
        </figure>
      </div>
      <p class="sub after" style="--i:3">Click <b>RC</b> on a session window and the launcher opens beside it. Again: full. Again: closed.</p>
      <div class="frame wide" style="--i:4"><img :src="besideSrc" alt="A session window with the launcher open beside the terminal" width="1120" height="384" loading="lazy"></div>
    </div></section>

    <section class="band" data-reveal><div class="wrap">
      <span class="tag" style="--i:0">yours</span>
      <h2 style="--i:1">Profile, persona, memory. Three things, never mixed.</h2>
      <div class="steps">
        <div style="--i:2"><span class="tag">profile</span><h3>A named setup</h3><p>Model, sign-in, persona, memory and switches. Make one per way you work.</p></div>
        <div style="--i:3"><span class="tag">persona</span><h3>A prompt file</h3><p>Who the session is. Optional, plain Markdown in <code>personas\</code>.</p></div>
        <div style="--i:4"><span class="tag">memory</span><h3>What it remembers</h3><p>Pinned facts and a dated journal, added to sessions with memory on.</p></div>
      </div>
    </div></section>

    <section class="band" id="download" data-reveal><div class="wrap split">
      <div v-if="release">
        <span class="tag" style="--i:0">download · v{{ release.version }} beta</span>
        <h2 style="--i:1">Install in a minute. Updates itself.</h2>
        <p class="sub" style="--i:2">One installer for your account, no admin rights. Your profiles and memory live in your own folder and survive every update and uninstall.</p>
        <div class="ctas" style="--i:3">
          <a class="btn primary" :href="release.url">download for windows</a><a class="btn" :href="docs">install guide</a>
        </div>
      </div>
      <div v-else>
        <span class="tag" style="--i:0">download</span>
        <h2 style="--i:1">Build it from source.</h2>
        <p class="sub" style="--i:2">The installer comes with the first release. Until then, Reidcc builds in a few minutes with Rust and Node, and your profiles and memory live in a folder you choose.</p>
        <div class="ctas" style="--i:3">
          <a class="btn primary" :href="build">build from source</a><a class="btn" :href="`${repo}/releases`">releases</a>
        </div>
      </div>
      <div class="install" v-if="release" style="--i:3">
        <div style="--i:4"><span class="p">1 </span><span class="c">{{ release.setup }}</span></div>
        <div style="--i:5"><span class="p">2 </span>Reidcc opens <span class="sep">→</span> <span class="c">pick folder</span></div>
        <div style="--i:6"><span class="p">3 </span><span class="c">open gate</span> <span class="muted">· Claude Code signed in once</span></div>
        <div style="--i:7"><span class="p">  </span><span class="muted">data in</span> <span class="c">%USERPROFILE%\Reidcc</span></div>
      </div>
      <div class="install" v-else style="--i:3">
        <div style="--i:4"><span class="p">1 </span><span class="c">git clone {{ repo }}</span></div>
        <div style="--i:5"><span class="p">2 </span><span class="c">cd reidcc\rs\ui; npm ci; npm run build</span></div>
        <div style="--i:6"><span class="p">3 </span><span class="c">cd ..; cargo build --release</span></div>
        <div style="--i:7"><span class="p">  </span><span class="muted">then run</span> <span class="c">target\release\Reidcc.exe</span></div>
      </div>
    </div></section>

    <footer data-reveal><div class="wrap">
      <img style="--i:0" :src="emblemSrc" alt="" width="72" height="72" loading="lazy">
      <div style="--i:1"><div>Only the essentials, all in sight.</div><div class="tag" style="margin-top:4px">reidcc v{{ version }} beta · built on claude code and codex</div></div>
      <div class="links" style="--i:2"><a :href="docs">docs</a><a :href="changes">changelog</a><a :href="next">what's next</a><a :href="repo">github</a><a :href="`${repo}/blob/main/LICENSE.md`">license</a></div>
    </div></footer>
  </div>
</template>
