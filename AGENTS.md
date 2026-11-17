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
| `selftest.py` | 208 headless checks, run via `Raze.exe --selftest` |
| `pause_and_toast.py` | 57 checks: pause/resume/toast routing, a tab-in stop continued by the resume key and begun again by the start key, settings changed mid-run, the session card's contents, the loop counter and a held notification against a real window |
| `layout_check.py` | 40 checks: the window fits the work area, the uptime on the status line, the loop counter's colour, the four keycaps, the hotkeys card and button hover backgrounds, the History tab's two record tiles (a forced record reaching its tile), the Updates tab's rows and its update-done badge (every row body on one x), captures the badge state plus typer/hotkeys/history/updates |
| `capture_window.py` | PrintWindow helper `layout_check.py` uses; never touches the screen |
| `rpc.py` | Discord presence: named pipe over ctypes, its own thread |
| `rpc_check.py` | 49 checks: the presence protocol against a fake local pipe |
| `build_assets.py` | Regenerates `assets/` artwork from source |
| `make_shortcut.py` | Dev-only Start Menu + Desktop shortcut (hardcoded paths, pywin32). The shipped exe installs itself — see *Install* |
| `version_info.txt` | PyInstaller version resource (`--version-file`), so Properties > Details reads "Raze, version 1.21". Bump with `APP_VERSION` and `UPDATES` |
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
AMBER     #f59e0b   warnings and refusals only - state words, never data
```

Colour follows meaning: **data is white, state is colour.** Every number
in the UI is TEXT (the four counters, the loop counter); GREEN/AMBER mark
what the app is *doing* (typing, paused, tab out). The loop counter was
amber until it collided with the amber state word 16 px away — two amber
phrases side by side read as one. FAINT is for captions you do not read;
anything read as text (the uptime clock) sits at MUTED, which clears AA
at 10 px where FAINT does not.

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
  - **plain tk widgets** (`tk.Frame`, `tk.Label`, and every raw
    `self.root.tk.call("place", …)`) are NOT scaled by customtkinter —
    pass them `px(...)` device px.
  - **`BakedLabel` scales its own geometry.** `place` x/y and the
    `padx/pady/ipadx/ipady` of `pack`/`grid` are rewritten through `px()`
    inside the class, mirroring CTk's `_apply_argument_scaling` — pass
    them **design px, never `px()`**. CTk does this scaling only for its
    own widgets, so before the override a plain tk child handed CTk-style
    design-px padding got device px instead: `cap.grid(padx=14)` was 14
    *device* px at every scale while the artwork around it shrank, which
    is what cut the tile captions on a clamped laptop screen.
  - **CTk widgets** scale their own `configure(width=…)`, `place` x/y and
    `pack`/`grid` padx/pady by `S` — pass them **design px, never
    `px()`**. A `px()` inside a CTk pack doubles the offset at 150%.
    `CTkCheckBox` scales still more internally — `checkbox_width`,
    `checkbox_height`, `corner_radius` and `border_width` all go through
    `_apply_widget_scaling` too. **`random_box` passes `px(20)`/`px(5)`
    and is therefore double-scaled at every scale but 100%** (at 125% it
    draws 25 design px wide instead of 20): latent, the sweep stays
    clean because it only makes the box bigger. The caption-row startup
    checkbox is the correct spelling — plain design px.
  - `CTkToplevel.geometry()` scales the `WxH` string but passes `+x+y`
    through raw — design px for the size, device px for the position.
  - `winfo_reqwidth()/winfo_width()` always report **device px**. If the
    value feeds design-px arithmetic (nav layout, tab centres), divide it
    by `S` first. `winfo_rootx/y()` diffs are device px and belong on raw
    tk `place_configure` calls as-is.
  - **`winfo_reqheight()` reads a placeholder (200) until the first idle
    pass has laid a widget's children out.** Measuring a stack at build
    time without a `root.update_idletasks()` first reports nonsense — the
    config card's give-back did, and quietly floored itself. Ask after
    settling, not before.
- The opening animation places widgets at their travel start (`x+dx, y+dy`)
  and settles them in `_play_intro`. Its reduce-motion branch must settle
  them too, or users with "turn off unnecessary animations" on get a
  permanently 10–18 px offset interface.
- `_align_nav` puts `● IDLE` — and the uptime label beside it — on the
  GitHub button's line by reading
  `winfo_rooty()` — but an **unmapped** widget reports 0, so a run that beat
  the first map computed `0 - rooty` and parked the status above the window
  where nothing could see it. It therefore retries (100 ms, at most 30
  times) until the root *and* the button's own label are mapped and the
  offset lands inside the window.
- **A tab view is placed exactly once, by its builder's `_place_in`.**
  `show()`, `_warm_views` and `_build_content` must not add a
  `place(relwidth=1, relheight=1)` on top of it: Tk *adds* `width` to
  `relwidth × parent`, so the redundant call doubled every view to
  2120x1584 — twice the container — and the audit saw the whole stack
  hanging outside the client.
- **The fit path is itself verified across real screen modes**, not only by
  the forced-scale sweep: 21 modes from `800x600` to `3840x2160@150%`, three
  tabs each, all through the shipped auto-fit (`%TEMP%\opencode\fit_probe.py`
  fakes the work area and DPI). It must also re-point Tk's `wm maxsize` at the
  faked screen, or a fake 4K run gets clamped to this machine's 1080p panel
  and reports overflow that no real machine would ever see.
- **The scale audit.** `%TEMP%\opencode\res_audit.py <scale> [tab]` builds
  the app at a forced scale and reports glyph boxes taller than their room
  plus every mapped widget outside the client, per tab. Sweep 0.50–1.20
  across `typer`/`hotkeys`/`history`/`updates` and require `RESULT: CLEAN`
  on all 60
  lines after any layout change. (Above ~1.2 on this 1080p machine is a
  probe artifact: `RAZE_SCALE` bypasses the clamp and the screen cannot
  hold the window. `cfg_stack.py` beside it dumps the config card's
  vertical stack; `cap_width.py` measures the worst-case design width of a
  fixed-box string at every scale.)

## Baked text

`textengine.render()` rasterises a string to a transparent PNG and returns a
`tk.PhotoImage`. Wrapped by `BakedLabel`.

- **Why:** ClearType fringes. Rasterised art is crisp at any size.
- **Gotcha:** `BakedLabel` keeps its text in `self._text`. `cget("text")` will
  NOT reflect `set_text()`. Always read `_text` in tests.
- **A pinned `height=` is a floor, not a box.** `_render()` raises it to
  `photo.height()` whenever the artwork is taller: the box is design px
  converted once at build, but the photo is font metrics at the *rounded*
  device size, and the two stop matching below ~100% (a 7 px box for a 9 px
  photo at `S=0.5`). Rows are sized by their content, so a floored label
  still cannot move anything — but a container pinned *around* one can clip
  it, which is why the config card's label rows propagate their height and
  the card gives back padding instead of squeezing (see *Config*).
- **A tile sizes itself once, at build, from the longest thing it can ever
  show.** `StatTile` takes `room = max(width, cap.winfo_reqwidth()/S + 2*PAD + 2,
  worst_room)` and pins that, so a running counter can never move it.
  `worst_room` is `_worst_room(worst)` — the tile's own ceiling string
  (`999999999` messages, `9999999999` characters, `999y 364d` elapsed,
  `86400s` next) rendered with `max_width=None` and **never** through the
  box: `textengine.render` ellipsizes internally when handed a `max_px`, so
  reading the box's own artwork only ever shows the already-cut result and
  can never fail. The value label is built `fit=True`: past the ceiling the
  glyphs shrink (`FIT_MIN_PX = 6` floor) instead of the string being cut —
  an ellipsis in a counter is a defect, because this app runs for years and
  every digit has to survive; beyond the floor anything longer still fits,
  just smaller. The caption measurement matters because a caption's
  **design** width peaks *below* 100%: the font is `round(size*S)` and the
  tracking `round(1.1*S)`, neither of which shrinks in step with `S` —
  `MESSAGES SENT` wants 109.8 design px at `S=0.51` against 89 at `S=1.0`.
- **The uptime label on the nav is boxed the same way.** `UPTIME <t>` sits
  left of the status dot and reads on every tab, updated by the heartbeat
  only when the string changes. Its box is pinned once — `place -width` of
  `min(measured worst case, the room between the tabs and the dot)` — with
  the artwork right aligned inside it (`anchor="e"`), so a clock growing
  toward `UPTIME 999y 364d` moves *away* from the status dot and can never
  reach the tabs; `fit=True` plus `set_box(max_width=room)` is the backstop
  if the worst case ever outgrows the room. `_move` only writes `-x`/`-y`,
  so the width set at build lasts for the life of the window, and
  `_align_nav` gives it the status line's own `y`.
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
- **Settings are read live, mid-run.** The worker never snapshots the
  interval, Loop, the selection mode or the pool for the whole run: each
  pass re-reads them from plain attributes the Tk thread writes - never a
  Tk object - so changing any of them under a running session applies to
  that session. `_update_pool_meta` publishes the pool as a fresh
  `self.messages` list on every edit (**replaced, never edited in place** -
  that invariant is what makes reading it from the worker thread safe), an
  emptied pool mid-run keeps the last non-empty one so rewriting the box
  cannot kill a session, and the wait between messages is re-cut from the
  live interval in `INTERVAL_POLL_S` slices: a shortened interval lands
  within 100 ms instead of at the next session, and `_next_deadline` - the
  deadline the countdown tile reads - stays the truth throughout.

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
- **After a tab-in stop the two keys answer different questions.** The
  announcement names the resume key — "switch to your app first, then press
  F7 to continue" — and that key continues the very session that stopped,
  counters and clock included; F8 instead begins again from the top. F8's
  `paused` guard does not cover this state, because a tab-in stop is not a
  pause: `_start()` clears `_tab_stopped` only **after** `_focus_refused()`
  passes, so a refused start leaves the resumable session exactly where it
  was. F9 discards it — `_stop()` clears the flag and any announcement still
  waiting for the screen to free up.
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
- **A tab-in stop keeps the session.** The heartbeat freezes
  `stats["elapsed"]` the way pause does, calls `_stop()`, and only then sets
  `_tab_stopped = True` — `_stop()` clears it, so the order matters — before
  writing the amber "Switch to your app first" and naming the resume key in
  the toast. `_stop()` nulls `_session_start` but never touches `stats`, so
  the numbers are still there for `_resume()` to carry on from; it must also
  set `typing = True`, because the stop cleared it.

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
- `_resume()` accepts **`paused or _tab_stopped`** — the two ways a session
  can still exist without a worker — and returns before doing anything if
  neither holds. Its guard sits before the flag is cleared, so a refused
  resume leaves the session resumable.
- `_stop()` clears `paused`, `_tab_stopped` and any pending announcement: a
  stop is a choice, so nothing may outlive it waiting to be resumed or shown.
  The heartbeat's tab-in branch sets `_tab_stopped` back straight after the
  call, which is the only reason the order works.
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
  builds on demand if a click beats the timer. Updates joined them when
  the fourth tab landed.
- **Four tabs: Typer, Hotkeys, History, Updates.** Updates is the
  in-app changelog — it exists because the updater moves users onto a new
  version in the background and they never see release notes, so a feature
  appears with no explanation. It reads the baked `UPDATES` constant and
  nothing else: one plain line per version, newest first, `APP_VERSION`
  heading the list (selftest fails a bump without the matching line). The
  list ships inside the exe, so an older copy shows fewer lines and every
  entry only ever describes a version at or below the one running. Same
  rule as History: **nothing scrolls** — rows that fit the panel are
  built, the rest are dropped, and the panel has no real height until the
  tab has been laid out, so `show()` renders it on open and again on
  `after_idle`.
- **The Updates tab badges itself once.** A blue dot sits beside the tab
  until the user opens the tab after an update; the open view then leads
  with one `UPDATED` banner row (BLUE tag + "Raze updated to <version> -
  what changed is below." — approved verbatim). The state is the config's
  `seen_version` against the pure `updates_unseen()` (only an exact
  `parse_version` match of the running version silences it): the dot is
  built in `_build_nav` but placed only by `_set_updates_dot(True)` from
  `_apply_config` pre-intro, and `show()` clears on visit —
  `seen_version = APP_VERSION`, dot hidden, the banner for that visit
  only, `_save_config()` stubbed in harnesses. The banner lives in
  `_updates_banner_row` (never `_updates_rows`) and consumes one
  `max_rows` slot. Its tag column is pinned by
  `grid_columnconfigure(0, minsize=...)`: a plain frame's `width=` is
  ignored under pack propagation and `BakedLabel(min_width=)` right-aligns
  text inside its box, so neither can pin it — every row body has to
  start on one x, and layout_check asserts exactly that.
- `_tab_anim` is a token: every switch supersedes a travel in flight, so
  rapid clicking starts each trip from wherever the last one reached, and
  the view that wins is always raised *from* the offset (it stays beneath
  the winner while it loses, so the snap is never seen). A losing view settles to
  zero the next time it opens.
- Two guards hand straight to the settled positions: Windows' "turn off
  unnecessary animations" (`reduce_motion_enabled`) and the opening
  sequence (`_intro_done`, set by `_play_intro` in every path), which owns
  the underline until it finishes — otherwise both loops would write it.
- The committed harnesses set the first guard, so `layout_check` only ever
  sees final geometry. The travel itself was checked by a one-off in
  `%TEMP%\opencode\tab_slide_check.py`, which stands the intro down
  instead (alpha stays 0) and leaves motion on.

## Dialogs

**No `messagebox` ever runs in the app.** Every confirmation, refusal and
error goes through `self._confirm(...)` — a `CTkToplevel` in the app's own
style (baked artwork, the palette, Enter/Escape) — and all seventeen former
`messagebox.*` call sites now use it; grep finds zero left. The one rule
that replaces them: `cancel_text=None` drops the cancel pill entirely
(Escape still says no) for the questions that are an offer, not a choice
with two equal sides. Exception text reaches a dialog through
`dialog_line(exc, fallback)` — one line, ≤ ~52 characters, because
`textengine` has no newline handling and a longer line would be
ellipsized; a hotkey refusal says only "Use a single key such as f8."
(`_confirm(..., wait=False)` returns with `state["dialog"]` for the rare
caller that needs the handle; nothing in the suites reaches `_confirm` or
`_prompt` — a probe that opened one would grab focus and surface a
window, so motion is verified against a withdrawn toplevel instead, see
*Small motions*).

`_prompt` is the text-entry sibling: same shell, one field, live
validation from a pure `check(text)` that answers
`{"ok": True, "name": ...}` or `{"ok": False, "error": ...}` — used by
`New pool` and `Rename` (see *Config*).

### Small motions

Three dress motions, one contract each, all in the `RISE_MS` block beside
the restore constants: `RISE_MS = 160`, `DIALOG_RISE = 8`,
`POOL_SETTLE_DIP = 6`. Frames run on `TAB_FRAME_MS` (16, the house
cadence) with ease-out cubic — the curve the tab views already rise on —
and every one of them follows the same three rules:

- **The last frame writes the exact final values** (alpha `1.0`,
  `geometry +x+y`, `pady (0, 0)`), never trusting the curve to land on
  them, so nothing can be left offset or half-faded.
- **Reduce motion is checked per frame**, not once at the start, so a
  setting flipped mid-flight still lands home; with the guard on from the
  start there is exactly one write, already final.
- **A token supersedes**: `_settle_token` lets a rapid second pool switch
  take over a settle still in flight instead of fighting it. The pill's
  flash carries the same idea in `BakedButton._flash`.

Where each lives:

- **`_dialog_in(dialog, x, y)`** — shared by `_confirm` and `_prompt`.
  The caller drops alpha to 0 *before* the map (nothing half-drawn
  reaches the screen) and calls `_dialog_in` after the icon block; it
  fades and rises the dialog in over `DIALOG_RISE` device px. An
  exception mid-flight takes the timer with it and the except clause
  stands the dialog up anyway — an invisible dialog would be one nobody
  can answer.
- **Pill press flash** — `BakedButton(press=...)`: one frame brighter on
  press, restored after 90 ms *per hover state* (hovered goes back to the
  hover fill, unhovered to rest). Per-kind press colours live in `Pill`:
  solid `#dcdce1`, danger `#3a181c` (one step redder than its hover),
  glass `BORDER_2`; the nav's white github button presses `#dcdce1`. A
  command that destroys the button only costs a swallowed TclError.
  **`CTkButton` steppers need no flash** — CTk's built-in
  `_on_release` already does a rest-colour beat and `_draw` re-asserts
  hover, so a `configure`-based flash would be overridden immediately.
