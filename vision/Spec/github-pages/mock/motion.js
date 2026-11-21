// Motion for the Reidcc site mock (SPEC-github-pages.md, Part 2b). No library: rAF, IntersectionObserver.
(() => {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // ---- reveal: each section draws in once, when it comes into view
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    io.unobserve(e.target);
    $$("[data-count]", e.target).forEach(count);
  }), { rootMargin: "0px 0px -12% 0px" });
  $$("[data-reveal]").forEach((el) => io.observe(el));

  // telemetry ticks up from 0 in one 240ms step, after its line lands
  function count(b) {
    const to = +b.dataset.count, lim = b.closest(".lim");
    if (reduced) { b.textContent = to; lim && lim.classList.toggle("warn", to >= 75); return; }
    b.textContent = "0";
    setTimeout(() => {
      const t0 = performance.now();
      const step = (now) => {
        const v = Math.round(to * clamp((now - t0) / 240));
        b.textContent = v;
        if (lim) lim.classList.toggle("warn", v >= 75); // the app's bronze threshold
        if (v < to) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, 240);
  }

  // ---- the gate: the app's own frames (assets\gate.json: rise 6 / ignite 8 in 360ms, open 30 in 480ms)
  const hero = $("#hero"), canvas = $("#gate");
  let p = 0, forced = null;
  if (hero && canvas) {
    const g = canvas.getContext("2d"), tag = $("#gatetag"), copy = $(".hero .copy"), stage = $(".hero .stage");
    const load = (pre, n) => Array.from({ length: n }, (_, i) => { const im = new Image(); im.src = `frames/${pre}${String(i).padStart(2, "0")}.webp`; return im; });
    const rise = load("r", 6), ignite = load("i", 8), open = load("o", 30);
    const draw = (im) => im.complete ? g.drawImage(im, 0, 0, 800, 704) : im.addEventListener("load", () => g.drawImage(im, 0, 0, 800, 704), { once: true });
    const ready = ignite[7];
    let risen = false;

    const setTag = (s) => {
      tag.textContent = s === "open" ? "reidcc · opening" : "reidcc · ready";
      tag.classList.toggle("opening", s === "open");
      tag.classList.toggle("gone", s === "gone");
    };

    // on load: rise out of the lines, ignite the keystone (one frame per 30ms, as in the app)
    hero.classList.add("in");
    if (reduced) { draw(ready); risen = true; }
    else {
      draw(rise[0]);
      const seq = [...rise, ...ignite];
      Promise.all(seq.map((im) => im.decode().catch(() => {}))).then(() => {
        const t0 = performance.now() + 200; // after the copy lands
        const tick = (now) => {
          const i = Math.floor((now - t0) / (360 / seq.length));
          if (i >= 0) draw(seq[Math.min(i, seq.length - 1)]);
          if (i < seq.length - 1) requestAnimationFrame(tick); else { risen = true; render(); }
        };
        requestAnimationFrame(tick);
      });
    }

    // scroll: the doors swing and the view goes through, frame by frame with the scroll position
    function heroProgress() {
      const r = hero.getBoundingClientRect();
      const sticky = getComputedStyle(stage).position === "sticky";
      const range = sticky ? hero.offsetHeight - stage.offsetHeight : hero.offsetHeight * 0.8;
      return clamp(((sticky ? 56 : 0) - r.top) / range);
    }
    function render() {
      if (!risen) return;
      const q = forced ?? p;
      draw(q > 0 ? open[Math.min(29, Math.round(q * 29))] : peek > 0 ? open[Math.round(peek * 7)] : ready);
      setTag(q <= 0 ? "ready" : q >= 0.97 ? "gone" : "open");
      hero.classList.toggle("moved", q > 0);
      const fade = clamp((q - 0.55) / 0.45); // the copy steps back as the light fills the passage
      copy.style.opacity = 1 - 0.8 * fade;
      copy.style.transform = `translateY(${-14 * fade}px)`;
    }
    window.__heroFrame = () => { p = reduced ? 0 : heroProgress(); render(); };

    // hover download: the doors part a hand's width (open frames 0–7 in 150ms), and close again on leave
    let peek = 0, peekTo = 0, peekRaf = 0;
    const peekStep = () => {
      peek = peekTo > peek ? Math.min(peekTo, peek + 1 / 9) : Math.max(peekTo, peek - 1 / 9); // ~150ms at 60fps
      render();
      peekRaf = peek !== peekTo ? requestAnimationFrame(peekStep) : 0;
    };
    const peekAt = (v) => { if (reduced) return; peekTo = v; if (!peekRaf) peekRaf = requestAnimationFrame(peekStep); };
    $("#open").addEventListener("pointerenter", () => peekAt(1));
    $("#open").addEventListener("pointerleave", () => peekAt(0));

    // click download: the gate opens all the way (480ms), the view goes through, and lands on download
    $("#open").addEventListener("click", (e) => {
      if (reduced || !risen) return;
      e.preventDefault();
      const from = p, t0 = performance.now(), ms = 480 * (1 - from);
      let done = false;
      const finish = () => {
        if (done) return; done = true;
        removeEventListener("keydown", finish); removeEventListener("pointerdown", finish);
        forced = null;
        $("#download").scrollIntoView({ behavior: "instant", block: "start" });
      };
      setTimeout(() => { addEventListener("keydown", finish); addEventListener("pointerdown", finish); }, 0); // any key or click skips, like the app
      const tick = (now) => {
        if (done) return;
        forced = from + (1 - from) * clamp((now - t0) / ms);
        render();
        forced < 1 ? requestAnimationFrame(tick) : finish();
      };
      requestAnimationFrame(tick);
    });
  }

  // ---- the flow: art revealed along its line; steps light as the line reaches them; the ● lights last
  const flow = $("#flow"), steps = $("#steps");
  const nodes = [0.188, 0.501, 0.813]; // folder, persona, ● along the art's line (measured on the image)
  let lastFlow = -1;
  steps && steps.classList.add("track");
  function flowFrame() {
    if (!flow) return;
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

  // ---- top bar progress hairline
  const bar = $(".bar");
  function barFrame() {
    const max = document.documentElement.scrollHeight - innerHeight;
    bar && bar.style.setProperty("--s", max > 0 ? (scrollY / max).toFixed(4) : 0);
  }

  // one rAF per scroll, whatever the event rate
  let queued = false;
  const frame = () => { queued = false; window.__heroFrame && window.__heroFrame(); flowFrame(); barFrame(); tocFrame(); };
  const queue = () => { if (!queued) { queued = true; requestAnimationFrame(frame); } };
  addEventListener("scroll", queue, { passive: true });
  addEventListener("resize", queue);

  // ---- press: a 160ms ring (emerald on the primary button only: emerald means go)
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn");
    if (!b || reduced) return;
    b.classList.remove("press"); void b.offsetWidth; b.classList.add("press");
  });

  // ---- measuring crosshair over art: coordinates in the art's own pixels
  $$("[data-measure]").forEach((el) => {
    if (matchMedia("(hover: none)").matches) return;
    const mx = document.createElement("span"), my = document.createElement("span"), ro = document.createElement("span");
    mx.className = "mx"; my.className = "my"; ro.className = "readout";
    el.append(mx, my, ro);
    const media = el.querySelector("img, canvas");
    el.addEventListener("pointerenter", () => el.classList.add("measuring"));
    el.addEventListener("pointerleave", () => el.classList.remove("measuring"));
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      el.style.setProperty("--x", x + "px"); el.style.setProperty("--y", y + "px");
      const nw = media.naturalWidth || media.width, nh = media.naturalHeight || media.height;
      const pad = (v) => String(Math.round(v)).padStart(4, "0");
      ro.textContent = `x ${pad(x / r.width * nw)} · y ${pad(y / r.height * nh)}`;
    });
  });

  // ---- docs: the sidebar marker slides to the hovered link and back; the toc follows the page; copy buttons
  const side = $(".side");
  if (side) {
    const ind = document.createElement("span"); ind.className = "ind"; side.append(ind);
    const cur = $("a[aria-current]", side);
    const to = (a) => { ind.style.setProperty("--ty", a.offsetTop + "px"); ind.style.height = a.offsetHeight + "px"; };
    if (cur) to(cur);
    $$("a", side).forEach((a) => a.addEventListener("pointerenter", () => to(a)));
    side.addEventListener("pointerleave", () => cur && to(cur));
  }
  const toc = $$(".toc a");
  function tocFrame() {
    if (!toc.length) return;
    let on = toc[0];
    for (const a of toc) { const h = $(a.getAttribute("href")); if (h && h.getBoundingClientRect().top < innerHeight * 0.3) on = a; }
    toc.forEach((a) => a === on ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current"));
  }
  $$(".page pre").forEach((pre) => {
    const b = document.createElement("button");
    b.className = "copy-btn"; b.type = "button"; b.textContent = "copy";
    b.addEventListener("click", () => {
      const text = $$("code .k", pre).map((k) => k.textContent).join("\n") || pre.innerText;
      navigator.clipboard?.writeText(text).catch(() => {});
      b.textContent = "copied"; b.classList.add("done");
      setTimeout(() => { b.textContent = "copy"; b.classList.remove("done"); }, 1200);
    });
    pre.append(b);
  });

  frame();
})();
