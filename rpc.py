r"""
Discord Rich Presence for Raze.

Discord exposes a local named pipe - \\.\pipe\discord-ipc-0 through -9 - and
speaks a small length-prefixed JSON protocol over it.  It is implemented here
with ctypes and the standard library for the same reason the toast is: hard
rule 6 keeps the shipped exe to one self-contained file, and a presence
library would drag its own baggage (pypresence pulls requests, which pulls the
whole http stack) into a payload that is unpacked from scratch on every
launch.

The thread owns the pipe and never touches Tk.  The Tk thread only ever
writes four values through set_state(); every byte of I/O happens over here.
Discord not running is not an error - it is the ordinary case, and it is
retried quietly forever.
"""

import ctypes
import json
import os
import struct
import threading
import time
import uuid
from ctypes import wintypes

CLIENT_ID = "1563320594743693483"

# The one thing a presence is really for: a stranger sees the activity and
# has somewhere to go.  The public repo, never the source one.
REPO_URL = "https://github.com/nawaf49/Raze"
BUTTON_LABEL = "Download"

# Harnesses turn this off before they build a real AutoTyper, for the same
# reason they stub the toast: a test must never put anything on the user's
# Discord profile.  See AGENTS.md, Testing protocol.
enabled = True

# Both prefixes are tried.  Discord has used each at different times and the
# two namespaces are interchangeable for named pipes, but there is no cost to
# asking twice and a real cost to not finding the pipe at all.
_PIPES = [r"\\.\pipe\discord-ipc-%d" % i for i in range(10)]
_PIPES += [r"\\?\pipe\discord-ipc-%d" % i for i in range(10)]

_OP_HANDSHAKE = 0
_OP_FRAME = 1
_OP_CLOSE = 2
_OP_PING = 3
_OP_PONG = 4

_ERROR_MORE_DATA = 234
_MAX_FRAME = 1 << 20

_RECONNECT_S = 5.0     # Discord is not running: ask again in a while
_POLL_S = 0.5          # how often the thread looks at the pipe
_MIN_PUSH_S = 1.0      # never push harder than this, whatever changes

_INVALIDS = {None, 0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD,
                                 wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p]
# A HANDLE is 64 bits wide.  Left at the default c_int restype it comes back
# truncated, and the pipe looks permanently unavailable - the exact trap
# GetForegroundWindow sets elsewhere in this project.
kernel32.CreateFileW.restype = ctypes.c_void_p

_RW_ARGS = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]

kernel32.WriteFile.argtypes = _RW_ARGS
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = _RW_ARGS
kernel32.ReadFile.restype = wintypes.BOOL

kernel32.PeekNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD)]
kernel32.PeekNamedPipe.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL


