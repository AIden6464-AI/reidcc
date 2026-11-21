"""Unit tests for the compact MCP toolset in mini_tools_mcp.py."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import mini_tools_mcp as m

SERVER = Path(__file__).resolve().parent.parent / "mini_tools_mcp.py"


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m._read_paths.clear()
    return tmp_path


def call(name, **args):
    r = m.call({"name": name, "arguments": args})
    return r["isError"], r["content"][0]["text"]


def write_bytes(path, data: bytes):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


# ---------- read ----------

def test_read_numbers_lines_and_reports_partial_range():
    write_bytes("a.txt", b"one\ntwo\nthree\nfour\n")
    err, out = call("read", path="a.txt", offset=2, limit=2)
    assert not err
    assert out == "2\ttwo\n3\tthree\n[lines 2-3 of 4]"


def test_read_directory_lists_entries():
    write_bytes("d/x.py", b"")
    (Path("d") / "sub").mkdir()
    assert call("read", path="d") == (False, "sub/\nx.py")


def test_read_rejects_binary():
    write_bytes("b.bin", b"\x00\x01\x02")
    err, out = call("read", path="b.bin")
    assert err and "binary" in out


def test_read_strips_bom_and_keeps_unicode():
    write_bytes("u.txt", "﻿dash — ok\n".encode("utf-8"))
    assert call("read", path="u.txt") == (False, "1\tdash — ok")


# ---------- write ----------

def test_write_new_file_then_overwrite_guard():
    assert call("write", path="new/f.txt", content="hi\n") == (False, "wrote 1 lines to new/f.txt")
    write_bytes("existing.txt", b"keep me")
    err, out = call("write", path="existing.txt", content="clobber")
    assert err and "read it before overwriting" in out
    assert Path("existing.txt").read_bytes() == b"keep me"
    call("read", path="existing.txt")
    assert call("write", path="existing.txt", content="ok")[0] is False
    assert Path("existing.txt").read_bytes() == b"ok"


def test_write_has_no_bom_and_no_newline_translation():
    call("write", path="f.txt", content="a\nb\n")
    assert Path("f.txt").read_bytes() == b"a\nb\n"


# ---------- edit ----------

def test_edit_preserves_crlf_and_returns_region():
    write_bytes("c.py", b"a = 1\r\nb = 2\r\nc = 3\r\n")
    err, out = call("edit", path="c.py", old="b = 2\n", new="b = 20\n")
    assert not err
    assert Path("c.py").read_bytes() == b"a = 1\r\nb = 20\r\nc = 3\r\n"
    assert "2\tb = 20" in out


def test_edit_ambiguous_reports_line_numbers_and_all_flag_works():
    write_bytes("x.txt", b"foo\nbar\nfoo\n")
    err, out = call("edit", path="x.txt", old="foo", new="baz")
    assert err and "matches 2 times (lines 1, 3)" in out
    err, out = call("edit", path="x.txt", old="foo", new="baz", all=True)
    assert not err and "2 replacements" in out
    assert Path("x.txt").read_text() == "baz\nbar\nbaz\n"


def test_edit_hint_whitespace_mismatch():
    write_bytes("w.py", b"def f():\n    return 1\n")
    err, out = call("edit", path="w.py", old="def f():\n  return 1", new="x")
    assert err and "Whitespace differs from lines 1-2" in out


def test_edit_hint_line_number_prefixes():
    write_bytes("n.py", b"x = 1\n")
    err, out = call("edit", path="n.py", old="1\tx = 1", new="x = 2")
    assert err and "prefixes from read" in out


def test_edit_hint_closest_match():
    write_bytes("t.py", b"def compute_total(items):\n    return sum(items)\n")
    err, out = call("edit", path="t.py", old="def compute_totals(items):\n    return sum(items)", new="x")
    assert err and "Closest match" in out and "1\tdef compute_total(items):" in out


def test_edit_rejects_empty_and_noop():
    write_bytes("e.txt", b"abc")
    assert call("edit", path="e.txt", old="", new="x")[0]
    assert call("edit", path="e.txt", old="abc", new="abc")[0]


# ---------- glob ----------

def test_glob_patterns_and_junk_skipped():
    for p in ["a.py", "src/b.py", "src/c.ts", "src/d.tsx", ".venv/lib/e.py", "node_modules/f.py"]:
        write_bytes(p, b"")
    assert call("glob", pattern="*.py") == (False, "a.py")
    _, out = call("glob", pattern="**/*.py")
    assert sorted(out.splitlines()) == ["a.py", "src/b.py"]
    _, out = call("glob", pattern="src/*.{ts,tsx}")
    assert sorted(out.splitlines()) == ["src/c.ts", "src/d.tsx"]
    assert call("glob", pattern="*.md") == (False, "no files found")


# ---------- grep ----------

def test_grep_lines_glob_filter_and_case():
    write_bytes("a.py", b"import os\nTODO fix\n")
    write_bytes("b.md", b"todo later\n")
    write_bytes(".git/x", b"TODO hidden\n")
    _, out = call("grep", pattern="todo", i=True)
    assert sorted(out.splitlines()) == ["a.py:2:TODO fix", "b.md:1:todo later"]
    assert call("grep", pattern="TODO", glob="*.py") == (False, "a.py:2:TODO fix")
    assert call("grep", pattern="todo", i=True, files_only=True, glob="*.md") == (False, "b.md")


def test_grep_context_and_bad_regex():
    write_bytes("c.txt", b"1\n2\nhit\n4\n5\n")
    assert call("grep", pattern="hit", ctx=1) == (False, "c.txt-2-2\nc.txt:3:hit\nc.txt-4-4")
    err, out = call("grep", pattern="(")
    assert err and "bad regex" in out


def test_grep_caps_matches():
    write_bytes("many.txt", b"x\n" * 300)
    _, out = call("grep", pattern="x")
    assert out.count("\n") == m.GREP_MAX
    assert "150 more matches; 300 total in 1 files" in out


# ---------- sh ----------

@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 5.1 tool")
def test_sh_unicode_and_exit_code():
    write_bytes("u.txt", "dash — ok\n".encode("utf-8"))
    assert call("sh", cmd="Get-Content u.txt") == (False, "dash — ok")
    err, out = call("sh", cmd="Write-Output hi; exit 3")
    assert err and out == "hi\n[exit 3]"


def test_clip_keeps_head_and_tail():
    text = "H" * 15000 + "T" * 15000
    out = m.clip(text)
    assert out.startswith("H" * 100) and out.endswith("T" * 100) and "omitted" in out


# ---------- MCP protocol (subprocess) ----------

def test_stdio_protocol_roundtrip():
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nope"},
    ]
    p = subprocess.run([sys.executable, str(SERVER)], input="\n".join(json.dumps(x) for x in msgs) + "\n",
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    replies = [json.loads(line) for line in p.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["read", "write", "edit", "glob", "grep", "sh"]
    assert replies[2]["error"]["code"] == -32601