- **`_pool_settle()`** — the editor's breath when another pool takes the
  screen: the pool frame dips `POOL_SETTLE_DIP` and rises home. The dip
  is written in **device px** (`pack_configure` is raw — CTk scales
  `pack()` but not `pack_configure()`). Called at the end of
  `_switch_profile`, `_new_profile` and `_delete_profile`; **not** on
  rename — the pool on screen never changes there.

Verified by `%TEMP%\opencode\polish_check.py` (19 checks: a withdrawn
toplevel with an alpha-pinning wrapper for `_dialog_in`, both reduce-motion
branches, the pill flash including token supersession, and the settle's
dip-and-home read through `pack_info`), alongside the committed suites.

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
  every `RESTORE_POLL_MS` (16 ms — frame cadence) and asks Tk for
  everything it still owes.
  Two polls back under `RESTORE_QUIET_MS` (8 ms) mean the paint has actually
  stopped, and only then is alpha put back to 1.0. The repaint happens while
  nobody can see it, so the window appears complete instead of in pieces.
  `RESTORE_MAX_MS` (1500 ms) caps the invisible period whatever a
  pathological restore does. Result: **0 ms of stall after the reveal** on
  every run, against 150–490 ms before.
- **The invisible wait is paint plus schedule, and only the paint is
  irreducible.** Probed end to end (`restore_probe.py`: real
  withdraw→deiconify, physical alpha pinned, save stubbed) the drain
  measured 295/343/417 ms at the old 50 ms poll against 296/307/398 ms at
  16 — then 220/271/347 ms final for 0.5 s / 2 s / 60 s absences. The
  paint itself (121–321 ms) grows the longer the window was away and is
  the price of complete-on-reveal; what 16 ms buys is the scheduling tail
  — the wait before the first poll plus two quiet ones, ~150 ms at 50
  against ~48 at 16. Heartbeat ticks were innocent the whole way (mean
  0.2 ms), so the old "resonance" theory was wrong: the interval
  arithmetic was the whole story. `RESTORE_MAX_MS` stays 1500 — never
  approached in 15 drains (worst real: 1235 ms, a one-time warm-views
  build inside the first poll), and lowering it only risks revealing
  mid-paint.
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
The tab-in one names the key that continues the run — "Stopped - switch to
your app first, then press F7 to continue" — because that stop is not the
end of the session.