class Presence:
    """Keeps one Discord activity in step with the typer's state."""

    def __init__(self, client_id=CLIENT_ID):
        self.client_id = client_id
        self._lock = threading.Lock()
        self._status = "IDLE"
        self._sent = 0
        self._lifetime = 0
        self._elapsed = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._handle = None
        self._ready = False
        self._rx = bytearray()
        self._last_push = 0.0
        self._last_activity = None

    # ------------------------------------------------------------------ #
    #  the whole Tk-thread interface: four values, one lock, no I/O
    # ------------------------------------------------------------------ #
    def set_state(self, status, sent, lifetime, elapsed):
        try:
            with self._lock:
                self._status = status or "IDLE"
                self._sent = int(sent or 0)
                self._lifetime = int(lifetime or 0)
                self._elapsed = float(elapsed or 0.0)
        except Exception:
            pass

    def start(self):
        if not enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="raze-presence")
        self._thread.start()

    def stop(self):
        """Take the activity down and leave. Safe to call twice."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            try:
                thread.join(2.0)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  the thread
    # ------------------------------------------------------------------ #
    def _loop(self):
        while not self._stop.is_set():
            try:
                if self._handle is None and not self._connect():
                    # Discord is closed.  Not a failure, just nothing to do.
                    self._stop.wait(_RECONNECT_S)
                    continue
                self._pump()
                self._stop.wait(_POLL_S)
            except Exception:
                # a broken pipe, a frame we did not like, anything at all:
                # drop it and start over rather than let it raise on a thread
                # nobody is watching
                self._drop()
                self._stop.wait(_RECONNECT_S)
        self._goodbye()

    def _pump(self):
        self._drain()
        if not self._ready:
            return
        activity = self._activity()
        if activity == self._last_activity:
            return
        now = time.monotonic()
        if now - self._last_push < _MIN_PUSH_S:
            return                      # still differs, so the next poll sends it
        self._send(_OP_FRAME, {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": activity},
            "nonce": uuid.uuid4().hex,
        })
        self._last_activity = activity
        self._last_push = now

    def _goodbye(self):
        # The run is over; the profile must not go on showing it.  Sent from
        # the thread that owns the pipe, then a beat of slack so Discord can
        # read the frame before the handle disappears under it.
        try:
            if self._handle is not None and self._ready:
                self._send(_OP_FRAME, {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": os.getpid(), "activity": None},
                    "nonce": uuid.uuid4().hex,
                })
                time.sleep(0.05)
        except Exception:
            pass
        self._drop()

    # ------------------------------------------------------------------ #
    #  what the profile shows
    # ------------------------------------------------------------------ #
    def _activity(self):
        with self._lock:
            status, sent = self._status, self._sent
            lifetime, elapsed = self._lifetime, self._elapsed

        details = {"TYPING": "Typing",
                   "PAUSED": "Paused",
                   "TAB OUT": "Waiting for your app"}.get(status, "Idle")

        # A session in progress counts its own messages, which is what the
        # session card shows.  With no session the count is stale or zero, so
        # the lifetime total is the number worth putting on screen.
        if sent > 0:
            state = "%d message%s sent" % (sent, "" if sent == 1 else "s")
        else:
            state = "%d message%s all time" % (lifetime,
                                               "" if lifetime == 1 else "s")

        activity = {"details": details, "state": state, "instance": False,
                    "buttons": [{"label": BUTTON_LABEL, "url": REPO_URL}]}

        # Discord draws the timer itself from `start`, so it only needs
        # handing over while the clock is actually running.  A frozen elapsed
        # would otherwise drift forward between pushes and snap back on each
        # one - which is why a paused session shows no timer at all.
        if status == "TYPING" and elapsed > 0:
            activity["timestamps"] = {"start": int(time.time() - elapsed)}
        return activity

    # ------------------------------------------------------------------ #
    #  the pipe
    # ------------------------------------------------------------------ #
    def _connect(self):
        handle = None
        for name in _PIPES:
            h = kernel32.CreateFileW(name, 0x80000000 | 0x40000000,
                                     0, None, 3, 0, None)
            if h not in _INVALIDS:
                handle = h
                break
        if handle is None:
            return False
        self._handle = handle
        self._rx = bytearray()
        self._ready = False
        self._last_activity = None
        try:
            self._send(_OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
        except Exception:
            self._drop()
            return False
        return True

    def _send(self, opcode, obj):
        if self._handle in _INVALIDS:
            raise OSError("no pipe")
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        frame = struct.pack("<II", opcode, len(data)) + data
        buf = ctypes.create_string_buffer(frame)
        written = wintypes.DWORD()
        if not kernel32.WriteFile(self._handle, buf, len(frame),
                                  ctypes.byref(written), None):
            raise OSError("write failed")
        if written.value != len(frame):
            raise OSError("short write")

    def _drain(self):
        # Peek rather than block: the thread has to stay interruptible so
        # stop() can join it promptly, and a blocking ReadFile would sit on
        # an idle pipe until Discord happened to speak.
        avail = wintypes.DWORD()
        if not kernel32.PeekNamedPipe(self._handle, None, 0, None,
                                      ctypes.byref(avail), None):
            raise OSError("pipe gone")
        if not avail.value:
            return
        want = min(avail.value, 65536)
        buf = ctypes.create_string_buffer(want)
        got = wintypes.DWORD()
        ok = kernel32.ReadFile(self._handle, buf, want, ctypes.byref(got), None)
        # ERROR_MORE_DATA is a message-mode pipe handing over part of a
        # message, which still fills the buffer and is not a failure
        if not ok and ctypes.get_last_error() not in (0, _ERROR_MORE_DATA):
            raise OSError("read failed")
        if got.value:
            self._rx += buf.raw[:got.value]
        self._frames()

    def _frames(self):
        while True:
            if len(self._rx) < 8:
                return
            opcode, length = struct.unpack("<II", self._rx[:8])
            if length > _MAX_FRAME:
                raise OSError("nonsense frame")
            if len(self._rx) < 8 + length:
                return
            payload = bytes(self._rx[8:8 + length])
            del self._rx[:8 + length]
            self._on_frame(opcode, payload)

    def _on_frame(self, opcode, payload):
        if opcode == _OP_PING:
            try:
                self._send(_OP_PONG, json.loads(payload or b"{}"))
            except Exception:
                raise
            return
        if opcode == _OP_CLOSE:
            raise OSError("discord closed the pipe")
        if opcode != _OP_FRAME:
            return
        try:
            msg = json.loads(payload)
        except Exception:
            return
        event = msg.get("evt")
        if event == "READY":
            self._ready = True
        elif event == "ERROR":
            # a client id Discord does not recognise, mostly - worth failing
            # the connection over so the retry does not keep half-alive
            raise OSError("discord said no")

    def _drop(self):
        handle, self._handle = self._handle, None
        self._ready = False
        self._last_activity = None
        self._rx = bytearray()
        if handle not in _INVALIDS:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
