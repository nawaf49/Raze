"""Headless self test for Raze.

Nothing in here touches the operating system's input state: no synthetic
keystrokes, no mouse movement, no focus changes and no visible window.  The
checks run as pure logic so they can be executed from the packaged exe with

    Raze.exe --selftest

which exits again before a single window is created.
"""

import ctypes
import io
import os
import sys
import tempfile


class _FakeKey:
    """Stands in for a pynput key event."""

    def __init__(self, name):
        self.name = name


def _check(label, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {label}{(' - ' + detail) if detail else ''}")
    return bool(condition)


def run():
    project = os.path.dirname(os.path.abspath(__file__))
    if project not in sys.path:
        sys.path.insert(0, project)

    import hotkeys
    import textengine

    failures = 0
    print("hotkeys")
    failures += not _check("normalise", hotkeys.normalise(" Ctrl + Shift + F8 ") ==
                           "ctrl+shift+f8")
    failures += not _check("is_valid f8", hotkeys.is_valid("f8"))
    failures += not _check("is_valid combo", hotkeys.is_valid("ctrl+shift+f8"))
    failures += not _check("is_valid junk", not hotkeys.is_valid("ctrl+ctrl"))
    failures += not _check("is_valid empty", not hotkeys.is_valid("   "))

    fired = []
    listener = hotkeys.HotkeyListener()
    listener.set_hotkey("f8", lambda: fired.append("start"))
    listener.set_hotkey("f9", lambda: fired.append("stop"))
    listener._on_press(_FakeKey("f8"))
    listener._on_press(_FakeKey("f9"))
    failures += not _check("f8 + f9 fire in order", fired == ["start", "stop"],
                           str(fired))

    fired.clear()
    listener.set_hotkey("ctrl+shift+f8", lambda: fired.append("combo"))
    listener._on_press(_FakeKey("ctrl"))
    listener._on_press(_FakeKey("shift"))
    listener._on_press(_FakeKey("f8"))
    failures += not _check("modifier combo fires", fired == ["combo"], str(fired))
    fired.clear()
    listener._on_release(_FakeKey("ctrl"))
    listener._on_release(_FakeKey("shift"))
    listener._on_press(_FakeKey("f8"))
    failures += not _check("plain key ignores held modifiers",
                           fired == ["start"], str(fired))
    listener.remove_hotkey("f8")
    listener.remove_hotkey("f9")
    listener.stop()

    print("text engine")
    fonts = os.path.join(project, "assets", "fonts")
    if not os.path.isdir(fonts):
        fonts = os.path.join(project, "..", "assets", "fonts")
    img = textengine.render("Raze", 20, fonts, weight="DisplayExtraBold",
                            color="#f6f6f8", tracking=-0.6)
    failures += not _check("renders an image", img.size[0] > 20 and img.size[1] > 8,
                           str(img.size))
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    dark = sum(hist[:40])
    lit = sum(hist[216:])
    edges = sum(hist[40:216])
    failures += not _check("has solid stems", lit > 40, f"{lit} opaque px")
    failures += not _check("has antialiased edges", edges > 0, f"{edges} edge px")
    colour = img.convert("RGB").getpixel((img.size[0] // 2, 1))
    failures += not _check("transparent pixels keep the text colour",
                           colour == (246, 246, 248), str(colour))

    print("history")
    import AutoTyper as A
    history = [("2026-10-21 18:00:00", "a"), ("2026-10-21 19:00:00", "b"),
               ("2026-10-20 10:00:00", "c")]
    days = A.group_history(history)
    failures += not _check("groups by day", days == {"2026-10-21": 2, "2026-10-20": 1},
                           str(days))
    failures += not _check("pretty date", A.pretty_day("2026-10-21") ==
                           "October 21 Wednesday, 2026", A.pretty_day("2026-10-21"))
    failures += not _check("pretty date fallback",
                           A.pretty_day("nonsense") == "nonsense")

    print("keystroke sender")
    # send_paste has to be exercised without sending anything: user32 is
    # swapped for a recorder, so no keystroke can possibly reach the desktop
    # and nothing here depends on what currently has focus
    sent = {}
    real_user32 = A._user32

    class _Recorder:
        def SendInput(self, count, arr, size):
            sent["count"] = count
            sent["size"] = size
            sent["events"] = [(arr[i].type, arr[i].ki.wVk, arr[i].ki.dwFlags)
                              for i in range(count)]
            return count

    A._user32 = _Recorder()
    try:
        paste_ok = A.send_paste()
    finally:
        A._user32 = real_user32
    events = sent.get("events", [])
    failures += not _check("the input struct is 40 bytes",
                           __import__("ctypes").sizeof(A._INPUT) == 40)
    failures += not _check("paste reports success", bool(paste_ok))
    failures += not _check("paste sends four key events",
                           sent.get("count") == 4, str(sent.get("count")))
    failures += not _check("paste is ctrl down, v down, v up, ctrl up",
                           events == [(1, 0x11, 0), (1, 0x56, 0),
                                      (1, 0x56, 2), (1, 0x11, 2)], str(events))

    # the two paths through _type_text must go where they should, with the
    # real sender and the real clipboard swapped out so nothing can reach the
    # keyboard while this runs
    import threading
    import types

    log = []
    real_char, real_paste, real_clip = A.send_char, A.send_paste, A.pyperclip

    class _Clip:
        @staticmethod
        def copy(text):
            log.append(("copy", len(text)))

    A.send_char = lambda ch, delay=0.0: log.append(("char", ch)) or True
    A.send_paste = lambda: log.append(("paste",)) or True
    A.pyperclip = _Clip
    try:
        fake = types.SimpleNamespace(char_delay=0, stop_event=threading.Event(),
                                     stats={"chars": 0})
        ascii_ok = A.AutoTyper._type_text(fake, "hi")
        ascii_chars, ascii_path = fake.stats["chars"], [e[0] for e in log]
        log.clear()
        fake.stats["chars"] = 0
        non_ascii_ok = A.AutoTyper._type_text(fake, "هلا")
        non_ascii_chars, non_ascii_path = fake.stats["chars"], [e[0] for e in log]
    finally:
        A.send_char, A.send_paste, A.pyperclip = real_char, real_paste, real_clip

    failures += not _check("plain text is typed character by character",
                           ascii_ok and ascii_chars == 2
                           and ascii_path == ["char", "char"],
                           "%s %s" % (ascii_chars, ascii_path))
    failures += not _check("non-ascii copies then pastes, never types",
                           non_ascii_ok and non_ascii_chars == len("هلا")
                           and non_ascii_path == ["copy", "paste"],
                           "%s %s" % (non_ascii_chars, non_ascii_path))

    print("random selection")

    class _Worker:
        """A stand-in carrying just the state _typing_worker reads."""

        def __init__(self, pool, randomise, limit, loop=0):
            self._random_pick = randomise
            self._auto_enter = False
            self.loop_count = loop
            self.messages = list(pool)
            self.stop_event = threading.Event()
            self.msg_interval = 0
            self.stats = {"sent": 0, "chars": 0, "elapsed": 0.0}
            self.history = []
            self.daily = {}
            self._history_dirty = False
            self._last_message = ""
            self._next_deadline = None
            self._worker_done = False
            self._raze_hwnd = 0
            self._tab_in_stop = False
            self._worker_error = None
            self._token_n = 0
            self.paused = False
            self.typed = []
            self._limit = limit

        def _type_text(self, text):
            self.typed.append(text)
            if len(self.typed) >= self._limit:
                self.stop_event.set()
            return True

    pool = ["a", "b", "c"]

    ordered = _Worker(pool, False, 6)
    A.AutoTyper._typing_worker(ordered)
    failures += not _check("random off walks the pool in order",
                           ordered.typed == ["a", "b", "c", "a", "b", "c"],
                           str(ordered.typed))

    # the same seed must reproduce the picks, which pins the behaviour to one
    # independent choice per interval instead of a shuffled pass through
    A.random.seed(20261023)
    expected = [A.random.choice(pool) for _ in range(6)]
    A.random.seed(20261023)
    picked = _Worker(pool, True, 6)
    A.AutoTyper._typing_worker(picked)
    failures += not _check("random on picks independently each interval",
                           picked.typed == expected,
                           "%s vs %s" % (picked.typed, expected))

    pass_one = _Worker(pool, False, 99, loop=1)
    A.AutoTyper._typing_worker(pass_one)
    failures += not _check("loop counts one pass of the pool",
                           pass_one.typed == pool, str(pass_one.typed))

    pass_rand = _Worker(pool, True, 99, loop=1)
    A.random.seed(3)
    A.AutoTyper._typing_worker(pass_rand)
    failures += not _check("loop counts a pool's worth when picking",
                           len(pass_rand.typed) == 3, str(pass_rand.typed))

    failures += not _check("the worker always marks itself finished",
                           ordered._worker_done and picked._worker_done,
                           str((ordered._worker_done, picked._worker_done)))

    print("focus guard")

    class _FgRecorder:
        def __init__(self, value, boom=False):
            self.value = value
            self.boom = boom
            self.calls = 0

        def GetForegroundWindow(self):
            self.calls += 1
            if self.boom:
                raise RuntimeError("no foreground window")
            return self.value

    real_user32 = A._user32
    try:
        A._user32 = _FgRecorder(0x1234)
        our_window = A.is_foreground(0x1234)
        other_window = A.is_foreground(0x5678)

        A._user32 = _FgRecorder(0x1234)
        zero = A.is_foreground(0)
        zero_calls = A._user32.calls

        A._user32 = _FgRecorder(0, boom=True)
        raised = A.is_foreground(0xABCD)
    finally:
        A._user32 = real_user32

    failures += not _check("our own window in front is recognised",
                           our_window is True, str(our_window))
    failures += not _check("another window in front is not recognised",
                           other_window is False, str(other_window))
    failures += not _check("an empty handle never queries the desktop",
                           zero is False and zero_calls == 0,
                           "%s %s" % (zero, zero_calls))
    failures += not _check("a failed query never counts as our window",
                           raised is False, str(raised))

    # --- mid-run: the same check has to fire between messages ------------
    try:
        # Raze in front again - bail out before anything is sent
        A._user32 = _FgRecorder(0x1234)
        tabbed = _Worker(pool, False, 6)
        tabbed._raze_hwnd = 0x1234
        A.AutoTyper._typing_worker(tabbed)

        # the target app in front - carry on as normal
        A._user32 = _FgRecorder(0x5678)
        running = _Worker(pool, False, 6)
        running._raze_hwnd = 0x1234
        A.AutoTyper._typing_worker(running)

        # no handle was ever captured - must not kill the run
        A._user32 = _FgRecorder(0x1234)
        no_handle = _Worker(pool, False, 6)
        no_handle._raze_hwnd = 0
        A.AutoTyper._typing_worker(no_handle)
    finally:
        A._user32 = real_user32

    failures += not _check("tabbing in stops the run before the message",
                           tabbed.typed == []
                           and tabbed._tab_in_stop is True,
                           "%s %s" % (tabbed.typed, tabbed._tab_in_stop))
    failures += not _check("typing continues while another app is in front",
                           len(running.typed) == 6
                           and running._tab_in_stop is False,
                           "%s %s" % (len(running.typed),
                                      running._tab_in_stop))
    failures += not _check("a missing handle never kills a run",
                           len(no_handle.typed) == 6, str(no_handle.typed))
    failures += not _check("the reason is raised together with worker_done",
                           tabbed._tab_in_stop and tabbed._worker_done,
                           str((tabbed._tab_in_stop, tabbed._worker_done)))

    print("message tokens")

    failures += not _check("an entry with no token is left alone",
                           A.expand_tokens("hello there", 1, 1) == "hello there",
                           A.expand_tokens("hello there", 1, 1))
    failures += not _check("an empty entry never trips it up",
                           A.expand_tokens("", 1, 1) == ""
                           and A.expand_tokens(None, 1, 1) is None, "empty")
    failures += not _check("n and i expand",
                           A.expand_tokens("msg {n} of {i}", 7, 2) == "msg 7 of 2",
                           A.expand_tokens("msg {n} of {i}", 7, 2))
    failures += not _check("an unknown token survives untouched",
                           A.expand_tokens("{nope} {date}", 1, 1)
                           == "{nope} " + A.time.strftime("%Y-%m-%d"),
                           A.expand_tokens("{nope} {date}", 1, 1))
    # {n} must never reach into a longer word, or "{name}" would come out
    # as "{1ame}"
    failures += not _check("n never reaches into a longer word",
                           A.expand_tokens("{name} {number} {i}", 9, 4)
                           == "{name} {number} 4",
                           A.expand_tokens("{name} {number} {i}", 9, 4))
    failures += not _check("date and time read as a full stamp",
                           A.expand_tokens("{date}|{time}", 1, 1)
                           == A.time.strftime("%Y-%m-%d|%H:%M:%S"),
                           A.expand_tokens("{date}|{time}", 1, 1))

    # the counter belongs to the session, not to one worker: pausing would
    # otherwise restart it at one
    counted = _Worker(["msg {n}", "line {i}"], False, 4)
    A.AutoTyper._typing_worker(counted)
    failures += not _check("the counter ends on what was sent",
                           counted._token_n == 4 and len(counted.typed) == 4,
                           "%s %s" % (counted._token_n, counted.typed))
    failures += not _check("each message carries its own number",
                           # n climbs every send while i stays on the entry's
                           # place in the pool - both meanings at once
                           counted.typed == ["msg 1", "line 2", "msg 3", "line 2"],
                           str(counted.typed))

    print("pause")

    # an exit the pause asked for must stay silent, or the main loop would
    # read it as the run ending and throw the session away
    suspended = _Worker(pool, False, 6)
    suspended.paused = True
    A.AutoTyper._typing_worker(suspended)
    failures += not _check("a pause leaves every counter where it was",
                           suspended.stats["sent"] == 6
                           and len(suspended.typed) == 6,
                           "%s %s" % (suspended.stats["sent"],
                                      len(suspended.typed)))
    failures += not _check("an exit pause asked for stays silent",
                           suspended._worker_done is False,
                           str(suspended._worker_done))

    # ...but tabbing back in still has to get through: that reason wins
    try:
        A._user32 = _FgRecorder(0x1234)
        overridden = _Worker(pool, False, 6)
        overridden.paused = True
        overridden._raze_hwnd = 0x1234
        A.AutoTyper._typing_worker(overridden)
    finally:
        A._user32 = real_user32
    failures += not _check("a tab-in still raises worker_done while paused",
                           overridden._tab_in_stop is True
                           and overridden._worker_done is True,
                           str((overridden._tab_in_stop, overridden._worker_done)))

    print("notification")

    # Explorer refuses a wrong cbSize by returning FALSE rather than reading
    # past it, so this is the one number that has to be exactly right
    struct_size = ctypes.sizeof(A._NOTIFYICONDATAW)
    wide = ctypes.sizeof(ctypes.c_void_p) == 8
    failures += not _check("the balloon struct matches Windows",
                           (not wide) or struct_size == 976,
                           "%d bytes" % struct_size)
    failures += not _check("cbSize leads the struct",
                           A._NOTIFYICONDATAW.cbSize.offset == 0,
                           str(A._NOTIFYICONDATAW.cbSize.offset))
    # the shell reads the text out of these - a shifted offset would show
    # the wrong line rather than fail loudly
    failures += not _check("the balloon text sits at the documented offset",
                           A._NOTIFYICONDATAW.szInfo.offset == 304
                           and A._NOTIFYICONDATAW.szInfoTitle.offset == 820,
                           str((A._NOTIFYICONDATAW.szInfo.offset,
                                A._NOTIFYICONDATAW.szInfoTitle.offset)))
    # Shell_NotifyIcon is exported by shell32.  A reference to user32 would
    # raise inside the try and be swallowed, so the feature would sit there
    # looking intact while never doing anything.
    failures += not _check("the balloon call is bound to shell32",
                           hasattr(A._shell32, "Shell_NotifyIconW")
                           and not hasattr(A._user32, "Shell_NotifyIconW"),
                           "shell32 / user32")
    failures += not _check("a notification without a window never raises",
                           A.notify_balloon(0, "Raze", "body") is False
                           and A.notify_clear(0) is False, "zero handle")

    print("config")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APPDATA"] = tmp
        cfg = os.path.join(tmp, "Raze", "config.json")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with io.open(cfg, "w", encoding="utf-8") as fh:
            fh.write('{"msg_interval": 3.5, "loop": 7, "messages": ["hi"],'
                     ' "history": [{"t": "2026-10-21 18:00:00", "m": "hi"}]}')
        data = A.read_config(cfg)
        failures += not _check("reads the config", data.get("loop") == 7, str(data))
        failures += not _check("keeps the history",
                               len(data.get("history", [])) == 1, str(data.get("history")))

        # a stray byte order mark must not make the config look unreadable
        with io.open(cfg, "w", encoding="utf-8-sig") as fh:
            fh.write('{"loop": 3, "messages": ["marked"]}')
        data = A.read_config(cfg)
        failures += not _check("reads a config with a byte order mark",
                               data.get("loop") == 3
                               and data.get("messages") == ["marked"], str(data))

        # and a file we truly cannot read is kept, never silently replaced
        with io.open(cfg, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        data = A.read_config(cfg)
        kept = os.path.join(os.path.dirname(cfg), "config.unreadable.json")
        failures += not _check("falls back to defaults on a broken config",
                               data.get("loop") == 0, str(data))
        failures += not _check("a broken config is preserved for recovery",
                               os.path.exists(kept)
                               and io.open(kept, encoding="utf-8").read()
                               == "{ this is not json", kept)

        # the save itself is atomic and leaves no byte order mark behind
        os.remove(kept)
        A.write_config({"loop": 9, "messages": ["kept"]}, cfg)
        raw = open(cfg, "rb").read()
        failures += not _check("the config is written without a mark",
                               not raw.startswith(b"\xef\xbb\xbf"), repr(raw[:8]))
        failures += not _check("no temporary file is left behind",
                               not os.path.exists(cfg + ".tmp"), cfg + ".tmp")
        data = A.read_config(cfg)
        failures += not _check("reads what was written",
                               data.get("loop") == 9
                               and data.get("messages") == ["kept"], str(data))

    print("single instance")
    # False here is unambiguous: it comes back only on ERROR_ALREADY_EXISTS,
    # and every other path of the function returns True.  Raze may already be
    # open when this runs - the app has to be running for anything else to be
    # useful - and in that case this process simply is the second copy, which
    # is what the first check below proves just as well
    held = A.acquire_single_instance()
    refused = A.acquire_single_instance()
    if held:
        failures += not _check("first copy takes the lock", held, str(held))
    else:
        failures += not _check("the lock was held before this test started",
                               not held and not refused,
                               "held=%s refused=%s" % (held, refused))
        print("        (a Raze was already running, so the first copy test does"
              " not apply)")
    failures += not _check("a second copy is refused", refused is False,
                           str(refused))

    print("app data")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APPDATA"] = tmp
        path = A.config_path()
        failures += not _check("config lives in the user profile",
                               path.startswith(tmp) and path.endswith("config.json"),
                               path)
        failures += not _check("no config next to the app",
                               not any(f.lower().endswith(".json")
                                       for f in os.listdir(project)))

    print()
    if failures:
        print(f"SELFTEST FAILED - {failures} check(s) did not pass")
        return 1
    print("SELFTEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