- **Balloons are dead on modern Windows; the channel moved to WinRT.**
  `Shell_NotifyIcon` `NIF_INFO` balloons were proven dead on this machine's
  Windows 26H2 (build 26300): every call answers `TRUE` and nothing ever
  renders — verified live against a WinRT toast that showed instantly from
  the same machine. `notify_balloon`/`notify_clear` and the whole
  `_NOTIFYICONDATAW` struct are gone; `notify_toast` drives
  `Windows.UI.Notifications` through ctypes COM instead — no dependency and
  no spawned PowerShell (hard rule 6).
- **The COM is hand-rolled, and the numbers come from the SDK headers, not
  memory.** `combase.dll` binds `RoInitialize` / `RoActivateInstance` /
  `RoGetActivationFactory` / `WindowsCreateString` (explicit `argtypes` —
  the default `c_int` would truncate the HSTRING out-pointer). IInspectable
  owns vtable slots 0–5 everywhere, so each interface's own method starts
  at **slot 6**: `LoadXml` on `IXmlDocumentIO`, `Show` on `IToastNotifier`,
  `CreateToastNotification` on `IToastNotificationFactory`, and **slot 7**
  `CreateToastNotifierWithId` on `IToastNotificationManagerStatics` (slot 6
  is the no-arg overload). IIDs are literals beside the code, read from
  `windows.ui.notifications.h` / `windows.data.xml.dom.h` in the
  tpn/winsdk-10 SDK mirror. Two traps cost real crashes: `QueryInterface`
  is **slot 0**, not 3 — slot 3 is IInspectable's `GetIids`, which answers
  `S_OK` and writes an IID-array pointer where an interface pointer was
  expected, so the next vtable read dies on GUID bytes; and every interface
  pointer must be released exactly once on every path, including the early
  returns taken after the toast object already exists.
- **The banner is attributed to `toast_app_id()`**, not to a window: no
  tray icon, no 7 s cleanup, no `_raze_hwnd` — `_toast` needs no handle at
  all. The id is the **installed exe's path**, because Windows resolves a
  classic Win32 toast through the Start Menu shortcut's target: a bare
  `"Raze"` answered S_OK, wrote a history entry and showed nothing
  (proven live), while the exe path bannered instantly. It prefers the
  registered install target so a portable run of the same file banners
  too; a dev run with no install falls back to a plain name it cannot
  render with anyway (harnesses stub `notify_toast`). `selftest` builds
  the objects headless (`_toast_objects`) and releases them; that path
  creates no `Notifications\Settings` registry key and shows nothing, so
  it is safe inside the suite.
- The payload is plain XML (`toast_xml`): a `ToastGeneric` binding with one
  title and one body line, every message escaped — a stray `&` would make
  Windows reject the toast outright. `selftest` parses it back with
  `xml.etree.ElementTree`, and the same check covers the escaping.
- **Two different icons, two different mechanisms.** The *body* emblem
  rides in the payload: `toast_icon_path()` unpacks the largest PNG frame
  of `raze.ico` (every frame `build_assets` writes is PNG-encoded) to one
  fixed file in `%TEMP%` — same capped-cache rule as the update download,
  rewritten whenever the bundled frame's size stops matching — and
  `toast_xml` references it as `file:///` in an
  `<image placement="appLogoOverride">` element. No icon:
  `toast_icon_path` returns `None`, the image is omitted and the banner
  goes out as before; an icon failure never blocks a toast.
  The *header* (attribution area) name and tile are not in the payload at
  all: starting with Windows 11 that area is shell-controlled and cannot
  be overridden from toast XML — `appLogoOverride` only draws in the
  visual area below it. Three things decide it, all keyed by the toast's
  app id, and all three were wrong at once. (1) The Start Menu link's
  `PKEY_AppUserModel_ID`: `_create_shortcut` stamps the target path (the
  exact string `toast_app_id()` reports) after releasing the ShellLink
  object, and `repair_shortcuts()` stamps links that predate it (rule:
  `aumid_needs_stamp`). (2) The link's icon location — the tile is the
  matched link's own icon, and every pre-fix link glued the index onto
  the path (`"Raze.exe,0"`, a file that does not exist), so the shell
  drew a blank page (rule: `icon_needs_fix`). (3) The registration at
  `HKCU\Software\Classes\AppUserModelId\<AUMID>` carrying `DisplayName`
  and `IconUri` — where an unpackaged app's header icon is actually read
  from (what Firefox and the Community Toolkit write); no build of ours
  ever wrote it until `register_aumid()` landed (pure plan:
  `aumid_registry_plan` — a path AUMID spells as nested registry keys,
  the same nesting Windows itself creates under
  `Notifications\Settings`). The process agrees with all of it:
  `_set_window_icon` sets the process AUMID to `toast_app_id()`; it set
  `"Raze.AutoTyper.1"` before, which matched nothing. Confirmed live on
  this machine with all three in place: the header shows the emblem.
  Windows is known to *cache* the attribution icon (WindowsAppSDK #6882,
  no invalidation API), so a generic header that survives the
  registration wants a sign-out or a notification-platform restart — ask
  before either.
