"""Verify the Discord presence protocol against a fake local pipe.

Nothing here reaches the desktop or the user's profile: `rpc._PIPES` is
swapped for a pipe this test creates, so Discord's real pipe is never opened
even when Discord is running.  What is checked is the framing, the handshake,
the exact payloads Raze would send, the push throttle and the clear-down on
exit - not Discord's opinion of them.
"""

import ctypes
import json
import struct
import sys
import threading
import time
from ctypes import wintypes

PROJ = r"C:\Users\nawaf\Documents\Default Project"
sys.path.insert(0, PROJ)

import rpc

TEST_PIPE = r"\\.\pipe\raze-rpc-test"
CLIENT_ID = "1567235402056859850"

PIPE_ACCESS_DUPLEX = 0x3
PIPE_TYPE_BYTE = 0x0
PIPE_TYPE_MESSAGE = 0x4
PIPE_READMODE_BYTE = 0x0
PIPE_READMODE_MESSAGE = 0x2
PIPE_WAIT = 0x0

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateNamedPipeW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, ctypes.c_void_p]
kernel32.CreateNamedPipeW.restype = ctypes.c_void_p
kernel32.ConnectNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL
kernel32.DisconnectNamedPipe.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                               wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = kernel32.WriteFile.argtypes
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.PeekNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD)]
kernel32.PeekNamedPipe.restype = wintypes.BOOL

failures = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label,
                           " - " + str(detail) if detail else ""))
    if not ok:
        failures.append(label)


def send(handle, opcode, obj):
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    frame = struct.pack("<II", opcode, len(data)) + data
    buf = ctypes.create_string_buffer(frame)
    written = wintypes.DWORD()
    if not kernel32.WriteFile(handle, buf, len(frame), ctypes.byref(written),
                              None):
        raise OSError("server write failed")
    return written.value


def peek(handle):
    n = wintypes.DWORD()
    if not kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(n),
                                  None):
        return None
    return n.value


def read(handle, want):
    buf = ctypes.create_string_buffer(want)
    got = wintypes.DWORD()
    ok = kernel32.ReadFile(handle, buf, want, ctypes.byref(got), None)
    if not ok and ctypes.get_last_error() not in (0, 234):
        return None
    return buf.raw[:got.value] if got.value else b""


