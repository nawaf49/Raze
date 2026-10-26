# Working on Raze

Read this before changing anything. It exists so a person or an AI picking the
project up cold has every decision that is not obvious from the code.

## What it is

A Windows auto-typer shipped as a single `Raze.exe`. The user keeps a pool of
messages, presses one global hotkey, and Raze types them into whatever
application currently has focus, one per interval, with Enter after each.

The visual direction is original — pure
black, quiet, premium, no chrome. Everything else here is original.

## Two repos

| Repo | Holds |
| --- | --- |
| `nawaf49/Raze-source` (private) | Everything: source, assets, this file, the source-side `README.md` |
| `nawaf49/Raze` (public) | Downloads only: `README.md`, `app_icon.png`, and Releases carrying the exe |

- **The public repo is never cloned.** It is driven through the GitHub API with
  `gh`: read the file's `sha`, base64 the new bytes, build a JSON payload, then
  `gh api -X PUT repos/.../contents/... --input payload.json`. Write the payload
  with `ConvertTo-Json` and a UTF8-without-BOM writer.
- **The exe never enters git, in either repo.** It ships as a Release asset and
  is gitignored here.
- **The public repo's history is one squashed commit plus plain README edits.**
  It used to be a dozen commits whose messages narrated their own changes —
  `simpler wording`, `center the title`, `App icon for the README title`. The
  user's objection: "people will say this is ai". It was squashed rather than
  edited one message at a time because every message in there was the same
  species, then force-pushed. Tags are separate refs, so the Release and its
  asset survived untouched. An edit since then is one API commit carrying a
  plain message (`README`); squashing it back to a single commit would mean
  cloning the repo and force-pushing, which the user declined at v1.7.
- The `README.md` in **this** repo is the developer-facing one: it carries
  *Build from source* and *Credits*, which the public one deliberately omits.
  They are not copies of each other. Fix drift by editing whichever is wrong —
  never by copying one over the other.

## Commit messages

Plain and unadorned: `README`, `resume hotkey`, `fix profile folder name`,
`agent notes`. **Never describe what you changed.** Multi-line messages go in a
file passed as `git commit -F file` — a bare multi-line `-m` is parsed as a
pathspec and fails confusingly.

## Hard rules

These are not preferences. Breaking one silently ruins the product.

1. **Nothing personal inside the exe.** Settings and history live in
   `%APPDATA%\Raze\config.json`, per user. Deleting the exe must never delete
   a user's data.
2. **One instance per user**, via the mutex
   `Local\Raze.AutoTyper.SingleInstance.<username>`. A second launch focuses
   the first instead of opening another window.
3. **Runs 24/7 for years.** Monotonic clock (`time.monotonic`, never
   `time.time` for intervals), guarded heartbeat, caches that are capped.
4. **All UI text is baked artwork.** No `tk.Label` ever renders text directly.
5. **Character delay is 0.** Message interval is whole seconds. Auto-enter is
   always on. These are product decisions, not omissions.
6. **No new runtime dependencies.** The exe must stay a single self-contained
   file. This is why the Windows notification is ctypes rather than a library.
7. **Testing never touches the user's desktop.** See *Testing protocol*.

## File map

| File | What it is |
| --- | --- |
| `AutoTyper.py` | Everything: UI, typing engine, heartbeat, config, Win32 bindings |
| `textengine.py` | Renders text to transparent PNGs (baked artwork) |
| `hotkeys.py` | Global hotkey listener, its own thread, never touches Tk |
| `selftest.py` | 83 headless checks, run via `Raze.exe --selftest` |
| `pause_and_toast.py` | 38 checks: pause/resume/toast routing, the session card's contents, the loop counter and a held notification against a real window |
| `layout_check.py` | 24 checks: the window fits the work area, the four keycaps, the hotkeys card and button hover backgrounds, captures both tabs |
| `capture_window.py` | PrintWindow helper `layout_check.py` uses; never touches the screen |
| `build_assets.py` | Regenerates `assets/` artwork from source |
| `make_shortcut.py` | Start Menu + Desktop shortcut "Raze" |
| `AGENTS.md` | This file — read it first |
| `README.md` | The **source-side** readme, not the public one. See *Two repos* |
| `app_icon.png` | The dark tile; the public README title references it by this exact name |
| `raze_emblem_src.png` | Source artwork the emblem is generated from |
| `hooks/hook-PIL.Image.py` | Trims Pillow to the one codec we use. See *Build* |
| `assets/` | Emblem, background, the 5 Geist faces + `OFL.txt`, `raze.ico` |