- `SHQueryUserNotificationState` decides whether Windows will show a banner
  at all. A full-screen game (VALORANT: `QUNS_BUSY`), a locked screen or
  quiet hours make Windows swallow a banner while the toast API still
  answers `S_OK` — accepted, then never shown, which is exactly what
  "notifications don't work" looked like. `_toast` therefore holds the
  message in `_pending_toast` and `_retry_pending_toast`, called from every
  heartbeat, re-asks every `TOAST_RETRY_S` (2 s) until the state is
  `QUNS_ACCEPTS_NOTIFICATIONS` (5). A failed query counts as allowed: never
  hold a notification hostage to a query that did not answer. **A send the
  API itself refuses is held the same way** — `_fire_toast` clears the
  pending message only on success, so a transient failure retries instead
  of dropping the announcement. `_start` clears any pending message — a new
  session supersedes an announcement that is about to be out of date — and
  so do `_stop` (F9 discards the announcement with the session) and
  `_resume` (the key it named has just been pressed).

## Discord presence

Rich Presence on its own thread, exactly like the hotkey listener. Built with
ctypes and the standard library because **hard rule 6** keeps the exe to one
self-contained file: a presence library drags its own http stack into a
payload that is unpacked from scratch on every launch.

- The pipe is `\\.\pipe\discord-ipc-0` … `-9`; both the `\\.\` and `\\?\`
  namespaces are tried, because Discord has used each. Framing is an 8-byte
  header — `uint32 opcode, uint32 length`, little-endian — then JSON.
  Opcodes: 0 handshake, 1 frame, 2 close, 3 ping, 4 pong.
- **`CreateFileW` needs `restype = c_void_p`.** Left at the default `c_int`
  the 64-bit handle comes back truncated and the pipe looks permanently
  unavailable — the same trap `GetForegroundWindow` sets elsewhere.
- Reads go through **`PeekNamedPipe`, never a blocking `ReadFile`**: the
  thread has to stay interruptible so `stop()` can join it promptly, and a
  blocked read would sit on an idle pipe until Discord happened to speak.
- **Discord not running is the ordinary case, not an error.** The thread
  reconnects every 5 s forever and does nothing in between. It pushes on
  change only, never more than once a second.
- The Tk thread's entire interface is `set_state(status, lifetime,
  started_at)` — three values under one lock. The heartbeat feeds it once per
  tick; every byte of I/O happens on the presence thread.
- **The timer is the app's uptime, and it never starts over.** `started_at`
  is `_up_wall`, the unix timestamp of `__init__` — one fixed value, taken
  once at launch beside the monotonic `_up_since` the in-app clock reads —
  so Discord draws a timer that starts at zero when Raze opens and resets
  only when the app closes: a pause, a stop or a new session moves it not at
  all, and `total_secs` is gone from the code and the config with it. Being
  fixed is also what makes it safe to send for *every* status, idle and
  paused included: a value recomputed each push would drift forward between
  pushes and snap back on each one, which is why a paused session used to
  show no timer at all. It also means the activity dict only changes when
  the status or the count does, so the push throttle still sees one shape.
- The state line is **always the lifetime total** from `daily`, never the
  session's own count. The session card is the place for that number; a profile
  is a stranger's view, and the only number worth showing a stranger is the one
  that never goes down.
- The activity carries one **button** — `Get Raze` → the public repo, never the
  source one. That is the real point of a presence: a stranger sees the
  activity and has somewhere to go. `REPO_URL` and `BUTTON_LABEL` are the two
  constants. Discord does not always draw the button for the account that set
  it, so check with an alt or a friend before calling it broken.
- `_on_close` stops it, and `stop()` clears the activity before the thread
  leaves, so the profile does not keep showing a session that ended.
- `CLIENT_ID` lives in `rpc.py`. Every call is inside `try/except`: a pipe
  that breaks mid-frame is dropped and retried rather than raised on a
  thread nobody is watching.
- The activity type is left at 0 ("Playing"), which is what Discord gives
  third-party RPC by default. Flagged to the user at build time: while a
  game is running it may compete with the game's own presence.

## Config

`%APPDATA%\Raze\config.json`. Keys: `msg_interval`, `loop`, `random`,
`start_key`, `stop_key`, `pause_key`, `resume_key`, `messages`, `profiles`,
`active_profile`, `history`, `daily`, `install_asked`, `seen_version`,
`best_sitting_msgs`, `best_sitting_s`, `best_sitting_msgs_day`,
`best_sitting_s_day`, `stats_sig`.

- **`stats_sig` guards the history and the two personal bests against hand
  edits.** `_save_config` writes `stats_sign()` — an HMAC-SHA256 over the
  six `STATS_KEYS` (`history`, `daily`, the two bests and their two day
  stamps) — and `read_config` verifies it *before* `harden` shapes the
  values: a signature that does not recompute resets all six fields
  together and drops the stale signature, so the file comes back as one
  this build would have written; the rest of the config is untouched.
  The key is derived from a machine-local seed, so this stops casual
  `%APPDATA%` spoofing, not a determined attacker who can read the code —
  honest about that limit. A config with no signature (every file from
  before this landed) is adopted as-is and signed on the next save: there
  is no way to tell "never signed" from "tampered", so absence must not
  punish an old file.

- `install_asked` is vestigial (see *Install*): the install question is
  gone, but the key stays readable and written on save — a config that
  carries it keeps carrying it — and nothing gates on it any more.

- `seen_version` is the update-done badge (see *Tabs*): the last
  `APP_VERSION` whose Updates tab was opened. The pure
  `updates_unseen()` decides the dot from it; `show()` writes the
  running version on the first visit after an update, through the same
  `_save_config()` every harness stubs.

- **"Start with Windows" is deliberately not a config key.** The Run
  key is the store (see *Install*), so the box reads `startup_value()`
  when it is built and re-reads it after every click — a config file
  can never disagree with the machine about it, and a refused toggle
  just stays where the registry is, with no word on screen.

- `total_secs` used to be here: lifetime typing seconds, which the presence
  timer counted from. The timer is the app's own uptime now (see *Discord
  presence*), so nothing reads or writes it any more. A config that still
  carries the key is left alone on save — never filter a file down to the
  keys you know about.
- `history` is a list of `{"t": "...", "m": "..."}`, capped at `HISTORY_KEEP`.
  Content and timestamps are **stored but never displayed** — the History tab
  shows day counts and a lifetime total only.
- **Message pools are `profiles` + `active_profile`; `messages` is the open
  one.** `profiles_plan(cfg)` (pure, beside `record_plan`) turns any config
  into `{name: [messages]}` plus the active name: a config from before pools
  keeps its `messages` as the single pool `Default`, a fresh config gets
  `SAMPLE_MESSAGES`, and junk anywhere — a pool that is not a list, an empty
  name, an active name that matches nothing — falls back to the first pool
  rather than to nothing. **`messages` has no default in `read_config`**,
  the way `history`/`daily` do not: absent means "never had a pool" (the
  samples apply), a stored `[]` means a pool the user emptied and it must
  come back empty — filling the key in would make those one answer, which
  is what used to resurrect the sample messages after a Clear. `_save_config`
  refreshes the active pool from the editor and writes `profiles` and
  `active_profile`; `messages` keeps carrying the active pool as well, for
  a hand-edit that drops the newer keys.
- **The pool card carries the switcher** — a row between the editor and the
  file pills: a `CTkOptionMenu` (palette-styled, `dynamic_resizing=False`
  so the row can never move) listing every pool, plus `New`, `Rename` and
  `Delete`. The menu's colours are set explicitly: the arrow side is a
  recessed `SURFACE` well lighting to `BORDER_2` on hover (CTk ships a
  light block there that read as a glued-on rectangle — the widget has no
  border param to borrow, so the well *is* the affordance), and the popup
  hovers `#3d3d46` rather than the old `#1d1d22`, which was invisible on
  `#141418`; the chevron is drawn in `text_color`. `New` opens the
  `_prompt` dialog with the first free `Profile N` as the offer — typing
  nothing keeps it, Escape makes no pool — and `Rename` re-prompts on the
  active pool with its current name selected. Both validate through the
  pure `profile_name_plan(profiles, current, raw)` (trimmed, ≤ 20
  chars, unique — errors are one short line the dialog shows in place),
  and `next_profile_name(profiles)` is the free-name rule on its own.
  `Delete` refuses to drop the last pool, because the typing thread needs
  one to read. All three paths — switch, new, delete — end in
  `_update_pool_meta`, which is the single place a pool edit marks the
  config dirty. `_switch_profile` stores the outgoing pool before loading
  the incoming one, so nothing is lost between pools, and a switch
  mid-run takes effect from the next message like any other pool edit.
