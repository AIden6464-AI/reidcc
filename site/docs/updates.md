<span class="tag">start</span>

# Updates and uninstall

Installed copies update themselves, but only when you ask.

## Updating

When a newer release is out, the footer shows `update <version> · install`. Click it once your sessions have finished (while one runs, it says `finish your sessions first`). Reidcc downloads the update and the installer takes over. Nothing installs unless you ask.

- **settings → updates → check for updates** checks right away. Reidcc also checks every 6 hours.
- In a terminal: `reid --update`.

Updates are signed, and Reidcc checks the signature before it installs anything.

::: tip
A copy you built from source doesn't update itself. Pull and build again (see [build from source](./build-from-source)).
:::

## Uninstalling

Open Windows **Settings → Apps → Reidcc** and uninstall. The program folder, PATH entry and shortcuts go. Your own folder, `%USERPROFILE%\Reidcc`, is kept with your profiles, personas and memory, and a reinstall picks it up again.
