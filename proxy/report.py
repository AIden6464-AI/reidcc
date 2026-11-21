"""
Build a self-contained HTML report from Claude Code session transcripts
+ this proxy's audit logs.

Usage:
    python report.py --project E--repo-claude-proxy
"""

import argparse
import json
import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path


def _default_projects_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~").expanduser()
    return home / ".claude" / "projects"


def parse_session(path: Path) -> dict:
    """Extract per-turn usage rows + session metadata."""
    turns = []
    cwd = git_branch = version = session_id = None
    first_ts = last_ts = None

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue

        cwd = d.get("cwd", cwd)
        git_branch = d.get("gitBranch", git_branch)
        version = d.get("version", version)
        session_id = d.get("sessionId", session_id)

        ts_str = d.get("timestamp")
        ts = None
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        if ts:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)

        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue

        turns.append({
            "ts": ts.isoformat() if ts else None,
            "input": int(usage.get("input_tokens", 0) or 0),
            "output": int(usage.get("output_tokens", 0) or 0),
            "cache_read": int(usage.get("cache_read_input_tokens", 0) or 0),
            "cache_create": int(usage.get("cache_creation_input_tokens", 0) or 0),
        })

    totals = {k: sum(t[k] for t in turns) for k in ("input", "output", "cache_read", "cache_create")}
    fresh_input = totals["input"] + totals["cache_create"]
    billed_input = fresh_input + totals["cache_read"]
    cache_eff = (totals["cache_read"] / billed_input) if billed_input else 0.0
    duration_s = (last_ts - first_ts).total_seconds() if first_ts and last_ts else 0.0

    return {
        "file": path.name,
        "session_id": session_id or path.stem,
        "cwd": cwd,
        "git_branch": git_branch,
        "version": version,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "duration_s": duration_s,
        "turns": turns,
        "n_turns": len(turns),
        "totals": totals,
        "fresh_input": fresh_input,
        "billed_input": billed_input,
        "cache_efficiency": cache_eff,
    }


def parse_audit(audit_dir: Path) -> list[dict]:
    """Load all proxy audit entries (request + response) sorted by ts."""
    entries = []
    if not audit_dir.is_dir():
        return entries
    for log_file in sorted(audit_dir.glob("*.jsonl")):
        for raw in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries


def render_overall_summary(sessions: list[dict]) -> dict:
    if not sessions:
        return {}
    total_output = sum(s["totals"]["output"] for s in sessions)
    total_fresh = sum(s.get("fresh_input", 0) for s in sessions)
    total_cache_read = sum(s["totals"]["cache_read"] for s in sessions)
    total_billed = total_fresh + total_cache_read
    overall_eff = (total_cache_read / total_billed * 100) if total_billed else 0
    eff_class = "good" if overall_eff > 50 else "warn"
    return {
        "total_output": total_output,
        "total_fresh": total_fresh,
        "total_cache_read": total_cache_read,
        "total_billed": total_billed,
        "overall_eff": overall_eff,
        "eff_class": eff_class,
    }


def render_card(s: dict) -> str:
    t = s["totals"]
    fresh = s.get("fresh_input", 0)
    total = max(1, fresh + t["cache_read"] + t["output"])
    bar = (
        f'<div class="bar">'
        f'<span class="input"  style="width:{fresh/total*100:.2f}%"></span>'
        f'<span class="create" style="width:{t["cache_create"]/total*100:.2f}%"></span>'
        f'<span class="read"   style="width:{t["cache_read"]/total*100:.2f}%"></span>'
        f'<span class="output" style="width:{t["output"]/total*100:.2f}%"></span>'
        f'</div>'
    )
    eff = s["cache_efficiency"]
    eff_class = "good" if eff > 0.5 else ("warn" if eff < 0.05 else "")
    duration = f"{s['duration_s']/60:.1f} min" if s["duration_s"] else "—"
    return (
        f'<div class="card">'
        f'<h3>{escape(s["session_id"][:8])}…</h3>'
        f'<div class="meta">'
        f'{escape(str(s["cwd"] or ""))} · '
        f'{escape(str(s["git_branch"] or "—"))} · v{escape(str(s["version"] or "?"))}'
        f'<br>{escape(s["first_ts"] or "?")} · {s["n_turns"]} turns · {duration}'
        f'</div>'
        f'<div class="kv">'
        f'<span class="k">fresh input</span><span class="v">{fresh:,}</span>'
        f'<span class="k">cache create</span><span class="v">{t["cache_create"]:,}</span>'
        f'<span class="k">cache read</span><span class="v">{t["cache_read"]:,}</span>'
        f'<span class="k">output</span><span class="v">{t["output"]:,}</span>'
        f'<span class="k">billed in</span><span class="v">{s["billed_input"]:,}</span>'
        f'<span class="k">cache eff</span><span class="v {eff_class}">{eff*100:.1f}%</span>'
        f'</div>'
        f'{bar}'
        f'</div>'
    )