- **Edits reach the disk without waiting for a close.** `_update_pool_meta`,
  `_set_msg_interval` and `_set_loop` set `_config_dirty`;
  `_maybe_save(now)` — called from the heartbeat — writes when either that
  flag has aged `CONFIG_SAVE_EVERY` (2 s) or `_history_dirty` has aged
  `SAVE_EVERY` (60 s), and one write serves both gates because the file
  carries everything at once. **The flags are cleared *after* `_save_config`
  returns**, never before: the save begins with `_commit_fields()`, whose
  setters mark the config dirty again, so clearing first left the flag set
  by the very write that saved it and the heartbeat would have rewritten
  the file every two seconds forever. `_apply_config` clears the flag on
  the way out — loading is not editing.
- **The two personal bests the History tab shows are config keys**
  (`best_sitting_msgs`, `best_sitting_s` in whole seconds), unlike the
  Start-with-Windows box above. `read_config` defaults them to 0 — an
  older config picks them up without ever having mentioned them —
  `_apply_config` reads them through `_as_count` (a hand-edited string,
  null or negative clamps to 0 and never reaches the UI or a `max()`),
  and `_save_config` writes them back. The fold is the pure
  `record_plan(cfg, candidates)` beside `group_history`: it reads `cfg`
  and never writes it, returns **only its own four keys** (the two bests
  plus their `..._day` stamps) so a record can never be the reason
  something else drops out of the file, and a record only ever moves up;
  the day stamp moves with it, blank when the value is 0.
  **Records read the saved history, not just the live session:**
  `_apply_config` runs `_backfill_records()`, which replays `history`
  through the same `record_plan`, so bests recorded by an older build —
  or written straight into the file — reach the tiles on the next launch.
  Capture is `_record_session()`, called from
  `_stop()` — the single point a session is over, since `_start` only
  ever runs while `not typing` — and from `_on_close()` for one still
  running; it folds the day's keys in from `daily` and is
  try/except-guarded (it sits inside the stop path, so
  nothing in it may take the status line down with it) and calls
  `_save_config()` + `_refresh_records()` only when a record actually
  changed. `_refresh_records()` guards every tile with `getattr` because
  the History tab builds lazily — it is often called before the tiles
  exist as often as after, and the build calls it itself to seed them.
  The captions read **MOST IN ONE RUN** and **LONGEST UPTIME** — the
  user's wording for "most messages sent in one run" and total uptime —
  and each tile carries its record's date beneath the value
  (`record_day_text`, which formats for a tile, unlike `pretty_day`
  which is for day rows; both read the `..._day` keys through
  `getattr`).
- **The records strip is a pinned 76 px row between the HISTORY header
  and the day list** — two `StatTile`s, so the two cards read as one
  design. The card is a fixed 726 and the day-list holder expands into
  whatever is left, so the list gives up a row or two rather than the
  card growing into the footer. **The pin needs both propagation
  switches**: `pack_propagate(False)` governs pack slaves only, and
  these tiles are *gridded* — with only the pack call the strip came
  out 200 tall (CTkFrame's default, taken from the tiles' own
  requested height) and silently ate three day rows. Calling
  `grid_propagate(False)` on the strip plus an explicit `height=76` on
  each tile pins it at 76 at every scale either way (verified:
  `hist_measure` in `%TEMP%\opencode`).
- Written atomically (`.tmp` then rename). No BOM — never use PowerShell
  `Set-Content -Encoding UTF8` on it, PS 5.1 writes one and breaks the parser.
- `read_config` defaults deliberately omit `history`, `daily` and `messages`.
  Never filter a config down to known keys or you will delete the user's
  history on save.
- **The configuration *card* has no slack.** Its stack — two field rows, the
  rule, the Random row — measures exactly `CONFIG_H = 336` at 100%, and the
  artwork outgrows its design box below ~60% scale (rounded font metrics,
  device-px glyph pad), so pack clamps the last slave: 16 design px of
  overflow at `S=0.5`, landing on `Random`/`Disabled`. The card gives it
  back from its own margins — half off the header's top padding, half off
  the body's bottom, each floored at 8 — measured after an
  `update_idletasks()` from what the stack actually asks for. Growing the
  card was never an option: only 18 design px separate it from the
  hotkeys card below, and 16 of them would have closed the gap to 2.
  The field's label row is likewise not pinned; it takes its height from
  the label, so the spinner below never sits on top of grown glyphs.

## Install

A downloaded file is not a program. Windows only lists something in
Settings > Apps when a per-user uninstall key names it, and only shows it
in the Start Menu when a .lnk points at it — so the exe installs *itself*,
once, on first run. Per-user throughout: no admin, no UAC, no second file.

- **No question — the install is enforced.** `__main__` polls
  `_intro_done` (200 ms beats), then waits one settled 700 ms, then calls
  `_auto_install`, which starts the worker the moment the gate passes: no
  modal, no pill, no way to decline. The gate is
  `install_needed(exe, registered)`: never for a dev run (`running_exe()`
  returns None unless `sys.frozen`), never when the registry already lists
  Raze, and never when the running file already *is* the installed copy.
  There is deliberately **no answer flag** — a failed install is retried on
  the next run, and a "Not now" recorded by v1.17's config no longer
  exempts anyone (`install_asked` stays in the config, read and written,
  but nothing reads it as a gate). Success is silent; only a failure raises
  the box, from `_tick_inner`.
- **What an install writes**, all computed read-only by `install_plan()`:
  a copy at `%LOCALAPPDATA%\Programs\Raze\Raze.exe`; `Raze.lnk` in the
  Start Menu's **Programs** folder (`CSIDL_PROGRAMS`) and on the Desktop;
  and the HKCU
  `Software\Microsoft\Windows\CurrentVersion\Uninstall\Raze` key that
  Settings > Apps reads — DisplayName, DisplayIcon, DisplayVersion
  (`APP_VERSION`), UninstallString `"<target>" --uninstall`, EstimatedSize.
  The shell folders come from `SHGetFolderPathW`, not from environment
  variables, so a OneDrive-redirected Desktop lands where Explorer puts it —
  and `CSIDL_STARTMENU` (the root, one level above Programs) is precisely
  the wrong folder: Windows lists apps only from `Programs`, so a link in
  the root is invisible. The selftest asserts the full
  `Start Menu\Programs\Raze.lnk` suffix, not the words "Start Menu",
  because the looser check passed over that exact bug.
- **How it is built.** `_create_shortcut` calls the IShellLinkW vtable by
  hand through ctypes, because pywin32 would be a new dependency — hard
  rule 6. Two things about it were settled the hard way, on the first live
  install: (1) an interface pointer points at the object, whose first field
  is lpVtbl, so the vtable array is **one deref further on** — reading
  slots straight off the object hands back its data fields, and calling
  one is an access violation at the very first call (that is what broke
  the first real `Install` click); (2) the slots are QI/AddRef/Release
  0–2, SetDescription 7, SetWorkingDirectory 9, SetIconLocation 17,
  **SetPath 20** — index 19 is `Resolve`, which answers S_OK and leaves
  the target empty, so the index was proven by reading the written `.lnk`
  back through WScript.Shell, never from memory. The `icon` argument is
  a **bare path**: `SetIconLocation` takes the index as its own argument,
  so the old `path + ",0"` spelling stored a nonexistent file named
  `Raze.exe,0` — the blank page the toast header and the link icons
  showed. Every successful `Save` is followed by `_notify_shell`
  (`SHChangeNotify` with `SHCNE_UPDATEITEM` + `SHCNF_PATHW`) so caches
  holding the old icon drop it. IPersistFile's Save is 6
  after a QueryInterface for its IID. `make_shortcut.py` still uses
  pywin32 — which is not even installed on this machine, so it cannot run
  either; it is a dev script with hardcoded paths and never ships. The
  registry goes through stdlib `winreg`.
