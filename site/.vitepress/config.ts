// The Reidcc website (vision\Spec\SPEC-github-pages.md). The version comes from rs\Cargo.toml and the download
// from GitHub's latest release, both read at build time, so neither can go stale or claim an installer that
// isn't out yet (the truth rule).
import { readFileSync } from "node:fs";
import { defineConfig } from "vitepress";

const REPO = "https://github.com/AIden6464-AI/reidcc";
const cargo = readFileSync(new URL("../../rs/Cargo.toml", import.meta.url), "utf8");
const version = cargo.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? "";

/** The latest release's installer, or null before the first release (or offline). */
async function latest(): Promise<{ version: string; setup: string; url: string } | null> {
  try {
    const r = await fetch("https://api.github.com/repos/AIden6464-AI/reidcc/releases/latest",
      { headers: { Accept: "application/vnd.github+json",
          // CI passes its token: unauthenticated calls from shared runners hit GitHub's rate limit
          ...(process.env.GITHUB_TOKEN ? { Authorization: `Bearer ${process.env.GITHUB_TOKEN}` } : {}) },
        signal: AbortSignal.timeout(8000) });
    if (!r.ok) return null;
    const rel = await r.json();
    const exe = rel.assets?.find((a: { name: string }) => a.name.endsWith("-setup.exe"));
    return exe ? { version: rel.tag_name.replace(/^v/, ""), setup: exe.name, url: exe.browser_download_url } : null;
  } catch {
    return null;
  }
}

export default async () => {
  const release = await latest();
  return defineConfig({
    title: "Reidcc",
    description: "Folder. Profile. Gate. A launcher for Claude Code and Codex.",
    base: "/reidcc/",
    lang: "en",
    appearance: "force-dark",
    cleanUrls: true,
    lastUpdated: false,
    markdown: { container: { tipLabel: "note", infoLabel: "note", warningLabel: "warning", dangerLabel: "warning", detailsLabel: "details" } },
    head: [
      ["link", { rel: "icon", type: "image/png", href: "/reidcc/favicon.png" }],
      ["meta", { property: "og:title", content: "Reidcc" }],
      ["meta", { property: "og:description", content: "Folder. Profile. Gate." }],
      ["meta", { property: "og:image", content: "https://aiden6464-ai.github.io/reidcc/og.png" }],
      ["meta", { name: "theme-color", content: "#040404" }],
    ],
    themeConfig: {
      // values the landing page reads (Home.vue, via useData().theme)
      ...({ reidcc: { version, release, repo: REPO } } as object),
      logo: { src: "/art/logo-52.webp", alt: "" },
      nav: [
        { text: "docs", link: "/docs/install" },
        { text: "download", link: "/#download" },
        { text: "changelog", link: `${REPO}/releases` },
      ],
      socialLinks: [{ icon: "github", link: REPO }],
      search: { provider: "local", options: { translations: { button: { buttonText: "search", buttonAriaLabel: "search" } } } },
      outline: { level: [2, 2], label: "on this page" },
      docFooter: { prev: "previous", next: "next" },
      sidebarMenuLabel: "menu",
      returnToTopLabel: "back to top",
      darkModeSwitchLabel: "",
      sidebar: [
        { text: "start", items: [
          { text: "install", link: "/docs/install" },
          { text: "first session", link: "/docs/first-session" },
          { text: "updates and uninstall", link: "/docs/updates" },
        ] },
        { text: "the launcher", items: [
          { text: "profiles", link: "/docs/profiles" },
          { text: "personas", link: "/docs/personas" },
          { text: "memory", link: "/docs/memory" },
          { text: "engines", link: "/docs/engines" },
          { text: "chat", link: "/docs/chat" },
          { text: "session windows", link: "/docs/session-windows" },
          { text: "sizes and the mini pod", link: "/docs/sizes" },
          { text: "settings", link: "/docs/settings" },
          { text: "keys", link: "/docs/keys" },
        ] },
        { text: "reference", items: [
          { text: "reid.json", link: "/docs/reid-json" },
          { text: "reid in a terminal", link: "/docs/cli" },
          { text: "folders and files", link: "/docs/files" },
          { text: "troubleshooting", link: "/docs/troubleshooting" },
        ] },
        { text: "extras", items: [
          { text: "build from source", link: "/docs/build-from-source" },
          { text: "proxy", link: "/docs/proxy" },
        ] },
      ],
    },
  });
};
