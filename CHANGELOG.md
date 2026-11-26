# NuzeHub TUI changes

## 0.2.3 (Nov 24, 2026): HUDdy Soft Contrast (stage 2)

- **HUDdy soft tokens** (Spec 1.0 §1, Template 1.1 §2.1.1). Only four tokens moved, each within 2° of its old hue:
  background `#03060b` → `#080e19`, surface `#0a1322` → `#0d192c`, panel `#0f1c30` → `#112138`, foreground
  (body text) `#d6e4f2` → `#c2cfdc`. Muted, primary/accent, secondary, success, warning, error and the eight branch
  colours are byte-identical. The 256/16-colour HUDdy maps are unchanged. No `#ffffff` is used on a HUDdy truecolor
  screen (the high-ink colour stays `#d6e4f2`); the 16-colour names are unchanged.
- **Selection rule** (Template 1.1 §2.5). `Palette.textual()` now sets `block-cursor-foreground` = background and
  `block-cursor-background` = primary for every dark theme whose background reaches 4.5:1 on its primary, so a
  focused tab, menu item or list row reads as dark text on the accent (HUDdy `#080e19` on `#5ee1ff` 12.59:1,
  GitHub Dark `#0d1117` on `#4493f8` 6.11:1). Light themes and dark themes that fail the check keep Textual's
  automatic contrast. The Markets list (`#item-list`) draws its focused, highlighted row entirely in that text
  colour, so the row's own foreground/up/down colours never sit on the accent fill.
- **Derived HUDdy colours that moved** (recomputed from the new tokens; every `btn-*` text is still >= 4.5:1 on the
  surface, the disabled label excepted as before):
  - token background: #03060b -> #080e19
  - token surface: #0a1322 -> #0d192c
  - token panel: #0f1c30 -> #112138
  - token foreground: #d6e4f2 -> #c2cfdc
  - button btn-primary-border: #238f61 -> #259368
  - button btn-primary-pressed: #63f8ba -> #5ef3b5
  - button btn-primary-pressed-bg: #0b2921 -> #0f302d
  - button btn-primary-text: #54fbb3 -> #51f8b0
  - button btn-primary-text-hover: #88f2cc -> #7ee8c2
  - button btn-neutral-border: #545b64 -> #505864
  - button btn-neutral-hover: #97a1ad -> #8a95a2
  - button btn-neutral-pressed: #a7b2be -> #98a4b0
  - button btn-neutral-pressed-bg: #181c22 -> #1a212c
  - button btn-neutral-text: #97a1ad -> #8a95a2
  - button btn-neutral-text-hover: #b0bcc9 -> #a0acb9
  - button btn-dismiss-border: #465464 -> #48576a
  - button btn-dismiss-pressed: #93a7be -> #8ea2b9
  - button btn-dismiss-pressed-bg: #141a22 -> #18212e
  - button btn-dismiss-text-hover: #a1b3c9 -> #99abc0
  - button btn-danger-border: #8e3143 -> #903449
  - button btn-danger-pressed: #f57890 -> #f0738b
  - button btn-danger-pressed-bg: #261119 -> #2b1825
  - button btn-danger-text: #f96a84 -> #f66680
  - button btn-danger-text-hover: #eb9bb0 -> #e190a5
  - button btn-disabled-text: #526274 -> #546479
  - button btn-disabled-border: #2e3744 -> #313d4d
  - pane-fallback: #275e6d -> #2a6275
  - css $accent 35% over background: #235360 -> #26586a
  - css $primary 12% over background: #0e2028 -> #122735
  - css $primary 40% over background: #275e6d -> #2a6275
  - globe style 1 (panel): #0f1c30 -> #112138
  - globe style 2 mix(muted,bg,.25): #5e7084 -> #607288
  - globe style 3 mix(muted,bg,.6): #343e4c -> #374354
  - globe ocean (surface): #0a1322 -> #0d192c
  - globe outline/edge mix(bg,primary,.4): #275e6d -> #2a6275
  - globe land mix(muted,bg,.55): #3a4554 -> #3d4a5c
  - textual var block-cursor-foreground: - -> #080e19
  - textual var block-cursor-background: - -> #5ee1ff
  - Sparklines and trend glyphs use success/error/warning directly (unchanged); Textual's own dims and darkened
    backgrounds follow the new background automatically (e.g. `#000004`).
