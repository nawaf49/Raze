"""
Global hotkey handling for Auto Typer.

One backend:
  * Win32 GetAsyncKeyState polling - light, predictable, and it never
    competes with the interface thread for the GIL.

Several hotkeys can be watched at the same time (e.g. one to start the typer
and one to stop it). The backends run on their own thread and only call the
registered callback; they never touch Tkinter.
"""

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.restype = wintypes.SHORT

# Combinations are not a feature - a hotkey is one key.  This set only
# exists so a bare modifier is refused as one, and so the listener can tell
# a modifier press apart from a key press.
MODIFIERS = {"ctrl", "control", "alt", "shift", "cmd", "win", "super"}

# --- virtual key codes for the polling fallback -------------------------- #
VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "capslock": 0x14, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
}
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i
for _i in range(10):
    VK[str(_i)] = 0x30 + _i
    VK[f"num{_i}"] = 0x60 + _i
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[_c] = ord(_c.upper())
VK.update({"`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
           "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF})


def normalise(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def is_valid(hotkey: str) -> bool:
    """One key, never a combination - combinations are not a feature."""
    parts = [p for p in normalise(hotkey).split("+") if p]
    if len(parts) != 1:
        return False
    key = parts[0]
    if key in MODIFIERS:
        return False
    if key in VK:
        return True
    return len(key) == 1 and key.isalnum()


class HotkeyListener:
    """Watches one or more global hotkeys and fires their callbacks."""

    def __init__(self):
        self._bindings = {}        # hotkey -> callback
        self._parts = {}           # hotkey -> list of parts
        self._pressed = set()
        self._stop = threading.Event()
        self._listener = None
        self._thread = None
        self._poll_prev = {}       # hotkey -> bool (was the key down)

    # ------------------------------------------------------------------ #
    #  registration
    # ------------------------------------------------------------------ #
    def set_hotkey(self, key, callback):
        """Register (or replace) a hotkey. Returns False if the key is invalid."""
        if not is_valid(key):
            return False
        key = normalise(key)
        with self._lock():
            self._bindings[key] = callback
            self._parts[key] = [p for p in key.split("+") if p]
        self._restart()
        return True

    def remove_hotkey(self, key):
        key = normalise(key)
        with self._lock():
            self._bindings.pop(key, None)
            self._parts.pop(key, None)
        self._restart()

    def _lock(self):
        if not hasattr(self, "_guard"):
            self._guard = threading.Lock()
        return self._guard

    # ------------------------------------------------------------------ #
    #  lifecycle
    # ------------------------------------------------------------------ #
    def start(self):
        self._restart()

    def stop(self):
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _restart(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._stop.clear()
        self._pressed.clear()
        self._poll_prev.clear()
        if not self._bindings:
            return
        # The win32 poll is used on purpose: pynput's windows backend spins
        # on the keyboard state in a tight loop, which holds the GIL and
        # starves the interface thread - the app then feels sluggish no
        # matter what it is doing.  Polling every 10 ms is just as quick to
        # react and leaves the cpu alone.
        self._start_polling()

    def _start_polling(self):
        def loop():
            while not self._stop.is_set():
                for hotkey in list(self._bindings):
                    down = self._state_down(hotkey)
                    was = self._poll_prev.get(hotkey, False)
                    self._poll_prev[hotkey] = down
                    if down and not was:
                        self._fire(hotkey)
                time.sleep(0.008)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ #
    #  matching
    # ------------------------------------------------------------------ #
    def _state_down(self, hotkey):
        parts = self._parts.get(hotkey, [])
        required = [p for p in parts if p in MODIFIERS]
        keys = [p for p in parts if p not in MODIFIERS]
        for mod in required:
            if not (user32.GetAsyncKeyState(VK.get(mod, 0)) & 0x8000):
                return False
        if not keys:
            return False
        return bool(user32.GetAsyncKeyState(VK.get(keys[0], 0)) & 0x8000)

    def _on_press(self, key):
        name = getattr(key, "name", None)
        if name is None:
            return
        name = name.lower()
        if name in MODIFIERS:
            self._pressed.add(name)
            return
        for hotkey, parts in self._parts.items():
            required = [p for p in parts if p in MODIFIERS]
            keys = [p for p in parts if p not in MODIFIERS]
            if required and not all(m in self._pressed for m in required):
                continue
            # a plain key must not fire while a modifier is held, so
            # holding one down for something else never trips a binding
            if not required and self._pressed:
                continue
            if keys and name == keys[0]:
                self._fire(hotkey)

    def _on_release(self, key):
        name = getattr(key, "name", None)
        if name:
            self._pressed.discard(name.lower())

    def _fire(self, hotkey):
        callback = self._bindings.get(hotkey)
        if callback is None:
            return
        try:
            callback()
        except Exception:
            pass