## The palette

Baked into `AutoTyper.py`. Any new UI must use these, not ad-hoc colours.

```
BG        #000000   pure black, never lighten it
SURFACE   #0d0d10
SURFACE_2 #141418
TEXT      #f6f6f8
MUTED     #a1a1aa
FAINT     #71717a
BORDER    #1e1e23
BORDER_2  #2c2c33
BLUE      #2f6bff
GREEN     #22c55e   typing state only
AMBER     #f59e0b   warnings and refusals only
```

Layout constants: window `1060x860`, nav `68` high, content from `y=96`.
`TICK_MS = 50` (heartbeat), `SAVE_EVERY = 60`, `HISTORY_KEEP = 200`.

## Scaling and fitting

The process is DPI aware and draws everything through **one** factor, `S`
(device pixels per design pixel: 1.0 at 100%, 1.25 at 125%, …). `S` is fixed
at import and then **clamped to fit the screen**: `_fit_scale(S, *_work_area())`
shrinks it until `WIN_W*S + FRAME_W` and `WIN_H*S + FRAME_H` fit the primary
monitor's work area, floored at `SCALE_MIN = 0.5`. The design is a fixed
1060x860 and the window is not resizable, so without the clamp a 1366x768
laptop or a 1080p screen at 125% simply loses the session card and the footer
off the bottom edge with no way to reach them. Everything — `px()`, CTk
scaling, baked artwork — rides on `S`, so shrinking it takes the whole app
down together, still sharp.

- `RAZE_SCALE` env var sets `S` exactly and **bypasses the clamp** — a
  debugging hatch for geometry tests, never set it for a real user.
- `_work_area()` is `SPI_GETWORKAREA` on the primary monitor (taskbar
  excluded), `GetSystemMetrics` as fallback, `1920x1080` as last resort.
  `_center_window` centres against it too, or the bottom edge hides under
  the taskbar.
- **The device/design pixel rule.** Everything written in the code is design
  px; `px()` converts once, at the boundary. Two boundaries exist:
  - **plain tk widgets** (`tk.Frame`, `tk.Label`, `BakedLabel`, and every
    raw `self.root.tk.call("place", …)`) are NOT scaled by customtkinter —
    pass them `px(...)` device px.
  - **CTk widgets** scale their own `configure(width=…)`, `place` x/y and
    `pack`/`grid` padx/pady by `S` — pass them **design px, never
    `px()`**. A `px()` inside a CTk pack doubles the offset at 150%.
  - `CTkToplevel.geometry()` scales the `WxH` string but passes `+x+y`
    through raw — design px for the size, device px for the position.
  - `winfo_reqwidth()/winfo_width()` always report **device px**. If the
    value feeds design-px arithmetic (nav layout, tab centres), divide it
    by `S` first. `winfo_rootx/y()` diffs are device px and belong on raw
    tk `place_configure` calls as-is.
- The opening animation places widgets at their travel start (`x+dx, y+dy`)
  and settles them in `_play_intro`. Its reduce-motion branch must settle
  them too, or users with "turn off unnecessary animations" on get a
  permanently 10–18 px offset interface.

## Baked text

`textengine.render()` rasterises a string to a transparent PNG and returns a
`tk.PhotoImage`. Wrapped by `BakedLabel`.

- **Why:** ClearType fringes. Rasterised art is crisp at any size.
- **Gotcha:** `BakedLabel` keeps its text in `self._text`. `cget("text")` will
  NOT reflect `set_text()`. Always read `_text` in tests.