- **Tests.** New `tests/test_soft_023.py`: soft tokens, hue guard (±2°, frozen accent/status/branches), every Spec §2
  contrast pair, buttons/no-white, the selection-token rule, and dark-on-accent text checked on the rendered screen
  (focused tab and Markets row, HUDdy and GitHub Dark). Three 0.2.2 tests that pinned the old HUDdy values now pin the
  new ones. `test_desk_offline` puts its three racing start-up ERROR lines in one fixed order (test-only; the race
  was flaky in 0.2.2 too). Snapshots regenerated deliberately (evidence/snapshot-review.md).
- Version 0.2.3 everywhere. Paste blocks: `cd ~` and a report-only pre-check first (docked, Ollama `/api/version`,
  swap); staging in `${TMPDIR:-/tmp}/nuzehub-tui-0.2.3` after it; a missing zip or wheel stops before install. The
  launcher heredoc and `remote.py` are byte-identical to 0.1.1.

## 0.2.2 (Nov 24, 2026): Polish and HUDdy

- **HUDdy.** The default theme is now called HUDdy (theme id `huddy`) in the Themes menu, the footer THEME pill, the Activity log, Help/About, the first-launch notice, the README and the paste-block printout. The colours are unchanged. A `settings.json` that saved the old id `gods-eye-hud` loads as `huddy`, and `theme_migrated_020` works as before.
- **Per-element Live Mode.** The one 0.2.1 switch is now three settings, all off by default: `live_globe` (Globe Spin, `G`), `live_ticker` (Stock Ticker, `K`) and `live_updates` (Auto-Updates, `U`). Any mix can be on.
  - A 0.2.1 file with `live_mode: true` and none of the three keys loads with all three on. `static_tape` is still ignored.
  - `L`, the LIVE chip and View > Live Mode (All) form the master switch. If anything is on, it turns everything off and remembers the mix (`live_last`). If everything is off, it restores that mix, or turns all three on if none was saved.
  - Chip: `◇ LIVE` muted when off, `◈ LIVE` when partial, `◆ LIVE` in the accent colour when full (`o` / `+` / `*` in ASCII).
  - The View menu lists each element with its check mark. Help and the Activity log name the active elements.
  - Auto-pause works as in 0.2.1, per element. Manual `r` always works.
- **Speed presets (addendum, Nov 23, 11:52 PM EST).** `live_speed` defaults to `smooth`. `S` (on the Desk) or View > Live Speed cycles eco → smooth → ultra.

  | Preset | Globe | Ticker |
  |---|---|---|
  | `eco` | +3° at 3 fps | 1 cell / 0.28 s |
  | `smooth` | +1.5° at 8 fps | 1 cell / 0.14 s |
  | `ultra` | +1° at 12 fps (capped; 15 fps measured 40.80 % CPU on a test machine, over the 40 % ceiling) | 1 cell / 0.08 s |

  Changing the speed re-creates only the spin and tape timers.
- **Auto-Update interval (addendum).** `live_update_interval` is in whole seconds, default 30. It sets the news, markets, hazards and instance/Day-dock polls; the alerts rotation stays at 7 s. `I` (on the Desk) or View > Auto-Update cycles 15/30/60/120 s. Any whole number in `settings.json` is honoured, clamped to 5..600, and other values load as 30. Changing it re-creates only the poll timers.
- **Smoother motion.** The orthographic globe rings now reuse cached per-vertex trigonometry. The output is bit-identical and a frame takes about 30% less time.
- **Smoother tab switching.**
  - A switch to the tab already showing does nothing.
  - Tab changes run in one `batch_update`.
  - The Desk repaints on return only when something changed while it was hidden.
  - Border titles, subtitles, hints, sidebar styles and row layouts are written only when they change.
- **Markets tab.** Each Watchlist-style row now shows a trend glyph (▲ up in `$success`, ▼ down in `$error`, – flat in `$text-muted`) and a coloured 12-cell sparkline. The detail pane shows a coloured change line and a 48-cell sparkline. In 256/16 colours it uses the Desk fallback colours, with ASCII `+ - =` when the output is not UTF-8.
- Version 0.2.2 everywhere. Paste blocks: version strings and the HUDdy line only. Staging is in `${TMPDIR:-/tmp}/nuzehub-tui-0.2.2`. The launcher heredoc and `remote.py` are byte-identical to 0.1.1.

