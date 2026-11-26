# Reidcc

## Rust readability rules (zero-degradation)

- Use plain, short variable names (`event`, `usage`, `guard`, `window`, `session`) instead of single-letter
  locals (`v`, `u`, `n`, `g`, `s`), except loop indices. Colour channels (`r`, `g`, `b`) and one-line
  closure parameters may stay short.
- Prefer private `fn` helpers over inline closures passed as `impl Fn(...)` parameters.
- Put every limit or buffer size in a named `const` at the top of the file; import Win32 constants from
  `windows_sys` instead of hardcoding hex/integers.
- Keep `py.rs` / `pyjson.rs` strictly for parity paths; new modules use `std::path::PathBuf`,
  `std::fmt::Write` (`writeln!`), and shared helpers (`now_iso()` for timestamps).
- Keep zero-dependency algorithms (FNV-1a, redmean), but name their constants and add a 1-line `///`
  comment explaining why.
- Cleanup passes go in their own commit, never mixed with feature work.
