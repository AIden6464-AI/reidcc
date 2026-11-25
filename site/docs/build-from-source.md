<span class="tag">extras</span>

# Build from source

Build Reidcc yourself.

## What you need

- [Rust](https://rustup.rs) (stable) and [Node.js](https://nodejs.org) 22.
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), installed and signed in once. Codex is optional.
- WebView2, which ships with Windows 11 and current Windows 10.

## Build

```powershell
git clone https://github.com/AIden6464-AI/reidcc
cd reidcc\rs\ui; npm ci; npm run build        # the window's UI
cd ..; cargo build --release                  # reid.exe (terminal) + Reidcc.exe (window)

# where your profiles, memory and personas live (any folder works)
mkdir "$env:USERPROFILE\Reidcc"; setx REIDCC_HOME "$env:USERPROFILE\Reidcc"
```

Open a new terminal (so it sees `REIDCC_HOME`), then run `rs\target\release\Reidcc.exe` for the window or `rs\target\release\reid.exe` for the terminal. The first run writes `reid.json` with one profile, `main`. Pick a folder, then **open gate**.

## Tests

```powershell
cd rs; cargo test --workspace
```

CI runs the same on every push.