- **The label's `bg` must always be the fill it is standing on.**
  `BakedButton._on_enter` lightens the pill's `fg_color`, but the artwork keeps
  the rest colour painted behind the glyphs — a stale rectangle that read as a
  dark box around every button label on hover. `BakedLabel.sync_bg()` re-resolves
  the background from the parent and is called from `_on_enter`/`_on_leave`;
  `layout_check` asserts the label matches its fill in both states.
- The cache is capped. Do not let it grow unbounded — this app runs forever.
- The font is Geist, 5 faces, bundled with `--add-data "assets;assets"` —
  with `OFL.txt`, which the licence requires to travel with the font. Geist has
  no display cut, so weights are `Regular`/`Medium`/`SemiBold`/`Bold`/
  `ExtraBold` and nothing else. The medium and semibold files carry their own
  family names (`Geist Medium`), which is what `FONT_MED`/`FONT_SB` resolve to
  in Tk after `register_fonts()` loads them privately.

## Typing

`SendInput` through ctypes. The `INPUT` struct is **exactly 40 bytes** on x64
and `selftest` asserts it. `GetForegroundWindow` needs
`restype = ctypes.c_void_p` or the handle is truncated and the guard never
matches.

- ASCII goes out character by character.
- Non-ASCII is copied to the clipboard and pasted (`Ctrl+V`), never typed,
  because `KEYEVENTF_UNICODE` is not honoured by every application.

## Hotkeys

`GetAsyncKeyState` polled at **8 ms** on a dedicated thread. Chosen over
`RegisterHotKey` because it does not steal keys from the focused application
and it never competes with Tk for the GIL.

- The listener **only ever adds** bindings. Changing a key must also call
  `remove_hotkey` on the old one or it stays armed beside the new one. This is
  what `_retire()` does. It bit us once.
- Four keys: `start_key` (F8), `pause_key` (F6), `resume_key` (F7),
  `stop_key` (F9). All rebindable. `_others_own()` refuses a key another
  action already has, because registration order would otherwise let the last
  one silently win.
- **The keys are not each other's aliases.** Pause only ever pauses and resume
  only ever resumes: F6 may not wake what it put to sleep, and F8 does nothing
  at all to a paused session. The user was explicit — "the hotkeys aren't
  meant for each other". This is why `_start()` opens with a `paused` guard
  and why `_pause_requested` is no longer a toggle.
- The listener must **never touch Tk**. It sets `_start_requested` /
  `_stop_requested` / `_pause_requested` / `_resume_requested` and the
  Tk-thread heartbeat consumes them. That is the only thread boundary in the
  app.

## Focus guard

Raze must never type into itself, and must never type into "whatever Windows
handed focus to".

- `_focus_refused()` checks whether Raze is the foreground window and, if so,
  writes the `TAB OUT` amber message and returns `True`. It also captures
  `self._raze_hwnd`, because the worker thread cannot read Tk.
- `_start()` and `_resume()` both take this guard. Resuming begins typing, so
  it needs exactly the protection starting has.
- Mid-run, `_typing_worker` re-checks **before every message, never during
  one**. If Raze is in front it sets `_tab_in_stop` and breaks, so a tab-back
  cannot dump keystrokes into our own message pool.

## Pause

Pause is not a lighter stop. Its entire value is that it keeps the session.

- `_pause()` sets `paused = True` **before** `stop_event.set()`. The worker's
  `finally` then finds `paused` and stays silent — otherwise the main loop
  would read the exit as the run ending and call `_stop()`, throwing the
  session away.
- The one exception: if `_tab_in_stop` is also set, the worker does raise
  `_worker_done`. Tabbing back in outranks a pause.
- `_pause()` freezes `stats["elapsed"]` and nulls `_session_start`, so the
  heartbeat stops advancing the clock. `_resume()` restores
  `_session_start = now - elapsed` and picks up where it left off.
- `_stop()` clears `paused`.
- **`_tick_inner` ordering is load-bearing.** `_pause_requested` must be
  consumed *before* `_worker_done`, because the flag hand-off only works if
  `paused` is already set when the worker reads it. `_resume_requested` sits
  immediately after it; it has no such hazard, because a plain pause never
  raises `_worker_done` for it to race with.