## 0.2.1 (Nov 23, 2026): Live Mode

- **One Live Mode switch** (`live_mode` in `settings.json`, default off). It turns three things on or off together:
  - the globe spins +6° of longitude every 0.5 s (2 fps);
  - the MKT tape scrolls one cell every 0.5 s (2 cells/s) through the existing `Tape` widget, still starting with the biggest movers;
  - the Desk updates itself: news and hazards every 5 min, markets every 2 min, the instance and Day dock every 30 s, alerts rotate every 7 s. Switching it on refreshes any stale source.
- **Off (the default) is the calm 0.2.0 Desk.** Nothing moves or polls on its own. The startup load and `r` still work, and the clock keeps ticking without repainting unchanged chrome.
- **Auto-pause.** Spin and scroll pause behind a dialog or menu and when the terminal loses focus. Everything pauses when you leave the Desk. Turning Live Mode off stops all three at once.
- **Controls.** A `LIVE` chip beside `◀ ▶ RESET` (`◆ LIVE` in the accent colour when on, `◇ LIVE` muted when off; focus never bold), `L` on the Desk, `Live Mode` in the View menu with its check mark, an Activity line for each switch, and a Help line.
- **SITREP header.** At 120x40, `STORIES` and `GEO` no longer sit flush and `TASKS` no longer wraps onto the next row. Each label keeps a space after it when the column is narrow; wider layouts are unchanged.
- An older `settings.json` (with or without `static_tape`) loads with Live Mode off. A non-boolean `live_mode` also loads as off.
- Paste blocks: version 0.2.1 only. Staging is in `${TMPDIR:-/tmp}/nuzehub-tui-0.2.1`, with no `/Volumes/Work` step. The launcher heredoc and `remote.py` are byte-identical to 0.1.1.

## 0.2.0 (Nov 23, 2026): Desk

- **New Desk tab (key 0), now the start tab.** It brings the web OPS desk to the terminal:
  - SITREP: tiles, hazards, last brief, world developments;
  - LAYERS (Alt+1-8);
  - the map: Kitty image in Ghostty, otherwise Braille, otherwise a text table. It moves only by hand: Shift+Left/Right, the mouse wheel or the ◀ ▶ chips rotate it, Shift+Up/Down tilt it, Reset/Home recentre it (no auto-spin);
  - ALERTS, rotating every 7 s, with read-only price-move alerts;
  - INTEL FEED and the Inspector;
  - WATCHLIST;
  - the Day dock with next event, tasks, and focus 25M/50M;
  - the MKT tape, biggest movers first (largest change %, ties by symbol). It moves only by hand: focus it, then Left/Right or the mouse wheel step one item and Home goes back to the start. An older `settings.json` with `static_tape` still loads (the key is ignored);
  - FEEDS and STORIES chips and a UTC clock.
- **Ranking matches the web.** `rankStories`, `geopoliticalStories` and `computeMapData` are ported and tested against fixtures from the TS functions.
- **Refresh.** News every 10 min, quotes every 5 min, hazards every 10 min and the instance every 60 s, all only while the Desk is showing. `r` refreshes at any time. Stale data is marked (`stale 5m`) and offline data is never blanked.
- **Themes (App Design Template 1.0).**
  - God's Eye HUD is the default, with a one-time switch that keeps a saved choice.
  - GitHub Dark uses the web accent `#4493f8` and muted `#8b949e`.
  - 256- and 16-colour fallback maps.
  - Focused toggles are shown in the accent colour, not bold.
- **Performance.**
  - The 1 s Desk clock no longer re-assigns the unchanged tab-box title and subtitle. Those assignments repainted the whole tab container and the map every second, about 1.45 MB of terminal output a minute.
  - The status rows repaint only when they change.
  - The tape is its own one-line widget (`Tape`) that repaints only its row.
  - Measured idle Desk CPU: 6.36% before, about 1.7% after; see the release evidence.
- **Paste blocks.** Version 0.2.0. Staging is in `${TMPDIR:-/tmp}/nuzehub-tui-0.2.0`, with no `/Volumes/Work` steps. The blocks print the theme after first launch.
- **New dependencies:** `textual-image>=0.8` (LGPL-3.0) and `Pillow` (MIT-CMU).