- **The link also carries the toast's AUMID.** Windows draws a banner's
  header name and tile by matching the toast's app id (the exe path,
  `toast_app_id`) against `PKEY_AppUserModel_ID` on a Start Menu shortcut,
  so `_create_shortcut` stamps the target path onto the link — the exact
  string the toast reports — through `IPropertyStore::SetValue` +
  `Commit` + `IPersistFile::Save`, called **after** the finally-block
  releases everything, so the file is closed and the stamp owns its own
  apartment. The numbers come from the SDK, not memory (no Windows SDK
  headers exist on this machine): `PKEY_AppUserModel_ID` =
  `{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}` pid 5 type `VT_LPWSTR`
  (propkey.h), `IID_IPropertyStore` =
  `{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}` and the vtable order
  QI/AddRef/Release 0–2, GetCount 3, GetAt 4, GetValue 5,
  **SetValue 6, Commit 7** (propsys.idl). Two traps: AutoTyper defines
  `_GUID` twice (install ~672, toast ~1396), so `_aumid_key` moves the
  fmtid as raw bytes — assigning a `_guid()` result into the struct field
  raises the confusing "incompatible types, `_GUID` instance instead of
  `_GUID` instance"; and the PROPVARIANT is deliberately never
  `PropVariantClear`'d in the setter (Python owns that buffer — the store
  copies it during SetValue) while the reader *does* clear the string the
  store allocated. Everything is best effort: a link that refuses the
  property still opens and uninstalls, only the header stays generic.
  **Links that predate the fix** are stamped once at startup by
  `repair_shortcuts()` — a worker thread from `_auto_install`'s
  nothing-to-install branch, through the `_repair_shortcuts` method so
  the selftest's probe can replace it; it reads each link first and
  stamps only a disagreement (`aumid_needs_stamp`), so the steady state
  writes nothing, and a failure on one link never stops the other. The
  same call also writes the header's registry registration
  (`register_aumid`, pure rule `aumid_registry_plan` — see *Toast*),
  `do_install` writes it right after the uninstall entry so a first-ever
  launch can already toast with an icon source, and `do_uninstall`
  removes it (`_unregister_aumid`: delete the leaf, then prune each
  parent only while it is empty, so another app's chain sharing the `C:`
  prefix stops the walk and the AppUserModelId root is never touched).
