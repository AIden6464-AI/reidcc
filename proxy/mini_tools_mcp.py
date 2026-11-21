"""
Compact Claude Code toolset: read, write, edit, glob, grep, sh.
Dependency-free stdio MCP server (JSON-RPC, one message per line).

Design goal: short tool descriptions, with the "smarts" in the tool results
(fuzzy hints on failed edits, edited-region echo, head+tail truncation) so the
model needs fewer retries instead of more instructions.

Used by claude-mini.cmd via mini-mcp.json.
"""
import difflib
import json
import os
import re
import subprocess
import sys

JUNK = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".tox"}
MAX_OUT = 20000        # chars per tool result
READ_LIMIT = 2000      # default lines per read
LINE_MAX = 2000        # chars per line in read output
LIST_MAX = 200         # glob results
GREP_MAX = 150         # grep matches
GREP_FILE_MAX = 2_000_000
DEFAULT_TIMEOUT, MAX_TIMEOUT = 120, 600

# Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI and writes stdout in the
# OEM codepage; force UTF-8 both ways so non-ASCII text survives.
PS_PREFIX = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;"
             "$PSDefaultParameterValues['Get-Content:Encoding']='UTF8';")


def _obj(props, required):
    return {"type": "object", "properties": props, "required": required}


S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}

# Descriptions only where the name + parameters don't already say it. Tested: these
# tools pass the multi-file e2e task even with ALL descriptions empty; the rest of
# the guidance is delivered in tool results (errors/hints) when it's actually needed.
TOOLS = [
    {"name": "read",
     "description": "Lines are prefixed 'N<tab>'; the prefix is not file content. Also lists directories.",
     "inputSchema": _obj({"path": S, "offset": I, "limit": I}, ["path"])},
    {"name": "write",
     "description": "",
     "inputSchema": _obj({"path": S, "content": S}, ["path", "content"])},
    {"name": "edit",
     "description": "old must match exactly once unless all=true.",
     "inputSchema": _obj({"path": S, "old": S, "new": S, "all": B}, ["path", "old", "new"])},
    {"name": "glob",
     "description": "",
     "inputSchema": _obj({"pattern": S, "path": S}, ["pattern"])},
    {"name": "grep",
     "description": "Regex.",
     "inputSchema": _obj({"pattern": S, "path": S, "glob": S, "i": B, "ctx": I, "files_only": B}, ["pattern"])},
    {"name": "sh",
     "description": "PowerShell 5.1.",
     "inputSchema": _obj({"cmd": S, "timeout": I}, ["cmd"])},
]


class ToolError(Exception):
    pass


_read_paths = set()  # files read/written this session (write-guard)


# ---------- helpers ----------

def _key(path):
    return os.path.normcase(os.path.abspath(path))


def _rel(path):
    try:
        r = os.path.relpath(path)
    except ValueError:  # other drive
        return path
    return path if r.startswith("..") else r.replace("\\", "/")


def clip(text, limit=MAX_OUT):
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...[{len(text) - limit} chars omitted]...\n{text[-half:]}"


def _is_binary(path):
    with open(path, "rb") as f:
        return b"\0" in f.read(8192)


def load(path):
    if not os.path.isfile(path):
        raise ToolError(f"no such file: {path}")
    if _is_binary(path):
        raise ToolError(f"binary file: {path}")
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        return f.read()


def save(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:  # no BOM, no newline translation
        f.write(text)


def numbered(lines, start):
    return "\n".join(f"{i}\t{line[:LINE_MAX]}" for i, line in enumerate(lines, start))


def glob_regex(pattern):
    out, i = "", 0
    pattern = pattern.replace("\\", "/").removeprefix("./")
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
            continue
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
            continue
        c = pattern[i]
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{" and "}" in pattern[i:]:
            j = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(x) for x in pattern[i + 1:j].split(",")) + ")"
            i = j + 1
            continue
        else:
            out += re.escape(c)
        i += 1
    return re.compile(out + r"\Z", re.IGNORECASE)