## 0.1.1 (Nov 23, 2026)

- Full colour over ssh (`remote.py`) and the launcher quoting/COLORTERM fix in the a client Mac and a client Mac blocks.
- A hint when 127.0.0.1 does not answer on a client Mac.

## 0.1.0 (Nov 21, 2026)

Built by Nuzhub on a test machine and the box, Sat Nov 21, 2026, in one attempt from
`brief/NuzeHub-TUI-Brief-0.1.0.md`. No changes to the server, no paste runs, no GitHub push.

### Built
- `nuzehub-tui` (pipx wheel + sdist; Python 3.11–3.13; Textual 8.2.8 and Rich 14.3.4 at test time). It has a key
  gate, the six screens (1 News, 2 Markets, 3 GEO list, 4 Brain, 5 Wikipedia, 6 Status), the File, View,
  Wikipedia, Themes and Help menus, and the Cite, Save, Theme, Help and About dialogs. Keys: r, t/T, b, A, ?, /,
  c, s, u, Esc, 1–6 and F10. `q` never quits from a dialog or the gate. `--check`, `--demo` and `--url` are
  supported.
- Chrome is copied from SSHush 0.7.0 / 1.0.0 (themes.py, dlayout.py, menubar.py, CSS): 22 themes, with GitHub
  Dark as the default (Decision A). A saved theme is left alone.
- **No /api/tui facade (Decision C).** The client calls NuzeHub's TanStack server functions directly:
  `POST /_serverFn/<id>`, a seroval body and a same-origin `Origin` header. Ids are discovered from
  `/src/lib/<module>` if the id scheme ever changes. This was checked against a booted NuzeHub tree.
- **Decision B:** the TUI runs on the server against 127.0.0.1:8080. a client Mac and a client Mac get `nuzehub-remote`,
  which is `/usr/bin/ssh -t nuzehub-server '$HOME/.local/bin/nuzehub-tui'` (or `nuzehub.example` when there is no
  `nuzehub-server` ssh alias).
  - **LaunchAgent bind address: 0.0.0.0:8080.** The LaunchAgent runs `npm run dev`, which is
    `vite dev --host 0.0.0.0 --port 8080`, and vite.config sets `server.host "0.0.0.0"` with `strictPort`.
  - I read this from NuzeHub's package.json and vite.config and from the plist generator in the boot-fix
    deliverable. The live the server plist was not read (no the server access).
  - The listen address is unchanged.
- **Decision D: /api/model-status is served by the production LaunchAgent.** It is vite dev-server middleware
  (`modelStatusPlugin`, `apply: "serve"`), and the LaunchAgent is that dev server. It answers on loopback only.
  The TUI calls it only on loopback and otherwise falls back to `probeEngines`.
- Ollama comes first. The model chip shows "Ollama · N models" in the normal colour; LM Studio appears only as
  the fallback (warning colour) when Ollama is down.