- **Start with Windows is a Run-key entry, through the same seam as
  everything else the install writes.** `HKCU\...\CurrentVersion\Run`,
  value `Raze`, carrying the target quoted (install paths have spaces).
  Four functions sit beside `install_needed`: `startup_target()` picks
  the installed copy, then the running file, then the path the next
  install would write (so the answer is never empty, but whether it
  exists is the caller's question — a missing target is a refusal);
  `startup_plan(raw)` is the pure dict `key`/`name`/`command`/`enabled`;
  `startup_value()` is the read-only read, best effort, answering `""`
  for a missing key, an unopenable key and a non-string value alike,
  because a failure must never let the box claim an entry the machine
  does not have; and `set_startup(enabled, command, reg=None)` writes or
  clears it, taking a **winreg seam** so the selftest drives a `_RunReg`
  stub and never the real key. Enabling with nothing to launch refuses
  silently. `_toggle_startup` then re-reads the key either way and puts
  the box back with `select()`/`deselect()` — which do **not** fire the
  checkbox command, so the revert cannot bounce back in (only
  `toggle()` fires it, which is what the label's own bind uses). The
  toggle lives in the **CONFIGURATION caption row**, right-aligned:
  the card stack measures exactly `CONFIG_H` with no slack, so a new
  row would clamp the Random line, while an 18 design px control on the
  18 px caption adds no height at all. It goes straight into `head` as
  a label plus checkbox — a `CTkFrame` would default to 200×200 and
  blow the caption open, and both are **design px**, because CTk scales
  `width`/`height`/`checkbox_*`/`corner_radius`/`border_width`
  internally. `do_uninstall` clears the entry beside `_unregister_aumid`.
- **The thread rule holds.** `do_install` runs on a worker thread (files
  and registry are not Tk work) and never touches Tk: it only sets
  `_install_done = (ok, err)`, and `_tick_inner` consumes it first thing —
  before the start request, because a failure is a modal and nothing may
  start under a dialog that just took focus. Success consumes silently.
- **`--install` / `--uninstall` run before `acquire_single_instance`** in
  `__main__` — they must never contend for the mutex with a live app — and
  report through native `MessageBoxW` (`_native_info` / `_native_error`)
  because no Tk exists yet. `--uninstall` refuses with a visible box while
  `instance_running()` says a copy holds the mutex (OpenMutexW *probes*, it
  never creates the mutex). Uninstall removes the registry key, the Run
  entry, both links
  and the installed copy — when the running file is the target, a detached
  `cmd` waits for this process to leave, then deletes — and **never
  `%APPDATA%\Raze`** (hard rule 1: deleting the program never deletes the
  user's data).
- **A harness must never call `do_install`/`do_uninstall`** — they write
  to the tester's machine. `selftest`'s install section asserts on
  `install_plan()`, `install_needed()`, the AUMID stamp, the pure
  header-registration plan and the startup entry (plan, target and a
  write against a `_RunReg` stub — the real Run key is never a test
  surface) only (36 checks); its `_auto_install` probe replaces both
  `_install_now` and `_repair_shortcuts`, so no suite ever stamps the
  tester's real links or writes the header registration.
- The failure dialog keeps its message to one line ≤ ~52 characters:
  `textengine` has no newline handling, and a longer line would be
  ellipsized by the artwork — never cut a word mid-way in a dialog either.

## Auto-updater

Mandatory, and settled with the user in his own words: *"on startup and
24/7 but if it finds one it shouldn't update if the user is running a loop
or is in a run. as soon as the run finishes it should auto update. it
constantly checks."* Every copy watches `nawaf49/Raze`'s releases and moves
itself onto a newer one with nothing to click and nothing to decline.

- **The checker is a daemon thread, never Tk.** Started by
  `AutoTyper._update_start()` from `__main__` (after the window exists, so
  `_update_stop` already exists), it checks once at start-up and then every
  `UPDATE_POLL_S` (4 h — GitHub allows 60 unauthenticated API calls an hour
  per IP, so this never gets near the ceiling). It only ever sets
  `_update_ready`, the same plain-attribute hand-off as `_install_done`,
  and `_on_close` sets `_update_stop` so it leaves with the app. **A dev
  run never checks**: `update_plan()["enabled"]` is false unless
  `running_exe()` names a frozen exe.
- **Offline is the ordinary case, not a failure.** No internet, GitHub down
  or a 403 rate limit all come back as an error string from
  `fetch_latest_release()` (which never raises), the app runs normally, and
  the next poll tries again. Mandatory means no *skipping* an available
  update — never that Raze stops working without a network.
- **Only a strictly newer, fully verifiable release counts.**
  `update_is_newer(tag)` compares parsed versions (unparseable → never
  newer, so a weird tag can't trigger a swap), and `update_release()`
  requires *both* the `Raze.exe` asset URL and GitHub's `sha256:` digest —
  a release missing either is simply not applicable yet and gets retried.
  `download_update()` streams to one fixed file (`%TEMP%\Raze-update.exe` —
  one path forever, a capped cache by construction) and **deletes it on any
  digest mismatch**: an exe that did not verify is never left where the
  apply step could find it.
- **The gate lives in `_tick_inner`.** `_update_ready` is consumed only
  when `not typing and not arming` (`typing` stays set through pause and a
  tab-in stop, so one flag covers every way a session is alive — a loop
  included) and `_intro_done` is set. Then `_update_apply()` puts
  `UPDATING`/amber on the status line, waits `UPDATE_SHOW_MS` (900 ms) —
  the one visible beat of the whole update — re-checks the run gate at the
  moment of hand-over (a run may have started during the beat; if so the
  file goes back into `_update_ready` and the gate re-fires when that run
  ends), saves the config, spawns the verified file with
  `--apply-update <target> <old_pid>` detached and destroys the window.
- **`--apply-update` runs before `acquire_single_instance`** — like
  `--install`, it must never contend for the mutex with a live app — and
  has no window: `do_apply_update()` is pure file work. It waits for the
  old PID with `OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject` (never a
  PID-number poll; `UPDATE_WAIT_S` caps it), copies itself to
  `target + ".new"` and swaps with `os.replace` — atomic, so a failure
  leaves the old file exactly as it was. It then **reopens the uninstall
  key with `OpenKey`, never `CreateKeyEx`** — creating one would list a
  portable copy in Settings > Apps that never chose to install — writes
  the new `DisplayVersion`, starts the target again, and hands its own
  deletion to a detached `cmd` (a running image cannot delete itself; same
  pattern as `do_uninstall`). If anything fails it restarts the *old*
  target, so a failed update never leaves the user without a running Raze.
- **It replaces the running file in place** — installed or portable: the
  Start Menu and Desktop shortcuts already point at that exact path, so
  the swap needs no shortcut or registry path surgery at all. The config
  profile `%APPDATA%\Raze` is never touched (hard rule 1), and nothing in
  the update path opens a Tk window of its own.
- **A harness must never call `do_apply_update`** — it rewrites the exe on
  disk and spawns processes. `selftest`'s update section asserts on
  `parse_version()`, `update_is_newer()`, `update_release()`,
  `update_plan()` and `update_download_path()` only (18 checks).

## Testing protocol

**Strictly non-intrusive.** The user is often playing a game while a change is
being verified.

- Never send a global keystroke, move the mouse, steal focus, or surface a
  window on the desktop.
- Never fire a live toast during testing. Validate the payload, the bindings
  and the API return codes instead, and **ask before** showing one.
- **Never call `do_install` / `do_uninstall` from a harness** — they write
  to the tester's machine (registry key, shortcuts, a copied exe). The same
  goes for `do_apply_update`: it rewrites the exe on disk and spawns
  processes. Assert on the read-only surface instead: `install_plan()`
  computes every path an install would touch without touching it,
  `install_needed()` and `update_plan()` are pure. Same for
  `_create_shortcut` — never point it at a real folder from a test.
- Harnesses that build a real `AutoTyper` must set
  `A.reduce_motion_enabled = lambda: True` and re-apply `root.attributes("-alpha", 0.0)`
  **after** construction, and must set `A.rpcmod.enabled = False` — otherwise
  the presence thread opens Discord's real pipe and puts a live activity on
  the user's profile while the test runs.
- Drive with `root.after()`-scheduled steps. Never a busy `root.update()` loop.
- Only ever stop processes this session started, and only by PID.
- `capture()` needs the top-level handle: `int(root.wm_frame(), 16)`. Off-screen
  windows do not composite, so stay on-screen at alpha 0.
- `selftest.py` stubs the app with a `_Worker` class that replaces `_type_text`.
  New worker behaviour needs new fields on that stub or it raises silently
  inside the worker's `except`. The same goes for `_Tick`, the stub
  `_tick_inner`/`_start`/`_resume` are driven on: anything those methods read
  — the uptime label, `_up_since`, `_tab_stopped` — has to exist on it, and
  out there an `AttributeError` is not swallowed.
- **Four harnesses are committed** next to it, and all of them are
  non-intrusive by construction: `send_enter`, `notify_toast` and
  `is_foreground` are replaced with recorders, the window is built at alpha 0,
  the presence seam is off, and nothing is ever typed, surfaced or focused.
  - `pause_and_toast.py` — 57 checks. The session card carries its four
    counters, the `LAST SENT` box and the loop counter (an orphaned block once
    left the card's body unreachable after a `return`, and every other suite
    stayed green because the heartbeat swallows the `AttributeError` that
    follows — so the boxes are asserted by name), then pause keeps the
    session, pause cannot
    resume, start-while-paused does nothing, F9 is silent, the two endings
    the user did not choose do toast, the session header's loop counter reads
    finite, infinite and clamped, and a notification Windows refused is held
    and sent once the screen frees up while a send the API itself refuses is
    held too; then, under a run already under way,
    an interval shortened inside its own wait, a selection-mode flip through
    the real checkbox, a pool edit through the real binding and a Loop change
    through its setter all land on that same run. A tab-in stop is then
    driven end to end: the toast names the resume key and the session waits,
    the resume key continues it with the counters intact, tabbing in again
    stops it a second time, the start key zeroes the counters for a fresh
    session, and F9 after all of that stays silent. It reconfigures
    `sys.stdout` with
    `errors="replace"`: the `∞` glyph cannot be encoded on a cp1252 console
    and one raised `print` breaks the `after()` chain, stalling the harness.
  - `layout_check.py` — 40 checks. The window fits the work area's width and
    height with its frame, the client area is the design at the clamped scale,
    the uptime sits on the status line between the tabs and the dot without
    crowding either and is the readable grey (MUTED), the loop counter reads
    as data (TEXT) rather than a warning, the four keycaps read
    `F8`/`F6`/`F7`/`F9` and fit their
    frames, the hotkeys
    card still fits its tab at 348 px, every button's label sits on the fill it
    is actually looking at (rest **and** hover), the History tab's two record
    tiles exist and a forced record reaches its tile through `_refresh_records`
    (the forced values never leave the process — `_save_config` is stubbed),
    the Updates tab's rows fit
    the panel with the shipped version heading them, and the update-done
    badge: the dot hides on visit, the `UPDATED` banner's tag/colour/body
    land, the banner sits above the rows, **every row body starts on the
    same x**, and a later visit has no banner (badge states forced,
    `_save_config` stubbed). It captures
    `typer.png` / `hotkeys.png` / `history.png` / `updates_badge.png` / `updates.png`
    for the eye to check.
  - `rpc_check.py` — 49 checks. The presence protocol end to end: handshake,
    all three activity shapes, the repo button, the timer that runs from app
    start through every status — paused and idle included — and never moves,
    ping/pong, the push throttle,
    the clear-down on exit, byte- and message-mode pipes, and the disabled
    seam. It swaps `rpc._PIPES` for a pipe it creates itself, so **Discord's
    real pipe is never opened** even while Discord is running. Its own
    `CLIENT_ID` literal pins the shipped app id rather than importing it.
  - `capture_window.py` — the PrintWindow helper `layout_check.py` uses.
  Run them with `python <file>` from the project root; each prints
  `RESULT: PASS` and exits 0.
- One-off scratch scripts from past sessions sit in `%TEMP%\opencode`
  (`patch_*.py`, `profile_*.py`, ...). They are deliberately not committed —
  they were single-use edits against file states that no longer exist.

## Build

```powershell
pyinstaller --onefile --windowed --icon="assets\raze.ico" `
  --version-file "version_info.txt" `
  --add-data "assets;assets" --additional-hooks-dir "hooks" `
  --exclude-module numpy --exclude-module typing_extensions `
  --exclude-module PyQt5 --exclude-module PyQt6 `
  --exclude-module PySide2 --exclude-module PySide6 `
  --name "Raze" AutoTyper.py
```

Every flag is load-bearing. The hook and the excludes exist for one reason —
the payload must not depend on what happens to be installed on the build
machine:

- `--version-file "version_info.txt"` stamps the VSVersionInfo resource, so
  the file's Properties > Details reads "Raze, version 1.21" instead of
  blank and Explorer shows the icon's file type properly. Its numbers must
  match `APP_VERSION` in `AutoTyper.py` — bump both together, every release
  (see *Releasing*). The file itself is compiled into the resource; it does
  not travel inside the onefile payload.

- `--additional-hooks-dir "hooks"` replaces Pillow's own hook, which collects
  **every** codec Pillow ships including a 7.7 MB AVIF library. Raze opens one
  PNG. A onefile build unpacks the whole payload on every launch, so this hook
  is most of why Raze opens fast.
- `--exclude-module numpy` stops a 20.6 MB OpenBLAS library riding along if
  numpy happens to be installed. Raze never builds an image from an array.
- The four Qt excludes stop ~30 MB of Qt DLLs, plugins and translations riding
  in behind imports that only *probe* for a binding: `PIL.Image` does
  `from . import ImageQt` at module level (ImageQt tries PyQt6, then PySide6)
  and `pyperclip` does `import PyQt5` inside a `try:` while looking for a
  clipboard. Neither ever opens a Qt widget — Raze draws with Tk — and while
  no binding is installed both imports fail quietly. The day one arrives on
  the machine (an unrelated `pip install` did exactly that) the build silently
  goes from 15 MB to 45.6 MB. All four names are excluded because different
  dependencies probe different ones.
- `--exclude-module typing_extensions` stops ~700 KB of stdlib the same way.
  Nothing here imports it on purpose: `customtkinter` and `packaging` name it
  only in `except ImportError:` / `if TYPE_CHECKING:` branches Python 3.12
  never takes (the suites prove the app runs with the module absent —
  `%TEMP%\opencode\blocked_tt.py` puts `None` in `sys.modules` first), but
  PyInstaller follows the static edge anyway, and `typing_extensions` imports
  `asyncio.coroutines`, which pulls in asyncio, multiprocessing, hmac, runpy
  and pkgutil behind it — 75 archive entries and 695 KB.
- **The excludes are command-line flags, not hook attributes.** A hook-level
  `excludes` is silently ignored (it is not a hook attribute; `excludedimports`
  is, but it only cuts edges out of *that one* module — `pyperclip` reaches
  Qt without touching Pillow). This cost an afternoon to learn; the command
  line is the only place that cuts globally.

Then `Start-Process ".\dist\Raze.exe" -ArgumentList "--selftest" -PassThru -Wait`
and check the exit code. `$LASTEXITCODE` is empty for a `--windowed` exe.

`Raze.exe --selftest` runs with no window at all. It is also safe while Raze is
open — the single-instance check reports honestly in both states.

## Releasing

- **Before building the next release: bump the version in both places, and
  give it its changelog line.** `APP_VERSION` in `AutoTyper.py` and
  `version_info.txt`
  (`filevers`/`prodvers` + the `FileVersion`/`ProductVersion` strings) must
  say the same number — the registry's DisplayVersion, the file's
  Properties > Details and the Settings > Apps entry all read them, and a
  mismatch ships visible in three places at once. The third bookkeeping
  step is `UPDATES` in `AutoTyper.py`: prepend `("1.xx", "<one line>")`
  for the new version, plain words, newest first. The Updates tab renders
  it, and selftest fails a bump that skipped it (`UPDATES[0][0]` must
  equal `APP_VERSION`).
- **The pitch changed at v1.18 — settled with the user, do not reopen it.**
  v1.16's "First run offers a one-click install — or run it from anywhere."
  died with the install offer: the shipped line is now "Single file. First
  run installs itself — nothing to click." (approved verbatim). The public
  README's Download section explains the automatic first-run install (plus a
  bullet in *What it does*) — approved and published with v1.18. The
  hotkeys table and the tab-out line under *Releasing*
  stay as they are. The same rule applies to whatever ships next: the
  public README's feature list gets its bullet for a new feature only at
  release time, drafted and approved by the user before it goes out.
- **Source lives in the private repo. The exe never does.** It is gitignored,
  and binaries committed to git inflate every clone forever.
- **Exactly one release exists at a time.** When the next one ships, delete the
  old: `gh release delete v1.22 --repo nawaf49/Raze --yes`. The user's rule — a
  visitor sees one clear download, never a menu of old versions. The private
  repo's git log is the only remaining record of what v1.0–v1.21 contained.
  **Current: v1.22.**
- **Exactly one *tag* too.** Deleting the release leaves its tag behind, and
  the Tags page would still advertise old versions:
  `gh api -X DELETE repos/nawaf49/Raze/git/refs/tags/v1.22`. Check with
  `gh api repos/nawaf49/Raze/tags --jq ".[].name"` — only the current one may
  answer. Never touch the current tag: it is what the release hangs on.
  (Public repo tags are pruned this way, so the Tags page shows one entry.)
- Create it as a real release, not a draft; it becomes *Latest* on its own:
  `gh release create v1.22 dist\Raze.exe --repo nawaf49/Raze --notes-file notes.md`
- **Verify before publishing.** `Get-FileHash .\dist\Raze.exe -Algorithm SHA256`
  must equal the digest GitHub reports for the uploaded asset, read back after
  publishing with `gh release view <tag> --json assets --jq ".assets[].digest"`.
  The notes carry neither: since v1.15 the user has not wanted the SHA256 in
  them ("what's the point of the sha56 idk what that is") and the feature list
  was dropped too — "it's already written in the readme". The match is still
  checked both ways on every ship; only the publication of it is gone.
  (v1.22: `F840B261273A285D5F4080EEC42CC61C6E4C5B710BF4782B5E57C9E5EE64EB11`
  over 15,183,604 bytes; v1.21: `7C79ACAED791F3D46D3155252DFEE0C6AD370CA3E3D8B721664871A7EB8DCE38`
  over 15,180,737 bytes; v1.20: `AB534CE801C8DFE598239E23663F3F833254801268B8A70E7EF209F4D4FCC849`
  over 15,145,654 bytes; v1.19: `ECE98842EF0CE1CF938D63BFBC8080D5A58F84CB2B83C645911AB1682942AD86`
  over 15,088,810 bytes; v1.18: `A1F0D292478CE6DC674E62DE70EF47BF407217DA5220580E016D791303892CAF`
  over 15,085,065 bytes; v1.17: `4D658097CC6256678F92D963326C57C0F7C0605C3FBB25B5C8EA46720B056AF9`
  over 15,078,839 bytes; v1.16: `8D3301F9515E6D67117684A804756F9387AD28D69FC9CD05BE9C69657E7FB4C4`
  over 15,061,800 bytes; v1.15: `EC33A7261BC31391333732F7C3D8FC6D3B73EAB782C3132AE12158B021E628E3`
  over 15,038,931 bytes; v1.14: `3EBFDB2D71F7B5AFC891A1C5E370D50AC2AAD8B9533D8F3D523F7C0AD1E78BBE`
  over 15,035,335 bytes; v1.13: `49F81E0A7652A4CBBC93ED25C4EA22C2B9E6544F43CA6F5B569A5AAA4C271620`
  over 14,997,700 bytes; v1.12: `C576CF2A16F059ED4C82D761B871BC1F2456F48B782E0755E6DAD9422F1FB2D2`
  over 14,988,741 bytes; v1.11: `B6A6DD62C09A7FF326EA63FE99DF15EB3C8BE763C93080E7F4B986D43E8CE0B1`
  over 14,988,092 bytes; v1.10: `CC0A17ECED4CA4FC08281A199D383D45D4ABB5624F52D07C1AB75B522576DDB0`
  over 14,983,806 bytes; v1.9: `3C362846C0A5DE061663DBF4FC3761AF9D731223E6EEF3B50D2757C10ADA6580`
  over 14,980,962 bytes; v1.8: `DE203AE80D8C4AE1FD8A6D1FEE10C77A5618736152AE383A7F61049425D2E06C`
  over 14,978,521 bytes — all confirmed identical on both sides.)
- **The notes format never changes** — same shape, same order, every time.
  Since v1.15 it is deliberately thin: the README carries the features, so
  the notes repeat neither them nor a checksum:

```text
Single file. First run installs itself — nothing to click.

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
  `gh release view v1.22 --repo nawaf49/Raze --json body --jq .body`.

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
- **No checksum section, anywhere public.** Users do not verify hashes; since
  v1.15 the SHA256 appears in neither the README nor the release notes — the
  user's word: "what's the point of the sha56 idk what that is". It is still
  verified on both sides at ship time (see *Releasing*), just not published.
  Links point at `releases/latest`, never a pinned version.
- **Every feature is listed — with exceptions.** When the uptime display and
  the tab-back split were added (v1.15) the instruction was "add all the
  features but don't include basic features like discord rpc": the README
  carries everything a user does, but the Discord presence is deliberately
  not among them. Do not add it without asking.
- The logo file is `app_icon.png`, referenced relatively. The name is
  load-bearing — renaming it breaks the title line silently.

## Deliberately absent

Do not add these without asking.

- **Background typing** (PostMessage / AttachThreadInput) — built, then removed
  at the user's request. Topic closed.
- **Error log** — there is none. `print("Typing error:", e)` in the `--windowed`
  exe goes nowhere. The user was offered a log and did not take it.
- **Cloud sync** — rejected. This is a local tool. (The auto-updater is no
  longer absent — see *Auto-updater*.)
