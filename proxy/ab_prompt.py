"""
A/B harness: run the same prompt through Claude Code with and without its
built-in system prompt / tool definitions, then compare output + token usage.

Uses only supported CLI flags (no request tampering), so it works with a
subscription login.

Usage:
    python ab_prompt.py "Explain what a mutex is in two sentences."
    python ab_prompt.py "..." --configs baseline,stripped --runs 3
    python ab_prompt.py "..." --cwd C:\\some\\empty\\dir --model sonnet

Results: printed table + ./ab_results/<timestamp>.json (full output text).
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MINIMAL_SYSTEM = "You are a helpful assistant."

# name -> extra CLI args
CONFIGS = {
    "baseline":  [],
    "no_system": ["--system-prompt", MINIMAL_SYSTEM],
    "no_tools":  ["--tools", "", "--strict-mcp-config", "--no-chrome"],
    "stripped":  ["--system-prompt", MINIMAL_SYSTEM, "--tools", "", "--strict-mcp-config", "--no-chrome"],
}

USAGE_KEYS = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"]


def run_once(claude, prompt, extra, cwd, model, timeout):
    cmd = [claude, "-p", "--output-format", "json", "--no-session-persistence", *extra]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd, timeout=timeout)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:500]}"}
    usage = data.get("usage") or {}
    return {
        "is_error": data.get("is_error", False),
        "result": data.get("result", ""),
        "usage": {k: usage.get(k, 0) for k in USAGE_KEYS},
        "total_input": sum(usage.get(k, 0) for k in USAGE_KEYS[:3]),
        "cost_usd": data.get("total_cost_usd"),
        "duration_ms": data.get("duration_ms"),
        "num_turns": data.get("num_turns"),
        "models": sorted((data.get("modelUsage") or {}).keys()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt")
    ap.add_argument("--configs", default=",".join(CONFIGS), help=f"comma list of {list(CONFIGS)}")
    ap.add_argument("--runs", type=int, default=1, help="runs per config")
    ap.add_argument("--cwd", default=None, help="working dir for claude (affects CLAUDE.md / git context)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude not found on PATH")

    names = [n.strip() for n in args.configs.split(",") if n.strip()]
    unknown = [n for n in names if n not in CONFIGS]
    if unknown:
        sys.exit(f"unknown configs: {unknown}; choose from {list(CONFIGS)}")

    results = []
    for name in names:
        for i in range(args.runs):
            print(f"running {name} #{i + 1} ...", file=sys.stderr, flush=True)
            r = run_once(claude, args.prompt, CONFIGS[name], args.cwd, args.model, args.timeout)
            r.update(config=name, run=i + 1)
            results.append(r)

    hdr = f"{'config':<10} {'run':>3} {'in':>7} {'c_write':>8} {'c_read':>8} {'total_in':>9} {'out':>6} {'cost$':>8} {'sec':>6}"
    print("\n" + hdr + "\n" + "-" * len(hdr))
    for r in results:
        if "error" in r:
            print(f"{r['config']:<10} {r['run']:>3}  ERROR {r['error']}")
            continue
        u = r["usage"]
        cost = f"{r['cost_usd']:.4f}" if r["cost_usd"] is not None else "-"
        sec = f"{r['duration_ms'] / 1000:.1f}" if r["duration_ms"] else "-"
        print(f"{r['config']:<10} {r['run']:>3} {u['input_tokens']:>7} {u['cache_creation_input_tokens']:>8} "
              f"{u['cache_read_input_tokens']:>8} {r['total_input']:>9} {u['output_tokens']:>6} {cost:>8} {sec:>6}")

    print("\n=== outputs ===")
    for r in results:
        if "error" not in r:
            print(f"\n--- {r['config']} #{r['run']} | turns={r['num_turns']} | models={r['models']} ---\n"
                  f"{r['result'].strip()}")

    out_dir = Path("ab_results")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_file.write_text(json.dumps({"prompt": args.prompt, "model": args.model, "cwd": args.cwd,
                                    "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