def render_audit_section(entries: list[dict]) -> str:
    if not entries:
        return ""
    req = [e for e in entries if e.get("phase") == "request"]
    resp = [e for e in entries if e.get("phase") == "response"]
    orig_total = sum(e.get("original_bytes", 0) for e in req)
    opt_total = sum(e.get("optimized_bytes", 0) for e in req)
    delta = opt_total - orig_total
    delta_pct = (delta / orig_total * 100) if orig_total else 0

    cache_read = sum((e.get("usage") or {}).get("cache_read_input_tokens", 0) or 0 for e in resp)
    cache_create = sum((e.get("usage") or {}).get("cache_creation_input_tokens", 0) or 0 for e in resp)
    input_t = sum((e.get("usage") or {}).get("input_tokens", 0) or 0 for e in resp)
    output_t = sum((e.get("usage") or {}).get("output_tokens", 0) or 0 for e in resp)
    billed = input_t + cache_read + cache_create
    eff = (cache_read / billed) if billed else 0
    eff_class = "good" if eff > 0.5 else ("warn" if eff < 0.05 else "")

    return (
        f'<section><h2>Proxy audit log</h2>'
        f'<div class="kv" style="max-width:420px">'
        f'<span class="k">requests intercepted</span><span class="v">{len(req):,}</span>'
        f'<span class="k">responses observed</span><span class="v">{len(resp):,}</span>'
        f'<span class="k">original bytes (sum)</span><span class="v">{orig_total:,}</span>'
        f'<span class="k">optimized bytes (sum)</span><span class="v">{opt_total:,}</span>'
        f'<span class="k">delta</span><span class="v">{delta:+,} ({delta_pct:+.1f}%)</span>'
        f'<span class="k">fresh input tokens</span><span class="v">{input_t + cache_create:,}</span>'
        f'<span class="k">cache read tokens</span><span class="v">{cache_read:,}</span>'
        f'<span class="k">output tokens</span><span class="v">{output_t:,}</span>'
        f'<span class="k">cache efficiency</span><span class="v {eff_class}">{eff*100:.1f}%</span>'
        f'</div></section>'
    )


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Claude Code session report — {project}</title>
<style>
:root {{ color-scheme: dark light; }}
body {{ font: 14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif; margin: 24px; background:#111; color:#e8e8e8; }}
h1, h2 {{ font-weight: 600; }}
h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
.sub {{ color:#888; margin-bottom: 24px; }}
.summary {{ background:#1b1b1b; border:1px solid #2a2a2a; border-radius:12px; padding:20px; margin-bottom:32px; }}
.summary-grid {{ display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:20px; }}
.summary-item h3 {{ margin:0 0 4px 0; font-size:13px; color:#aaa; }}
.summary-item .big {{ font-size:28px; font-family:ui-monospace,Consolas,monospace; font-weight:600; line-height:1; }}
.good {{ color:#3ecf8e; }} .warn {{ color:#f5a524; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fill,minmax(360px,1fr)); gap: 14px; }}
.card {{ background:#1b1b1b; border:1px solid #2a2a2a; border-radius:8px; padding:14px; }}
.card h3 {{ margin: 0 0 6px 0; font-size: 14px; font-family: ui-monospace,Consolas,monospace; }}
.meta {{ color:#888; font-size:12px; margin-bottom: 10px; }}
.kv {{ display:grid; grid-template-columns: 1fr auto; gap: 2px 12px; font-variant-numeric: tabular-nums; }}
.kv .k {{ color:#aaa; }}
.kv .v {{ font-family: ui-monospace,Consolas,monospace; }}
.bar {{ height: 6px; background: #2a2a2a; border-radius: 3px; overflow:hidden; margin-top:8px; display:flex; }}
.bar > span {{ display:block; height:100%; }}
.bar .read   {{ background:#3ecf8e; }}
.bar .create {{ background:#f5a524; }}
.bar .input  {{ background:#5e5e5e; }}
.bar .output {{ background:#8a4fff; }}
.legend {{ font-size:11px; color:#888; margin-top:4px; }}
.legend span {{ display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:4px; vertical-align:middle; }}
table {{ border-collapse: collapse; width:100%; font-size: 13px; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 6px 10px; text-align: right; border-bottom:1px solid #2a2a2a; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ color:#aaa; font-weight: 500; }}
.controls {{ margin: 8px 0 14px 0; display:flex; gap:8px; align-items:center; }}
button {{ background:#2a2a2a; color:#e8e8e8; border:1px solid #3a3a3a; padding: 5px 12px; border-radius:4px; cursor:pointer; font: inherit; }}
button:hover {{ background:#333; }}
.pill {{ display:inline-block; padding: 1px 6px; border-radius: 3px; background:#2a2a2a; font-size:11px; color:#aaa; margin-right:4px; }}
.warn {{ color:#f5a524; }}
.good {{ color:#3ecf8e; }}
section {{ margin-bottom: 32px; }}
</style></head>
<body>
<h1>{project}</h1>
<div class="sub">{n_sessions} sessions · {n_turns_total} turns · generated {generated_at}</div>

<div class="summary">
  <h2>Overall Summary (all sessions in this project)</h2>
  <div class="summary-grid">
    <div class="summary-item"><h3>Unique Tokens Outputted</h3><div class="big">{total_output:,}</div><div class="legend">total generated by Claude</div></div>
    <div class="summary-item"><h3>Fresh Tokens Sent Up</h3><div class="big">{total_fresh:,}</div><div class="legend">input + cache_create (what actually cost tokens)</div></div>
    <div class="summary-item"><h3>Cache Read (Savings)</h3><div class="big good">{total_cache_read:,}</div><div class="legend">tokens served from cache</div></div>
    <div class="summary-item"><h3>Billed Input Tokens</h3><div class="big">{total_billed:,}</div><div class="legend">fresh + cache read</div></div>
    <div class="summary-item"><h3>Cache Efficiency</h3><div class="big {eff_class}">{overall_eff:.1f}%</div></div>
  </div>
</div>

<section>
<h2>5-hour window aggregation</h2>
<div class="controls">
  <button id="shift-back">◀ shift −1h</button>
  <span id="window-anchor" class="pill"></span>
  <button id="shift-fwd">shift +1h ▶</button>
  <button id="shift-reset">reset</button>
</div>
<table id="windows">
  <thead><tr>
    <th>Window start (local)</th><th>Sessions</th><th>Turns</th>
    <th>Fresh Input</th><th>Cache create</th><th>Cache read</th><th>Output</th>
    <th>Billed in</th><th>Cache eff</th>
  </tr></thead>
  <tbody></tbody>
</table>
</section>

<section>
<h2>Sessions</h2>
<div class="legend">
<span style="background:#5e5e5e"></span>fresh input
<span style="background:#f5a524"></span>cache create
<span style="background:#3ecf8e"></span>cache read
<span style="background:#8a4fff"></span>output
</div>
<div class="grid">{cards}</div>
</section>

{audit_section}

<script>
const SESSIONS = {sessions_json};
const WINDOW_HOURS = 5;
let shiftHours = 0;

function fmt(n){{ return n.toLocaleString(); }}
function pct(x){{ return (x*100).toFixed(1)+"%"; }}

function rebucket() {{
  const tsList = SESSIONS.map(s => s.first_ts).filter(Boolean).sort();
  if (!tsList.length) return;
  const earliest = new Date(tsList[0]);
  const anchor = new Date(earliest);
  anchor.setMinutes(0,0,0);
  anchor.setHours(anchor.getHours() + shiftHours);
  document.getElementById("window-anchor").textContent = "anchor: " + anchor.toLocaleString() + " (shift " + (shiftHours>=0?"+":"") + shiftHours + "h)";

  const windows = new Map();
  for (const s of SESSIONS) {{
    if (!s.first_ts) continue;
    const t = new Date(s.first_ts);
    const diffMs = t - anchor;
    const idx = Math.floor(diffMs / (WINDOW_HOURS*3600*1000));
    const winStart = new Date(anchor.getTime() + idx*WINDOW_HOURS*3600*1000);
    const key = winStart.toISOString();
    if (!windows.has(key)) windows.set(key, {{start: winStart, sessions: 0, turns: 0, fresh:0, create:0, read:0, output:0}});
    const w = windows.get(key);
    w.sessions += 1;
    w.turns += s.n_turns;
    w.fresh += s.fresh_input;
    w.create += s.totals.cache_create;
    w.read += s.totals.cache_read;
    w.output += s.totals.output;
  }}

  const rows = [...windows.values()].sort((a,b)=>a.start-b.start);
  const tbody = document.querySelector("#windows tbody");
  tbody.innerHTML = "";
  for (const w of rows) {{
    const billed = w.fresh + w.create + w.read;
    const eff = billed ? w.read / billed : 0;
    const tr = document.createElement("tr");
    const cls = eff > 0.5 ? "good" : (eff < 0.05 ? "warn" : "");
    tr.innerHTML = "<td>"+w.start.toLocaleString()+"</td><td>"+w.sessions+"</td><td>"+w.turns+"</td><td>"+fmt(w.fresh)+"</td><td>"+fmt(w.create)+"</td><td>"+fmt(w.read)+"</td><td>"+fmt(w.output)+"</td><td>"+fmt(billed)+"</td><td class='"+cls+"'>"+pct(eff)+"</td>";
    tbody.appendChild(tr);
  }}
}}

document.getElementById("shift-back").onclick = () => {{ shiftHours -= 1; rebucket(); }};
document.getElementById("shift-fwd").onclick  = () => {{ shiftHours += 1; rebucket(); }};
document.getElementById("shift-reset").onclick= () => {{ shiftHours  = 0; rebucket(); }};
rebucket();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-dir", default=str(_default_projects_dir()))
    ap.add_argument("--project", required=True, help="Project name, e.g. E--repo-claude-proxy")
    ap.add_argument("--audit", default="./claude_audit")
    ap.add_argument("-o", "--output", default="report.html")
    args = ap.parse_args()

    proj_dir = Path(args.projects_dir) / args.project
    if not proj_dir.is_dir():
        raise SystemExit(f"project not found: {proj_dir}")

    sessions = [parse_session(p) for p in sorted(proj_dir.glob("*.jsonl"))]
    sessions = [s for s in sessions if s["n_turns"] > 0]
    sessions.sort(key=lambda s: s.get("first_ts") or "")

    audit_entries = parse_audit(Path(args.audit))
    summary = render_overall_summary(sessions)

    cards = "\n".join(render_card(s) for s in sessions)
    audit_section = render_audit_section(audit_entries)

    html = HTML_TEMPLATE.format(
        project=escape(args.project),
        n_sessions=len(sessions),
        n_turns_total=sum(s["n_turns"] for s in sessions),
        generated_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        total_output=summary.get("total_output", 0),
        total_fresh=summary.get("total_fresh", 0),
        total_cache_read=summary.get("total_cache_read", 0),
        total_billed=summary.get("total_billed", 0),
        overall_eff=summary.get("overall_eff", 0),
        eff_class=summary.get("eff_class", ""),
        cards=cards,
        audit_section=audit_section,
        sessions_json=json.dumps(sessions),
    )

    out = Path(args.output)
    out.write_text(html, encoding="utf-8")
    print(f"✅ Wrote {out}  ({len(sessions)} sessions • {summary.get('total_fresh',0):,} fresh tokens • {summary.get('total_output',0):,} output tokens)")


if __name__ == "__main__":
    main()