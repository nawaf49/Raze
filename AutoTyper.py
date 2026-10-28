"""
Auto Typer
A premium random auto typer for Windows.

Visual language: a near-black canvas, a neon aurora glow,
a particle field, hairline borders, 20-24px radii, pill buttons and tightly
tracked display type in Plus Jakarta Sans.

The artwork is a single pre-rendered canvas and the UI is positioned on top
with absolute coordinates, so nothing overwrites the background. The process
is DPI aware and CustomTkinter scaling is disabled -> 1:1 pixels, razor sharp.
"""

import ctypes
import json
import math
import os
import random
import sys
import threading
import time
from datetime import datetime

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, END
from tkinter import font as tkfont

from PIL import Image
import pyperclip

import hotkeys as hotkeymod


# --------------------------------------------------------------------------- #
#  DPI awareness (must run before any window exists)
# --------------------------------------------------------------------------- #
def _enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


# --------------------------------------------------------------------------- #
#  Design tokens
# --------------------------------------------------------------------------- #
BG = "#000000"
SURFACE = "#0d0d10"
SURFACE_2 = "#141418"
FIELD = "#0a0a0c"
TEXT = "#f6f6f8"
MUTED = "#a1a1aa"
FAINT = "#71717a"
BORDER = "#1e1e23"
BORDER_2 = "#2c2c33"
INK = "#08080a"
BLUE = "#2f6bff"
CYAN = "#22d3ee"
GREEN = "#22c55e"
RED = "#ef4444"
AMBER = "#f59e0b"

FONT = "Geist"
FONT_MED = "Geist Medium"
FONT_SB = "Geist SemiBold"
FONT_MONO = "Cascadia Mono"

# the font files that get registered at runtime.  Only the faces the app
# actually renders with are shipped: every byte of this list is unpacked by a
# onefile build on each launch.  The names match what Tk resolves - the medium
# and semibold cuts carry their own family names ("Geist Medium").
FONT_FILES = ("Geist-Regular.ttf", "Geist-Medium.ttf", "Geist-SemiBold.ttf",
              "Geist-Bold.ttf", "Geist-ExtraBold.ttf")

TITLE = "Raze"
GITHUB_URL = "https://github.com/nawaf49/Raze"

# --- opening animation ---------------------------------------------------- #
# The window is painted the moment the build finishes, then everything
# settles into place.  The whole window fades up while the nav drops in and
# the cards rise, each one a beat behind the last.
INTRO_FADE_MS = 190          # how long the window takes to fade up
INTRO_MOVE_MS = 380          # how long one element takes to travel
INTRO_STAGGER_MS = 55        # the beat between one card and the next
INTRO_RISE = 18              # how far a card comes up from
INTRO_DROP = -10             # how far the nav comes down from
INTRO_FRAME_MS = 16          # ~60 fps

# --- tab switching --------------------------------------------------------- #
# The underline travels to the chosen tab while the view rises into place.
# The switch itself happens first, so a click is always answered at once -
# this is only the polish on top of it.  Windows' "turn off unnecessary
# animations" is honoured the same way the opening sequence honours it.
TAB_MOVE_MS = 170            # how long one trip takes
TAB_RISE = 10                # how far the view comes up from
TAB_FRAME_MS = 16            # ~60 fps
TAB_WARM_MS = 1500           # when the off-screen tabs are built ahead

# --- coming back from a minimise -------------------------------------------
# Showing the window again repaints every child window it owns, and Windows
# puts that on the screen as it finishes - the interface assembling itself
# piece by piece, which is what "loads choppy on tab-back" was.  So the window
# is held at alpha 0 while the work is paid for: a poll every RESTORE_POLL_MS
# asks Tk for everything it still owes, and two polls under RESTORE_QUIET_MS
# in a row mean the paint has actually stopped.  RESTORE_MAX_MS caps how long
# the window may stay invisible, whatever a pathological restore does.
RESTORE_POLL_MS = 50
RESTORE_QUIET_MS = 8
RESTORE_QUIET_NEEDED = 2
RESTORE_MAX_MS = 1500

# --- status pulse --------------------------------------------------------- #
# The dot and the word breathe while the typer is running.  Every brightness
# step is baked once, so running the animation costs one image swap per frame
# and no rendering at all.  Honours Windows' "turn off unnecessary animations"
# exactly like the opening sequence does.
PULSE_MS = 45                # how long one step is held
PULSE_STEPS = 10             # brightness levels between dim and full

# how often the interface refreshes (the countdown needs to look smooth)
TICK_MS = 50
# how often the log is written to disk (it only runs when something changed)
SAVE_EVERY = 60.0
# how often a notification Windows refused re-asks whether it may go out
TOAST_RETRY_S = 2.0
# how many recent messages are kept in the file
HISTORY_KEEP = 200

# nav tabs: (label, key)
TABS = (("Typer", "typer"), ("Hotkeys", "hotkeys"),
        ("History", "history"))

# big display headline per tab - none any more.  The hotkeys tab used to
# carry "Set it your way." above its card; it was decoration that pushed the
# real controls 100 px down the screen.

# --- layout grid (mirrors build_assets.py) ------------------------------- #
WIN_W = 1060
WIN_H = 860
NAV_H = 68            # content starts below the top bar
MARGIN = 44
CARD_Y = 96
CARD_H = 556
POOL_X, POOL_W = 44, 596
CONFIG_X, CONFIG_W = 654, 362
CONFIG_H = 336
HOTKEY_Y = 450
HOTKEY_H = 202
SESSION_Y, SESSION_H = 672, 150
FOOTER_Y = 840

# the live animated band (canvas layer)
HERO_Y = 96
HERO_H = 204


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def register_fonts():
    """Register the bundled Geist family so Tk can use it."""
    folder = os.path.join(os.path.dirname(resource_path("bg.png")), "fonts")
    ok = False
    for name in FONT_FILES:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        try:
            ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(path), 0x10, 0)
            ok = True
        except Exception:
            pass
    return ok


def read_config(path=None):
    """Read the stored configuration (with the defaults filled in).

    Two things have to survive here.  A byte order mark - which some shells
    and editors leave on the file - must not make the whole config look
    unreadable, and a genuinely unreadable file must never be quietly thrown
    away: the raw bytes are kept beside it as ``config.unreadable.json`` so
    that whatever the user typed can always be recovered by hand.
    """
    defaults = {
        "msg_interval": 2, "loop": 0, "random": False,
        "start_key": "f8", "stop_key": "f9", "pause_key": "f6",
        "resume_key": "f7",
        "messages": []
    }
    target = path or config_path()
    try:
        with open(target, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config is not an object")
        defaults.update(data)
        # a target window used to be configurable; the feature is gone, so
        # drop the retired key rather than carry it forward forever
        defaults.pop("target", None)
    except FileNotFoundError:
        pass                     # first run - the defaults simply apply
    except Exception:
        _preserve_unreadable(target)
    return defaults


def _preserve_unreadable(target):
    """Keep a config we could not parse instead of letting it be overwritten."""
    try:
        if not os.path.exists(target) or os.path.getsize(target) == 0:
            return
        keep = os.path.join(os.path.dirname(target), "config.unreadable.json")
        if os.path.exists(keep):
            return                # the earliest broken state is the useful one
        with open(target, "rb") as src, open(keep, "wb") as dst:
            dst.write(src.read())
    except Exception:
        pass


def group_history(history):
    """How many messages went out on each day -> {day: count}."""
    days = {}
    for stamp, _message in history:
        day = stamp[:10]
        days[day] = days.get(day, 0) + 1
    return days


def pretty_day(day):
    """'2026-10-21' -> 'October 21 Wednesday, 2026'."""
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
        return f"{dt.strftime('%B')} {dt.day} {dt.strftime('%A')}, {dt.year}"
    except ValueError:
        return day


def _ensure_folder_name(folder: str) -> None:
    """Put the profile folder's name right, if it happens to be wrong.

    Windows compares paths without regard to case, so a folder an older build
    created as ``raze`` is accepted forever: ``os.makedirs(..., exist_ok=True)``
    finds it and returns, spelling and all, and the profile shows ``raze`` on
    every machine that ever started out that way.  Renaming the folder itself is
    safe because every path the rest of the code holds is case insensitive - they
    all keep resolving to the same place, now with the product's name on the
    front of it.  A rename that fails because something has the config open just
    waits for the next call.
    """
    parent, want = os.path.split(folder)
    try:
        entries = os.listdir(parent)
    except OSError:
        return
    for entry in entries:
        if entry != want and entry.lower() == want.lower():
            try:
                os.rename(os.path.join(parent, entry), os.path.join(parent, want))
            except OSError:
                pass
            return


def config_path() -> str:
    folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Raze")
    os.makedirs(folder, exist_ok=True)
    _ensure_folder_name(folder)
    return os.path.join(folder, "config.json")


def write_config(data, path=None):
    """Persist the configuration atomically (temp file, then swap it in).

    A crash or a full disk in the middle of the write must never be able to
    leave a half written config behind, so the new bytes are written beside
    the file and only then moved over the old ones.
    """
    target = path or config_path()
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, target)


_MUTEX_HANDLE = None


def acquire_single_instance():
    """Only one copy of Raze may run. Returns False if another one is open."""
    global _MUTEX_HANDLE
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                         ctypes.c_wchar_p]
        kernel32.GetLastError.restype = ctypes.c_ulong
        # per user, per session: a second person on the same machine gets
        # their own Raze and their own app data
        name = "Local\\Raze.AutoTyper.SingleInstance." + \
            os.environ.get("USERNAME", "user")
        handle = kernel32.CreateMutexW(None, True, name)
        if not handle:
            return True
        if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _MUTEX_HANDLE = handle
        return True
    except Exception:
        return True


def focus_existing_instance():
    """Bring the already running window to the front."""
    try:
        user32 = ctypes.windll.user32
        hits = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == "raze":
                hits.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        if hits:
            hwnd = hits[0]
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def reduce_motion_enabled() -> bool:
    """True when Windows has client-area animations turned off."""
    try:
        SPI_GETCLIENTAREAANIMATION = 0x1042
        enabled = ctypes.c_int(0)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
        return bool(ok and enabled.value == 0)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  Keystroke sender
# --------------------------------------------------------------------------- #
# Every key goes out through SendInput rather than keybd_event.  The legacy
# API applies shift one character late, and sending a modifier as its own
# call leaks its state whenever the inter-key delay is zero.  SendInput posts
# the whole batch atomically, so it stays exact at any speed.
_user32 = ctypes.windll.user32
# Shell_NotifyIcon is exported by shell32, not user32 - getting this wrong
# is silent, because every call here is allowed to fail quietly
_shell32 = ctypes.windll.shell32
try:
    # the default int restype would truncate a 64-bit window handle on x64,
    # which would then never compare equal to the real one
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    # without these the icon filename is passed as narrow bytes, and the icon
    # handle is cut down to 32 bits on the way back out
    _user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint]
    _user32.LoadImageW.restype = ctypes.c_void_p
    _user32.DestroyIcon.argtypes = [ctypes.c_void_p]
except Exception:
    pass
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_INPUT_KEYBOARD = 1
_VK_SHIFT = 0x10
_VK_RETURN = 0x0D
_VK_CONTROL = 0x11
_VK_V = 0x56


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class _INPUTunion(ctypes.Union):
    # the union must contain every member so sizeof(INPUT) matches Windows
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTunion)]


def _key_event(vk, flags=0):
    return _INPUT(type=_INPUT_KEYBOARD,
                  u=_INPUTunion(ki=_KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags,
                                              time=0, dwExtraInfo=None)))


def _vk_for(ch):
    """(virtual key, needs shift) for an ASCII character, or (None, False)."""
    try:
        res = _user32.VkKeyScanA(ctypes.c_char(ch.encode("ascii")))
    except Exception:
        return None, False
    if res == -1:
        return None, False
    return res & 0xFF, bool((res >> 8) & 0x01)


def send_char(ch, delay=0.0):
    """Type a single character. Returns False if it cannot be sent."""
    vk, shift = _vk_for(ch)
    if vk is None:
        return False
    events = []
    if shift:
        events.append(_key_event(_VK_SHIFT, 0))
    events.append(_key_event(vk, 0))
    events.append(_key_event(vk, _KEYEVENTF_KEYUP))
    if shift:
        events.append(_key_event(_VK_SHIFT, _KEYEVENTF_KEYUP))
    arr = (_INPUT * len(events))(*events)
    sent = _user32.SendInput(len(events), arr, ctypes.sizeof(_INPUT))
    if sent != len(events):
        return False
    if delay:
        time.sleep(delay)
    return True


def send_enter():
    events = (_INPUT * 2)(_key_event(_VK_RETURN, 0),
                          _key_event(_VK_RETURN, _KEYEVENTF_KEYUP))
    return _user32.SendInput(2, events, ctypes.sizeof(_INPUT)) == 2


def send_paste():
    """Ctrl+V, sent the same way every other key in this app is sent.

    pyautogui used to do this one chord, and it drags in numpy, OpenCV and
    four sibling packages - over a hundred megabytes of payload for a single
    key combination.  One atomic batch is also the more reliable form: the
    window under the caret sees the modifier and the key together rather
    than as two calls with a gap between them.
    """
    events = (_INPUT * 4)(_key_event(_VK_CONTROL, 0),
                          _key_event(_VK_V, 0),
                          _key_event(_VK_V, _KEYEVENTF_KEYUP),
                          _key_event(_VK_CONTROL, _KEYEVENTF_KEYUP))
    return _user32.SendInput(4, events, ctypes.sizeof(_INPUT)) == 4


def is_foreground(hwnd):
    """True when that top-level window is the one currently in front.

    Starting the typer from inside Raze would send the messages straight
    into Raze's own editor, and after the window minimises the destination
    becomes whatever Windows happens to hand focus to - which is not a
    choice the user made.  So a start raised from Raze is refused instead,
    until they have switched to the application they actually want.
    """
    try:
        if not hwnd:
            return False
        return bool(_user32.GetForegroundWindow() == hwnd)
    except Exception:
        return False


# --- the notification the automatic stops raise -------------------------- #
# Balloons go through Shell_NotifyIcon rather than a library: the process is
# meant to sit there for years and has no business taking a dependency, or
# spawning PowerShell, to put one line on the screen.

_NIM_ADD = 0
_NIM_MODIFY = 1
_NIM_DELETE = 2
_NIF_ICON = 0x00000001
_NIF_TIP = 0x00000004
_NIF_INFO = 0x00000010
_NIIF_INFO = 0x00000001
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