class Server:
    """Accepts one client and records every frame it sends."""

    def __init__(self, message_mode):
        self.records = []          # (opcode, payload, monotonic time)
        self.pushes = []           # SET_ACTIVITY payloads, in order
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.message_mode = message_mode
        self.handle = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        mode = PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT \
            if self.message_mode else PIPE_TYPE_BYTE | PIPE_READMODE_BYTE \
            | PIPE_WAIT
        h = kernel32.CreateNamedPipeW(TEST_PIPE, PIPE_ACCESS_DUPLEX, mode,
                                      1, 65536, 65536, 0, None)
        if h in (None, 0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return
        self.handle = h
        kernel32.ConnectNamedPipe(h, None)
        rx = bytearray()
        while not self.stop.is_set():
            avail = peek(h)
            if avail is None:
                break
            if avail:
                chunk = read(h, avail)
                if chunk is None:
                    break
                rx += chunk
            while len(rx) >= 8:
                opcode, length = struct.unpack("<II", rx[:8])
                if len(rx) < 8 + length:
                    break
                raw = bytes(rx[8:8 + length])
                del rx[:8 + length]
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {}
                self.records.append((opcode, payload, time.monotonic()))
                if opcode == 0:
                    # what Discord says the moment the handshake lands
                    send(h, 1, {"cmd": "DISPATCH", "evt": "READY",
                                "data": {"v": 1}})
                    self.ready.set()
                elif opcode == 1 and payload.get("cmd") == "SET_ACTIVITY":
                    self.pushes.append(payload)
                elif opcode == 3:
                    send(h, 4, payload)
            time.sleep(0.02)

    def wait(self, predicate, timeout=6.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self):
                return True
            time.sleep(0.05)
        return predicate(self)

    def close(self):
        self.stop.set()
        try:
            self.thread.join(2.0)
        except Exception:
            pass
        if self.handle:
            try:
                kernel32.DisconnectNamedPipe(self.handle)
            except Exception:
                pass
            try:
                kernel32.CloseHandle(self.handle)
            except Exception:
                pass


def activities(server):
    return [p.get("args", {}).get("activity") for p in server.pushes]


def run_exchange(label, message_mode):
    print("%s (%s pipes)" % (label,
                             "message" if message_mode else "byte"))
    server = Server(message_mode)
    original = rpc._PIPES
    rpc._PIPES = [TEST_PIPE]
    presence = rpc.Presence(CLIENT_ID)
    # the instant the app launched, an hour ago so the shape is the real
    # one: this is what the timer counts from and it never moves again
    started = int(time.time()) - 3600
    try:
        presence.set_state("TYPING", 41, started)
        presence.start()
        if not server.wait(lambda s: s.ready.is_set(), timeout=8.0):
            check("%s: the handshake was answered" % label, False,
                  "no READY after 8s")
            return

        # the handshake itself
        hs = [r for r in server.records if r[0] == 0]
        check("%s: a handshake was sent" % label, len(hs) >= 1, len(hs))
        if hs:
            check("%s: the handshake carries the client id" % label,
                  hs[0][1].get("client_id") == CLIENT_ID, hs[0][1])
            check("%s: the handshake declares protocol v1" % label,
                  hs[0][1].get("v") == 1, hs[0][1].get("v"))

        # first activity: typing, with the timer running from app start
        got = server.wait(lambda s: len(activities(s)) >= 1)
        acts = activities(server)
        check("%s: a typing activity was pushed" % label, got and acts,
              len(acts))
        if acts:
            a = acts[0] or {}
            check("%s: details say Typing" % label,
                  a.get("details") == "Typing", a.get("details"))
            check("%s: state counts everything ever sent" % label,
                  a.get("state") == "41 messages sent", a.get("state"))
            start = (a.get("timestamps") or {}).get("start")
            check("%s: the timer runs from app start" % label,
                  start == started, start)
            buttons = a.get("buttons") or []
            check("%s: the activity carries the repo button" % label,
                  len(buttons) == 1
                  and buttons[0].get("label") == rpc.BUTTON_LABEL
                  and buttons[0].get("url") == rpc.REPO_URL, buttons)

        # paused: same count, and the timer stays - it is the app's own
        # clock, so a pause must neither drop it nor move it
        presence.set_state("PAUSED", 41, started)
        got = server.wait(lambda s: len(activities(s)) >= 2)
        acts = activities(server)
        check("%s: a paused activity replaced it" % label, got and len(acts) >= 2,
              len(acts))
        if len(acts) >= 2:
            a = acts[1] or {}
            check("%s: details say Paused" % label,
                  a.get("details") == "Paused", a.get("details"))
            check("%s: a paused session keeps the timer" % label,
                  (a.get("timestamps") or {}).get("start") == started,
                  a.get("timestamps"))

        # idle with no session: still the lifetime total, never a session number
        presence.set_state("IDLE", 1234, started)
        got = server.wait(lambda s: len(activities(s)) >= 3)
        acts = activities(server)
        check("%s: an idle activity replaced it" % label, got and len(acts) >= 3,
              len(acts))
        if len(acts) >= 3:
            a = acts[2] or {}
            check("%s: details say Idle" % label,
                  a.get("details") == "Idle", a.get("details"))
            check("%s: the idle line is still the lifetime total" % label,
                  a.get("state") == "1234 messages sent", a.get("state"))
            check("%s: an idle session keeps the timer" % label,
                  (a.get("timestamps") or {}).get("start") == started,
                  a.get("timestamps"))

        # nothing may move the start: sessions come and go, the app does not
        presence.set_state("TYPING", 1240, started)
        got = server.wait(lambda s: len(activities(s)) >= 4)
        acts = activities(server)
        later = (acts[3] or {}).get("timestamps") or {} if len(acts) >= 4 else {}
        check("%s: the timer never moves" % label,
              got and later.get("start") == started, later.get("start"))

        # Discord pings, and a presence that does not answer is one it drops
        ping_at = time.monotonic()
        send(server.handle, 3, {"nonce": "probe"})
        got = server.wait(lambda s: any(r[0] == 4 for r in s.records))
        pong = [r for r in server.records if r[0] == 4]
        check("%s: a ping is answered with a pong" % label, got and pong,
              len(pong))
        if pong:
            check("%s: the pong carries the nonce back" % label,
                  pong[-1][1].get("nonce") == "probe", pong[-1][1])
            check("%s: the pong came back promptly" % label,
                  time.monotonic() - ping_at < 3.0,
                  round(time.monotonic() - ping_at, 2))

        # throttling: nothing may be pushed harder than once a second
        pushes = [p for p in server.pushes]
        times = [r[2] for r in server.records
                 if r[0] == 1 and r[1].get("cmd") == "SET_ACTIVITY"]
        gaps = [b - a for a, b in zip(times, times[1:])]
        check("%s: pushes are at least a second apart" % label,
              not gaps or min(gaps) >= 0.9,
              [round(g, 2) for g in gaps])

        # leaving must take the activity down with it
        thread_ref = presence._thread
        presence.stop()
        got = server.wait(lambda s: any(
            p.get("args", {}).get("activity") is None for p in s.pushes))
        check("%s: stopping clears the activity" % label, got,
              [p.get("args", {}).get("activity") for p in server.pushes][-3:])
        check("%s: the thread actually ended" % label,
              thread_ref is None or not thread_ref.is_alive())
    finally:
        rpc._PIPES = original
        try:
            presence.stop()
        except Exception:
            pass
        server.close()


def run_disabled():
    print("disabled seam")
    original = rpc.enabled
    rpc.enabled = False
    try:
        p = rpc.Presence(CLIENT_ID)
        p.start()
        check("a disabled presence never starts a thread",
              p._thread is None, p._thread)
        p.set_state("TYPING", 1, int(time.time()) - 3600)
        p.stop()
        check("stopping a presence that never started is harmless",
              p._thread is None)
    finally:
        rpc.enabled = original


def run_silent():
    print("discord absent")
    original = rpc._PIPES
    rpc._PIPES = [r"\\.\pipe\raze-definitely-not-here"]
    try:
        p = rpc.Presence(CLIENT_ID)
        p.start()
        time.sleep(1.2)
        check("a missing pipe is not an error", p._thread is not None)
        check("it stays connected to nothing rather than raising",
              p._handle is None, p._handle)
        p.stop()
        check("it still stops cleanly", p._thread is None)
    finally:
        rpc._PIPES = original


def main():
    run_exchange("byte", False)
    run_exchange("message", True)
    run_disabled()
    run_silent()
    print("RESULT:", "PASS" if not failures else "FAIL " + str(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