- The heartbeat's live-status block has to skip while paused. Pause
  deliberately leaves `typing` set, so that block would overwrite
  `Paused`/amber with `Typing`/green a few milliseconds later. It did.

## Tabs

Switching a tab must never wait. `show()` lifts the view and marks the
label first; `_slide_tab` then travels the underline across (`mid - 12`
under the chosen tab, tracked in `_underline_x`) and lets the view rise
`TAB_RISE` 10 px into place over `TAB_MOVE_MS` 170 ms, ease-out cubic —
polish on an already-done turn, so no click is ever delayed by it.

- The stutter the user called choppy was the *first* click on Hotkeys or
  History paying for their ~110 ms build out of the click itself. Both are
  now built by `_warm_views`, `TAB_WARM_MS` 1.5 s after start-up while the
  interface is idle, and tucked under the open view — `show()` still only
  builds on demand if a click beats the timer.
- `_tab_anim` is a token: every switch supersedes a travel in flight, so
  rapid clicking starts each trip from wherever the last one reached, and
  the view that wins is always raised *from* the offset (it is lowered
  while it loses, so the snap is never seen). A losing view settles to
  zero the next time it opens.
- Two guards hand straight to the settled positions: Windows' "turn off
  unnecessary animations" (`reduce_motion_enabled`) and the opening
  sequence (`_intro_done`, set by `_play_intro` in every path), which owns
  the underline until it finishes — otherwise both loops would write it.
- The committed harnesses set the first guard, so `layout_check` only ever
  sees final geometry. The travel itself was checked by a one-off in
  `%TEMP%\opencode\tab_slide_check.py`, which stands the intro down
  instead (alpha stays 0) and leaves motion on.

## Restore