def walk(root):
    if os.path.isfile(root):
        yield root
        return
    if not os.path.isdir(root):
        raise ToolError(f"no such path: {root}")
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in JUNK)
        for f in sorted(files):
            yield os.path.join(d, f)


def _posix_rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/") if os.path.isdir(root) else os.path.basename(path)


def edit_hint(text, old):
    """Explain why `old` wasn't found: line-number prefixes, whitespace, or closest match."""
    target = old.replace("\r\n", "\n").strip("\n").split("\n")
    if target and all(re.match(r"^\s*\d+\t", t) for t in target):
        return " old looks like it includes the 'N<tab>' prefixes from read; remove them."
    lines = text.splitlines()
    k = len(target)
    if not lines or k == 0:
        return ""
    stripped = [t.strip() for t in target]
    joined = "\n".join(target)
    best_r, best_i = 0.0, -1
    for i in range(max(len(lines) - k + 1, 1)):
        window = lines[i:i + k]
        if [w.strip() for w in window] == stripped:
            return f" Whitespace differs from lines {i + 1}-{i + k}:\n" + numbered(window, i + 1)
        sm = difflib.SequenceMatcher(None, "\n".join(window), joined, autojunk=False)
        if sm.real_quick_ratio() <= best_r or sm.quick_ratio() <= best_r:
            continue
        r = sm.ratio()
        if r > best_r:
            best_r, best_i = r, i
    if best_r >= 0.6:
        return (f" Closest match ({best_r:.0%}) at lines {best_i + 1}-{best_i + k}:\n"
                + numbered(lines[best_i:best_i + k], best_i + 1))
    return ""


# ---------- tools ----------

def t_read(a):
    path = a["path"]
    if os.path.isdir(path):
        entries = sorted(os.listdir(path), key=str.lower)
        out = [e + ("/" if os.path.isdir(os.path.join(path, e)) else "") for e in entries]
        return clip("\n".join(out) or "(empty directory)")
    text = load(path)
    _read_paths.add(_key(path))
    lines = text.splitlines()
    if not lines:
        return "(empty file)"
    start = max(int(a.get("offset") or 1), 1)
    limit = max(int(a.get("limit") or READ_LIMIT), 1)
    chunk = lines[start - 1:start - 1 + limit]
    if not chunk:
        return f"(offset {start} is past end; file has {len(lines)} lines)"
    end = start + len(chunk) - 1
    footer = f"\n[lines {start}-{end} of {len(lines)}]" if (start > 1 or end < len(lines)) else ""
    return clip(numbered(chunk, start) + footer)


def t_write(a):
    path, content = a["path"], a["content"]
    if os.path.exists(path) and _key(path) not in _read_paths:
        raise ToolError(f"{path} exists; read it before overwriting (or use edit)")
    save(path, content)
    _read_paths.add(_key(path))
    return f"wrote {len(content.splitlines())} lines to {path}"


def t_edit(a):
    path = a["path"]
    text = load(path)
    old, new, replace_all = a["old"], a["new"], bool(a.get("all"))
    if not old:
        raise ToolError("old is empty; use write to create a file")
    if old == new:
        raise ToolError("old and new are identical")
    if "\r\n" in text:  # match the file's CRLF convention
        old = old.replace("\r\n", "\n").replace("\n", "\r\n")
        new = new.replace("\r\n", "\n").replace("\n", "\r\n")
    n = text.count(old)
    if n == 0:
        raise ToolError("old not found." + edit_hint(text, old))
    if n > 1 and not replace_all:
        at = [text.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(old), text)]
        raise ToolError(f"old matches {n} times (lines {', '.join(map(str, at[:20]))}); "
                        "add surrounding context or set all=true")
    first_line = text.count("\n", 0, text.index(old)) + 1
    new_text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    save(path, new_text)
    _read_paths.add(_key(path))
    lines = new_text.splitlines()
    s = max(first_line - 3, 1)
    e = min(first_line + new.count("\n") + 3, len(lines))
    count = n if replace_all else 1
    return f"edited {path} ({count} replacement{'s' if count > 1 else ''}):\n" + numbered(lines[s - 1:e], s)


