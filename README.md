<h1 align="center"><img src="app_icon.png" width="43" align="top" alt=""> Raze</h1>

<p align="center">
  A Windows auto-typer.<br>
  Put your messages in, press a key, and it types them for you.
</p>

<p align="center">
  <a href="https://github.com/nawaf49/Raze/releases/latest"><img alt="Downloads" src="https://img.shields.io/github/downloads/nawaf49/Raze/total?style=flat-square&labelColor=22c55e&color=141418"></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-141418?style=flat-square&labelColor=2f6bff&logo=windows11&logoColor=f6f6f8">
  <a href="https://github.com/nawaf49/Raze/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/nawaf49/Raze?style=flat-square&labelColor=22c55e&color=141418"></a>
</p>

## Overview

Raze is a desktop auto-typer for Windows, shipped as a single `Raze.exe` -
one file, no runtime dependencies, no installer to click through and no
admin rights. Give it a list of messages, press one key, and it types them
into whatever application you are working in, one message at a time, pressing
Enter after each.

It runs quietly in the background for as long as you leave it open: your
messages and history are stored in your own user profile, the interface fits
itself to any screen from 800x600 to 4K, and the app keeps itself up to date
in the background with nothing to approve.

## What it does

- **Message pool** - one message per line. Import / export `.txt`, shuffle,
  clear, and keep several named lists at once.
- **Message interval** - the gap between each message, in seconds.
- **Loop** - how many times to repeat the pool. `0` is infinite, `1` is a
  single pass.
- **Random** - pick the next message at random instead of walking the list.
- **Four hotkeys** - `F8` start, `F6` pause, `F7` resume, `F9` stop by default,
  all four changeable on the Hotkeys tab. They are not aliases of each other:
  pause freezes the clock and keeps your session counters, only resume picks
  it back up, and stop ends the session so the next start begins a new one.
- **Session history** - how many messages went out on every day, plus
  lifetime records for the most messages in one run and the longest uptime.
  It is permanent: it stays until the app data is deleted.
- **Self-updating** - a newer release is downloaded, verified and applied
  between runs, so the version you have is always current.
- **Notifications** - if Raze stops without you asking (the list ran out,
  typing failed, or you tabbed back into it), you get a Windows toast. Not
  when you stop it yourself.

## How it works

- **The typing loop.** The pool is read fresh on every message, so editing
  the list, the interval or the loop count mid-run applies to the run already
  under way. ASCII goes out character by character through `SendInput`;
  everything else is copied to the clipboard and pasted, because not every
  application honours Unicode key events. Enter follows each message.
- **The focus guard.** Raze never types into itself. It refuses to start
  while its own window is in front, and if you tab back in mid-run it stops
  within one 100 ms slice of the wait between messages - the session and its
  counters survive, `F7` continues it, and `F8` starts a fresh one.
- **Global hotkeys** are polled at 8 ms on their own thread rather than
  registered with Windows, so the focused application never loses a key and
  the listener never competes with the interface.
- **The interface is artwork.** No widget ever renders text directly; every
  label is drawn to a transparent PNG at startup, which keeps type crisp at
  any size. Everything scales through a single factor that clamps itself to
  the screen, so the whole app shrinks together on a small display instead of
  running off the edge.
- **Updates** are checked against this repository's releases on a background
  thread, and the download is only ever applied after its SHA-256 digest
  matches what GitHub reports. A run or a loop in progress is never
  interrupted: the update waits for the session to end.
- **Everything is stored locally**, in `%APPDATA%\Raze\config.json`, written
  atomically as you change it.

## Download