Bringing the window back after a minimise (F8's `_launch`, the minimise
button, or the user's own Win+Down) used to look like it "loads choppy on
tab-back": showing the window repaints ~120 child windows at once, and
Windows presents that work to the screen as it finishes — the interface
assembling itself piece by piece. Measured on a real restore: 150–490 ms of
stalls spread over the first half second.

- **A plain exposure is not the storm.** Tabbing away and back without
  minimising repaints the whole client in under 8 ms — measured with an
  explicit `InvalidateRect`, which raised no stalls at all. Only the
  *map/restore* path pays, which is why the fix hangs off `<Map>` and not off
  focus.
- **The fix is a drain, not a redesign.** `_on_map` (bound in `__init__`)
  drops the window to alpha 0, then `_restore_poll` calls `root.update()`
  every `RESTORE_POLL_MS` (50 ms) and asks Tk for everything it still owes.
  Two polls back under `RESTORE_QUIET_MS` (8 ms) mean the paint has actually
  stopped, and only then is alpha put back to 1.0. The repaint happens while
  nobody can see it, so the window appears complete instead of in pieces.
  `RESTORE_MAX_MS` (1500 ms) caps the invisible period whatever a
  pathological restore does. Result: **0 ms of stall after the reveal** on
  every run, against 150–490 ms before.
- **The guards matter more than the drain.** `<Map>` on the root fires for
  every descendant too (the tag is inherited), so `_on_map` returns unless
  `event.widget is self.root`. It also returns unless `_restore_drain` is set
  — armed by `<Unmap>` (`_on_unmap`) and explicitly in `_launch`/`_minimize`
  — and unless `_intro_done`, which owns the window during the opening
  sequence. **The alpha read is the test guard**: a harness keeps the window
  at alpha 0, so `_on_map` refuses to touch it and no suite can ever surface a
  window or run a drain.
- The cost is *per child window and its content*, not our own Python: 120
  plain `tk.Frame`s repaint in ~70 ms, the same 120 as CTk frames in ~198 ms,
  and the real window in ~187 ms; roughly half the drain's wall time is
  process CPU and half is waiting on Windows. A rebuild in plain Tk would buy
  ~130 ms and cost the whole look — not worth it. One-off probes for all of
  this are in `%TEMP%\opencode` (`minimize_probe.py`, `adaptive_drain.py`,
  `paint_compare.py`, `ship_check.py`, …).
- `_restore_poll` runs from an `after` and calls `root.update()`, which
  re-enters the loop — schedule the *next* poll only after `update()` returns,
  never from inside it. A probe that did `after(0)` + `update()` recursed
  until the interpreter died.

## Toast

Shown only for endings the user did not choose: pool ran out, worker error,
tabbed back in. **Never** on F9, pause, or resume — they already know why.

- `Shell_NotifyIconW` is exported by **shell32.dll, not user32.dll**. Every
  call here sits inside a `try/except`, so pointing at the wrong DLL was
  invisible: it raised and was swallowed, and the feature sat there looking
  intact while never firing. `selftest` now asserts it is bound to `_shell32`.
- `_NOTIFYICONDATAW` is **976 bytes on x64**, `szInfo` at offset 304,
  `szInfoTitle` at 820. `selftest` asserts all three. Explorer rejects a wrong
  `cbSize` with `FALSE` rather than reading past it.
- The tray entry is deleted 7 s later and on app close.
- `SHQueryUserNotificationState` decides whether Windows will show a banner at
  all. A full-screen game (VALORANT: `QUNS_BUSY`), a locked screen or quiet
  hours make Explorer swallow a balloon while `Shell_NotifyIconW` still answers
  TRUE — accepted, then never shown, which is exactly what "notifications don't
  work" looked like. `_toast` therefore holds the message in `_pending_toast`
  and `_retry_pending_toast`, called from every heartbeat, re-asks every
  `TOAST_RETRY_S` (2 s) until the state is `QUNS_ACCEPTS_NOTIFICATIONS` (5).
  A failed query counts as allowed: never hold a notification hostage to a
  query that did not answer. `_start` clears any pending message — a new
  session supersedes an announcement that is about to be out of date.

## Config

`%APPDATA%\Raze\config.json`. Keys: `msg_interval`, `loop`, `random`,
`start_key`, `stop_key`, `pause_key`, `resume_key`, `messages`, `history`,
`daily`.

- `history` is a list of `{"t": "...", "m": "..."}`, capped at `HISTORY_KEEP`.
  Content and timestamps are **stored but never displayed** — the History tab
  shows day counts and a lifetime total only.
- Written atomically (`.tmp` then rename). No BOM — never use PowerShell
  `Set-Content -Encoding UTF8` on it, PS 5.1 writes one and breaks the parser.
- `read_config` defaults deliberately omit `history`/`daily`. Never filter a
  config down to known keys or you will delete the user's history on save.

## Testing protocol

**Strictly non-intrusive.** The user is often playing a game while a change is
being verified.

- Never send a global keystroke, move the mouse, steal focus, or surface a
  window on the desktop.
- Never fire a live toast during testing. Validate the struct and the API
  return codes instead, and **ask before** showing one.
- Harnesses that build a real `AutoTyper` must set
  `A.reduce_motion_enabled = lambda: True` and re-apply `root.attributes("-alpha", 0.0)`
  **after** construction.
- Drive with `root.after()`-scheduled steps. Never a busy `root.update()` loop.
- Only ever stop processes this session started, and only by PID.
- `capture()` needs the top-level handle: `int(root.wm_frame(), 16)`. Off-screen
  windows do not composite, so stay on-screen at alpha 0.
- `selftest.py` stubs the app with a `_Worker` class that replaces `_type_text`.
  New worker behaviour needs new fields on that stub or it raises silently
  inside the worker's `except`.
- **Three harnesses are committed** next to it, and all of them are
  non-intrusive by construction: `send_enter`, `notify_balloon` and
  `is_foreground` are replaced with recorders, the window is built at alpha 0,
  and nothing is ever typed, surfaced or focused.
  - `pause_and_toast.py` — 38 checks. The session card carries its four
    counters, the `LAST SENT` box and the loop counter (an orphaned block once
    left the card's body unreachable after a `return`, and every other suite
    stayed green because the heartbeat swallows the `AttributeError` that
    follows — so the boxes are asserted by name), then pause keeps the
    session, pause cannot
    resume, start-while-paused does nothing, F9 is silent, the two endings
    the user did not choose do toast, the session header's loop counter reads
    finite, infinite and clamped, and a notification Windows refused is held
    and sent once the screen frees up. It reconfigures `sys.stdout` with
    `errors="replace"`: the `∞` glyph cannot be encoded on a cp1252 console
    and one raised `print` breaks the `after()` chain, stalling the harness.
  - `layout_check.py` — 24 checks. The window fits the work area's width and
    height with its frame, the client area is the design at the clamped scale,
    the four keycaps read `F8`/`F6`/`F7`/`F9` and fit their frames, the hotkeys
    card still fits its tab at 348 px, every button's label sits on the fill it
    is actually looking at (rest **and** hover), and it captures `typer.png` /
    `hotkeys.png` for the eye to check.
  - `capture_window.py` — the PrintWindow helper `layout_check.py` uses.
  Run them with `python <file>` from the project root; each prints
  `RESULT: PASS` and exits 0.
- One-off scratch scripts from past sessions sit in `%TEMP%\opencode`
  (`patch_*.py`, `profile_*.py`, ...). They are deliberately not committed —
  they were single-use edits against file states that no longer exist.

## Build

```powershell
pyinstaller --onefile --windowed --icon="assets\raze.ico" `
  --add-data "assets;assets" --additional-hooks-dir "hooks" `
  --exclude-module numpy --name "Raze" AutoTyper.py
```

Both flags matter:

- `--additional-hooks-dir "hooks"` replaces Pillow's own hook, which collects
  **every** codec Pillow ships including a 7.7 MB AVIF library. Raze opens one
  PNG. A onefile build unpacks the whole payload on every launch, so this hook
  is most of why Raze opens fast.
- `--exclude-module numpy` stops a 20.6 MB OpenBLAS library riding along if
  numpy happens to be installed. Raze never builds an image from an array.

Then `Start-Process ".\dist\Raze.exe" -ArgumentList "--selftest" -PassThru -Wait`
and check the exit code. `$LASTEXITCODE` is empty for a `--windowed` exe.

`Raze.exe --selftest` runs with no window at all. It is also safe while Raze is
open — the single-instance check reports honestly in both states.

## Releasing

- **Source lives in the private repo. The exe never does.** It is gitignored,
  and binaries committed to git inflate every clone forever.
- **Exactly one release exists at a time.** When the next one ships, delete the
  old: `gh release delete v1.10 --repo nawaf49/Raze --yes`. The user's rule — a
  visitor sees one clear download, never a menu of old versions. The private
  repo's git log is the only remaining record of what v1.0–v1.9 contained.
  **Current: v1.10.**
- **Exactly one *tag* too.** Deleting the release leaves its tag behind, and
  the Tags page would still advertise old versions:
  `gh api -X DELETE repos/nawaf49/Raze/git/refs/tags/v1.10`. Check with
  `gh api repos/nawaf49/Raze/tags --jq ".[].name"` — only the current one may
  answer. Never touch the current tag: it is what the release hangs on.
  (Public repo tags are pruned this way, so the Tags page shows one entry.)
- Create it as a real release, not a draft; it becomes *Latest* on its own:
  `gh release create v1.11 dist\Raze.exe --repo nawaf49/Raze --notes-file notes.md`
- **Verify before publishing.** `Get-FileHash .\dist\Raze.exe -Algorithm SHA256`
  must equal the digest GitHub reports for the uploaded asset; the SHA256 that
  goes in the notes comes from that match, never from a build nobody re-checked.
  Both sides are read back after publishing — `gh release view <tag>
  --json assets --jq ".assets[].digest"`.
  (v1.10: `CC0A17ECED4CA4FC08281A199D383D45D4ABB5624F52D07C1AB75B522576DDB0`
  over 14,983,806 bytes; v1.9: `3C362846C0A5DE061663DBF4FC3761AF9D731223E6EEF3B50D2757C10ADA6580`
  over 14,980,962 bytes; v1.8: `DE203AE80D8C4AE1FD8A6D1FEE10C77A5618736152AE383A7F61049425D2E06C`
  over 14,978,521 bytes — all confirmed identical on both sides.)
- **The notes format never changes** — same shape, same order, every time:

```text
Single file. No install, no folder to keep.

**SHA256** `<hex>`

## What's in it

- <one line per user-visible feature>

## Hotkeys

| Key | Action |
| --- | --- |
| `F8` | Start |
| `F6` | Pause |
| `F7` | Resume |
| `F9` | Stop |

Tab to your application first — Raze won't start while it's the window in front,
and stops if you tab back in.
```

  Read the published one back with
  `gh release view v1.10 --repo nawaf49/Raze --json body --jq .body`.

## The public README

Lives in the public repo only, edited through the API. These are settled
decisions — do not re-open one without asking:

- **Wording.** The user's rule, in his own words: "please display it in a
  simple way. users won't know what you're talking about if you don't say what
  you're talking about. i'm all for simplisicty." Concretely: every section
  opens by saying what it is about before it uses a term, and every bullet
  names its own subject — "Choose how many seconds pass between messages, and
  how many times **Raze** goes through the list" — rather than hanging off an
  implied one. All features stay listed; they just get short.
- **No key combinations.** The user's word: "there are no key combinations" —
  said a second time to remove it as a feature, not only from the wording.
  `hotkeys.is_valid` now rejects anything that is not exactly one key, so
  `set_hotkey` refuses a combination and nothing can arm one;
  `_apply_config` swaps a combination still sitting in an old config back to
  that action's default key (`_stored_key`), so no action is ever left with
  a key that will not register; and the Hotkeys dialog says only "Use a
  single key such as f8." Neither README nor the release notes may
  advertise a combination anywhere. `MODIFIERS` remains in `hotkeys.py` —
  a bare `shift` must not pass for a hotkey, and the listener has to tell a
  modifier press apart — which is not the feature.
- **The title line is measured, not eyeballed:**
  `<h1 align="center"><img src="app_icon.png" width="43" align="top" alt=""> Raze</h1>`
  - `align="middle"` is wrong on GitHub: Blink maps it to
    `-webkit-baseline-middle`, which pins the image centre to the **baseline**.
    The icon hung 11.5 px below the optical centre of "Raze" and the user
    spotted it at a glance — "look how uneven they are".
  - The target is the glyph box centre of the word, cap top to baseline. On the
    live page: baseline 571, cap height 23, target 559.5.
  - Sweeping every `align` value against every plausible size on the real page
    gave `align="top"` + `width="43"` = **0.0 px**. `align="absmiddle"` (+3.5 px)
    was tried first and works, but `top` is standard HTML4 and cannot be quietly
    stripped the way an exotic value might be.
  - How to measure, since it has to be done on the published page: in the
    browser console, drop a zero-height `inline-block` span with
    `vertical-align: baseline` immediately after the word — its
    `getBoundingClientRect().bottom` **is** the baseline. Take the cap height
    from a canvas `measureText('Raze').actualBoundingBoxAscent`. The target
    centre is `baseline - capHeight/2`; compare that to the image's own
    centre. No clone is needed, and the public repo is driven through the API
    anyway.
  - Re-measure after any edit. Changing the line box moves the baseline, so a
    delta computed before a change is meaningless after it — this bit us once.
- **Badges** are `flat-square`, `color=141418` (`SURFACE_2`), label green
  `22c55e` for downloads and blue `2f6bff` for platform — the app palette, not
  shields.io's defaults.
- **No checksum section.** Users do not verify hashes; the SHA256 lives in the
  release notes only. Links point at `releases/latest`, never a pinned version.
- The logo file is `app_icon.png`, referenced relatively. The name is
  load-bearing — renaming it breaks the title line silently.

## Deliberately absent

Do not add these without asking.

- **Background typing** (PostMessage / AttachThreadInput) — built, then removed
  at the user's request. Topic closed.
- **Error log** — there is none. `print("Typing error:", e)` in the `--windowed`
  exe goes nowhere. The user was offered a log and did not take it.
- **Auto-updater, cloud sync** — rejected. This is a local tool.
