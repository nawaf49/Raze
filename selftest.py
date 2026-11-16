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
import time


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
    failures += not _check("normalise", hotkeys.normalise(" F8 ") == "f8")
    failures += not _check("is_valid f8", hotkeys.is_valid("f8"))
    failures += not _check("is_valid escape", hotkeys.is_valid("escape"))
    failures += not _check("a combination is not valid",
                           not hotkeys.is_valid("ctrl+shift+f8"))
    failures += not _check("a bare modifier is not valid",
                           not hotkeys.is_valid("shift"))
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
    armed = listener.set_hotkey("ctrl+shift+f8", lambda: fired.append("combo"))
    listener._on_press(_FakeKey("ctrl"))
    listener._on_press(_FakeKey("shift"))
    listener._on_press(_FakeKey("f8"))
    failures += not _check("a combination never arms",
                           armed is False and fired == [],
                           "armed=%s fired=%s" % (armed, fired))
    fired.clear()
    listener._on_release(_FakeKey("ctrl"))
    listener._on_release(_FakeKey("shift"))
    listener._on_press(_FakeKey("f8"))
    failures += not _check("plain key fires on its own",
                           fired == ["start"], str(fired))
    listener.remove_hotkey("f8")
    listener.remove_hotkey("f9")
    listener.stop()

    print("text engine")
    fonts = os.path.join(project, "assets", "fonts")
    if not os.path.isdir(fonts):
        fonts = os.path.join(project, "..", "assets", "fonts")
    img = textengine.render("Raze", 20, fonts, weight="ExtraBold",
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

    print("session clock")
    # the two counters the session card shows, both of which used to be able
    # to outgrow their tile: the clock printed unbounded mm:ss (nine
    # characters a year in, in a five digit box) and the countdown printed
    # a decimal
    failures += not _check("elapsed under an hour reads mm:ss",
                           A._elapsed_text(87) == "01:27", A._elapsed_text(87))
    failures += not _check("elapsed over an hour reads hours",
                           A._elapsed_text(3661) == "1h 01m",
                           A._elapsed_text(3661))
    failures += not _check("elapsed over a day reads days",
                           A._elapsed_text(90000) == "1d 1h",
                           A._elapsed_text(90000))
    failures += not _check("elapsed over a year reads years",
                           A._elapsed_text(86400 * 400) == "1y 35d",
                           A._elapsed_text(86400 * 400))
    three_years = A._elapsed_text(86400 * 365 * 3)
    failures += not _check("years of seconds still fit the tile",
                           len(three_years) <= 9, three_years)
    failures += not _check("the countdown is whole seconds",
                           A._next_text(94.7) == "95s", A._next_text(94.7))
    failures += not _check("no countdown pending reads --",
                           A._next_text(0) == "--", A._next_text(0))

    print("hotkey ownership")
    # four actions, four owners - a collision check that forgot one of them
    # would quietly let the last setter take a key over
    class _Owned:
        start_key, stop_key, pause_key, resume_key = "f8", "f9", "f6", "f7"

    failures += not _check("the resume key counts as owned",
                           A.AutoTyper._others_own(_Owned, "f7", "start")
                           == [("resume", "f7")],
                           str(A.AutoTyper._others_own(_Owned, "f7", "start")))
    failures += not _check("an action may keep its own key",
                           A.AutoTyper._others_own(_Owned, "f7", "resume") == [],
                           str(A.AutoTyper._others_own(_Owned, "f7", "resume")))

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

    print("message counter")

    # the counter belongs to the session, not to one worker: pausing would
    # otherwise restart it at one
    counted = _Worker(["one", "two"], False, 4)
    A.AutoTyper._typing_worker(counted)
    failures += not _check("the counter ends on what was sent",
                           counted.stats["sent"] == 4 and len(counted.typed) == 4,
                           "%s %s" % (counted.stats["sent"], counted.typed))
    # nothing is rewritten at send time - the pool is typed exactly as stored
    failures += not _check("each message goes out exactly as typed",
                           counted.typed == ["one", "two", "one", "two"],
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

    # ------------------------------------------------------------------ #
    #  settings changed while a run is under way
    # ------------------------------------------------------------------ #
    # The worker used to snapshot interval, loop, mode and pool once at
    # start, so a change only ever reached the next session.  Each check
    # flips one setting from inside the run - through _type_text, the moment
    # the change has to land - and asserts the run itself moved.  Nothing
    # here waits on the wall clock: the interval check runs on a clock the
    # harness owns.
    print("mid-run settings")

    # a Loop raised from infinite to one pass has to end the run at the
    # first pass boundary rather than carry on to the limit
    looped = _Worker(["a", "b", "c"], False, 50)
    loop_send = looped._type_text

    def loop_mid_run(text):
        ok = loop_send(text)
        if len(looped.typed) == 1:
            looped.loop_count = 1
        return ok

    looped._type_text = loop_mid_run
    A.AutoTyper._typing_worker(looped)
    failures += not _check("a loop count changed mid-run ends the run",
                           len(looped.typed) == 3 and looped.passes == 1,
                           "%s passes %s" % (looped.typed, looped.passes))

    # picking flipped to walking: the first message is whatever the random
    # mode chose, and from the next one on the walk has to be strict
    walked = _Worker(["a", "b", "c"], True, 6)
    walk_send = walked._type_text

    def walk_mid_run(text):
        ok = walk_send(text)
        if len(walked.typed) == 1:
            walked._random_pick = False
        return ok

    walked._type_text = walk_mid_run
    A.AutoTyper._typing_worker(walked)
    failures += not _check("a mode change mid-run is picked up",
                           walked.typed[1:] == ["a", "b", "c", "a", "b"],
                           str(walked.typed))

    # a pool replaced wholesale: the new list takes over, and the walk's
    # index - already past the end of a pool this short - is clamped rather
    # than indexing into nothing
    replaced = _Worker(["a", "b", "c"], False, 4)
    replace_send = replaced._type_text

    def replace_mid_run(text):
        ok = replace_send(text)
        if len(replaced.typed) == 1:
            replaced.messages = ["x"]      # exactly what _update_pool_meta publishes
        return ok

    replaced._type_text = replace_mid_run
    A.AutoTyper._typing_worker(replaced)
    failures += not _check("a pool replaced mid-run takes over",
                           replaced.typed == ["a", "x", "x", "x"],
                           str(replaced.typed))
    failures += not _check("and the walk cannot run past the new pool",
                           replaced._worker_error is None,
                           str(replaced._worker_error))

    # clearing the box to rewrite it is one keystroke away from an empty
    # pool, and that must not kill a run already under way
    emptied = _Worker(["a", "b"], False, 4)
    empty_send = emptied._type_text

    def empty_mid_run(text):
        ok = empty_send(text)
        if len(emptied.typed) == 1:
            emptied.messages = []
        return ok

    emptied._type_text = empty_mid_run
    A.AutoTyper._typing_worker(emptied)
    failures += not _check("an emptied pool does not kill the run",
                           emptied.typed == ["a", "b", "a", "b"]
                           and emptied._worker_error is None,
                           "%s %s" % (emptied.typed, emptied._worker_error))

    # The interval mid-wait: a clock the harness owns stands in for the
    # monotonic one and every wait advances it, so the run takes no real
    # time and the numbers cannot flake.  The interval is shortened from
    # inside the first wait - the one place a snapshot could not reach.
    class _Clock:
        def __init__(self):
            self.t = 5000.0

        def monotonic(self):
            return self.t

    class _SlicedEvent(threading.Event):
        """A stop_event whose wait() lands on the clock instead of sleeping."""

        def __init__(self, clock, on_wait=None):
            super().__init__()
            self.clock = clock
            self.waits = []
            self.on_wait = on_wait

        def wait(self, timeout=None):
            self.waits.append(timeout)
            if self.on_wait is not None:
                first, self.on_wait = self.on_wait, None
                first()
            if timeout:
                self.clock.t += timeout
            return self.is_set()

    clock = _Clock()
    sliced = _Worker(["a", "b"], False, 2)
    sliced.msg_interval = 1.0
    sliced.stop_event = _SlicedEvent(clock, lambda: setattr(
        sliced, "msg_interval", 0.02))
    real_time = A.time
    try:
        A.time = clock
        started = clock.t
        A.AutoTyper._typing_worker(sliced)
    finally:
        A.time = real_time

    failures += not _check("the wait is cut into slices so a change can land",
                           sliced.stop_event.waits
                           and sliced.stop_event.waits[0] == min(1.0, A.INTERVAL_POLL_S),
                           str(sliced.stop_event.waits))
    failures += not _check("an interval shortened inside the wait fires at once",
                           sliced.typed == ["a", "b"] and clock.t - started < 0.5,
                           "%s %.3fs" % (sliced.typed, clock.t - started))
    failures += not _check("a wait the stop cut through leaves no countdown",
                           sliced._next_deadline is None,
                           str(sliced._next_deadline))

    # The four keys are deliberately not aliases of one another.  _tick_inner
    # is driven straight on a stub so this needs no window, no desktop and no
    # worker thread - the flags are the whole thread boundary, so setting them
    # is exactly what pressing the key does
    class _Tile:
        def __init__(self):
            self.value = None

        def set(self, value, *args):
            self.value = value

    class _State:
        def __init__(self, text=""):
            self._text = text

        def set_text(self, text):
            self._text = text

        def set_color(self, colour):
            pass

    class _Tick:
        def __init__(self, paused, typing):
            self.paused = paused
            self.typing = typing
            self.arming = False
            self.calls = []
            self._start_requested = False
            self._stop_requested = False
            self._pause_requested = False
            self._resume_requested = False
            self._worker_done = False
            self._tab_in_stop = False
            # a tab-in stop waiting for the resume key, and the app's own
            # clock - both are read by the heartbeat, so the stub carries them
            self._tab_stopped = False
            self._up_since = time.monotonic()
            self._up_wall = time.time()
            self.uptime_text = _State("UPTIME 00:00")
            self._worker_error = None
            self._session_start = None
            self._next_deadline = None
            self._last_message = ""
            self._history_dirty = False
            self._config_dirty = False
            self._last_save = 0.0
            self._pulse_on = False
            # the held notification and the loop the session card reads;
            # both are touched by every heartbeat, so the stub carries them
            self._pending_toast = None
            self._toast_retry = 0.0
            self.passes = 0
            self.stats = {"sent": 0, "chars": 0, "elapsed": 0.0}
            self.session_state = _State()
            self.tile_sent = _Tile()
            self.tile_chars = _Tile()
            self.tile_time = _Tile()
            self.tile_next = _Tile()
            self.last_label = _State()
            self.stop_event = threading.Event()

        def _start(self):
            self.calls.append("start")

        def _stop(self):
            self.calls.append("stop")

        def _pause(self):
            self.calls.append("pause")

        def _resume(self):
            self.calls.append("resume")
            # the dispatch above is the only part this stub owns - the
            # behaviour is the app's own, so a check can drive the heartbeat
            # and still assert on what a real resume did to the session
            A.AutoTyper._resume(self)

        def _launch(self):
            # deliberately not recorded: the checks here are about which key
            # answered, not about the window getting out of the way
            pass

        def _set_status(self, *args):
            pass

        def _toast(self, *args):
            self.calls.append("toast")

        def _retry_pending_toast(self):
            # silent on purpose: the stub's calls are the contract the
            # ordering checks above assert on, and this runs every tick
            pass

        def _save_config(self):
            pass

        def _maybe_save(self, now):
            # the real gate, driven on the stub: nothing here is dirty
            # (and _save_config above is a no-op), so a heartbeat tick in
            # these tests never writes - but the wiring the tick relies
            # on is exercised all the same
            A.AutoTyper._maybe_save(self, now)

        def _pulse_start(self):
            self._pulse_on = True

        def _pulse_stop(self):
            self._pulse_on = False

        def _focus_refused(self):
            return False

        def _collect_messages(self):
            self.calls.append("collect")
            return ["x"]

    def tick(stub):
        A.AutoTyper._tick_inner(stub)
        return list(stub.calls)

    live = _Tick(paused=False, typing=True)
    live._pause_requested = True
    failures += not _check("the pause key pauses a live run",
                           tick(live) == ["pause"], str(live.calls))

    # the whole point: pause may not be a way back out
    asleep = _Tick(paused=True, typing=True)
    asleep._pause_requested = True
    failures += not _check("the pause key never resumes",
                           tick(asleep) == [], str(asleep.calls))

    awake = _Tick(paused=True, typing=True)
    awake._resume_requested = True
    failures += not _check("the resume key wakes a paused run",
                           tick(awake) == ["resume"], str(awake.calls))

    nothing = _Tick(paused=False, typing=False)
    nothing._resume_requested = True
    failures += not _check("the resume key is silent when nothing is paused",
                           tick(nothing) == [], str(nothing.calls))

    # a run the tab-in stop left waiting is still a session: the resume key
    # carries it on where it stopped, counters and clock included - it is
    # only the start key that begins again from the top
    tabbed = _Tick(paused=False, typing=False)
    tabbed._tab_stopped = True
    tabbed.stats = {"sent": 7, "chars": 42, "elapsed": 13.0}
    tabbed._resume_requested = True
    tick(tabbed)
    failures += not _check("the resume key wakes a tab-in stop",
                           tabbed.calls == ["resume"]
                           and tabbed.typing is True
                           and tabbed._tab_stopped is False
                           and tabbed.stats["sent"] == 7
                           and tabbed.stats["chars"] == 42
                           and abs(tabbed.stats["elapsed"] - 13.0) < 0.5
                           and tabbed._session_start is not None,
                           str((tabbed.calls, tabbed.typing, tabbed._tab_stopped,
                                tabbed.stats, tabbed._session_start)))

    # start has to bail before it reads the pool, so an empty one cannot
    # raise a warning for a key that was meant to do nothing
    paused_start = _Tick(paused=True, typing=True)
    A.AutoTyper._start(paused_start)
    failures += not _check("the start key does nothing to a paused run",
                           paused_start.calls == [], str(paused_start.calls))

    print("notification")

    # The toast rides on WinRT through ctypes: combase.dll binds the entry
    # points, the interface IIDs come from the SDK headers, and the payload
    # reaches Windows as XML - so the bindings, the ids and the XML are the
    # three things that have to be exactly right.
    failures += not _check("the WinRT runtime is bound",
                           A._combase is not None
                           and hasattr(A._combase, "RoInitialize")
                           and hasattr(A._combase, "WindowsCreateString"),
                           "combase")
    # the payload is built as a string, so escaping has to survive a parse:
    # a stray & or < in a message would otherwise make Windows reject it
    import xml.etree.ElementTree as ElementTree
    try:
        doc = ElementTree.fromstring(
            A.toast_xml("Raze & co <one>", "it's a \"test\""))
        texts = [t.text for t in doc.iter("text")]
        template = doc.find(".//binding").get("template")
        xml_ok = (texts == ['Raze & co <one>', 'it\'s a "test"']
                  and template == "ToastGeneric")
        xml_detail = str((texts, template))
    except Exception as e:
        xml_ok = False
        xml_detail = str(e)
    failures += not _check("the toast payload is well-formed XML",
                           xml_ok, xml_detail)
    # the header icon rides in the payload (appLogoOverride) because
    # Windows cannot resolve one from an exe-path AppID: the image element
    # has to be there, and the file it names has to be a real PNG, or the
    # banner falls back to the generic page this fix exists to kill
    try:
        icon_doc = ElementTree.fromstring(A.toast_xml("Raze", "selftest"))
        images = list(icon_doc.iter("image"))
        src = images[0].get("src") if images else ""
        image_ok = (len(images) == 1
                    and images[0].get("placement") == "appLogoOverride"
                    and src.startswith("file:///"))
        image_detail = str([(i.get("placement"), i.get("src"))
                            for i in images])
    except Exception as e:
        image_ok = False
        image_detail = str(e)
    failures += not _check("the toast payload carries the app logo",
                           image_ok, image_detail)
    try:
        icon_path = A.toast_icon_path()
        with open(icon_path, "rb") as fh:
            magic = fh.read(8)
        icon_ok = bool(icon_path) and magic == b"\x89PNG\r\n\x1a\n"
        icon_detail = str((icon_path, magic))
    except Exception as e:
        icon_ok = False
        icon_detail = str(e)
    failures += not _check("the toast icon unpacks to a PNG on disk",
                           icon_ok, icon_detail)
    # a bad IID string would raise inside _guid at toast time, where the
    # caller only ever sees False - so parse them all here instead
    try:
        for iid in (A._IID_TOAST_MANAGER, A._IID_TOAST_NOTIFIER,
                    A._IID_TOAST_FACTORY, A._IID_XML_DOCUMENT_IO,
                    A._IID_XML_DOCUMENT):
            A._guid(iid)
        ids_ok = True
        ids_detail = "5 iids"
    except Exception as e:
        ids_ok = False
        ids_detail = str(e)
    failures += not _check("the toast interface ids parse", ids_ok,
                           ids_detail)
    # with combase gone the refusal has to stay visible: _winrt_start must
    # not latch a success it never had, or later checks would see a runtime
    # that is not there
    real_combase = A._combase
    try:
        A._combase = None
        refused = A.notify_toast("Raze", "selftest")
        latched = A._winrt_started
    finally:
        A._combase = real_combase
    failures += not _check("a missing WinRT binding refuses without latching",
                           refused is False and latched is False,
                           str((refused, latched)))
    # headless build of the real objects - Show is never called, so nothing
    # reaches the screen or the notification platform
    n_obj, t_obj = A._toast_objects("Raze", "selftest")
    built = bool(n_obj) and bool(t_obj)
    A._release(n_obj)
    A._release(t_obj)
    failures += not _check("a toast builds headless and is released",
                           built, str((bool(n_obj), bool(t_obj))))

    # the shell answers whether now is a time to interrupt; a full-screen
    # game (QUNS_BUSY) makes Windows swallow a banner that the toast API
    # still reports as accepted, so Raze holds the message and retries
    failures += not _check("the notification state query is bound to shell32",
                           hasattr(A._shell32, "SHQueryUserNotificationState"),
                           "shell32")
    real_state = A._notification_state
    real_shell32 = A._shell32
    try:
        A._notification_state = lambda: 5      # QUNS_ACCEPTS_NOTIFICATIONS
        accepted = A.notifications_allowed()
        A._notification_state = lambda: 2      # QUNS_BUSY: a game owns the screen
        blocked = A.notifications_allowed()
    finally:
        A._notification_state = real_state

    class _NoAnswer:
        def SHQueryUserNotificationState(self, _ptr):
            raise OSError("shell would not answer")

    A._shell32 = _NoAnswer()
    try:
        unanswered = A.notifications_allowed()
    finally:
        A._shell32 = real_shell32

    failures += not _check("a free screen lets a notification through",
                           accepted is True, str(accepted))
    failures += not _check("a busy screen holds a notification back",
                           blocked is False, str(blocked))
    failures += not _check("a failed state query never holds a notification",
                           unanswered is True, str(unanswered))

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

        # the fourth key arrives through the defaults, so a config written
        # before it existed picks it up without ever having mentioned it
        failures += not _check("an older config gets the resume key",
                               data.get("resume_key") == "f7",
                               str(data.get("resume_key")))

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

        # the personal bests the History tab shows: they arrive through
        # the defaults, they survive a file that already carries them,
        # and the plan that folds runs into them is pure
        fresh = A.read_config(os.path.join(tmp, "no-such-file.json"))
        failures += not _check(
            "a fresh config carries every record key",
            fresh.get("best_sitting_msgs") == 0
            and fresh.get("best_sitting_s") == 0
            and fresh.get("best_sitting_msgs_day") == ""
            and fresh.get("best_sitting_s_day") == "",
            str((fresh.get("best_sitting_msgs"),
                 fresh.get("best_sitting_s"),
                 fresh.get("best_sitting_msgs_day"),
                 fresh.get("best_sitting_s_day"))))
        A.write_config({"loop": 4, "best_sitting_msgs": 42,
                        "best_sitting_s": 3600,
                        "best_sitting_msgs_day": "2026-01-05",
                        "best_sitting_s_day": "2026-01-06"}, cfg)
        data = A.read_config(cfg)
        failures += not _check(
            "a stored record is read back untouched",
            data.get("best_sitting_msgs") == 42
            and data.get("best_sitting_s") == 3600
            and data.get("best_sitting_msgs_day") == "2026-01-05"
            and data.get("best_sitting_s_day") == "2026-01-06"
            and data.get("loop") == 4, str(data))
        worse = A.record_plan(data, [(7, 60, "2026-02-02")])
        failures += not _check(
            "a worse sitting never lowers a record",
            worse == {"best_sitting_msgs": 42, "best_sitting_s": 3600,
                      "best_sitting_msgs_day": "2026-01-05",
                      "best_sitting_s_day": "2026-01-06"},
            str(worse))
        better = A.record_plan(data, [(100, 60, "2026-02-02")])
        failures += not _check(
            "a better sitting raises only what it beats",
            better == {"best_sitting_msgs": 100, "best_sitting_s": 3600,
                       "best_sitting_msgs_day": "2026-02-02",
                       "best_sitting_s_day": "2026-01-06"},
            str(better))
        equal = A.record_plan(data, [(42, 3600, "2026-03-03")])
        failures += not _check(
            "an equal count keeps the day it was first set on",
            equal == {"best_sitting_msgs": 42, "best_sitting_s": 3600,
                      "best_sitting_msgs_day": "2026-01-05",
                      "best_sitting_s_day": "2026-01-06"},
            str(equal))
        junk = A.record_plan({"best_sitting_msgs": "many",
                              "best_sitting_s": -5,
                              "best_sitting_msgs_day": 7},
                             [(None, "soon", "x")])
        failures += not _check(
            "junk in the config clamps to zero",
            junk == {"best_sitting_msgs": 0, "best_sitting_s": 0,
                     "best_sitting_msgs_day": "",
                     "best_sitting_s_day": ""},
            str(junk))
        only = A.record_plan({"loop": 9, "messages": ["kept"]},
                             [(3, 4, "2026-03-03")])
        failures += not _check(
            "the plan returns nothing but its own four keys",
            sorted(only) == ["best_sitting_msgs", "best_sitting_msgs_day",
                             "best_sitting_s", "best_sitting_s_day"],
            str(sorted(only)))

        # the log's runs: a burst of close timestamps is one sitting, a
        # gap starts the next, and a stamp the file cannot parse is dropped
        runs = A.history_runs(
            [("2026-11-01 10:00:00", "a"),
             ("2026-11-01 10:00:03", "b"),
             ("junk", "c"),
             ("2026-11-01 10:30:00", "d"),
             ("2026-11-02 12:00:00", "e")], 300.0)
        failures += not _check(
            "close timestamps group into one run, a gap starts the next",
            runs == [(2, 3, "2026-11-01"), (1, 0, "2026-11-01"),
                     (1, 0, "2026-11-02")],
            str(runs))
        failures += not _check(
            "an empty log is no runs at all",
            A.history_runs([], 300.0) == []
            and A.history_runs(None, 300.0) == [], "non-empty")

        # the day beside a record, as the tile shows it
        failures += not _check(
            "a record day reads as Nov 16, 2026",
            A.record_day_text("2026-11-16") == "Nov 16, 2026",
            repr(A.record_day_text("2026-11-16")))
        failures += not _check(
            "a single digit day carries no zero pad",
            A.record_day_text("2026-01-05") == "Jan 5, 2026",
            repr(A.record_day_text("2026-01-05")))
        failures += not _check(
            "junk in a record day reads as no day",
            A.record_day_text("yesterday") == ""
            and A.record_day_text(7) == "",
            repr((A.record_day_text("yesterday"), A.record_day_text(7))))

        # the load-time backfill: the stored log folded into the records
        # once, and only while it actually knows more than the config does
        class _Fold:
            def __init__(self):
                self.cfg = {"best_sitting_msgs": 0, "best_sitting_s": 0}
                self.history = [("2026-11-01 10:00:00", "a"),
                                ("2026-11-01 10:00:03", "b"),
                                ("2026-11-01 10:00:06", "c"),
                                ("2026-11-02 12:00:00", "d")]
                self.msg_interval = 3
                self.best_sitting_msgs = 0
                self.best_sitting_s = 0
                self.best_sitting_msgs_day = ""
                self.best_sitting_s_day = ""
                self._config_dirty = False
                self.seeded = 0

            def _refresh_records(self):
                self.seeded += 1

        fold = _Fold()
        A.AutoTyper._backfill_records(fold)
        failures += not _check(
            "the backfill reads the log's best run into the records",
            fold.best_sitting_msgs == 3
            and fold.best_sitting_s == 6
            and fold.best_sitting_msgs_day == "2026-11-01"
            and fold.best_sitting_s_day == "2026-11-01",
            str((fold.best_sitting_msgs, fold.best_sitting_s,
                 fold.best_sitting_msgs_day, fold.best_sitting_s_day)))
        failures += not _check(
            "a backfill that improved something marks the config dirty",
            fold._config_dirty and fold.seeded == 1,
            str((fold._config_dirty, fold.seeded)))
        fold._config_dirty = False
        A.AutoTyper._backfill_records(fold)
        failures += not _check(
            "a second fold over the same log changes nothing",
            not fold._config_dirty and fold.seeded == 1,
            str((fold._config_dirty, fold.seeded)))

        # the message pools.  A config from before pools keeps its one
        # pool, a fresh one gets the samples, and an emptied pool stays
        # emptied: absent and empty are two different answers, which is
        # why read_config no longer fills the key in
        failures += not _check(
            "a fresh config carries no messages key",
            "messages" not in fresh, str(fresh.get("messages")))
        profiles, active = A.profiles_plan(fresh)
        failures += not _check(
            "a fresh config gets the sample pool",
            profiles == {"Default": A.SAMPLE_MESSAGES}
            and active == "Default", str((profiles, active)))
        profiles, active = A.profiles_plan({"messages": ["kept"]})
        failures += not _check(
            "a pre-profiles config becomes one pool",
            profiles == {"Default": ["kept"]} and active == "Default",
            str((profiles, active)))
        profiles, active = A.profiles_plan({"messages": []})
        failures += not _check(
            "an emptied pool comes back emptied",
            profiles == {"Default": []} and active == "Default",
            str((profiles, active)))
        profiles, active = A.profiles_plan(
            {"profiles": {"A": ["x"], "B": ["y", "z"]},
             "active_profile": "B"})
        failures += not _check(
            "stored pools and the active one are honoured",
            profiles == {"A": ["x"], "B": ["y", "z"]}
            and active == "B", str((profiles, active)))
        profiles, active = A.profiles_plan(
            {"profiles": {"A": ["x"]}, "active_profile": "gone"})
        failures += not _check(
            "an active name that matches nothing falls back",
            profiles == {"A": ["x"]} and active == "A",
            str((profiles, active)))
        profiles, active = A.profiles_plan(
            {"profiles": {"": ["junk"], "B": "not a list"}})
        failures += not _check(
            "junk pools fall all the way back to the samples",
            profiles == {"Default": A.SAMPLE_MESSAGES}
            and active == "Default", str((profiles, active)))

        # the heartbeat's write gate: an edit is on disk within a couple
        # of seconds, history within a minute - and the write itself
        # re-marks the dirty flag (it flushes the number fields through
        # their setters), which must not condemn the file to a rewrite
        # every two seconds forever
        class _Saver(object):
            def __init__(self):
                self._config_dirty = False
                self._history_dirty = False
                self._last_save = 0.0
                self.writes = 0

            def _save_config(self):
                self.writes += 1
                self._config_dirty = True      # what _commit_fields does

        s = _Saver()
        A.AutoTyper._maybe_save(s, 100.0)      # nothing changed yet
        failures += not _check(
            "an untouched config is not written",
            s.writes == 0, str(s.writes))
        s._config_dirty = True
        A.AutoTyper._maybe_save(s, 100.0)
        failures += not _check(
            "a pending edit is written at once",
            s.writes == 1 and s._last_save == 100.0,
            str((s.writes, s._last_save)))
        failures += not _check(
            "the write clears the flag it re-marked",
            s._config_dirty is False and s._history_dirty is False,
            str((s._config_dirty, s._history_dirty)))
        s._config_dirty = True
        A.AutoTyper._maybe_save(s, 101.0)      # 1 s after the last write
        failures += not _check(
            "the throttle holds a second edit back",
            s.writes == 1 and s._config_dirty is True,
            str((s.writes, s._config_dirty)))
        A.AutoTyper._maybe_save(s, 103.5)      # 3.5 s after the last write
        failures += not _check(
            "the edit goes out once the throttle opens",
            s.writes == 2 and s._config_dirty is False,
            str((s.writes, s._config_dirty)))
        s._history_dirty = True
        A.AutoTyper._maybe_save(s, 150.0)      # 46.5 s after the last write
        failures += not _check(
            "history still waits its full minute",
            s.writes == 2 and s._history_dirty is True,
            str((s.writes, s._history_dirty)))
        A.AutoTyper._maybe_save(s, 164.0)      # 60.5 s after the last write
        failures += not _check(
            "history goes out once its minute is up",
            s.writes == 3 and s._history_dirty is False,
            str((s.writes, s._history_dirty)))

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

    print("display scale")
    # _fit_scale is the whole resolution story in one pure function: the
    # window is a fixed 1060x860, so on any screen with less room than that
    # the scale has to come down or the bottom of the app is simply gone.
    fit = A._fit_scale
    s = fit(1.0, 1920, 1040)
    failures += not _check("a 1080p screen keeps 100%", abs(s - 1.0) < 1e-9,
                           f"{s:.4f}")
    s = fit(1.5, 2560, 1400)
    failures += not _check("a 1440p screen at 150% keeps its scale",
                           abs(s - 1.5) < 1e-9, f"{s:.4f}")
    s = fit(1.25, 1920, 1040)
    failures += not _check("1080p at 125% is shrunk to fit", s < 1.25,
                           f"{s:.4f}")
    failures += not _check("...and the window it produces fits the width",
                           A.WIN_W * s + A.FRAME_W <= 1920, f"{s:.4f}")
    failures += not _check("...and the window it produces fits the height",
                           A.WIN_H * s + A.FRAME_H <= 1040, f"{s:.4f}")
    s = fit(1.0, 1366, 720)
    failures += not _check("a 1366x768 laptop is shrunk to fit", s < 1.0,
                           f"{s:.4f}")
    failures += not _check("...and stays above the usability floor",
                           s >= A.SCALE_MIN, f"{s:.4f}")
    failures += not _check("...and the window it produces fits the height",
                           A.WIN_H * s + A.FRAME_H <= 720, f"{s:.4f}")
    s = fit(0.25, 320, 240)
    failures += not _check("a screen smaller than the floor stops at the floor",
                           abs(s - A.SCALE_MIN) < 1e-9, f"{s:.4f}")
    s = fit(1.0, 0, 0)
    failures += not _check("an unknown work area leaves the scale alone",
                           abs(s - 1.0) < 1e-9, f"{s:.4f}")
    # the clamp only ever shrinks, never enlarges a small display
    s = fit(1.0, 3840, 2160)
    failures += not _check("a 4K screen is not enlarged", abs(s - 1.0) < 1e-9,
                           f"{s:.4f}")

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

        # a profile an older build left behind as "raze" has to come out as
        # Raze - Windows is case insensitive, so otherwise it stays wrong for
        # as long as that folder exists, on every machine that started wrong
        with tempfile.TemporaryDirectory() as legacy_root:
            legacy = os.path.join(legacy_root, "raze")
            os.makedirs(legacy)
            with open(os.path.join(legacy, "config.json"), "w",
                      encoding="utf-8") as f:
                f.write('{"messages": ["kept"]}')
            os.environ["APPDATA"] = legacy_root
            A.config_path()
            named = [d for d in os.listdir(legacy_root)
                     if d.lower() == "raze"]
            failures += not _check("a lowercase profile folder is corrected",
                                   named == ["Raze"], str(named))
            failures += not _check("the correction keeps the config",
                                   os.path.exists(os.path.join(
                                       legacy_root, "Raze", "config.json")),
                                   str(os.listdir(os.path.join(
                                       legacy_root, "Raze"))))

    print("install")
    # Read-only throughout: install_plan computes what an install would
    # touch without touching it, and no harness may ever call do_install
    # or do_uninstall - they write to this machine's registry and folders.
    plan = A.install_plan()
    local = os.environ.get("LOCALAPPDATA", "")
    failures += not _check("install home sits under LOCALAPPDATA",
                           plan["dir"] == A.install_dir()
                           and plan["dir"].startswith(local) and local,
                           plan["dir"])
    failures += not _check("the target is Raze.exe inside that home",
                           plan["target"] == os.path.join(plan["dir"],
                                                          "Raze.exe")
                           and plan["target"] == A.install_exe_path(),
                           plan["target"])
    failures += not _check(
        "two shortcuts: Start Menu\\Programs and Desktop",
        len(plan["links"]) == 2
        and all(link.endswith(A.INSTALL_LINK_NAME) for link in plan["links"])
        and any(link.endswith(os.path.join("Start Menu", "Programs",
                                           A.INSTALL_LINK_NAME))
                for link in plan["links"])
        and any(link.endswith(os.path.join("Desktop", A.INSTALL_LINK_NAME))
                for link in plan["links"]),
        str(plan["links"]))
    failures += not _check("the uninstall entry names --uninstall",
                           plan["uninstall_string"]
                           == '"%s" --uninstall' % plan["target"]
                           and plan["uninstall_key"] == A.UNINSTALL_KEY
                           and plan["uninstall_key"].endswith("\\Raze"),
                           plan["uninstall_string"])
    # hard rule 1: the config profile must be outside every path an
    # install or uninstall ever writes to
    data_home = os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                             "Raze")
    failures += not _check("nothing in the plan touches the config profile",
                           not any(os.path.normcase(p).startswith(
                               os.path.normcase(data_home) + os.sep)
                               for p in [plan["dir"], plan["target"]]
                               + plan["links"]),
                           data_home)
    if getattr(sys, "frozen", False):
        failures += not _check("a frozen run reports its own exe",
                               A.running_exe()
                               == os.path.abspath(sys.executable),
                               str(A.running_exe()))
    else:
        failures += not _check("a dev run has no install source",
                               A.running_exe() is None,
                               str(A.running_exe()))
    # the three gates of the enforced install, each on its own - only a
    # fresh, unlisted download copy outside its install home installs
    fresh = r"C:\Users\someone\Downloads\Raze.exe"
    failures += not _check("a dev run never installs",
                           not A.install_needed(None, False))
    failures += not _check("a listed install is not installed again",
                           not A.install_needed(fresh, True))
    failures += not _check("the installed copy does not install itself",
                           not A.install_needed(plan["target"], False))
    failures += not _check("a fresh download installs itself",
                           A.install_needed(fresh, False))
    # the entry point has to consult that gate: a dev run must never get
    # as far as starting the worker, and a real download must.  The probe
    # replaces _install_now and _repair_shortcuts, so do_install is never
    # touched and the repair thread (which rewrites the real Start Menu
    # links) never starts
    class _InstallProbe:
        started = 0
        repaired = 0

        def _install_now(self):
            _InstallProbe.started += 1

        def _repair_shortcuts(self):
            _InstallProbe.repaired += 1
    probe = _InstallProbe()
    real_running_exe = A.running_exe
    real_registry_installed = A.registry_installed
    try:
        A.AutoTyper._auto_install(probe)
        dev_started = _InstallProbe.started
        dev_repaired = _InstallProbe.repaired
        A.running_exe = lambda: fresh
        A.registry_installed = lambda: False
        A.AutoTyper._auto_install(probe)
        fresh_started = _InstallProbe.started
        fresh_repaired = _InstallProbe.repaired - dev_repaired
    finally:
        A.running_exe = real_running_exe
        A.registry_installed = real_registry_installed
    failures += not _check(
        "the install worker starts only for a real download",
        dev_started == 0 and fresh_started == 1,
        str((dev_started, fresh_started)))
    # the AUMID repair hangs off the same gate, the other way round: it
    # only has work to do when Windows already lists Raze
    failures += not _check(
        "the AUMID repair runs only when there is nothing to install",
        dev_repaired == 1 and fresh_repaired == 0,
        str((dev_repaired, fresh_repaired)))

    # The banner's header name and icon resolve by matching the toast's
    # app id against the Start Menu link's AppUserModelID, so the link has
    # to carry the exact string toast_app_id reports.  The rule is pure,
    # the key layout is fixed by the SDK, and the stamp round-trips on a
    # throwaway link in a temp dir - never a shell folder.
    target = r"C:\somewhere\Raze.exe"
    failures += not _check(
        "a link without an AUMID needs a stamp",
        A.aumid_needs_stamp(None, target)
        and A.aumid_needs_stamp("", target))
    failures += not _check(
        "a matching AUMID does not need a stamp",
        not A.aumid_needs_stamp(target, target))
    failures += not _check(
        "another app's AUMID needs a stamp",
        A.aumid_needs_stamp(r"C:\other\Elsewhere.exe", target))
    failures += not _check(
        "the property key is the SDK's",
        A._AUMID_FMTID == "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
        and A._AUMID_PID == 5 and A._VT_LPWSTR == 31
        and A._IID_PROPERTY_STORE
        == "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}",
        str((A._AUMID_FMTID, A._AUMID_PID)))
    import uuid
    key = A._aumid_key()
    failures += not _check(
        "the key carries the format id and pid",
        ctypes.string_at(ctypes.byref(key.fmtid), 16)
        == uuid.UUID(A._AUMID_FMTID).bytes_le and key.pid == A._AUMID_PID,
        str(key.pid))
    # x64 PROPVARIANT: vt at 0, the string pointer at 8, 24 bytes with
    # the trailing pad a callee copying sizeof(PROPVARIANT) reads
    failures += not _check(
        "the structs match the x64 layout",
        ctypes.sizeof(A._PROPERTYKEY) == 20
        and ctypes.sizeof(A._PROPVARIANT) == 24
        and A._PROPVARIANT.vt.offset == 0
        and A._PROPVARIANT.pwszVal.offset == 8,
        str((ctypes.sizeof(A._PROPERTYKEY),
             ctypes.sizeof(A._PROPVARIANT))))
    with tempfile.TemporaryDirectory(prefix="aumid_") as tmp:
        link = os.path.join(tmp, "Raze.lnk")
        exe = os.path.join(tmp, "Raze.exe")
        A._create_shortcut(link, exe, tmp, exe, "selftest")
        stamped = A._shortcut_aumid(link)
    failures += not _check(
        "a new link carries its target as AUMID",
        stamped == exe, str(stamped))
    # The icon location is the other half of the toast header: the tile
    # Windows draws is the matched link's own icon, and every link
    # written before the fix stored the index glued onto the path - a
    # file named "Raze.exe,0" that does not exist, so the shell drew a
    # blank page instead of the emblem.
    failures += not _check(
        "an unreadable icon location counts as wrong",
        A.icon_needs_fix(None, exe))
    failures += not _check(
        "the target's own icon is left alone",
        not A.icon_needs_fix((exe, 0), exe))
    failures += not _check(
        "the glued-on index is caught",
        A.icon_needs_fix((exe + ",0", 0), exe))
    failures += not _check(
        "an index that is not zero is caught",
        A.icon_needs_fix((exe, 1), exe))
    with tempfile.TemporaryDirectory(prefix="icon_") as tmp:
        link = os.path.join(tmp, "Raze.lnk")
        exe = os.path.join(tmp, "Raze.exe")
        # the icon argument is a bare path: SetIconLocation takes the
        # index as its own argument, so a fresh link must store the
        # target with nothing glued onto it
        A._create_shortcut(link, exe, tmp, exe, "selftest")
        written = A._shortcut_icon(link)
        # the exact shape do_install used to write - the index glued
        # onto the path, which no file ever answers to
        A._create_shortcut(link, exe, tmp, exe + ",0", "selftest")
        broken = A._shortcut_icon(link)
        fixed = A._set_shortcut_icon(link, exe, 0)
        after = A._shortcut_icon(link)
    failures += not _check(
        "a fresh link stores the target as its icon",
        written == (exe, 0), str(written))
    failures += not _check(
        "a glued icon path is read back as written",
        broken == (exe + ",0", 0), str(broken))
    failures += not _check(
        "the repair rewrites a broken icon location",
        fixed and after == (exe, 0), str((fixed, after)))
    # The attribution area (header name + tile) is shell-controlled and
    # cannot come from the payload, so an unpackaged app names it in the
    # AUMID registration - DisplayName and IconUri under
    # Software\Classes\AppUserModelId.  Pure here: the write itself
    # happens on the install/repair worker, never in a suite.
    subkey, values = A.aumid_registry_plan(target, r"C:\t\emblem.png")
    failures += not _check(
        "the header registration lives under the AUMID's path",
        subkey == "Software\\Classes\\AppUserModelId\\" + target,
        subkey)
    failures += not _check(
        "the header registration carries name and tile",
        ("DisplayName", "Raze") in values
        and ("IconUri", r"C:\t\emblem.png") in values,
        str(values))
    failures += not _check(
        "no icon file leaves IconUri out entirely",
        A.aumid_registry_plan(target, None)[1] == [("DisplayName", "Raze")],
        str(A.aumid_registry_plan(target, None)))

    # "Start with Windows" is a Run-key entry: the config file is never
    # involved, so the pure plan plus a write against a stub registry
    # are the whole surface a suite may touch.  The real Run key is the
    # user's machine, not a test field.
    class _RunReg:
        HKEY_CURRENT_USER = object()
        KEY_SET_VALUE = 2
        REG_SZ = 1

        def __init__(self):
            self.values = {}
            self.opened = []

        def OpenKey(self, _hkey, path, _reserved=0, _access=0):
            self.opened.append(path)
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def SetValueEx(self, _key, name, _reserved, _kind, value):
            self.values[name] = value

        def DeleteValue(self, _key, name):
            if name not in self.values:
                raise OSError(name)
            del self.values[name]

    entry = A.startup_plan(r"C:\p\Raze.exe")
    failures += not _check(
        "the startup entry names the Run key and Raze",
        entry["key"] == A.STARTUP_KEY and entry["name"] == A.STARTUP_NAME
        and entry["key"].endswith("CurrentVersion\\Run"),
        str(entry))
    failures += not _check(
        "the startup command is quoted for its spaces",
        entry["command"] == '"C:\\p\\Raze.exe"' and entry["enabled"],
        str(entry))
    blank = A.startup_plan("")
    failures += not _check(
        "no target means no entry at all",
        blank["command"] == "" and not blank["enabled"], str(blank))
    failures += not _check(
        "a startup target always answers a path",
        bool(A.startup_target()), A.startup_target())
    reg = _RunReg()
    failures += not _check(
        "enabling writes the quoted command into the Run key",
        A.set_startup(True, entry["command"], reg=reg)
        and reg.values.get(A.STARTUP_NAME) == entry["command"]
        and reg.opened[-1] == A.STARTUP_KEY,
        str((reg.values, reg.opened)))
    refused = A.set_startup(True, "", reg=reg)
    kept = reg.values.get(A.STARTUP_NAME) == entry["command"]
    cleared = A.set_startup(False, "", reg=reg)
    failures += not _check(
        "an empty enable refuses, disabling clears the entry",
        (not refused and kept
         and not cleared and A.STARTUP_NAME not in reg.values),
        str((refused, kept, cleared, reg.values)))

    print("update")
    # Read-only throughout: the checker thread downloads and the apply
    # path writes, so the selftest only ever asserts on the pure
    # functions - version compare, release parsing and the plan.
    failures += not _check("a tag with a v prefix parses",
                           A.parse_version("v1.17") == (1, 17),
                           str(A.parse_version("v1.17")))
    failures += not _check("a bare version parses",
                           A.parse_version("1.17.0") == (1, 17, 0),
                           str(A.parse_version("1.17.0")))
    failures += not _check("junk never parses",
                           A.parse_version("latest") is None
                           and A.parse_version("") is None
                           and A.parse_version(None) is None
                           and A.parse_version("v1.x") is None)
    failures += not _check("a newer tag counts as newer",
                           A.update_is_newer("v1.17", "1.16")
                           and A.update_is_newer("2.0", "1.16"))
    failures += not _check("the same version is not newer",
                           not A.update_is_newer("v1.16", "1.16"))
    failures += not _check("an older tag is not newer",
                           not A.update_is_newer("v1.15", "1.16"))
    failures += not _check("an unparseable tag never triggers",
                           not A.update_is_newer("nightly", "1.16")
                           and not A.update_is_newer(None, "1.16"))
    failures += not _check("a short tag is padded, not truncated",
                           not A.update_is_newer("v1.16", "1.16.1"))
    rel = A.update_release({
        "tag_name": "v1.17",
        "assets": [
            {"name": "notes.txt", "browser_download_url": "x"},
            {"name": A.UPDATE_ASSET,
             "browser_download_url": "https://example/Raze.exe",
             "digest": "sha256:ABC123"},
        ],
    })
    failures += not _check("the release yields tag, url and digest",
                           rel == {"tag": "v1.17",
                                   "url": "https://example/Raze.exe",
                                   "digest": "abc123"},
                           str(rel))
    missing = A.update_release({"tag_name": "v1.17", "assets": []})
    failures += not _check("a release without the exe is not applicable",
                           missing["url"] is None and missing["digest"] is None
                           and missing["tag"] == "v1.17",
                           str(missing))
    nodigest = A.update_release({
        "tag_name": "v1.17",
        "assets": [{"name": A.UPDATE_ASSET,
                    "browser_download_url": "https://example/Raze.exe"}],
    })
    failures += not _check("an asset without a digest is not applicable",
                           nodigest["url"] is not None
                           and nodigest["digest"] is None,
                           str(nodigest))
    failures += not _check("a non-dict release parses to nothing",
                           A.update_release(None) == {"tag": None, "url": None,
                                                      "digest": None}
                           and A.update_release("oops")["tag"] is None)
    up = A.update_plan()
    temp = os.environ.get("TEMP", "")
    failures += not _check("the plan's download sits in TEMP",
                           up["download"] == A.update_download_path()
                           and up["download"].startswith(temp) and temp,
                           up["download"])
    failures += not _check("the download path is one fixed file",
                           up["download"].endswith("Raze-update.exe"),
                           up["download"])
    failures += not _check("the plan watches the public repo",
                           up["repo"] == "nawaf49/Raze"
                           and up["asset"] == "Raze.exe",
                           up["repo"])
    failures += not _check("the plan carries the running version",
                           up["version"] == A.APP_VERSION
                           and up["tag"] == "v%s" % A.APP_VERSION
                           and up["poll_s"] >= 3600,
                           up["tag"])
    failures += not _check("the plan never touches the config profile",
                           not os.path.normcase(up["download"]).startswith(
                               os.path.normcase(data_home) + os.sep),
                           up["download"])
    if getattr(sys, "frozen", False):
        failures += not _check("a frozen run enables the updater",
                               up["enabled"] and up["target"])
    else:
        failures += not _check("a dev run never checks for updates",
                               not up["enabled"] and not up["target"])

    # The Updates tab ships its list inside the exe, so the two have to
    # stay in step: the newest entry is the version actually running, the
    # list runs newest first, and every line is short enough for the panel
    # it is drawn in.  A release that bumps APP_VERSION without giving the
    # version its line fails here.
    def _pad(t):
        p = tuple(t or ())
        return p + (0,) * max(0, 3 - len(p))
    parsed = [A.parse_version(v) for v, _line in A.UPDATES]
    failures += not _check("the update history starts at the shipped version",
                           bool(A.UPDATES) and A.UPDATES[0][0] == A.APP_VERSION,
                           str(A.UPDATES[0] if A.UPDATES else None))
    failures += not _check("the update history runs newest first",
                           len(parsed) > 1
                           and all(_pad(parsed[i]) > _pad(parsed[i + 1])
                                   for i in range(len(parsed) - 1)),
                           str([v for v, _l in A.UPDATES]))
    longest = max((len(line) for _v, line in A.UPDATES), default=0)
    failures += not _check("every update line fits its row",
                           longest > 0 and longest <= 78, str(longest))

    # The badge beside the Updates tab: it shows until the running
    # version's list has been opened once, and it takes an exact match to
    # silence it.  A config written before the key existed, or one
    # carrying something that is not a version at all, both read as "not
    # seen yet" - the worst case either way is a dot until the tab is
    # opened once.
    failures += not _check("no stored version means unseen",
                           A.updates_unseen(None, A.APP_VERSION))
    failures += not _check("the shipped version is already seen",
                           not A.updates_unseen(A.APP_VERSION, A.APP_VERSION),
                           str(A.APP_VERSION))
    failures += not _check("an older version is unseen",
                           A.updates_unseen("1.0", A.APP_VERSION))
    failures += not _check("a version that will not parse is unseen",
                           A.updates_unseen("latest", A.APP_VERSION))
    failures += not _check("a v prefix still matches the running version",
                           not A.updates_unseen("v" + A.APP_VERSION,
                                                A.APP_VERSION))

    print()
    if failures:
        print(f"SELFTEST FAILED - {failures} check(s) did not pass")
        return 1
    print("SELFTEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