- Wikipedia results are pinned to the library named by `brain wiki status` (a TUI-side check on top of the
  server's check). When the library is off, missing or mismatched, the TUI clears the results, keeps the query
  and says what to do.
- Cite uses a note picker plus "New note" (Decision F). A note cites an article only once.
- Save to Brain files the note in Resources with the tag `wikipedia`.
- Undo writes the earlier Brain back with `baseRev`; a conflict reloads instead of overwriting.
- The host key is never shown, logged or saved. `accessStatus`'s `key` is dropped, and `?key=` URLs are
  refused without being echoed.
- **Carry-in fix:** `nuzehub-wiki-panel-decoy-test.diff` for NuzeHub's `src/lib/brain/wiki-panel.test.ts`.
  - The decoy regression now expects the CLI to report the library off or missing and the panel to show
    "unavailable", with no decoy rows.
  - Decoys are planted at `$HOME/SecondBrain-data/wiki/` (temp HOME) and at `/Volumes/Work/...` only when Work is
    writable and holds no library; otherwise the launcher's intercepted default is used.
  - Results:
    - Before the fix, against SB 1.0.2: 228/229 (the old decoy test failed).
    - After the fix, against SB 1.0.2: 229/229 for src and 200/200 for scripts, and `tsc --noEmit` is clean.
    - The new test fails against pre-1.0.2 Second Brain ("the CLI answered from a decoy"), as it should.
  - This is a diff only. It is not applied to any NuzeHub checkout.

### Fixes found during the build (each shown failing first)
- A saved non-default theme made the theme Select and the app swap themes back and forth (312 switches in a
  short session, about 5 s per key). `test_saved_theme_does_not_ping_pong` failed before the fix (see
  `evidence/pingpong-before.txt`) and passes after it.
- `_log` and `action_back` shadowed Textual's own methods (mypy caught it). They are renamed `_note` and
  `action_wiki_back`.

### Not built / gaps
- News ranking: NuzeHub ranks stories in the browser (`rankStories`) and has no server function for it, so the
  TUI lists stories newest first.
- The globe and map, chat/AI features and anything outside the brief's MVP list are not built (out of scope).
- No the server install was done. The paste blocks are for David to run after Brainstorm verifies.

### Tests
- a test machine (Python 3.13.18, textual 8.2.8, rich 14.3.4): **65 passed, 2 skipped**. The 2 skips are the
  live tests, which need a scratch server. The 65 include:
  - 17 snapshots: every tab, main at 80x24 and 70x24, 5 menus, the gate, Cite, Save and the theme dropdown;
  - border fit at 80x24, 120x40 and 200x50;
  - button widths at 120x40, 100x30, 80x24 and 70x24;
  - client handlers (denied, unlock, timeout, unreachable, id discovery, CSRF);
  - Wikipedia (off, missing, mismatched, vanishing, ssh, decoy);
  - state flows (repeated runs, switching, stale instance, wiki cleared, Save→Undo byte-for-byte, Cite twice,
    `q` in dialogs, gate);
  - CLI and path rules.
- `ruff check src tests` is clean, and `mypy src` reports no issues. Swap is 0.00M before and after every run.
- Wikipedia decoy test with `/Volumes/Work` present: a scratch disk image named Work was mounted on a test machine,
  so the decoy sat at the real `/usr/local/var/second-brain/wiki/wikipedia.sqlite` as well as at
  `$HOME/SecondBrain-data/wiki/` (temp HOME). Result: 6/6 passed (`evidence/wiki-decoy-with-volumes-work-image.txt`).
- Live end to end, once, against a booted NuzeHub tree: a scratch dev server on the build box with Second
  Brain 1.0.2, a synthetic library and decoys. Result: 2/2 passed (`evidence/live-run.txt`). This covered every
  handler, Save→Undo byte-for-byte on the real server, Cite twice, and the primary renamed away (no decoy rows;
  unavailable).
- Paste blocks: all 3 Macs were tested on a test machine with Work absent, read-only and writable (disk image).
  Result: 9/9 PASS (`evidence/paste-block-tests/`). scp and ssh were local stand-ins in a copy of each block;
  pipx went to a scratch PIPX_HOME.
  - Since that run, the only change was a comment line in the a client Mac and a client Mac launchers; `zsh -n` is
    clean.
- Ghostty: real screenshots at 120x40 and 80x24 are in `visual-check/shots/` (7 shots per size).
  `visual-check/compare.py` gives OK for all 10 checks: the chrome rows match SSHush 0.7.0's 01/02/03 captures,
  the window size is the same, and the pane background is GitHub Dark #0d1117.
  - The 07-cite shot shows the "Open an article first, then Cite." notice rather than the dialog (the script
    does not open an article). The Cite dialog is covered by its snapshot.
- Carry-in (NuzeHub): with Second Brain 1.0.2, `npm test` gives src 229/229 and scripts 200/200, and
  `tsc --noEmit` is clean (`evidence/nuzehub-npm-test-with-sb-1.0.2.txt`).

### Could not verify
- The real 53 GB library, the real LaunchAgent on the server (its plist, a restart, the bind address as loaded) and a
  real ssh session to the server. These are all the server-only.
- The live end-to-end run used a scratch NuzeHub dev server (the wiki-panel branch tree plus Second Brain 1.0.2
  with a synthetic library and decoys) on the build box, not on a test machine.
- `/api/model-status` was confirmed from source and from that scratch dev server, not from the server.
- Whether David's Macs have an `nuzehub-server` ssh alias (the client block falls back to `nuzehub.example`).

0.2.3: GO