[Raze.exe](https://github.com/nawaf49/Raze/releases/latest) - grab it and run it.
Run it once and Raze installs itself: a shortcut appears in your Start Menu,
and it shows up in Settings, where the Uninstall button removes it. There is
nothing to click.

## Keys

| Key | Command |
| --- | --- |
| `F8` | Start |
| `F6` | Pause |
| `F7` | Resume |
| `F9` | Stop |

Tab over to your app first, then press `F8`. Raze won't start while its own
window is in front, and it stops itself if you tab back in. When that
happens, `F7` continues that same run and `F8` starts a new one.

## Screen sizes

Raze fits itself to your screen: it shrinks or grows the whole window to
match what your display can show, so nothing gets cut off at the edges. It
works on screens from 800x600 up to 4K, at 100%, 125% and 150% Windows
scaling. Anything smaller than 800x600 may not fit.

## Your data

Everything is saved on your own computer, in `%APPDATA%\Raze` - a folder in
your user account, not next to the program. You can delete `Raze.exe` and
nothing is lost.

Your messages and settings are saved as you change them, so nothing is lost
even if Raze closes unexpectedly.

## Build from source

```powershell
python build_assets.py
pyinstaller --onefile --windowed --icon="assets\raze.ico" --version-file "version_info.txt" --add-data "assets;assets" --additional-hooks-dir "hooks" --exclude-module numpy --exclude-module typing_extensions --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 --name "Raze" AutoTyper.py
```

`--additional-hooks-dir "hooks"` is not optional. `hooks/hook-PIL.Image.py`
replaces Pillow's own hook, which collects **every** image codec Pillow ships -
including a 7.7 MB AVIF library. Raze only ever opens one PNG, and a onefile
build unpacks the entire payload to a temporary folder on every single launch,
so that hook is most of what makes Raze open quickly.

`--exclude-module numpy` matters for the same reason, and it is a trap that only
springs once numpy happens to be installed. Pillow names numpy inside a couple of
docstrings and inside one `try: import numpy / except ImportError:` block, and
PyInstaller's modulegraph collects it as a real dependency. Raze never builds an
image from an array, so the import always fails at runtime and is always caught -
but if numpy *is* on the machine it gets bundled anyway, and it drags a 20.6 MB
OpenBLAS library with it. Excluding it keeps the payload the same size on every
machine regardless of what else is installed.

The Qt excludes (`PyQt5`, `PyQt6`, `PySide2`, `PySide6`) and
`--exclude-module typing_extensions` guard the same boundary. Pillow's `ImageQt`
and the clipboard library `pyperclip` both probe for a Qt binding inside
`try:`/`except ImportError:` blocks - imports that fail harmlessly on a machine
without Qt, but that PyInstaller follows as if they were real. One is enough:
a stray `pip install` put PyQt5 on a build machine and the executable grew from
15 MB to 45.6 MB of DLLs, plugins and translations for code Raze never runs
(it draws with Tk). `typing_extensions` is the same story one layer deeper -
`customtkinter` only names it in Python-3.7-era fallbacks - except that it
imports `asyncio`, which drags `multiprocessing`, `hmac` and `runpy` in behind
it, about 700 KB all told. None of these modules is ever imported at runtime;
excluding them costs nothing and pins the payload.

`python make_shortcut.py` then drops a Start Menu and Desktop shortcut - a
dev convenience (pywin32, not installed on every machine). The
shipped exe does the same job itself, from inside `AutoTyper.py`.

## Tests

```powershell
python selftest.py      # or: Raze.exe --selftest
```

runs the headless suite - 208 checks over the typing engine, hotkeys, text
rendering, history, config, install and updater logic - without opening a
window. Beside it sit four committed harnesses (`pause_and_toast.py`,
`layout_check.py`, `rpc_check.py`, `capture_window.py`), each printing
`RESULT: PASS`.

The testing rule is that nothing ever reaches the desktop: keystrokes and
notifications are replaced with recorders, windows are built at alpha 0, and
no suite can type, focus or surface anything.

## Project layout

| File | What it is |
| --- | --- |
| `AutoTyper.py` | The whole app: UI, typing engine, heartbeat, config, Win32 bindings |
| `textengine.py` | Renders text to transparent PNGs for the baked interface |
| `hotkeys.py` | Global hotkey listener on its own thread |
| `rpc.py` | Discord Rich Presence, ctypes and the standard library only |
| `selftest.py` | The headless check suite |
| `AGENTS.md` | Engineering notes: every decision that is not obvious from the code |
| `assets/` | Emblem, background, the Geist typefaces and `raze.ico` |

## License

MIT - see [LICENSE](LICENSE).

The bundled [Geist](https://github.com/vercel/geist-font) typeface is
licensed under the SIL Open Font License (`assets/OFL.txt`).

## Credits

Typeface: [Geist](https://github.com/vercel/geist-font) by Vercel, in
collaboration with basement.studio (SIL Open Font License).