def t_glob(a):
    root = a.get("path") or "."
    rx = glob_regex(a["pattern"])
    hits = [f for f in walk(root) if rx.match(_posix_rel(f, root))]
    if not hits:
        return "no files found"
    hits.sort(key=os.path.getmtime, reverse=True)
    out = [_rel(f) for f in hits[:LIST_MAX]]
    if len(hits) > LIST_MAX:
        out.append(f"...[{len(hits) - LIST_MAX} more; narrow the pattern]")
    return "\n".join(out)


def t_grep(a):
    try:
        rx = re.compile(a["pattern"], re.IGNORECASE if a.get("i") else 0)
    except re.error as e:
        raise ToolError(f"bad regex: {e}")
    root = a.get("path") or "."
    fglob = a.get("glob")
    gx = glob_regex(fglob) if fglob else None
    ctx = max(int(a.get("ctx") or 0), 0)
    files_only = bool(a.get("files_only"))

    out, shown, total, files_hit = [], 0, 0, 0
    for f in walk(root):
        if gx:
            rp = _posix_rel(f, root)
            if not (gx.match(rp) or ("/" not in fglob and gx.match(os.path.basename(f)))):
                continue
        try:
            if os.path.getsize(f) > GREP_FILE_MAX or _is_binary(f):
                continue
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        matched = [i for i, line in enumerate(lines) if rx.search(line)]
        if not matched:
            continue
        files_hit += 1
        total += len(matched)
        if files_only:
            out.append(_rel(f))
            continue
        if shown >= GREP_MAX:
            continue
        want = sorted({j for i in matched for j in range(max(i - ctx, 0), min(i + ctx + 1, len(lines)))})
        hit_set, prev = set(matched), None
        for j in want:
            if shown >= GREP_MAX:
                break
            if ctx and prev is not None and j != prev + 1:
                out.append("--")
            sep = ":" if j in hit_set else "-"
            out.append(f"{_rel(f)}{sep}{j + 1}{sep}{lines[j][:300]}")
            shown += j in hit_set
            prev = j
    if not files_hit:
        return "no matches"
    if not files_only and total > shown:
        out.append(f"...[{total - shown} more matches; {total} total in {files_hit} files. Narrow the search]")
    return clip("\n".join(out))


def t_sh(a):
    timeout = min(max(int(a.get("timeout") or DEFAULT_TIMEOUT), 1), MAX_TIMEOUT)
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_PREFIX + a["cmd"]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"timed out after {timeout}s")
    out = (p.stdout + p.stderr).strip() or "(no output)"
    if p.returncode != 0:
        raise ToolError(clip(f"{out}\n[exit {p.returncode}]"))
    return clip(out)


HANDLERS = {"read": t_read, "write": t_write, "edit": t_edit, "glob": t_glob, "grep": t_grep, "sh": t_sh}


# ---------- MCP plumbing ----------

def call(params):
    fn = HANDLERS.get(params.get("name"))
    if not fn:
        raise ValueError(f"unknown tool {params.get('name')}")
    try:
        return {"content": [{"type": "text", "text": fn(params.get("arguments") or {})}], "isError": False}
    except (ToolError, OSError, KeyError, ValueError, TypeError) as e:
        msg = str(e) if isinstance(e, ToolError) else f"{type(e).__name__}: {e}"
        return {"content": [{"type": "text", "text": msg}], "isError": True}


def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mini", "version": "3"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call(params)
    if method == "ping":
        return {}
    raise LookupError(method)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:  # notification
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except LookupError as e:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"method not found: {e}"}}
        except Exception as e:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
