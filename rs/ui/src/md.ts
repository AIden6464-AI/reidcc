// The chat stream's markdown: just what engines write in replies. Code fences, inline code, bold,
// links and headings; everything else stays as typed (the stream is pre-wrap). The TUI follows the
// same rules (SPEC-unified-interface Part 6).

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** One line outside a fence. Escaped first, so `Option<T>` stays text; code spans are left alone. */
function inline(line: string): string {
  const h = /^#{1,6} +(.*)$/.exec(line);
  if (h) return `<b>${inline(h[1])}</b>`;
  return esc(line).split(/(`[^`]+`)/).map((part, i) => {
    if (i % 2) return `<code>${part.slice(1, -1)}</code>`;
    return part
      .replace(/\*\*([^*]+?)\*\*/g, "<b>$1</b>")
      // a link shows its text; the target (often a local path) is its tooltip, never a navigation
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<span class="mdlink" title="$2">$1</span>');
  }).join("");
}

/** HTML for a reply so far. A fence still open (the text is streaming) is a code block to the end. */
export function md(text: string): string {
  const out: string[] = [];
  let code: string[] | null = null;
  for (const line of text.split("\n")) {
    if (/^ {0,3}```/.test(line)) {
      if (code) {
        out.push(`<pre class="code">${code.join("\n")}</pre>`);
        code = null;
      } else {
        code = [];
      }
      continue;
    }
    if (code) code.push(esc(line));
    else out.push(inline(line) + "\n");
  }
  if (code) out.push(`<pre class="code open">${code.join("\n")}</pre>`);
  return out.join("").replace(/\n$/, "");
}
