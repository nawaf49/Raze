# Working on Raze

Read this before changing anything. It exists so a person or an AI picking the
project up cold has every decision that is not obvious from the code.

## What it is

A Windows auto-typer shipped as a single `Raze.exe`. The user keeps a pool of
messages, presses one global hotkey, and Raze types them into whatever
application currently has focus, one per interval, with Enter after each.

The visual direction is original — pure
black, quiet, premium, no chrome. Everything else here is original.

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
| `selftest.py` | 56 headless checks, run via `Raze.exe --selftest` |
| `build_assets.py` | Regenerates `assets/` artwork from source |
| `make_shortcut.py` | Start Menu + Desktop shortcut "Raze" |
| `hooks/hook-PIL.Image.py` | Trims Pillow to the one codec we use. See *Build* |
| `assets/` | Emblem, background, the 7 Inter faces, `raze.ico` |

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

## Baked text

`textengine.render()` rasterises a string to a transparent PNG and returns a
`tk.PhotoImage`. Wrapped by `BakedLabel`.

- **Why:** ClearType fringes. Rasterised art is crisp at any size.
- **Gotcha:** `BakedLabel` keeps its text in `self._text`. `cget("text")` will
  NOT reflect `set_text()`. Always read `_text` in tests.
- The cache is capped. Do not let it grow unbounded — this app runs forever.
- The font is Inter, 7 faces, bundled with `--add-data "assets;assets"`.

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
- The exe goes on a **Release** on the public repo:
  `gh release create v1.1 dist\Raze.exe --repo nawaf49/Raze --notes "..."`
- Attach the SHA256 in the notes so people can verify.

## Deliberately absent

Do not add these without asking.

- **Background typing** (PostMessage / AttachThreadInput) — built, then removed
  at the user's request. Topic closed.
- **Discord RPC** — declined.
- **Error log** — there is none. `print("Typing error:", e)` in the `--windowed`
  exe goes nowhere. The user was offered a log and did not take it.
- **Auto-updater, cloud sync** — rejected. This is a local tool.