class _NOTIFYICONDATAW(ctypes.Structure):
    # Field for field the Vista+ NOTIFYICONDATAW.  sizeof comes to 976 on
    # 64-bit, which selftest asserts - Explorer rejects a wrong cbSize by
    # returning FALSE rather than reading past it, so a mistake degrades to
    # no notification instead of a broken shell.
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_ulong),
        ("uFlags", ctypes.c_ulong),
        ("uCallbackMessage", ctypes.c_ulong),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_ulong),
        ("dwStateMask", ctypes.c_ulong),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeout", ctypes.c_ulong),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_ulong),
        ("guidItem", _GUID),
        ("hBalloonIcon", ctypes.c_void_p),
    ]


def _icon_from(path):
    """Load the app icon, or 0 - a missing icon must never block the call."""
    try:
        return _user32.LoadImageW(0, path, _IMAGE_ICON, 0, 0,
                                  _LR_LOADFROMFILE) or 0
    except Exception:
        return 0


def notify_balloon(hwnd, title, body, icon_path=None, uid=1):
    """Raise a Windows notification. Returns True if Windows took it.

    Everything in here is best effort: the run is already over, and the
    interface still shows what happened, so a refused notification is never
    allowed to turn into an error the caller has to deal with.
    """
    if not hwnd:
        return False
    try:
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = uid

        hicon = _icon_from(icon_path) if icon_path else 0
        try:
            if hicon:
                nid.hIcon = hicon
                nid.szTip = "Raze"
                nid.uFlags = _NIF_ICON | _NIF_TIP
                # an entry has to exist before a balloon can hang off it
                _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
        finally:
            if hicon:
                _user32.DestroyIcon(hicon)

        nid.uFlags = _NIF_INFO
        nid.szInfo = body[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = _NIIF_INFO
        return bool(_shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(nid)))
    except Exception:
        return False


def notify_clear(hwnd, uid=1):
    """Drop the tray entry the notification created."""
    if not hwnd:
        return False
    try:
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = uid
        return bool(_shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid)))
    except Exception:
        return False


# The shell's own verdict on whether now is a time to interrupt.  A
# full-screen game (QUNS_BUSY), a locked screen, quiet hours or presentation
# settings make Explorer swallow a balloon while Shell_NotifyIcon still
# answers TRUE - accepted, and then never shown.  That is exactly what
# "notifications don't work" looked like from in here: Raze did its part and
# Windows sat on it, so the message now waits for the screen to free up.
_QUNS_ACCEPTS_NOTIFICATIONS = 5


def _notification_state():
    """The shell's current state, or None when it would not answer."""
    try:
        state = ctypes.c_int(0)
        if _shell32.SHQueryUserNotificationState(ctypes.byref(state)):
            return None
        return int(state.value)
    except Exception:
        return None


def notifications_allowed():
    """True unless Windows is refusing banners right now.

    None (no answer) counts as allowed: a notification must never be held
    hostage by a query that failed.
    """
    return _notification_state() in (None, _QUNS_ACCEPTS_NOTIFICATIONS)


_IMAGE_CACHE = {}


def image_for(name):
    """Cached CTkImage for an asset (avoids rebuilding them on every widget)."""
    if name not in _IMAGE_CACHE:
        im = Image.open(resource_path(name))
        _IMAGE_CACHE[name] = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
    return _IMAGE_CACHE[name]


_EMBLEM_CACHE = {}


def emblem_photo(size):
    """The raze emblem, re-cut from the master artwork at device resolution.

    It is drawn through a plain tk label so the pixels are placed 1:1 on the
    screen - customtkinter would rescale the image a second time.
    """
    key = ("emblem", size)
    if key not in _EMBLEM_CACHE:
        from PIL import ImageTk
        im = Image.open(resource_path("raze_emblem.png")).convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        px_size = px(size)
        im = im.resize((px_size, px_size), Image.Resampling.LANCZOS)
        _EMBLEM_CACHE[key] = ImageTk.PhotoImage(im)
    return _EMBLEM_CACHE[key]


# --- device scale --------------------------------------------------------- #
def _device_scale():
    """How many device pixels one design pixel is worth on this display."""
    override = os.environ.get("RAZE_SCALE")
    if override:
        try:
            return max(0.25, float(override))
        except ValueError:
            pass
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return max(1.0, dpi / 96.0)
    except Exception:
        pass
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        if dpi:
            return max(1.0, dpi / 96.0)
    except Exception:
        pass
    return 1.0


S = _device_scale()       # 1.0 on a standard display, 1.5 on a 150% 4K screen

# The frame Windows draws around the client area - borders plus title bar -
# at the display's own dpi.  The design grid never sees it, but anything
# that has to fit on screen has to leave room for it.  Measured 16x39 at
# 100%; the extra is slack for larger title bars.
FRAME_W, FRAME_H = 24, 48
SCALE_MIN = 0.5           # below this the app is too small to be usable


def _fit_scale(dpi_scale, avail_w, avail_h):
    """Shrink the scale so the whole window fits the screen it opens on.

    The design is a fixed 1060x860 and the window is not resizable, so on
    a screen smaller than that - a 1366x768 laptop, or a 1080p display at
    125% - the session card and the footer used to sit past the bottom
    edge with no way to reach them.  Everything on screen is drawn through
    this one factor, so shrinking it takes the whole app down together,
    still sharp: the baked artwork is re-rendered at the new size rather
    than stretched.
    """
    if avail_w <= 0 or avail_h <= 0:      # no usable work area reported
        return dpi_scale
    room_w = (avail_w - int(FRAME_W * dpi_scale)) / WIN_W
    room_h = (avail_h - int(FRAME_H * dpi_scale)) / WIN_H
    return max(SCALE_MIN, min(dpi_scale, room_w, room_h))


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _work_area():
    """The primary monitor's work area in device pixels (taskbar excluded)."""
    try:
        rect = _RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0)      # SPI_GETWORKAREA
        if ok and rect.right > rect.left and rect.bottom > rect.top:
            return rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        pass
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


if not os.environ.get("RAZE_SCALE"):
    # A forced scale is a debugging hatch and is taken as asked; anything
    # else is shrunk to fit this screen - see _fit_scale.
    S = _fit_scale(S, *_work_area())


def px(value):
    """Design pixels -> device pixels."""
    return int(round(value * S))


# --- text rendering ------------------------------------------------------- #
_TEXT_CACHE = {}


def _font_dir():
    return os.path.join(os.path.dirname(resource_path("bg.png")), "fonts")


_MONO_PATH = None


def _mono_font_path():
    """A monospaced face for the log.

    Windows ships Cascadia Mono; Consolas is the fallback.  When neither is
    present the log falls back to the bundled Geist.
    """
    global _MONO_PATH
    if _MONO_PATH is not None:
        return _MONO_PATH or None
    root = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("CascadiaMono.ttf", "CascadiaCode.ttf", "consola.ttf",
                 "Consola.ttf", "DejaVuSansMono.ttf"):
        path = os.path.join(root, "Fonts", name)
        if os.path.exists(path):
            _MONO_PATH = path
            return path
    _MONO_PATH = ""
    return None


_DIGIT_SPRITES = {}

# the numbers sit on the card, so their shades are pre blended with it
_GUTTER_BG = (13, 13, 16)
_GUTTER_FG = (113, 113, 122)


def _gutter_palette():
    """The pre blended shades of a number, from the card to the ink."""
    flat = []
    for v in range(256):
        t = v / 255.0
        for c in range(3):
            flat.append(int(_GUTTER_BG[c] + (_GUTTER_FG[c] - _GUTTER_BG[c]) * t))
    return flat


def _digit_sprite(digit, size=10, weight="Regular", color=FAINT):
    """A baked digit, reused by every number that contains it."""
    key = (digit, size, weight, color)
    sprite = _DIGIT_SPRITES.get(key)
    if sprite is None:
        from textengine import render
        sprite = render(digit, px(size), _font_dir(), weight=weight, color=color,
                        pad=0)
        _DIGIT_SPRITES[key] = sprite
    return sprite


def _draw_number(target, text, right, top):
    """Draw a number right aligned at `right`, with its top at `top`."""
    x = right
    for ch in reversed(text):
        sprite = _digit_sprite(ch)
        x -= sprite.width
        if x < 0:
            break
        target.alpha_composite(sprite, (x, top))


def luminance(color):
    """The perceived brightness of a colour (0 - 255)."""
    try:
        c = str(color).lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 255.0


