# Raze

A Windows auto-typer. Drop a list of messages in, press one key, and it types
them for you into whatever app you are working in.

![Raze](app_icon.png)

## What it does

- **Message pool** - one message per line. Import / export `.txt`, shuffle, clear.
- **Message interval** - the gap between each message, in seconds.
- **Loop** - how many times to repeat the pool. `0` is infinite, `1` is a single pass.
- **Random** - pick the next message at random instead of walking the list.
- **Four hotkeys** - `F8` start, `F6` pause, `F7` resume, `F9` stop by default,
  all four changeable on the Hotkeys tab. They are not aliases of each other:
  pause freezes the clock and keeps your session counters, only resume picks it
  back up, and stop ends the session so the next start begins a new one.
- **History** - how many messages went out on every day, grouped by date.
  It is permanent: it stays until the app data is deleted.
- Everything is typed with `Enter` afterwards, automatically.

A run that ends on its own raises a Windows notification - the loop ran out,
typing failed, or you tabbed back into Raze. Pressing stop does not: you already
know why that one happened.

## Install

Grab `Raze.exe` and run it. It is a single, self-contained file - no folders,
no runtime, no dependencies.

## Where your data lives

Raze stores its settings and history **in your own user profile**, never next
to the executable:

```
%APPDATA%\Raze\config.json
```

(`C:\Users\<you>\AppData\Roaming\Raze\config.json`)

That means:

- every person on the machine gets their own separate Raze data
- deleting `Raze.exe` does **not** delete your history
- if you want to wipe it, delete `%APPDATA%\Raze` yourself

## Build from source

```powershell
python build_assets.py
pyinstaller --onefile --windowed --icon="assets\raze.ico" --add-data "assets;assets" --additional-hooks-dir "hooks" --exclude-module numpy --name "Raze" AutoTyper.py
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

`python make_shortcut.py` then drops a Start Menu and Desktop shortcut.

```powershell
python selftest.py      # or: Raze.exe --selftest
```

runs the headless checks (hotkeys, text rendering, history, config) without
opening a window.

## Credits

Typeface: [Inter](https://rsms.me/inter/) by Rasmus Andersson (SIL Open Font
License).