def mix(color_a, color_b, t):
    """Blend two #rrggbb colours.  0.0 is all of the first, 1.0 all of the second."""
    a = tuple(int(color_a[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(
        int(round(x + (y - x) * t)) for x, y in zip(a, b))


def text_photo(text, size, weight="Regular", color=TEXT, tracking=0.0,
               mono=False, darken=True, min_width=None, max_width=None):
    """Rasterise text at the display's native resolution.

    The glyphs are drawn by FreeType at exactly the pixel size they are
    displayed at and the colour is applied to the coverage mask afterwards,
    so the antialiasing stays neutral and every stem lands on a whole pixel.
    """
    key = (text, size, weight, color, round(tracking, 3), S, mono, darken,
           min_width, max_width)
    if key in _TEXT_CACHE:
        return _TEXT_CACHE[key]
    if len(_TEXT_CACHE) > 4000:
        # years of running must not eat memory - the oldest artwork goes
        _TEXT_CACHE.clear()

    from PIL import ImageTk
    from textengine import render

    img = render(text, px(size), _font_dir(), weight=weight, color=color,
                 tracking=px(tracking), darken=darken,
                 path=_mono_font_path() if mono else None,
                 min_px=px(min_width) if min_width else None,
                 max_px=px(max_width) if max_width else None)
    photo = ImageTk.PhotoImage(img)
    _TEXT_CACHE[key] = (photo, img.size)
    return _TEXT_CACHE[key]


def resolve_bg(widget):
    """Find the opaque background colour behind a widget."""
    w = widget
    while w is not None:
        try:
            fg = w.cget("fg_color")
            if fg and fg != "transparent":
                return fg
        except Exception:
            pass
        try:
            bg = w.cget("bg")
            if isinstance(bg, str) and bg not in ("", "transparent"):
                return bg
        except Exception:
            pass
        w = getattr(w, "master", None)
    return "#000000"


class Card(ctk.CTkFrame):
    """A surface card: dark fill, hairline border, 20px radius."""

    def __init__(self, master, width=None, height=None, **kwargs):
        kwargs.setdefault("fg_color", SURFACE)
        kwargs.setdefault("corner_radius", 20)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER)
        if width is not None:
            kwargs["width"] = width
        if height is not None:
            kwargs["height"] = height
        super().__init__(master, **kwargs)


class BakedLabel(tk.Label):
    """A label whose text is rendered as artwork.

    Tk draws text with ClearType, which puts blue/orange fringes on a dark
    background.  Rendering the glyphs ourselves gives clean grayscale
    antialiasing instead - the same look a browser shows on a dark page.
    """

    def __init__(self, master, text="", size=12, weight="Regular", color=TEXT,
                 tracking=0.0, mono=False, min_width=None, max_width=None, **kwargs):
        bg = kwargs.pop("bg", None) or resolve_bg(master)
        if kwargs.get("height"):
            kwargs["height"] = px(kwargs["height"])
        # stem darkening only helps light text on a dark background
        self._darken = luminance(color) > luminance(bg)
        super().__init__(master, bd=0, highlightthickness=0, bg=bg, **kwargs)
        self._size = size
        self._weight = weight
        self._color = color
        self._tracking = tracking
        self._mono = mono
        self._min_width = min_width
        self._max_width = max_width
        # whether the caller pinned a height at build time (already px()d)
        self._fixed_height = bool(kwargs.get("height"))
        self._photo = None
        self._text = None
        self.set_text(text)

    def set_text(self, text):
        if text == self._text and self._photo is not None:
            return
        self._text = text
        self._render()

    def set_color(self, color):
        if color == self._color:
            return
        self._color = color
        self._render()

    def sync_bg(self):
        """Re-resolve the background after an ancestor's fill changed.

        The background is read once at build time, so a parent that changes
        fill later (a pill lightening under the cursor) used to leave the old
        colour painted behind the artwork - a visible dark box around the
        text.  Call this whenever the parent's fill moves.
        """
        bg = resolve_bg(self.master)
        if str(self.cget("bg")) != bg:
            self.configure(bg=bg)

    def show_frame(self, frames, index):
        """Show one of a set of pre-rendered images.

        Animating by redrawing the glyphs each frame would mean a FreeType
        render and a fresh PhotoImage at frame rate.  The steps are baked
        ahead of time instead, so running an animation is a single swap.
        """
        if not frames:
            return
        self.configure(image=frames[max(0, min(index, len(frames) - 1))],
                       text="")

    def _render(self):
        photo, _size = text_photo(self._text, self._size, self._weight, self._color,
                                  self._tracking, self._mono, self._darken,
                                  self._min_width, self._max_width)
        self._photo = photo
        self.configure(image=photo, text="")
        if self._fixed_height:
            # A box shorter than its own artwork cuts the glyphs.  The box is
            # design px converted once at build time, but the rendered photo
            # is font metrics at the rounded device size, so below ~100%
            # scale the two stop matching (height 7 for a 9 px photo at
            # S=0.5).  The floor keeps a pinned height a *minimum*: rows are
            # sized by their content, so a pinned box still cannot move.
            if int(self.cget("height")) < photo.height():
                self.configure(height=photo.height())

    def set_box(self, min_width=None, max_width=None):
        """Pin the label to a fixed box so its content cannot move anything."""
        if min_width == self._min_width and max_width == self._max_width:
            return
        self._min_width = min_width
        self._max_width = max_width
        self._render()

    def place(self, **kwargs):
        """Place the label using device pixels (a plain tk widget is not
        scaled by customtkinter the way CTk widgets are)."""
        for key in ("x", "y"):
            if kwargs.get(key) is not None:
                kwargs[key] = px(kwargs[key])
        return super().place(**kwargs)

    @staticmethod
    def _pad(kwargs):
        """Rewrite geometry padding from design px to device px.

        CTkBaseClass.pack/grid run their arguments through
        _apply_argument_scaling, so a CTk child's padx/pady is scaled for
        free; a plain tk child never sees that call.  Left alone, a
        `padx=14` here stays 14 *device* px while the artwork around it
        shrinks with S - which is exactly what cut the tile captions on a
        clamped laptop screen (92 px tile - 28 px padding = 64 px of room
        for 73 px of text at S=0.78).
        """
        kwargs = dict(kwargs)
        for key in ("padx", "pady", "ipadx", "ipady"):
            v = kwargs.get(key)
            if v is None:
                continue
            if isinstance(v, (tuple, list)):
                kwargs[key] = tuple(px(i) for i in v)
            elif isinstance(v, (int, float)):
                kwargs[key] = px(v)
        return kwargs

    def pack(self, **kwargs):
        """Pack with padding written in design px - see _pad()."""
        return super().pack(**self._pad(kwargs))

    def grid(self, **kwargs):
        """Grid with padding written in design px - see _pad()."""
        return super().grid(**self._pad(kwargs))


class BakedButton(ctk.CTkFrame):
    """A pill button whose label is baked artwork (no ClearType fringing)."""

    def __init__(self, master, text, command=None, size=12, weight="SemiBold",
                 color=TEXT, fill=TEXT, hover="#ffffff", border=None,
                 hover_border=None, height=36, radius=None, tracking=0.0,
                 **kwargs):
        super().__init__(master, fg_color=fill, corner_radius=radius or height // 2,
                         border_width=1 if border else 0,
                         border_color=border or fill, height=height, cursor="hand2",
                         **kwargs)
        self._command = command
        self.label = BakedLabel(self, text, size=size, weight=weight,
                                color=color, tracking=tracking)
        self.label.place(relx=0.5, rely=0.5, anchor="center")
        # No update_idletasks() here.  The label's requested width is already
        # correct the moment its photo is configured - it matches the rendered
        # image pixel for pixel - and a flush would instead drain every pending
        # layout event in the whole app.  During _warm_views that pile is at
        # its largest, so four pills alone cost ~130 ms and the opening
        # interface visibly hitched.
        # winfo_reqwidth is device px; CTk configure expects design px and
        # scales it again - divide it back out or every button is S times
        # too wide on a scaled display
        self.configure(width=self.label.winfo_reqwidth() / S + 28, height=height)
        self._hover = hover
        self._rest_fill = fill
        self._rest_border = border
        self._hover_border = hover_border
        for widget in (self, self.label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None):
        self.configure(fg_color=self._hover)
        if self._hover_border is not None:
            self.configure(border_color=self._hover_border)
        self.label.sync_bg()

    def _on_leave(self, _event=None):
        self.configure(fg_color=self._rest_fill)
        if self._rest_border is not None:
            self.configure(border_color=self._rest_border)
        self.label.sync_bg()

    def _on_click(self, event):
        if self._command:
            self._command()


class Pill(BakedButton):
    """Rounded pill button whose label is baked artwork (no ClearType fringes).

    kind: 'solid' (white), 'glass' (outlined) or 'danger'.
    """

    def __init__(self, master, text, command=None, kind="glass", width=None,
                 font=(FONT_SB, -12), **kwargs):
        height = kwargs.pop("height", 36)
        size = abs(font[1]) if len(font) > 1 and isinstance(font[1], int) else 12
        if kind == "solid":
            fill, hover, text_color = TEXT, "#ffffff", INK
            border, hover_border = None, None
        elif kind == "danger":
            fill, text_color, border = "#1a0f11", "#ff7a7a", "#4a1f24"
            hover, hover_border = "#2a1216", "#3a181c"
        else:
            fill, text_color, border = SURFACE_2, TEXT, BORDER_2
            hover, hover_border = "#1d1d22", "#28282f"
        super().__init__(master, text, command, size=size, weight="SemiBold",
                         color=text_color, fill=fill, hover=hover,
                         border=border, hover_border=hover_border,
                         height=height, **kwargs)
        if width:
            self.configure(width=width)


class IconButton(ctk.CTkButton):
    def __init__(self, master, text, command=None, danger=False, **kwargs):
        super().__init__(master, text=text, command=command, width=32, height=32,
                         corner_radius=16, font=(FONT, -12),
                         fg_color=SURFACE_2, hover_color="#1d1d22",
                         text_color="#ff7a7a" if danger else MUTED,
                         border_width=1, border_color=BORDER_2, **kwargs)


class NumberField(ctk.CTkFrame):
    """A premium numeric field: free-form typing + steppers, no fixed range."""

    def __init__(self, master, value=0, minimum=0, maximum=None, step=1,
                 decimals=0, on_change=None, width=92, height=36):
        super().__init__(master, fg_color="transparent")
        self._value = value
        self._min = minimum
        self._max = maximum
        self._step = step
        self._decimals = decimals
        self._on_change = on_change

        self.var = tk.StringVar(value=self._format(value))
        self.entry = ctk.CTkEntry(self, textvariable=self.var, width=width, height=height,
                                  corner_radius=10, font=(FONT_SB, -12),
                                  fg_color=SURFACE_2, border_color=BORDER_2,
                                  text_color=TEXT, justify="right")
        self.entry.pack(side="left")
        self.entry.bind("<Return>", lambda e: self._commit())
        self.entry.bind("<FocusOut>", lambda e: self._commit())
        self.entry.bind("<KeyPress>", self._on_key)

        self.minus = self._stepper("−", -1)
        self.minus.pack(side="left", padx=(8, 0))
        self.plus = self._stepper("+", 1)
        self.plus.pack(side="left", padx=(6, 0))

    def _stepper(self, glyph, direction):
        btn = ctk.CTkButton(self, text=glyph, command=lambda: self._bump(direction),
                            width=36, height=36, corner_radius=10,
                            font=(FONT, -14), fg_color=SURFACE_2,
                            hover_color="#1d1d22", text_color=MUTED,
                            border_width=1, border_color=BORDER_2)
        return btn

    # ----- value ---------------------------------------------------------- #
    def _format(self, value):
        if self._decimals:
            return f"{value:.{self._decimals}f}".rstrip("0").rstrip(".")
        return str(int(round(value)))

    def get(self):
        return self._value

    def set(self, value, call_change=True):
        value = max(self._min, value)
        if self._max is not None:
            value = min(self._max, value)
        if not self._decimals:
            value = int(round(value))
        self._value = value
        self.var.set(self._format(value))
        if call_change and self._on_change:
            self._on_change(value)

    def _bump(self, direction):
        self.set(self._value + direction * self._step)

    def _on_key(self, event):
        # keep the entry numeric-ish
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Home", "End"):
            return
        if event.char and not (event.char.isdigit() or
                               (event.char == "." and self._decimals)):
            return "break"

    def _commit(self):
        raw = self.var.get().strip().replace("∞", "0")
        try:
            value = float(raw)
        except ValueError:
            self.var.set(self._format(self._value))
            return
        if self._decimals == 0:
            value = int(round(value))
        self.set(value, call_change=False)
        if self._on_change:
            self._on_change(self._value)


class StatTile(ctk.CTkFrame):
    # design px of room either side of the caption and the value
    PAD = 14

    def __init__(self, master, caption, width=None, **kwargs):
        super().__init__(master, fg_color=SURFACE_2, corner_radius=14,
                         border_width=1, border_color=BORDER, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)      # top spacer
        self.grid_rowconfigure(3, weight=1)      # bottom spacer
        cap = BakedLabel(self, caption, size=9, weight="SemiBold", color=FAINT,
                         tracking=1.1, height=14, anchor="w")
        cap.grid(row=1, column=0, sticky="w", padx=self.PAD)
        # the tile has a fixed width, so a counter going from 9 to 10 cannot
        # move a single pixel - the value stays left aligned under its caption
        self.value = BakedLabel(self, "0", size=21, weight="SemiBold", color=TEXT,
                                anchor="w", height=28)
        self.value.grid(row=2, column=0, sticky="w", padx=self.PAD, pady=(2, 0))
        if width:
            # The caption is already rendered, so the room it needs is known
            # exactly for *this* scale.  Its design width grows below ~60%
            # scale (the font is round(size*S) and the tracking round(1.1*S),
            # neither of which shrinks in step with S), so the box takes the
            # wider of the design width and what this scale's artwork needs.
            # It is computed once, at build time: a running counter still
            # cannot move it.
            room = max(width, cap.winfo_reqwidth() / S + 2 * self.PAD + 2)
            self.configure(width=room)
            self.grid_propagate(False)
            # and a value that outgrows the box (7 digits and up) is
            # ellipsized by its own label rather than cut by the tile
            self.value.set_box(max_width=room - 2 * self.PAD)

    def set(self, text, color=None):
        self.value.set_text(text)
        if color:
            self.value.set_color(color)


# --------------------------------------------------------------------------- #
#  Session counters
# --------------------------------------------------------------------------- #
def _elapsed_text(seconds):
    """The session clock in a form that cannot outgrow its tile.

    It used to be `mm:ss`, which is exact and unbounded: minutes never stop
    climbing, so a day and a half printed `2098:47`, and a year in it wanted
    `525600:00` - nine characters in a five digit box, ellipsized down to
    `5256…`.  Each step below trades the precision you no longer need for
    the digits you do: `mm:ss` under an hour, then hours, days, years.  The
    longest string it can produce is nine characters.
    """
    t = max(0, int(seconds or 0))
    if t < 3600:
        return "%02d:%02d" % divmod(t, 60)
    if t < 86400:
        return "%dh %02dm" % (t // 3600, (t % 3600) // 60)
    if t < 86400 * 365:
        return "%dd %dh" % (t // 86400, (t % 86400) // 3600)
    return "%dy %dd" % (t // (86400 * 365), (t % (86400 * 365)) // 86400)


def _next_text(seconds):
    """Whole seconds until the next message: `95s`, never `94.7s`."""
    if not seconds:
        return "--"
    return "%ds" % math.ceil(seconds)


# --------------------------------------------------------------------------- #
#  Application
# --------------------------------------------------------------------------- #
class AutoTyper:
    def __init__(self, root):
        self.root = root
        self.root.title("Raze")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG)
        # nothing may flash on screen before the opening animation takes it
        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            pass
        self._set_window_icon()

        self._intro_items = []

        # a restore repaints the whole app at once - see _on_map
        self._restore_drain = False
        self._restore_quiet = 0
        self._restore_polls = 0
        self._restore_started = 0.0
        self.root.bind("<Map>", self._on_map)
        self.root.bind("<Unmap>", self._on_unmap)

        self._drag_offset = (0, 0)
        self.typing = False
        self.arming = False
        self.paused = False
        self.typing_thread = None
        self.stop_event = threading.Event()
        self.start_key = "f8"
        self.stop_key = "f9"
        self.pause_key = "f6"
        self.resume_key = "f7"
        self.messages = []
        self.stats = {"sent": 0, "chars": 0, "elapsed": 0.0}
        self._next_deadline = None
        self._session_start = None
        self._last_message = ""
        self._stop_requested = False
        self._start_requested = False
        self._worker_done = False
        # the top-level handle captured at start time (reading Tk from the
        # worker thread is not safe), and the reason the worker bailed out
        self._raze_hwnd = 0
        self._tab_in_stop = False
        self._worker_error = None
        # the pause and resume requests raised by the hotkey thread and read
        # on the Tk thread - the only thing that crosses between the two
        self._pause_requested = False
        self._resume_requested = False
        self._history_dirty = False
        self._last_save = 0.0
        # a notification Windows would not show yet, and the last time the
        # heartbeat asked whether it may go out now
        self._pending_toast = None
        self._toast_retry = 0.0
        # which loop the worker is on, read by the session card
        self.passes = 0
        self._generation = 0
        self.daily = {}
        # the status pulse - its frames are baked once and then swapped,
        # never redrawn, so it costs nothing to leave running
        self._pulse_on = False
        self._pulse_i = 0
        self._pulse_frames = None
        # auto send (enter) after every message is always on; whether the
        # pool is walked in order or picked from at random is configurable
        self._random_pick = False
        self._auto_enter = True

        self.cfg = self._load_config()
        self._tab = "typer"
        self._views = {}
        self.history = []

        self._build_canvas()
        self._build_nav()
        self._build_content()

        self._apply_config()
        self._register_hotkey()
        self._center_window()
        self._play_intro()
        self.root.after(150, self._tick)
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
        self.root.after(1500, self._prebake_history)
        self.root.after(1800, self._pulse_build)
        self.root.after(300, lambda: self.root.focus_force())
        self.root.after(400, self._set_window_icon)

    # ------------------------------------------------------------------ #
    #  Animated background (canvas layer)
    # ------------------------------------------------------------------ #

    def _set_window_icon(self, window=None):
        """Force the raze emblem as the window + taskbar icon.

        Tk's iconphoto() is ignored by the Windows title bar, so the icon is
        pushed through WM_SETICON directly. This also beats any icon cache
        Windows may still hold for a previously built exe.
        """
        window = window or self.root
        try:
            # proper app identity -> taskbar uses the shortcut's name + icon
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Raze.AutoTyper.1")
        except Exception:
            pass
        try:
            path = resource_path("raze.ico")
            if not os.path.exists(path):
                return
            user32 = ctypes.windll.user32
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000010
            WM_SETICON = 0x0080

            # 64-bit safe signatures (handles must not be truncated to int)
            user32.GetParent.restype = ctypes.c_void_p
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                         ctypes.c_uint, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_uint]
            user32.SendMessageW.restype = ctypes.c_size_t
            user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                            ctypes.c_size_t, ctypes.c_size_t]

            big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_DEFAULTSIZE)
            small = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            if not big:
                return
            hwnd = user32.GetParent(window.winfo_id())
            user32.SendMessageW(hwnd, WM_SETICON, 1, big)    # ICON_BIG
            if small:
                user32.SendMessageW(hwnd, WM_SETICON, 0, small)   # ICON_SMALL

            # the Windows 11 title bar draws the *class* icon, so set that too
            set_class = getattr(user32, "SetClassLongPtrW", None)
            if set_class is None:
                set_class = user32.SetClassLongW
            set_class.restype = ctypes.c_size_t
            set_class.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
            set_class(hwnd, -14, big)      # GCLP_HICON
            if small:
                set_class(hwnd, -40, small)   # GCLP_HICONSM

            self._icon_handles = (big, small)
        except Exception:
            pass

    def _build_canvas(self):
        """Pure black backdrop (no animation).

        This used to load a full window sized PNG that turned out to be one
        flat colour - opening, decoding and stretching it cost about 60 ms on
        every launch to draw a picture of nothing.
        """
        tk.Frame(self.root, bg=BG).place(x=0, y=0, relwidth=1.0, relheight=1.0)

    def _img(self, name, size=None):
        im = Image.open(resource_path(name))
        if size:
            im = im.resize(size, Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=im, dark_image=im, size=size or im.size)

    def _place(self, widget, x, y, w=None, h=None):  # noqa: D401
        """Place a widget at an exact pixel size (CTk forbids width/height in place())."""
        args = ["place", widget._w, "-x", str(px(x)), "-y", str(px(y))]
        if w:
            args += ["-width", str(px(w))]
        if h:
            args += ["-height", str(px(h))]
        self.root.tk.call(*args)

    # ------------------------------------------------------------------ #
    #  Opening animation
    # ------------------------------------------------------------------ #
    def _anim(self, widget, x, y, delay=0.0, dx=0.0, dy=0.0):
        """Place a widget and remember it for the opening animation.

        dx/dy are where it starts from; the travel back to x/y happens in
        _play_intro.  A straight tk place call is used for both plain and
        customtkinter widgets so one code path covers everything.
        """
        self._intro_items.append((widget, x, y, delay, dx, dy))
        self._move(widget, x + dx, y + dy)

    def _move(self, widget, x, y):
        """Slide an already placed widget to a new position."""
        # width/height are left alone on purpose - tk keeps whatever was set
        self.root.tk.call("place", widget._w, "-x", str(px(x)), "-y", str(px(y)))

    def _play_intro(self):
        """Fade the window up while the interface settles into place.

        Windows' own "turn off unnecessary animations" setting is honoured:
        with it on the window simply appears, fully formed.
        """
        items, self._intro_items = self._intro_items, []
        try:
            if not items or reduce_motion_enabled():
                # "fully formed" means at the final positions - the widgets
                # were placed where the travel would have started them, so
                # they have to be settled home before the intro stands down
                for widget, x, y, _delay, _dx, _dy in items:
                    self._move(widget, x, y)
                self._intro_done = True
                self.root.attributes("-alpha", 1.0)
                self.root.after(120, self._align_nav)
                return
        except Exception:
            self._intro_done = True
            return
        start = time.perf_counter()

        def step():
            try:
                t = (time.perf_counter() - start) * 1000.0
                self.root.attributes("-alpha", min(1.0, t / INTRO_FADE_MS))
                live = t < INTRO_FADE_MS
                for widget, x, y, delay, dx, dy in items:
                    p = (t - delay) / INTRO_MOVE_MS
                    if p < 0.0:
                        p = 0.0
                    elif p < 1.0:
                        live = True
                    else:
                        p = 1.0
                    ease = 1.0 - (1.0 - p) ** 3       # ease out cubic
                    self._move(widget, x + dx * (1.0 - ease),
                               y + dy * (1.0 - ease))
                if live:
                    self.root.after(INTRO_FRAME_MS, step)
                else:
                    self._intro_done = True
                    self.root.attributes("-alpha", 1.0)
                    # everything has settled, so the nav can be lined up
                    # against its real, final positions
                    self._align_nav()
            except Exception:
                pass                                  # the window is gone

        step()

    # ------------------------------------------------------------------ #
    #  Navigation
    # ------------------------------------------------------------------ #
    def _build_nav(self):
        """A flat top bar: brand on the left, tabs centred, actions on the right."""
        # --- brand, far left
        emblem = tk.Label(self.root, image=emblem_photo(34), bd=0, cursor="hand2",
                           highlightthickness=0, bg=BG)
        self._anim(emblem, MARGIN, 17, dy=INTRO_DROP)
        wordmark = BakedLabel(self.root, "Raze", size=20, weight="ExtraBold",
                              color=TEXT, tracking=-0.6, height=26, anchor="w", cursor="hand2")
        self._anim(wordmark, MARGIN + 44, 19, dy=INTRO_DROP)

        # the lockup doubles as the repository link, the way a site logo does
        self._brand = (emblem, wordmark)
        for brand in self._brand:
            brand.bind("<Button-1>", lambda e: self._open_github())

        # --- tabs, centred
        self._tab_items = {}
        self._tab_font = tkfont.Font(family=FONT_MED, size=-px(12))
        labels = []
        total = 0
        for name, key in TABS:
            # the font is sized in device px, so the measurement comes back
            # in device px; divide it out so every position below is in
            # design px, the units _move/px() expect
            width = self._tab_font.measure(name) / S
            item = BakedLabel(self.root, name, size=12, weight="Medium", color=MUTED,
                              height=24, cursor="hand2")
            item.bind("<Button-1>", lambda e, k=key: self.show(k))
            item.bind("<Enter>", lambda e, k=key: self._tab_hover(k, True))
            item.bind("<Leave>", lambda e, k=key: self._tab_hover(k, False))
            self._tab_items[key] = (item, 0, width)
            labels.append((name, key, item, width))
            total += width + 30
        total -= 30                       # no trailing gap
        x = (WIN_W - total) // 2
        for name, key, item, width in labels:
            self._anim(item, x, 21, delay=INTRO_STAGGER_MS * 0.75, dy=INTRO_DROP)
            self._tab_items[key] = (item, x, x + width)
            x += width + 30
        self._underline = ctk.CTkFrame(self.root, width=24, height=2, corner_radius=1,
                                       fg_color=TEXT)
        # parked under the tab that opens, so the travel lands on it exactly
        first_x0, first_x1 = self._tab_items[TABS[0][1]][1:]
        self._underline_x = (first_x0 + first_x1) // 2 - 12
        self._anim(self._underline, self._underline_x, 52,
                   delay=INTRO_STAGGER_MS * 0.75, dy=INTRO_DROP)

        # --- actions, far right
        self.status_dot = BakedLabel(self.root, "\u25cf", size=13, color=FAINT)
        self.status_text = BakedLabel(self.root, "IDLE", size=10, weight="SemiBold",
                                      color=MUTED)
        self.github_btn = BakedButton(self.root, "Star on GitHub", self._open_github,
                                      size=10, weight="SemiBold", fill=TEXT,
                                      hover="#ffffff", color=INK, height=32)
        self.root.update_idletasks()
        # same unit rule as the tabs: these widgets report device px, the
        # arithmetic below is design px
        gw = self.github_btn.winfo_reqwidth() / S
        gx = WIN_W - MARGIN - gw
        self._anim(self.github_btn, gx, 18, delay=INTRO_STAGGER_MS * 1.5,
                   dy=INTRO_DROP)
        sw = self.status_text.winfo_reqwidth() / S
        sx = gx - 40 - sw
        self._anim(self.status_text, sx, 20, delay=INTRO_STAGGER_MS * 1.5,
                   dy=INTRO_DROP)
        self._anim(self.status_dot, sx - 20, 20, delay=INTRO_STAGGER_MS * 1.5,
                   dy=INTRO_DROP)

    def _set_status(self, text, color):
        self.status_text.set_text(text)
        self.status_text.set_color(color)
        self.status_dot.set_color(color)

    # ----- status pulse --------------------------------------------------- #
    def _pulse_build(self):
        """Bake the brightness steps for everything that breathes.

        Done on a timer after start-up rather than when typing begins, so
        pressing the hotkey never pays for it.
        """
        if self._pulse_frames is not None:
            return self._pulse_frames
        # the dot swings hard, the words only a little - a word that fades
        # far enough stops being readable, and it should stay readable
        try:
            def steps(text, size, weight, floor):
                out = []
                for i in range(PULSE_STEPS):
                    t = i / (PULSE_STEPS - 1)
                    out.append(text_photo(text, size, weight,
                                          mix(mix(FAINT, GREEN, floor), GREEN, t))[0])
                return out

            self._pulse_frames = [
                (self.status_dot, steps("\u25cf", 13, "Regular", 0.35)),
                (self.status_text, steps("TYPING", 10, "SemiBold", 0.55)),
                (self.session_state, steps("Typing", 11, "Regular", 0.55)),
            ]
        except Exception:
            # remembered as unusable, so the frame loop never retries the
            # bake over and over, twenty times a second, for ever
            self._pulse_frames = []
        return self._pulse_frames

    def _pulse_start(self):
        if self._pulse_on or reduce_motion_enabled():
            return
        self._pulse_on = True
        self._pulse_i = 0
        try:
            self.root.after(PULSE_MS, self._pulse_step)
        except Exception:
            self._pulse_on = False

    def _pulse_stop(self):
        self._pulse_on = False

    def _pulse_step(self):
        if not self._pulse_on or not self.typing:
            self._pulse_on = False
            return                      # set colour restores the still image
        try:
            targets = self._pulse_build()
            if not targets:
                self._pulse_on = False
                return                      # the bake failed - stop cleanly
            span = PULSE_STEPS - 1
            p = self._pulse_i % (span * 2)
            index = p if p <= span else span * 2 - p
            for widget, frames in targets:
                widget.show_frame(frames, index)
            self._pulse_i += 1
            self.root.after(PULSE_MS, self._pulse_step)
        except Exception:
            self._pulse_on = False

    def _align_nav(self, tries=0):
        """Put the status on exactly the same line as the GitHub button.

        The window has to be mapped before the real positions are known, so
        this runs once the layout has settled - and if it beats the first
        map of the button's own label it is *not* settled yet: an unmapped
        widget reports rooty 0, so 0 - rooty would park the status above the
        window.  Retry until the pair is actually on screen.
        """
        try:
            bl = self.github_btn.label
            if not (self.root.winfo_ismapped() and bl.winfo_ismapped()):
                if tries < 30:
                    self.root.after(100, lambda: self._align_nav(tries + 1))
                return
            by = bl.winfo_rooty() - self.root.winfo_rooty()
            # device px: rooty diffs are device px and place_configure is a
            # raw tk call, which is exactly the unit it wants
            if not 0 <= by < self.root.winfo_height():
                if tries < 30:
                    self.root.after(100, lambda: self._align_nav(tries + 1))
                return
            text_h = self.status_text.winfo_reqheight()
            dot_h = self.status_dot.winfo_reqheight()
            self.status_text.place_configure(y=by)
            # the dot is a bigger glyph - centre its artwork on the same axis
            self.status_dot.place_configure(y=by - (dot_h - text_h) / 2)
        except Exception:
            pass

    def _tab_hover(self, key, on):
        if key == self._tab:
            return
        item = self._tab_items[key][0]
        item.set_color(TEXT if on else MUTED)

    def show(self, key):
        """Switch the visible view, with a short slide into place.

        The switch is made first - the view lifted, the tab marked - so a
        click is always answered at once.  The travel is polish on top of
        an already-done turn, never a wait in front of one.
        """
        builder = self._pending_views.pop(key, None)
        if builder is not None:
            # the first time this tab is opened it is built right here
            # (its builder has already _place_in'd it at the design size)
            view = builder()
            self._views[key] = view
        if key not in self._views:
            return
        switching = key != self._tab
        self._tab = key
        for k, (item, x0, x1) in self._tab_items.items():
            item.set_color(TEXT if k == key else MUTED)
        mid = (self._tab_items[key][1] + self._tab_items[key][2]) // 2
        for k, view in self._views.items():
            if k == key:
                view.lift()
            else:
                view.lower()
        if key == "history":
            self._refresh_history()
        self._slide_tab(mid - 12, switching)

    def _slide_tab(self, target, switching):
        """Travel the underline to target while the view rises into place.

        The guards here only ever leave the polish off, never the switch:
        Windows' "turn off unnecessary animations" and the opening sequence
        both get the settled positions directly, the latter because it owns
        the underline until it has finished.  A trip already under way is
        superseded - rapid clicks start the next travel from wherever the
        last one reached, and the incoming view is raised from below the
        offset either way, so it only ever appears while on its way in.
        """
        self._tab_anim = getattr(self, "_tab_anim", 0) + 1
        view = self._views[self._tab]
        try:
            if (not switching or not getattr(self, "_intro_done", False)
                    or reduce_motion_enabled()):
                self._underline.place(x=target, y=52)
                self._underline_x = target
                self._move(view, 0, 0)
                return
        except Exception:
            return
        mine = self._tab_anim
        start_x = self._underline_x
        self._move(view, 0, TAB_RISE)
        start = time.perf_counter()

        def step():
            try:
                if self._tab_anim != mine:
                    return                       # a later click took over
                p = (time.perf_counter() - start) * 1000.0 / TAB_MOVE_MS
                if p >= 1.0:
                    p = 1.0
                ease = 1.0 - (1.0 - p) ** 3       # ease out cubic
                x = start_x + (target - start_x) * ease
                self._underline.place(x=x, y=52)
                self._underline_x = x
                self._move(view, 0, TAB_RISE * (1.0 - ease))
                if p < 1.0:
                    self.root.after(TAB_FRAME_MS, step)
                else:
                    self._underline_x = target
                    self._move(view, 0, 0)
            except Exception:
                pass                              # the window is gone

        step()

    def _drag_start(self, event):
        self._drag_offset = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())

    def _drag_move(self, event):
        self.root.geometry(f"+{event.x_root - self._drag_offset[0]}+"
                           f"{event.y_root - self._drag_offset[1]}")

    def _minimize(self):
        self._restore_drain = True       # the next map is a restore of ours
        self.root.withdraw()

    def _on_unmap(self, event=None):
        """Note that this window has gone away, so the next map is a restore.

        Armed by the event rather than by the two callers (_launch and
        _minimize) because the user can also minimise the window himself, and
        that repaint costs exactly the same.  Descendants unmap on their own
        all the time - only the toplevel leaving the screen counts.
        """
        if event is not None and event.widget is not self.root:
            return
        try:
            self._restore_drain = True
        except Exception:
            pass

    def _on_map(self, event=None):
        """Hold the window back until a restore has finished painting.

        root.bind is on the toplevel's path, and Tk puts that tag on every
        descendant as well, so only the toplevel's own map counts - and only
        one we caused ourselves: _launch and _minimize are the two places this
        window ever goes away.

        A harness keeps the window at alpha 0, so an invisible window is never
        touched either: it has nothing to hide and nothing to show.
        """
        if event is not None and event.widget is not self.root:
            return
        if not self._restore_drain or not getattr(self, "_intro_done", False):
            return
        try:
            if float(self.root.attributes("-alpha") or 0.0) <= 0.001:
                return
            self.root.attributes("-alpha", 0.0)
        except Exception:
            return                                  # the window is gone
        self._restore_drain = False
        self._restore_quiet = 0
        self._restore_polls = 0
        self._restore_started = time.perf_counter()
        try:
            self.root.after(RESTORE_POLL_MS, self._restore_poll)
        except Exception:
            pass

    def _restore_poll(self):
        """Ask Tk for everything it still owes the window, then show it.

        One root.update() pays the whole repaint while the window is still at
        alpha 0, so nothing of it reaches the screen; the reveal happens when
        two polls in a row come back under RESTORE_QUIET_MS, which means the
        work has genuinely stopped rather than merely paused between two
        bursts.  The time cap is the other half of the promise: a restore can
        be slow, but it may never leave the window invisible for long.
        """
        try:
            if self.root.state() in ("iconic", "withdrawn"):
                # minimised again mid-drain - leave it dark and re-arm, so the
                # next restore runs this from the top
                self._restore_drain = True
                return
            self._restore_polls += 1
            t = time.perf_counter()
            self.root.update()
            ms = (time.perf_counter() - t) * 1000.0
            self._restore_quiet = (0 if ms >= RESTORE_QUIET_MS
                                   else self._restore_quiet + 1)
            spent = (time.perf_counter() - self._restore_started) * 1000.0
            if (self._restore_quiet >= RESTORE_QUIET_NEEDED
                    or spent >= RESTORE_MAX_MS):
                self.root.attributes("-alpha", 1.0)
                return
            self.root.after(RESTORE_POLL_MS, self._restore_poll)
        except Exception:
            try:
                self.root.attributes("-alpha", 1.0)
            except Exception:
                pass                                  # the window is gone

    def _quit(self):
        self.stop_event.set()
        try:
            self.hotkey_listener.stop()
        except Exception:
            pass
        try:
            notify_clear(getattr(self, "_raze_hwnd", 0))
        except Exception:
            pass
        self._save_config()
        self.root.destroy()

    # ------------------------------------------------------------------ #
    #  Hero CTAs
    # ------------------------------------------------------------------ #
    def _build_hero(self):
        """The headline and subtitle are baked into the artwork - nothing to add."""
        pass

    # ------------------------------------------------------------------ #
    #  Cards
    # ------------------------------------------------------------------ #
    def _build_content(self):
        """A container that holds the tab views.

        Only the tab that opens is built here.  Hotkeys and History cost
        about 110 ms between them, and a first click on either used to pay
        for that out of the click itself - which is exactly what a tab
        switch felt like when it stuttered.  They are now built ahead on a
        timer instead, while the interface is idle: see _warm_views.
        """
        self.content = ctk.CTkFrame(self.root, fg_color="transparent", width=WIN_W,
                                    height=WIN_H - NAV_H)
        self.content.place(x=0, y=NAV_H)

        self._views["typer"] = self._build_typer_view()
        self._pending_views = {"hotkeys": self._build_hotkeys_view,
                               "history": self._build_history_view}
        self.show("typer")
        # built while the app is idle, so opening either is instant
        self.root.after(TAB_WARM_MS, self._warm_views)

    def _warm_views(self):
        """Build the tabs nobody is looking at, before they are clicked.

        About 110 ms of work, one and a half seconds after start-up, when
        the interface is otherwise doing nothing at all.  Each view goes
        down under the one on screen, so the tab that is open never
        flickers; lifting it stays show()'s job.
        """
        try:
            for key in list(self._pending_views):
                builder = self._pending_views.pop(key, None)
                if builder is None:
                    continue
                view = builder()          # the builder _place_in's it
                self._views[key] = view
                view.lower()
        except Exception:
            pass                                  # the window is gone

    def _place_in(self, parent, x, y, w, h, delay=None, dx=0.0, dy=0.0):
        """Place a frame at an exact pixel size (CTk forbids width/height in
        place()).  With a delay it also takes part in the opening animation."""
        if delay is not None:
            self._intro_items.append((parent, x, y, delay, dx, dy))
            x, y = x + dx, y + dy
        args = ["place", parent._w, "-x", str(px(x)), "-y", str(px(y)),
                "-width", str(px(w)), "-height", str(px(h))]
        self.root.tk.call(*args)

    # ----- typer view (the main screen) ---------------------------------- #
    def _build_typer_view(self):
        view = ctk.CTkFrame(self.content, fg_color="transparent")
        self._place_in(view, 0, 0, WIN_W, WIN_H - NAV_H)
        # the view sits straight on the black window - bg_view.png was a flat
        # black rectangle and did nothing but cost time to decode
        self._build_pool(view)
        self._build_config(view)
        self._build_hotkey_card(view)
        self._build_session(view)
        return view

    # ----- hotkey card ---------------------------------------------------- #
    def _build_hotkey_card(self, parent):
        card = Card(parent, width=CONFIG_W, height=HOTKEY_H)
        self._place_in(card, CONFIG_X, HOTKEY_Y - NAV_H, CONFIG_W, HOTKEY_H,
                       delay=INTRO_STAGGER_MS * 2, dy=INTRO_RISE)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(24, 12))
        BakedLabel(head, "HOTKEYS", size=10, weight="Bold", color=TEXT,
                    height=18).pack(side="left")

        caps = ctk.CTkFrame(card, fg_color="transparent")
        caps.pack(fill="x", padx=24, pady=(0, 18))
        for col in range(4):
            caps.grid_columnconfigure(col, weight=1, uniform="caps")

        for col, (key, cap_attr, caption) in enumerate((
                (self.start_key, "key_cap_start", "start"),
                (self.pause_key, "key_cap_pause", "pause"),
                (self.resume_key, "key_cap_resume", "resume"),
                (self.stop_key, "key_cap_stop", "stop"))):
            cell = ctk.CTkFrame(caps, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew",
                      padx=(0 if col == 0 else 10, 0))
            cap = ctk.CTkFrame(cell, fg_color=SURFACE_2, corner_radius=14,
                               border_width=1, border_color=BORDER_2, height=104,
                               cursor="hand2")
            cap.pack(fill="x")
            cap.pack_propagate(False)
            label = BakedLabel(cap, key.upper(), size=26, weight="SemiBold",
                               color=TEXT)
            label.place(relx=0.5, rely=0.5, anchor="center")
            BakedLabel(cell, caption, size=9, color=FAINT,
                        height=14).pack(pady=(12, 0))
            for widget in (cap, label):
                widget.bind("<Button-1>", lambda e: self.show("hotkeys"))
                widget.bind("<Enter>", lambda e: cap.configure(border_color="#3a3a46"))
                widget.bind("<Leave>", lambda e: cap.configure(border_color=BORDER_2))
            setattr(self, cap_attr, label)


    # ----- hotkeys view -------------------------------------------------- #
    def _build_hotkeys_view(self):
        view = ctk.CTkFrame(self.content, fg_color="transparent")
        self._place_in(view, 0, 0, WIN_W, WIN_H - NAV_H)

        # the card starts where the removed headline used to sit, so nothing
        # is left floating 100 px below the top of the tab
        card = Card(view, width=WIN_W - MARGIN * 2, height=348)
        self._place_in(card, MARGIN, 96, WIN_W - MARGIN * 2, 348)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(24, 10))
        BakedLabel(head, "HOTKEYS", size=11, weight="SemiBold", color=TEXT,
                    height=18).pack(side="left")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=26, pady=(6, 24))

        def key_row(label, value, setter, width=190):
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(0, 22))
            BakedLabel(row, label, size=12, color=MUTED,
                        height=44, anchor="w").pack(side="left")
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(side="right")
            var = tk.StringVar(value=value)
            ctk.CTkEntry(inner, textvariable=var, width=width, height=44,
                         corner_radius=22, font=(FONT_SB, -13), fg_color=SURFACE_2,
                         border_color=BORDER_2, text_color=CYAN).pack(side="left")
            Pill(inner, "Set", setter, kind="solid", height=44,
                 width=72, font=(FONT_SB, -11)).pack(side="left", padx=(8, 0))
            return var

        self.hotkey_view_var = key_row("Start key", self.start_key, self._set_hotkey)
        self.pausekey_view_var = key_row("Pause key", self.pause_key,
                                         self._set_pause_hotkey)
        self.resumekey_view_var = key_row("Resume key", self.resume_key,
                                          self._set_resume_hotkey)
        self.stopkey_view_var = key_row("Stop key", self.stop_key, self._set_stop_hotkey)
        return view


    # ----- history view -------------------------------------------------- #
    def _build_history_view(self):
        view = ctk.CTkFrame(self.content, fg_color="transparent")
        self._place_in(view, 0, 0, WIN_W, WIN_H - NAV_H)
        card = Card(view, width=WIN_W - MARGIN * 2, height=726)
        self._place_in(card, MARGIN, CARD_Y - NAV_H, WIN_W - MARGIN * 2, 726)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(22, 10))
        BakedLabel(head, "HISTORY", size=10, weight="Bold", color=TEXT,
                   height=18).pack(side="left")
        self.history_total = BakedLabel(head, "", size=10, weight="Regular",
                                        color=FAINT, height=18)
        self.history_total.pack(side="right")

        # The log is baked artwork as well - Windows would render it with
        # ClearType fringes, which is exactly what this app avoids.
        #
        # This used to scroll inside a canvas of its own.  That needed a
        # scrollbar which sat on top of the counts on the right and clipped
        # them, and its virtualisation could leave a single row stranded in
        # the middle of an otherwise empty panel.  Nothing scrolls here any
        # more, so the rows are packed straight into the panel and there is
        # no way for one to drift out of place.
        holder = ctk.CTkFrame(card, fg_color=FIELD, corner_radius=14,
                              border_width=1, border_color=BORDER)
        holder.pack(fill="both", expand=True, padx=26, pady=(0, 22))
        self.history_list = tk.Frame(holder, bg=FIELD, bd=0,
                                     highlightthickness=0)
        self.history_list.pack(side="left", fill="both", expand=True,
                               padx=12, pady=12)
        self._history_rows = []
        self._history_days = []
        self._history_note = None
        return view

    def _render_history(self):
        """One row per day, packed from the top, as many as the panel shows.

        There is nothing to scroll, so there is nothing to virtualise: only
        the days that actually fit are drawn.  That keeps a year of
        accumulated days from costing anything - the ones below the fold are
        simply never built - while the lifetime total in the header still
        counts every message ever sent.
        """
        try:
            for row, _date, _count in self._history_rows:
                try:
                    row.destroy()
                except Exception:
                    pass
            self._history_rows = []

            days = self._history_days
            if not days:
                return
            row_h, gap = 34, 12                     # pitch and spacing
            try:
                room = self.history_list.winfo_height()
            except Exception:
                room = 0
            if room > px(20):
                max_rows = max(1, int(room) // px(row_h + gap))
            else:
                # the tab has never been drawn, so the panel has no height
                # yet - draw a sensible amount and redraw once it does
                max_rows = 14

            for day in days[:max_rows]:
                row = tk.Frame(self.history_list, bg=FIELD)
                row.pack(fill="x", pady=(0, px(gap)))
                date = BakedLabel(row, pretty_day(day), size=13,
                                  weight="SemiBold", color=TEXT, height=22,
                                  anchor="w", bg=FIELD)
                date.pack(side="left")
                total_msg = self.daily.get(day, 0)
                count = BakedLabel(
                    row, f"{total_msg} message{'s' if total_msg != 1 else ''}",
                    size=12, color=FAINT, height=22, anchor="e", bg=FIELD)
                count.pack(side="right")
                self._history_rows.append((row, date, count))
        except Exception:
            pass


    def _prebake_history(self):
        """Bake the day names quietly in the background.

        With a year of history there are hundreds of dates, and drawing them
        all at once freezes the app for seconds.  They are rendered in small
        batches instead, while the app is idle.
        """
        try:
            days = sorted(self.daily, reverse=True)
            if not days:
                return
            state = [0]

            def chunk():
                start = state[0]
                for day in days[start:start + 20]:
                    try:
                        text_photo(pretty_day(day), 13, "SemiBold", TEXT)
                    except Exception:
                        pass
                state[0] = start + 20
                if state[0] < len(days):
                    self.root.after(60, chunk)

            self.root.after(1500, chunk)
        except Exception:
            pass

    def _refresh_history(self):
        """One row per day: the full date and how many messages went out."""
        if not hasattr(self, "history_list"):
            return
        if self._history_note is not None:
            try:
                self._history_note.destroy()
            except Exception:
                pass
            self._history_note = None

        total = sum(self.daily.values())
        self.history_total.set_text(f"{total} message{'s' if total != 1 else ''}")

        if not self.history:
            for row, _date, _count in self._history_rows:
                try:
                    row.destroy()
                except Exception:
                    pass
            self._history_rows = []
            self._history_days = []
            note = tk.Frame(self.history_list, bg=FIELD)
            note.pack(anchor="w")
            self._history_note = note
            BakedLabel(note, "Nothing sent yet.", size=13, weight="SemiBold",
                       color=TEXT, height=20, anchor="w", bg=FIELD).pack(anchor="w")
            BakedLabel(note, "Start the typer and every message shows up here -",
                       size=12, color=MUTED, height=18, anchor="w",
                       bg=FIELD).pack(anchor="w")
            BakedLabel(note, "kept until you delete Raze's app data.",
                       size=12, color=MUTED, height=18, anchor="w",
                       bg=FIELD).pack(anchor="w")
            return

        self._history_days = sorted(self.daily, reverse=True)
        self._render_history()
        # the panel only knows its real height once it has been laid out, so
        # draw once more now that it has - that is what decides how many rows
        # the space can actually show
        self.root.after_idle(self._render_history)

    # ----- message pool ------------------------------------------------- #
    def _build_pool(self, parent):
        card = Card(parent, width=POOL_W, height=CARD_H)
        self._place_in(card, POOL_X, CARD_Y - NAV_H, POOL_W, CARD_H,
                       delay=0.0, dy=INTRO_RISE)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(22, 12))
        try:
            BakedLabel(head, "MESSAGE POOL", size=10, weight="SemiBold", color=TEXT,
                       tracking=1.7, height=18, anchor="w").pack(side="left")
        except Exception:
            ctk.CTkLabel(head, text="MESSAGE POOL", font=(FONT_SB, -10),
                         text_color=TEXT, height=18).pack(side="left")
        self.pool_meta = BakedLabel(head, "0 messages", size=11, color=FAINT, height=18)
        self.pool_meta.pack(side="right")

        pool = ctk.CTkFrame(card, fg_color="transparent")
        pool.pack(fill="both", expand=True, padx=24)

        # a numbered rail on the left - one number per message
        # CTk constructor width is design px (scaled once by CTk itself)
        self.pool_gutter = ctk.CTkFrame(pool, fg_color="transparent", width=24)
        self.pool_gutter.pack(side="left", fill="y")
        self.pool_gutter.pack_propagate(False)
        self._gutter_numbers = []
        # one label holds every visible number - a widget per line would
        # mean thousands of them for a long pool
        self.pool_numbers = tk.Label(self.pool_gutter, bd=0, highlightthickness=0,
                                     bg=SURFACE)
        self.pool_numbers.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self._gutter_photo = None

        self.editor = ctk.CTkTextbox(
            pool, font=(FONT_MONO, -13), fg_color=FIELD, border_width=1,
            border_color=BORDER, corner_radius=14, text_color=TEXT,
            scrollbar_button_color="#2c2c33", scrollbar_button_hover_color="#3d3d46",
            wrap="word", activate_scrollbars=True)
        self.editor.pack(side="left", fill="both", expand=True)
        self.editor.bind("<Configure>", lambda e: self._update_pool_gutter())
        self._hook_pool_scroll()
        # the typing happens in the text widget inside the box, so that is
        # where the counter has to listen - a key event never reaches the
        # frame around it
        try:
            inner = getattr(self.editor, "_textbox", None)
            if inner is not None:
                def pool_changed(event=None):
                    self._update_pool_meta()
                    try:
                        inner.edit_modified(False)
                    except Exception:
                        pass

                inner.bind("<KeyRelease>", pool_changed)
                inner.bind("<<Modified>>", pool_changed)
        except Exception:
            pass

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=18)
        for i in range(4):
            row.grid_columnconfigure(i, weight=1, uniform="acts")
        for i, (text, cmd, kind) in enumerate((
                ("Import .txt", self._import_txt, "glass"),
                ("Export .txt", self._export_txt, "glass"),
                ("Shuffle", self._shuffle, "glass"),
                ("Clear", self._clear_messages, "danger"))):
            Pill(row, text, cmd, kind=kind, height=34, font=(FONT_SB, -11)).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))

    # ----- configuration ------------------------------------------------ #
    def _build_config(self, parent):
        card = Card(parent, width=CONFIG_W, height=CONFIG_H)
        self._place_in(card, CONFIG_X, CARD_Y - NAV_H, CONFIG_W, CONFIG_H,
                       delay=INTRO_STAGGER_MS, dy=INTRO_RISE)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(26, 10))
        try:
            BakedLabel(head, "CONFIGURATION", size=10, weight="SemiBold", color=TEXT,
                       tracking=1.7, height=18, anchor="w").pack(side="left")
        except Exception:
            ctk.CTkLabel(head, text="CONFIGURATION", font=(FONT_SB, -10),
                         text_color=TEXT, height=18).pack(side="left")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        def field(parent, label, value, step, decimals, setter, hint=None,
                 unit=None, width=104, last=False):
            wrap = ctk.CTkFrame(parent, fg_color="transparent")
            wrap.pack(fill="x", pady=(0, 0 if last else 24))
            top = ctk.CTkFrame(wrap, fg_color="transparent")
            # the row is not pinned: it takes its height from the label, so
            # below ~70% scale - where the glyphs are taller in design px
            # than the 18 they measure at 100% - the row grows instead of
            # cutting them.  At 100% the label is pinned to 18 anyway, so
            # the spinner below lands on exactly the line it always did.
            BakedLabel(top, label, size=11, color=MUTED,
                       height=18, anchor="w").pack(side="left")
            top.pack(fill="x")
            nf = NumberField(wrap, value=value, minimum=0, step=step,
                             decimals=decimals, on_change=setter, width=width)
            nf.pack(fill="x", pady=(11, 0))
            if hint:
                BakedLabel(wrap, hint, size=9, color=FAINT,
                            height=14, anchor="w").pack(fill="x", pady=(8, 0))
            return nf

        self.nf_interval = field(body, "Message interval", 2, 1, 0,
                                 self._set_msg_interval,
                                 hint="seconds between each message")
        self.nf_loop = field(body, "Loop", 0, 1, 0, self._set_loop,
                             hint="0 = infinite  ·  how many times to repeat the message pool",
                             last=True)

        # a full-width rule cutting the card, with the selection mode under it
        rule = ctk.CTkFrame(body, fg_color="#7a7a86", height=2)
        rule.pack(fill="x", pady=(18, 14))
        rule.pack_propagate(False)

        row = ctk.CTkFrame(body, fg_color="transparent", height=30,
                           cursor="hand2")
        row.pack(fill="x")
        row.pack_propagate(False)
        BakedLabel(row, "Random", size=13, weight="SemiBold", color=TEXT,
                   height=30, anchor="w").pack(side="left")

        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right")
        self.random_word = BakedLabel(right, "Disabled", size=11, color=FAINT,
                                      height=30, anchor="w")
        try:
            self.random_box = ctk.CTkCheckBox(
                right, text="", width=px(20), height=px(20),
                checkbox_width=px(20), checkbox_height=px(20),
                corner_radius=px(5), border_width=2, border_color=BORDER_2,
                fg_color=TEXT, hover_color="#c9c9d2", checkmark_color=BG,
                command=self._toggle_random)
            self.random_box.pack(side="left", padx=(0, 9))
        except Exception:
            self.random_box = None
        self.random_word.pack(side="left")

        # the whole row acts as the switch, the way the keycaps do
        def _flip(_event=None):
            box = getattr(self, "random_box", None)
            if box is not None:
                try:
                    box.toggle()
                except Exception:
                    pass
        row.bind("<Button-1>", _flip)

        # The stack measures exactly the card's height at 100% - there is
        # no slack anywhere in it - and the baked artwork outgrows its own
        # design box below ~60% scale (font metrics round up, and the pad
        # around the glyphs is device px), so pack would clamp the Random
        # row off its own line.  The card's margins are where the give is:
        # 46 design px of rhythm, none of it load-bearing, against 18 px of
        # gap below the card.  pack_configure is a raw tk call - CTk scales
        # only the pack() it overrides - so these values are device px, and
        # the floors keep the rhythm legible whatever the shortfall.
        # Req heights read as a placeholder (200 apiece) until the first
        # idle pass has laid the children out, so settle the stack first.
        self.root.update_idletasks()
        over = (head.winfo_reqheight() + body.winfo_reqheight()
                + px(26 + 10 + 20) - px(CONFIG_H))
        if over > 0:
            give = over / 2.0
            head.pack_configure(pady=(max(px(8), px(26) - give), px(10)))
            body.pack_configure(pady=(0, max(px(8), px(20) - give)))

    def _set_random_word(self):
        word = getattr(self, "random_word", None)
        if word is None:
            return
        on = bool(getattr(self, "_random_pick", False))
        try:
            word.set_text("Enabled" if on else "Disabled")
            word.set_color(TEXT if on else FAINT)
        except Exception:
            pass

    def _toggle_random(self):
        box = getattr(self, "random_box", None)
        if box is None:
            return
        try:
            self._random_pick = bool(box.get())
        except Exception:
            return
        self._set_random_word()
        self._save_config()


    # ------------------------------------------------------------------ #
    #  Session
    # ------------------------------------------------------------------ #
    def _build_session(self, parent):
        card = Card(parent, width=WIN_W - MARGIN * 2, height=SESSION_H)
        self._place_in(card, MARGIN, SESSION_Y - NAV_H, WIN_W - MARGIN * 2, SESSION_H,
                       delay=INTRO_STAGGER_MS * 3, dy=INTRO_RISE)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(18, 10))
        try:
            BakedLabel(head, "SESSION", size=10, weight="SemiBold", color=TEXT,
                       tracking=1.7, height=18, anchor="w").pack(side="left")
        except Exception:
            ctk.CTkLabel(head, text="SESSION", font=(FONT_SB, -10),
                         text_color=TEXT, height=18).pack(side="left")
        self.session_state = BakedLabel(head, "Ready", size=11, color=FAINT, height=18)
        self.session_state.pack(side="right")
        # packed after the state, so it lands on its left: which loop the run
        # is on, separated from how many times it repeats - `/` and the
        # infinity sign in gold, the rest of the label gold with them.  The
        # heartbeat rewrites it, and only when the words change
        self.session_loop = BakedLabel(head, self._loop_text(), size=11,
                                       color=AMBER, height=18)
        self.session_loop.pack(side="right", padx=(0, 16))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        # only the preview may grow - the four counters keep a fixed width so
        # a number changing can never shift the row
        body.grid_columnconfigure(4, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.tile_sent = StatTile(body, "MESSAGES SENT", width=118)
        self.tile_sent.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tile_chars = StatTile(body, "CHARACTERS", width=104)
        self.tile_chars.grid(row=0, column=1, sticky="nsew", padx=8)
        self.tile_time = StatTile(body, "ELAPSED", width=118)
        self.tile_time.grid(row=0, column=2, sticky="nsew", padx=8)
        self.tile_next = StatTile(body, "NEXT IN", width=92)
        self.tile_next.grid(row=0, column=3, sticky="nsew", padx=(8, 20))

        preview = ctk.CTkFrame(body, fg_color=SURFACE_2, corner_radius=14,
                                border_width=1, border_color=BORDER)
        preview.grid(row=0, column=4, sticky="nsew", padx=(20, 0))
        inner = ctk.CTkFrame(preview, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=13)
        try:
            BakedLabel(inner, "LAST SENT", size=9, weight="SemiBold", color=FAINT,
                       tracking=1.1, height=14, anchor="w").pack(fill="x")
        except Exception:
            BakedLabel(inner, "LAST SENT", size=9, color=FAINT,
                        anchor="w", height=14).pack(fill="x")
        self.last_label = BakedLabel(inner, "—", size=12, weight="Regular",
                                     color=MUTED, anchor="w", height=20)
        self.last_label.pack(fill="x", pady=(8, 0))
        preview.bind("<Configure>", self._fit_last_label)

    def _loop_text(self):
        """`Loop 2 of 5 / 3 left`, or `Loop 3 / ∞` when Loop is 0.

        The worker counts completed passes in self.passes, so the current
        loop is always the next one up; a finished run stays where it stopped
        until the next start takes it back to one.
        """
        total = int(getattr(self, "loop_count", 0) or 0)
        current = int(getattr(self, "passes", 0) or 0) + 1
        if total > 0:
            current = min(current, total)
            left = total - current
            return "Loop %d of %d%s" % (current, total,
                                        " / %d left" % left if left else "")
        return "Loop %d / ∞" % current

    # ------------------------------------------------------------------ #
    #  Sliders
    # ------------------------------------------------------------------ #
    def _set_char_delay(self, v):
        # fixed at 0 ms - there is no control for it
        self.char_delay = 0.0

    def _set_msg_interval(self, v):
        self.msg_interval = float(v)

    def _set_loop(self, v):
        self.loop_count = int(round(float(v)))

    def _set_countdown(self, v):
        self.countdown = 0.0

    # ------------------------------------------------------------------ #
    #  Config
    # ------------------------------------------------------------------ #
    def _load_config(self):
        return read_config()

    def _stored_key(self, value, default):
        """A hotkey as it sits in the config, or the default for its action.

        Configs written while combinations were accepted may still hold one
        of those; it no longer registers, so the default takes its place
        and the action is never left with a key that refuses to arm.
        """
        key = hotkeymod.normalise(str(value or ""))
        return key if hotkeymod.is_valid(key) else default

    def _apply_config(self):
        c = self.cfg
        self.start_key = self._stored_key(c.get("start_key", c.get("hotkey", "f8")),
                                          "f8")
        self.stop_key = self._stored_key(c.get("stop_key", "f9"), "f9")
        self.pause_key = self._stored_key(c.get("pause_key", "f6"), "f6")
        self.resume_key = self._stored_key(c.get("resume_key", "f7"), "f7")
        self.char_delay = 0.0
        self.msg_interval = c.get("msg_interval", 2.0)
        self.countdown = 0.0
        self.loop_count = int(c.get("loop", 0))

        self.nf_interval.set(c.get("msg_interval", 2.0), call_change=False)
        self.nf_loop.set(c.get("loop", 0), call_change=False)
        self._set_msg_interval(self.nf_interval.get())
        self._set_loop(self.nf_loop.get())
        self._random_pick = bool(c.get("random"))
        try:
            if self._random_pick:
                self.random_box.select()
            else:
                self.random_box.deselect()
        except Exception:
            pass
        self._set_random_word()
        # the hotkey tab builds itself the first time it is opened, so its
        # entry fields may not exist yet - they read these values when they do
        values = {"hotkey_view_var": self.start_key,
                  "stopkey_view_var": self.stop_key,
                  "pausekey_view_var": self.pause_key,
                  "resumekey_view_var": self.resume_key}
        for name, value in values.items():
            var = getattr(self, name, None)
            if var is not None:
                var.set(value)

        self.history = [(h.get("t", ""), h.get("m", ""))
                        for h in (c.get("history") or [])]
        # the per day counters are kept separately, so they stay correct
        # even after the recent log has rolled over
        self.daily = dict(c.get("daily") or {})
        if not self.daily:
            for stamp, _message in self.history:
                day = stamp[:10]
                self.daily[day] = self.daily.get(day, 0) + 1
        msgs = c.get("messages") or ["Hello there!", "How can I help you?", "Have a great day!"]
        self.editor.insert("1.0", "\n".join(msgs))
        self._update_pool_meta()

    def _commit_fields(self):
        """Read what is on screen, not what was there before the user typed.

        NumberField keeps the entry's text and its own _value apart, and only
        reconciles them on <Return> or <FocusOut>.  The four hotkeys are polled
        globally and deliberately never steal focus, so a number typed into a
        field and started with F8 fires neither one: the field shows 3 while
        get() still answers 0, and 0 Loop means infinite.  Anything that reads
        a field has to flush it first, or the value the user just typed is the
        one value the app never sees.
        """
        for name in ("nf_interval", "nf_loop"):
            nf = getattr(self, name, None)
            if nf is not None:
                nf._commit()

    def _save_config(self):
        self._commit_fields()
        self.cfg.update({
            "msg_interval": self.nf_interval.get(),
            "loop": self.nf_loop.get(),
            "start_key": self.start_key,
            "stop_key": self.stop_key,
            "pause_key": self.pause_key,
            "resume_key": self.resume_key,
            "messages": self._collect_messages(),
            "random": self._random_pick,
            "history": [{"t": t, "m": m} for t, m in self.history[-HISTORY_KEEP:]],
            "daily": self.daily,
        })
        try:
            write_config(self.cfg)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Message pool
    # ------------------------------------------------------------------ #
    def _collect_messages(self):
        raw = self.editor.get("1.0", END)
        return [m.strip() for m in raw.split("\n") if m.strip()]

    def _hook_pool_scroll(self):
        """Keep the numbers in step with the text while it scrolls."""
        try:
            inner = getattr(self.editor, "_textbox", None)
            if inner is None:
                return
            scroll = inner.cget("yscrollcommand")
            if not scroll:
                return

            def on_scroll(*args):
                try:
                    inner.tk.call(scroll, *args)
                except Exception:
                    pass
                self.root.after_idle(self._update_pool_gutter)

            inner.configure(yscrollcommand=on_scroll)
        except Exception:
            pass

    def _update_pool_gutter(self):
        """Number the lines on screen, the way an editor numbers its lines.

        Only the lines that are on screen are numbered, and all of them are
        drawn into a single picture - one widget per line would mean
        thousands of widgets and the app would crawl.  The rail also grows
        with the number of digits, so there is no limit on the list length.
        """
        try:
            inner = getattr(self.editor, "_textbox", None)
            if inner is None:
                return
            total = int(inner.index("end-1c").split(".")[0])

            # the rail is wide enough for any number of digits - it is only
            # resized when the number of digits actually changes, because
            # resizing it would re-flow the whole text
            digits = len(str(max(total, 1)))
            rail_w = px(15 + 7 * digits)
            if rail_w != getattr(self, "_rail_width", 0):
                self._rail_width = rail_w
                # configure takes design px (CTk scales it); rail_w is
                # device px, because the strip below is drawn in device px
                self.pool_gutter.configure(width=15 + 7 * digits)

            # the lines that are actually on screen
            height = max(inner.winfo_height() - 2, 1)
            first = int(inner.index("@0,0").split(".")[0])
            last = int(inner.index(f"@0,{height}").split(".")[0])
            last = min(max(last, first), total)

            offset = (inner.winfo_rooty() -
                      self.pool_gutter.winfo_rooty())
            rail_h = max(self.pool_gutter.winfo_height(), 1)

            strip = Image.new("RGBA", (rail_w, rail_h), (0, 0, 0, 0))
            for line in range(first, last + 1):
                box = inner.bbox(f"{line}.0")
                if box is None:
                    continue
                _draw_number(strip, str(line), rail_w - px(6),
                             box[1] + offset + px(1))

            # A palette picture is fifty times cheaper for tk to upload
            # than an alpha one, and the numbers are pre blended with the
            # card so the edges look exactly the same.
            indexed = strip.getchannel("A").convert("P")
            indexed.putpalette(_gutter_palette())

            from PIL import ImageTk
            photo = ImageTk.PhotoImage(indexed)
            self._gutter_photo = photo
            self.pool_numbers.configure(image=photo)
        except Exception:
            pass

    def _update_pool_meta(self):
        msgs = self._collect_messages()
        chars = sum(len(m) for m in msgs)
        self.pool_meta.set_text(f"{len(msgs)} messages  ·  {chars} characters")
        self._update_pool_gutter()

    def _import_txt(self):
        path = filedialog.askopenfilename(
            title="Import messages", filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            parent=self.root)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            current = self.editor.get("1.0", END)
            if current.strip():
                self.editor.insert(END, "\n" + content)
            else:
                self.editor.delete("1.0", END)
                self.editor.insert("1.0", content)
            self._update_pool_meta()
        except Exception as e:
            messagebox.showerror("Import failed", str(e), parent=self.root)

    def _export_txt(self):
        msgs = self._collect_messages()
        if not msgs:
            messagebox.showinfo("Nothing to export", "The message pool is empty.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            title="Export messages", defaultextension=".txt", initialfile="messages.txt",
            filetypes=[("Text files", "*.txt")], parent=self.root)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(msgs))
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self.root)

    def _shuffle(self):
        msgs = self._collect_messages()
        if not msgs:
            return
        random.shuffle(msgs)
        self.editor.delete("1.0", END)
        self.editor.insert("1.0", "\n".join(msgs))
        self._update_pool_meta()

    def _confirm(self, title, message, confirm_text="Confirm", cancel_text="Cancel",
                 kind="solid", wait=True):
        """A confirmation dialog in the app's own style. Returns True on yes."""
        state = {"ok": False}
        try:
            dialog = ctk.CTkToplevel(self.root)
        except Exception:
            return False
        try:
            # w/h are device px, for centring maths only; the geometry
            # string must be in design px because CTkToplevel scales WxH
            w, h = px(452), px(178)
            dialog.withdraw()
            dialog.title(title)
            dialog.configure(fg_color=BG)
            dialog.resizable(False, False)
            try:
                dialog.iconbitmap(default="")
            except Exception:
                pass

            body = ctk.CTkFrame(dialog, fg_color="transparent")
            # design px: CTk pack scales padx/pady by the widget scaling
            body.pack(fill="both", expand=True, padx=26, pady=(22, 20))

            top = ctk.CTkFrame(body, fg_color="transparent")
            top.pack(fill="x")
            try:
                mark = tk.Label(top, image=emblem_photo(28), bd=0,
                                highlightthickness=0, bg=BG)
                mark.pack(side="left", padx=(0, px(12)))
            except Exception:
                pass
            BakedLabel(top, title, size=17, weight="SemiBold", color=TEXT,
                       height=26, anchor="w").pack(side="left")

            BakedLabel(body, message, size=12, color=MUTED, height=18,
                       anchor="w").pack(fill="x", pady=(12, 0))

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", side="bottom")

            def close(value):
                state["ok"] = value
                try:
                    dialog.grab_release()
                except Exception:
                    pass
                dialog.destroy()

            Pill(row, cancel_text, lambda: close(False), kind="glass", height=36,
                 font=(FONT_SB, -12)).pack(side="right")
            Pill(row, confirm_text, lambda: close(True), kind=kind, height=36,
                 font=(FONT_SB, -12)).pack(side="right", padx=(0, 8))

            # centre it over the app; x/y are already device px and pass
            # through CTk's geometry untouched, WxH must stay design px
            x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
            dialog.geometry(f"452x178+{x}+{y}")
            dialog.bind("<Escape>", lambda e: close(False))
            dialog.bind("<Return>", lambda e: close(True))
            dialog.transient(self.root)
            dialog.deiconify()
            dialog.lift()
            try:
                self._set_window_icon(dialog)
            except Exception:
                pass
            if wait:
                try:
                    dialog.grab_set()
                except Exception:
                    pass
                self.root.wait_window(dialog)
            else:
                state["dialog"] = dialog
        except Exception:
            return False
        return state["ok"]

    def _clear_messages(self):
        if self._confirm("Clear pool",
                         "Remove every message from the pool?",
                         confirm_text="Clear", kind="danger"):
            self.editor.delete("1.0", END)
            self._update_pool_meta()

    # ------------------------------------------------------------------ #
    #  Hotkey
    # ------------------------------------------------------------------ #
    def _register_hotkey(self, key=None):
        self.hotkey_listener = hotkeymod.HotkeyListener()
        self.hotkey_listener.set_hotkey(self.start_key, self._request_start)
        self.hotkey_listener.set_hotkey(self.stop_key, self._request_stop)
        self.hotkey_listener.set_hotkey(self.resume_key, self._request_resume)
        # registered last, so a duplicate key would silently take the others
        # over - every setter refuses a key another action already owns
        self.hotkey_listener.set_hotkey(self.pause_key, self._request_pause)
        self.hotkey_listener.start()

    def _request_start(self):
        """Called from the hotkey thread - never touch Tk from here."""
        self._start_requested = True

    def _request_stop(self):
        """Called from the hotkey thread - never touch Tk from here."""
        self._stop_requested = True

    def _request_pause(self):
        """Called from the hotkey thread - never touch Tk from here."""
        self._pause_requested = True

    def _request_resume(self):
        """Called from the hotkey thread - never touch Tk from here."""
        self._resume_requested = True

    def _others_own(self, key, skip):
        """Which of the other actions already claimed this key."""
        key = hotkeymod.normalise(key)
        return [(attr, value) for attr, value in (
            ("start", self.start_key), ("stop", self.stop_key),
            ("pause", self.pause_key), ("resume", self.resume_key))
            if attr != skip and hotkeymod.normalise(value) == key]

    def _open_github(self):
        """Open the project repository in the default browser."""
        try:
            import webbrowser
            webbrowser.open(GITHUB_URL)
        except Exception:
            pass

    def _set_hotkey(self):
        key = self.hotkey_view_var.get().lower().strip()
        if not key:
            return
        if not hotkeymod.is_valid(key):
            messagebox.showerror("Invalid hotkey",
                                 f"'{key}' is not a valid key.\n\n"
                                 "Use a single key such as f8.",
                                 parent=self.root)
            return
        clash = self._others_own(key, "start")
        if clash:
            messagebox.showerror("Hotkey in use",
                                 f"{key} is already the {clash[0][0]} key.",
                                 parent=self.root)
            return
        if not self.hotkey_listener.set_hotkey(key, self._request_start):
            messagebox.showerror("Hotkey error", f"Could not register {key}.", parent=self.root)
            return
        self._retire(self.start_key, key)
        self.start_key = hotkeymod.normalise(key)
        self.hotkey_view_var.set(self.start_key)
        self._refresh_key_caps()
        self._save_config()

    def _set_stop_hotkey(self):
        key = self.stopkey_view_var.get().lower().strip()
        if not key:
            return
        if not hotkeymod.is_valid(key):
            messagebox.showerror("Invalid hotkey",
                                 f"'{key}' is not a valid key.\n\n"
                                 "Use a single key such as f9.",
                                 parent=self.root)
            return
        clash = self._others_own(key, "stop")
        if clash:
            messagebox.showerror("Hotkey in use",
                                 f"{key} is already the {clash[0][0]} key.",
                                 parent=self.root)
            return
        if not self.hotkey_listener.set_hotkey(key, self._request_stop):
            messagebox.showerror("Hotkey error", f"Could not register {key}.", parent=self.root)
            return
        self._retire(self.stop_key, key)
        self.stop_key = hotkeymod.normalise(key)
        self.stopkey_view_var.set(self.stop_key)
        self._refresh_key_caps()
        self._save_config()

    def _set_pause_hotkey(self):
        key = self.pausekey_view_var.get().lower().strip()
        if not key:
            return
        if not hotkeymod.is_valid(key):
            messagebox.showerror("Invalid hotkey",
                                 f"'{key}' is not a valid key.\n\n"
                                 "Use a single key such as f6.",
                                 parent=self.root)
            return
        clash = self._others_own(key, "pause")
        if clash:
            messagebox.showerror("Hotkey in use",
                                 f"{key} is already the {clash[0][0]} key.",
                                 parent=self.root)
            return
        if not self.hotkey_listener.set_hotkey(key, self._request_pause):
            messagebox.showerror("Hotkey error", f"Could not register {key}.", parent=self.root)
            return
        self._retire(self.pause_key, key)
        self.pause_key = hotkeymod.normalise(key)
        self.pausekey_view_var.set(self.pause_key)
        self._refresh_key_caps()
        self._save_config()

    def _set_resume_hotkey(self):
        key = self.resumekey_view_var.get().lower().strip()
        if not key:
            return
        if not hotkeymod.is_valid(key):
            messagebox.showerror("Invalid hotkey",
                                 f"'{key}' is not a valid key.\n\n"
                                 "Use a single key such as f7.",
                                 parent=self.root)
            return
        clash = self._others_own(key, "resume")
        if clash:
            messagebox.showerror("Hotkey in use",
                                 f"{key} is already the {clash[0][0]} key.",
                                 parent=self.root)
            return
        if not self.hotkey_listener.set_hotkey(key, self._request_resume):
            messagebox.showerror("Hotkey error", f"Could not register {key}.", parent=self.root)
            return
        self._retire(self.resume_key, key)
        self.resume_key = hotkeymod.normalise(key)
        self.resumekey_view_var.set(self.resume_key)
        self._refresh_key_caps()
        self._save_config()

    def _retire(self, old, new):
        """Withdraw the key that was just replaced.

        set_hotkey only ever adds, so without this the old key stays armed
        beside the new one and both would do the same job.
        """
        try:
            if hotkeymod.normalise(old) != hotkeymod.normalise(new):
                self.hotkey_listener.remove_hotkey(old)
        except Exception:
            pass

    def _refresh_key_caps(self):
        if getattr(self, "key_cap_start", None):
            self.key_cap_start.set_text(self.start_key.upper())
        if getattr(self, "key_cap_stop", None):
            self.key_cap_stop.set_text(self.stop_key.upper())
        if getattr(self, "key_cap_pause", None):
            self.key_cap_pause.set_text(self.pause_key.upper())
        if getattr(self, "key_cap_resume", None):
            self.key_cap_resume.set_text(self.resume_key.upper())

    # ------------------------------------------------------------------ #
    #  Typing engine
    # ------------------------------------------------------------------ #
    def _focus_refused(self):
        """True when Raze itself is in front, having explained why not.

        This also captures the handle the worker re-checks between messages
        - reading Tk from that thread is not safe, so it has to be taken here.
        """
        try:
            here = int(self.root.wm_frame(), 16)
        except Exception:
            here = 0
        if is_foreground(here):
            self._set_status("TAB OUT", AMBER)
            self.session_state.set_text("Switch to your app first")
            self.session_state.set_color(AMBER)
            return True
        self._raze_hwnd = here
        return False

    def _start(self):
        if self.paused:
            # the keys are not each other's aliases: pause put this session
            # to sleep and only the resume key wakes it, so start has no
            # business undoing that behind the user's back.  It has to bail
            # before the pool is read, or an empty one would pop a warning
            # for a key that was meant to do nothing at all
            return
        # a new session supersedes any announcement still waiting for the
        # screen to free up - it is about to be out of date
        self._pending_toast = None
        self.passes = 0
        self.messages = self._collect_messages()
        if not self.messages:
            messagebox.showwarning("No messages", "Add at least one message before starting.",
                                    parent=self.root)
            return
        self._tab_in_stop = False
        if self._focus_refused():
            return

        # a fresh start always opens a new session - which is precisely what
        # pause exists so that stepping away does not have to cost
        self.typing = True
        self.arming = False
        self.paused = False
        self.stop_event.clear()
        self.stats = {"sent": 0, "chars": 0, "elapsed": 0.0}
        self._session_start = time.monotonic()
        self._next_deadline = None
        self._last_message = ""
        self._stop_requested = False
        self._worker_error = None
        # snapshot the settings on the UI thread (Tk vars are not thread safe)
        self._auto_enter = True
        # flush first: pressing F8 leaves focus in the Loop field, so the
        # typed number has not been committed and get() would still answer
        # with the old value
        self._commit_fields()
        self.loop_count = int(self.nf_loop.get())

        self._set_status("TYPING", GREEN)
        self.session_state.set_text("Typing")
        self.session_state.set_color(GREEN)
        self._launch()

    def _launch(self):
        """Get out of the way, then start typing into whatever now has focus.

        The window is minimised rather than withdrawn, so it keeps its
        taskbar entry and can be brought back with one click.
        """
        self.arming = False
        self._restore_drain = True       # the next map is a restore of ours
        try:
            self.root.iconify()
        except Exception:
            try:
                self.root.withdraw()
            except Exception:
                pass
        self._generation += 1
        self.root.after(120, lambda: self._begin_typing(self._generation))

    def _begin_typing(self, generation):
        # a stop (or a restart) in the meantime invalidates this timer
        if generation != self._generation or self.stop_event.is_set():
            return
        self._next_deadline = time.monotonic() + self.msg_interval
        self.typing_thread = threading.Thread(target=self._typing_worker, daemon=True)
        self.typing_thread.start()

    def _pause(self):
        """Suspend the run without ending the session.

        The clock is frozen first and only then is the worker asked to leave,
        so the counters keep everything already sent.  That is the whole
        difference between this and F9, which throws the session away.
        """
        if not self.typing or self.paused:
            return
        self.paused = True
        if self._session_start:
            self.stats["elapsed"] = time.monotonic() - self._session_start
            self._session_start = None
        self._next_deadline = None
        # the worker reads paused in its finally and then leaves quietly,
        # without raising the _worker_done that would mean a real stop
        self.stop_event.set()
        self._set_status("PAUSED", AMBER)
        self.session_state.set_text("Paused")
        self.session_state.set_color(AMBER)

    def _resume(self):
        if not self.paused:
            return
        # resuming starts typing, so it needs the guard starting takes
        if self._focus_refused():
            return
        self._tab_in_stop = False
        self._worker_error = None
        self.paused = False
        self.stop_event.clear()
        # carry the clock on from where it was frozen rather than restarting it
        self._session_start = time.monotonic() - float(self.stats.get("elapsed", 0.0))
        self._set_status("TYPING", GREEN)
        self.session_state.set_text("Typing")
        self.session_state.set_color(GREEN)
        self._launch()

    def _stop(self):
        self.typing = False
        self.arming = False
        self.paused = False
        self.stop_event.set()
        self._session_start = None
        self._next_deadline = None

        self._set_status("IDLE", FAINT)
        self.session_state.set_text("Stopped")
        self.session_state.set_color(FAINT)

        # The window stays where it is.  Stopping the typer must never
        # yank the user back to Raze - the app keeps running in the
        # background and stays one click away in the taskbar.

    def _typing_worker(self):
        # read the settings on the main thread - Tk variables are not thread safe
        randomise = self._random_pick
        auto_enter = self._auto_enter
        loop_count = self.loop_count
        order = list(self.messages)
        if not order:
            self._worker_done = True
            return
        passes = 0
        index = 0
        counted = 0
        self.passes = 0

        try:
            while not self.stop_event.is_set():
                if randomise:
                    # a fresh pick every interval: the same line can win
                    # twice while another goes unsent for a whole pass
                    slot = random.randrange(len(order))
                    message = order[slot]
                else:
                    # strictly top to bottom
                    slot = index
                    message = order[index]
                    index += 1
                    if index >= len(order):
                        index = 0

                # stop before the message goes out, never during it: Raze
                # being in front means these keystrokes would land in our own
                # message pool instead of the application the user chose
                if is_foreground(self._raze_hwnd):
                    self._tab_in_stop = True
                    break

                # the counters only advance once the message is away, so a
                # failed send never burns the number it was about to use
                if not self._type_text(message):
                    break
                if auto_enter and not self.stop_event.is_set():
                    send_enter()
                self.stats["sent"] += 1
                self._last_message = message
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.history.append((stamp, message))
                day = stamp[:10]
                self.daily[day] = self.daily.get(day, 0) + 1
                self._history_dirty = True
                if len(self.history) > HISTORY_KEEP:
                    del self.history[:-HISTORY_KEEP]

                end = time.monotonic() + self.msg_interval
                self._next_deadline = end
                # an exact wait - it wakes instantly when the typer is
                # stopped instead of spinning on a timer
                remaining = end - time.monotonic()
                if remaining > 0:
                    self.stop_event.wait(remaining)

                # a pass is one pool's worth of messages in either mode, so
                # Loop keeps the same meaning whether picking or walking
                counted += 1
                if counted >= len(order):
                    counted = 0
                    passes += 1
                    # published for the session card, which reads it on the
                    # Tk thread - a plain int assignment is all it takes
                    self.passes = passes
                    if loop_count and passes >= loop_count:
                        break
        except Exception as e:
            print("Typing error:", e, flush=True)
            self._worker_error = str(e)
        finally:
            # never touch Tk from this thread - the main loop picks the flag up.
            #
            # An exit a pause asked for has to stay silent: _pause has already
            # frozen the clock and written the status, and _worker_done here
            # would be read as the run having ended.  A tab-in still raises it,
            # because that reason outranks the pause.
            if not (self.paused and not self._tab_in_stop):
                self._worker_done = True

    def _type_text(self, text):
        delay = self.char_delay
        if all(ord(c) < 128 for c in text):
            for ch in text:
                if self.stop_event.is_set():
                    return False
                if not send_char(ch, delay):
                    return False
                self.stats["chars"] += 1
            return True
        # non-ascii -> paste through the clipboard
        try:
            pyperclip.copy(text)
            if not send_paste():
                return False
            self.stats["chars"] += len(text)
            return not self.stop_event.is_set()
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Live stats
    # ------------------------------------------------------------------ #
    def _tick(self):
        """The heartbeat of the app.

        It is wrapped in a guard: a single hiccup must never take the loop
        down, the app has to survive days of running.
        """
        try:
            self._tick_inner()
        except Exception:
            pass
        self.root.after(TICK_MS, self._tick)

    def _toast(self, body, title="Raze"):
        """Surface a stop the user did not ask for, best effort.

        Pressing F9 already told them what they wanted to know, so only the
        endings they did not choose raise one.  The handle is the one captured
        while the window was mapped: by the time this runs Raze is minimised,
        and this is the address Windows still recognises.
        """
        hwnd = getattr(self, "_raze_hwnd", 0)
        if not hwnd:
            try:
                hwnd = int(self.root.wm_frame(), 16)
            except Exception:
                hwnd = 0
        if not hwnd:
            return
        if not notifications_allowed():
            # Windows would only swallow it - a game owns the screen, or the
            # session is locked.  Hold it; the heartbeat sends it the moment
            # the screen frees up, instead of losing it quietly
            self._pending_toast = (title, body)
            self._toast_retry = time.monotonic()
            return
        self._fire_toast(hwnd, title, body)

    def _fire_toast(self, hwnd, title, body):
        self._pending_toast = None
        if notify_balloon(hwnd, title, body, resource_path("raze.ico")):
            # the entry would otherwise sit in the notification area forever
            self.root.after(7000, lambda h=hwnd: notify_clear(h))

    def _retry_pending_toast(self):
        """Send a held notification once Windows says it will show it."""
        if not self._pending_toast:
            return
        now = time.monotonic()
        if now - self._toast_retry < TOAST_RETRY_S:
            return
        self._toast_retry = now
        if not notifications_allowed():
            return
        hwnd = getattr(self, "_raze_hwnd", 0)
        if not hwnd:
            self._pending_toast = None
            return
        title, body = self._pending_toast
        self._fire_toast(hwnd, title, body)

    def _tick_inner(self):
        if self._start_requested:
            self._start_requested = False
            if not self.typing:
                self._start()

        if self._stop_requested:
            self._stop_requested = False
            self._stop()

        # has to come before _worker_done: _pause sets paused and only then
        # releases the worker, so by the time its finally runs it finds this
        # and stays silent.  The other way round a pause would be mistaken
        # for the run ending and would be stopped properly
        if self._pause_requested:
            self._pause_requested = False
            if self.typing and not self.paused:
                self._pause()

        # its own key, so pause can only pause and resume can only resume
        if self._resume_requested:
            self._resume_requested = False
            if self.paused:
                self._resume()

        if self._worker_done:
            self._worker_done = False
            if not self.typing and not self.paused:
                # F9 got here first, so this is only the worker tidying up
                # after a stop the user asked for - there is nothing to say
                self._tab_in_stop = False
                self._worker_error = None
            elif self._tab_in_stop:
                # outranks a pause: the run did not end by choice
                self._tab_in_stop = False
                self.paused = False
                self._stop()
                self._set_status("TAB OUT", AMBER)
                self.session_state.set_text("Switch to your app first")
                self.session_state.set_color(AMBER)
                self._toast("Stopped - you switched back to Raze")
            elif self.paused:
                # the worker left because _pause asked it to
                pass
            else:
                # it ran out of pool, or it failed - either way nothing asked
                # for this, so it is worth saying
                error = self._worker_error
                self._worker_error = None
                if error:
                    self._stop()
                    self._toast("Stopped - typing error: " + error[:70])
                else:
                    sent = self.stats["sent"]
                    self._stop()
                    self._toast("Finished - %d message%s sent"
                                % (sent, "" if sent == 1 else "s"))

        # a message Windows refused while a game owned the screen is still
        # owed to the user - it goes out as soon as the screen frees up
        self._retry_pending_toast()

        # where the run sits in the loop.  set_text is a no-op when the words
        # have not changed, so this costs a string compare per tick
        loop_label = getattr(self, "session_loop", None)
        if loop_label is not None:
            loop_label.set_text(self._loop_text())

        if self._session_start and (self.typing or self.arming):
            self.stats["elapsed"] = time.monotonic() - self._session_start

        self.tile_sent.set(str(self.stats["sent"]), GREEN if self.stats["sent"] else TEXT)
        self.tile_chars.set(str(self.stats["chars"]))
        self.tile_time.set(_elapsed_text(self.stats["elapsed"]))

        nxt = 0.0
        if self._next_deadline and self.typing:
            nxt = max(0.0, self._next_deadline - time.monotonic())
        self.tile_next.set(_next_text(nxt), TEXT if nxt else FAINT)

        # live session status.  A pause deliberately leaves typing set - the
        # run still exists, it is only suspended - so this has to step aside
        # for it, and stop the indicator turning over the message each tick
        if self.typing and not self.paused:
            if self.session_state._text != "Typing":
                self.session_state.set_text("Typing")
            self.session_state.set_color(GREEN)
            self._pulse_start()
        elif self._pulse_on:
            self._pulse_stop()

        if self._last_message:
            text = self._last_message.replace("\n", " ")
            self.last_label.set_text(text[:70] + ("…" if len(text) > 70 else ""))

        # keep the history on disk (it survives restarts until app data is
        # deleted).  Writing the file is not free, so it only happens when
        # something actually changed and not more than once a minute.
        now = time.time()
        if self._history_dirty and now - self._last_save > SAVE_EVERY:
            self._history_dirty = False
            self._last_save = now
            self._save_config()

    def _fit_last_label(self, event=None):
        """Clip the last message into the panel so the row cannot grow."""
        try:
            # the box takes design px (text_photo scales it); winfo_width
            # reports device px, so divide it back out
            width = self.last_label.master.winfo_width() / S - 2
            if width > 40 and width != getattr(self, "_last_fit", 0):
                self._last_fit = width
                self.last_label.set_box(max_width=width)
                self.last_label.set_text(self._last_message or "—")
        except Exception:
            pass

    def _on_close(self):
        """Save everything and leave."""
        try:
            self.stop_event.set()
            self.typing = False
            self._history_dirty = False
            self._save_config()
        except Exception:
            pass
        # a notification still on screen would otherwise outlive the app
        try:
            notify_clear(getattr(self, "_raze_hwnd", 0))
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _center_window(self):
        # the work area, not the raw screen: centering against the full
        # display can push the bottom edge under the taskbar
        aw, ah = _work_area()
        x = max(0, (aw - px(WIN_W)) // 2)
        y = max(0, (ah - px(WIN_H)) // 2 - 20)
        self.root.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        import selftest
        sys.exit(selftest.run())

    if "--startup-probe" in sys.argv:
        # Headless end-to-end timing.  The window is withdrawn before it is
        # ever mapped, so nothing appears on screen and no key is touched.
        import time as _t
        t0 = _t.perf_counter()
        register_fonts()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        ctk.set_widget_scaling(S)
        ctk.set_window_scaling(S)
        t1 = _t.perf_counter()
        root = ctk.CTk()
        root.withdraw()
        t2 = _t.perf_counter()
        AutoTyper(root)
        t3 = _t.perf_counter()
        root.update()
        t4 = _t.perf_counter()
        print("fonts + theme     %8.1f ms" % ((t1 - t0) * 1000))
        print("tk root           %8.1f ms" % ((t2 - t1) * 1000))
        print("build the window  %8.1f ms" % ((t3 - t2) * 1000))
        print("first frame       %8.1f ms" % ((t4 - t3) * 1000))
        print("TOTAL             %8.1f ms" % ((t4 - t0) * 1000))
        # proves the PNG codec travelled with the bundle - a trimmed build
        # that lost it would render the window with no emblem at all
        from PIL import Image
        with Image.open(resource_path("raze_emblem.png")) as probe_img:
            print("emblem PNG        %8s  (%dx%d)"
                  % (probe_img.format, probe_img.width, probe_img.height))
        root.destroy()
        sys.exit(0)

    if not acquire_single_instance():
        # another copy is already running - bring it forward instead
        focus_existing_instance()
        sys.exit(0)

    register_fonts()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    ctk.set_widget_scaling(S)
    ctk.set_window_scaling(S)

    root = ctk.CTk()
    app = AutoTyper(root)
    root.mainloop()
