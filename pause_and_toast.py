"""Verify pause and the toast routing against a real Raze window.

Nothing reaches the desktop: the keystroke sender and the notification call
are both replaced with recorders, so the only thing ever produced is what the
real heartbeat and the real worker threads leave behind.
"""
import os
import sys

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)
os.environ.setdefault("APPDATA",
                      os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))

import time

import customtkinter as ctk

import AutoTyper as A

A.reduce_motion_enabled = lambda: True

# a test must never put anything on the user's Discord profile
A.rpcmod.enabled = False

# the loop counter legitimately reads "Loop 3 ∞", and a cp1252 console
# cannot encode it - one raised print would break the callback chain and
# stall the whole harness
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

failures = []
typed = []          # what the worker believes it sent
stamps = []         # when it believes it sent it - the interval check reads these
toasts = []         # what _toast asked Windows to show
balloons = []       # what reached notify_toast itself


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label,
                           " - " + str(detail) if detail else ""))
    if not ok:
        failures.append(label)


def main():
    # nothing may reach the keyboard, and nothing may reach the desktop
    A.send_enter = lambda: True
    A.notify_toast = lambda *a, **k: False
    # the harness window is on-screen and does take focus, which is precisely
    # what the real guard is meant to refuse.  This harness is about pause and
    # the toast routing - the guard has its own coverage in selftest - so the
    # guard is answered here rather than exercised
    A.is_foreground = lambda handle: False

    def fake_type(text):
        typed.append(text)
        stamps.append(time.monotonic())
        return True

    A.register_fonts()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    ctk.set_widget_scaling(A.S)
    ctk.set_window_scaling(A.S)

    root = ctk.CTk()
    app = A.AutoTyper(root)
    root.attributes("-alpha", 0.0)

    app._type_text = fake_type
    app._toast = lambda body, title="Raze": toasts.append((title, body))
    # This harness shares the machine's real profile, and both the
    # heartbeat and a checkbox flip end in _save_config - config writing
    # has its own coverage in selftest, against a temp folder. Nothing here
    # may rewrite the file the real app keeps.
    app._save_config = lambda: None
    app.msg_interval = 0.15
    # ...but the interval field is whole seconds, and _start()/_save_config()
    # now flush it (_commit_fields), which would put the field's value back
    # through _set_msg_interval. Drop the callback: only msg_interval itself
    # is read by the run, and the harness needs it far below one second.
    app.nf_interval._on_change = None
    # the first run has to survive on its own: the real config may well say
    # loop 1, which would end the run long before the pause ever lands
    app.nf_loop.set(0, call_change=False)

    app.editor.delete("1.0", "end")
    app.editor.insert("1.0", "one\ntwo")

    # ---------------------------------------------------------------- #
    #  the session card has to be the whole card
    # ---------------------------------------------------------------- #
    # An orphaned block once dropped the card's body out of the build: the
    # four counters and the LAST SENT box were sitting unreachable after a
    # return in another method, and every other suite stayed green because
    # the heartbeat swallows the AttributeError that follows.  So the boxes
    # are asserted by name, here, where a missing one cannot hide.
    tiles = [getattr(app, n, None) for n in
             ("tile_sent", "tile_chars", "tile_time", "tile_next")]
    check("the session card carries its four counters",
          all(t is not None for t in tiles) and all(t.master is not None for t in tiles),
          [None if t is None else t.master for t in tiles])
    check("and the LAST SENT box",
          getattr(app, "last_label", None) is not None
          and app.last_label.master is not None,
          getattr(app, "last_label", None))
    check("and the loop counter beside the state",
          getattr(app, "session_loop", None) is not None
          and app.session_loop.master is not None,
          getattr(app, "session_loop", None))

    # ---------------------------------------------------------------- #
    #  pause: the clock and the counters have to survive the stop
    # ---------------------------------------------------------------- #
    def start():
        app._start()
        check("a run away from Raze is underway", app.typing is True, app.typing)
        check("nothing was paused at the start", app.paused is False, app.paused)
        root.after(700, pause_it)

    def pause_it():
        app._pause_requested = True     # exactly what the hotkey thread sets
        root.after(600, verify_paused)

    def verify_paused():
        frozen = app.stats["elapsed"]
        check("the heartbeat paused the run",
              app.paused is True and app.typing is True,
              str((app.paused, app.typing)))
        check("the status pill says so", app.status_text._text == "PAUSED",
              app.status_text._text)
        check("the session card says so",
              app.session_state._text == "Paused", app.session_state._text)
        check("the paused state is amber", app.session_state._color == A.AMBER,
              app.session_state._color)
        check("nothing was torn down", app._session_start is None,
              app._session_start)
        sent_before = app.stats["sent"]
        typed_before = len(typed)
        store = {"frozen": frozen, "sent": sent_before, "typed": typed_before}
        # let it sit: a pause that leaks messages is not a pause
        root.after(1200, lambda: verify_it_sits(store))

    def verify_it_sits(store):
        check("the clock is frozen exactly where it was left",
              app.stats["elapsed"] == store["frozen"],
              "%s vs %s" % (app.stats["elapsed"], store["frozen"]))
        check("no message escaped while paused",
              app.stats["sent"] == store["sent"] and len(typed) == store["typed"],
              "%s %s vs %s %s" % (app.stats["sent"], len(typed),
                                  store["sent"], store["typed"]))
        check("the counters were not thrown away",
              app.stats["sent"] > 0, app.stats["sent"])
        root.after(200, pause_again)

    def pause_again():
        app._pause_requested = True     # pause must not double as resume
        root.after(600, verify_still_paused)

    def verify_still_paused():
        check("the pause key cannot wake what it put to sleep",
              app.paused is True and app.typing is True,
              str((app.paused, app.typing)))
        check("and it leaves the frozen session alone",
              app._session_start is None, app._session_start)
        root.after(200, resume_it)

    def resume_it():
        app._resume_requested = True     # its own key, and only its own
        root.after(600, verify_resumed)

    def verify_resumed():
        check("the heartbeat resumed the run",
              app.paused is False and app.typing is True,
              str((app.paused, app.typing)))
        check("the session carries on instead of restarting",
              app._session_start is not None, app._session_start)
        check("back to typing", app.status_text._text == "TYPING",
              app.status_text._text)
        sent_at_resume = app.stats["sent"]
        root.after(900, lambda: verify_clock_runs_on(sent_at_resume))

    def verify_clock_runs_on(sent_at_resume):
        check("the clock runs again after a resume",
              app.stats["elapsed"] > 0, app.stats["elapsed"])
        check("messages are flowing again",
              app.stats["sent"] > sent_at_resume,
              "%s vs %s" % (app.stats["sent"], sent_at_resume))

        # start while paused has to do nothing: the keys are not aliases
        app._pause_requested = True
        root.after(500, start_while_paused)

    def start_while_paused():
        check("the run is paused before the start key",
              app.paused is True, app.paused)
        sent_before = app.stats["sent"]
        elapsed_before = app.stats["elapsed"]
        app._start()
        check("the start key does nothing to a paused run",
              app.paused is True and app.typing is True,
              str((app.paused, app.typing)))
        check("and it leaves the session exactly where it was",
              app.stats["sent"] == sent_before
              and app.stats["elapsed"] == elapsed_before,
              "%s/%s vs %s/%s" % (app.stats["sent"], sent_before,
                                  app.stats["elapsed"], elapsed_before))
        # only the resume key gets it moving again
        app._resume_requested = True
        root.after(700, manual_stop)

    def manual_stop():
        app._stop_requested = True       # F9
        root.after(600, verify_manual_stop)

    def verify_manual_stop():
        check("F9 stops the run", app.typing is False, app.typing)
        check("and clears the pause", app.paused is False, app.paused)
        check("a stop you asked for is silent", toasts == [], str(toasts))

        mid_run_settings()

    # ---------------------------------------------------------------- #
    #  settings changed while a run is under way
    # ---------------------------------------------------------------- #
    # The worker reads the interval, the selection mode, the pool and Loop
    # live, so every one of them is changed here under a session that is
    # already typing - each through the path a user would take, never by
    # touching the worker.  _save_config is a no-op above because the real
    # checkbox flip would otherwise carry a write of this machine's profile.
    def mid_run_settings():
        # back to a known session: ordered, the two lines, no loop limit
        app.random_box.deselect()
        app._toggle_random()
        app.editor.delete("1.0", "end")
        app.editor.insert("1.0", "one\ntwo")
        app._start()
        root.after(400, lengthen_pending)

    def lengthen_pending():
        # the next message opens a two second wait, so the shortening
        # below lands while that wait is still in flight - the one place a
        # setting snapshotted at start could never reach
        app._set_msg_interval(2.0)
        root.after(250, shorten_pending)

    def shorten_pending():
        changed = time.monotonic()
        app._set_msg_interval(0.1)
        root.after(700, lambda: verify_interval(changed))

    def verify_interval(changed):
        gap = next((s - changed for s in stamps if s > changed), None)
        check("an interval shortened inside its own wait fires at once",
              gap is not None and gap < 0.6, gap)
        check("and the run carried straight on", app.typing is True, app.typing)
        app._set_msg_interval(0.15)
        root.after(200, flip_random)

    def flip_random():
        real_randrange = A.random.randrange
        hits = []

        def rec(slot):
            hits.append(slot)
            return 0

        # the worker would take every pick from slot 0, so a message in
        # flight when the chooser swaps cannot be told from the rest
        A.random.randrange = rec
        app.random_box.select()
        app._toggle_random()            # exactly the command a click runs
        root.after(400, lambda: watch_random(real_randrange, hits))

    def watch_random(real_randrange, hits):
        # n0 is taken once everything already in flight has landed, so
        # only picks made with the new chooser are judged
        n0 = len(typed)
        root.after(500, lambda: verify_random(real_randrange, hits, n0))

    def verify_random(real_randrange, hits, n0):
        A.random.randrange = real_randrange
        taken = typed[n0:]
        check("the selection mode flips mid-run",
              app._random_pick is True, app._random_pick)
        check("and the worker picks from the pool with it",
              len(hits) > 0 and len(taken) > 0 and all(m == "one" for m in taken),
              "%s %s" % (hits, taken))
        app.random_box.deselect()
        app._toggle_random()
        check("and flips back again",
              app._random_pick is False, app._random_pick)
        root.after(100, edit_pool)

    def edit_pool():
        n0 = len(typed)
        # a keystroke's worth of edit - this is what the pool binding sees
        app.editor.insert("end", "\nthree")
        root.after(800, lambda: verify_pool(n0))

    def verify_pool(n0):
        taken = typed[n0:]
        check("a pool edited mid-run sends the new line",
              "three" in taken, taken)
        root.after(100, set_loop_mid_run)

    def set_loop_mid_run():
        app._set_loop(1)                # what the Loop field commits
        root.after(1500, verify_loop_end)

    def verify_loop_end():
        check("a loop count changed mid-run ends the run",
              app.typing is False, app.typing)
        check("and that ending is announced like any other finish",
              len(toasts) == 1 and toasts[0][1].startswith("Finished - "),
              str(toasts))
        # the next stage expects to count its own toast from zero
        del toasts[:]
        finish_run()

    # ---------------------------------------------------------------- #
    #  the two endings the user did not choose do get a toast
    # ---------------------------------------------------------------- #
    def finish_run():
        del typed[:]
        app.editor.delete("1.0", "end")
        app.editor.insert("1.0", "only one")
        app.nf_loop.set(1, call_change=False)
        app._start()
        root.after(1500, verify_finished)

    def verify_finished():
        check("a run that runs out of pool stops itself",
              app.typing is False, app.typing)
        check("the ending the user did not choose is announced",
              toasts == [("Raze", "Finished - 1 message sent")], str(toasts))

        tab_in()

    def tab_in():
        del toasts[:]
        # exactly what the worker leaves behind when Raze is tabbed into
        app.typing = True
        app._stop_requested = False
        app._start_requested = False
        app._tab_in_stop = True
        app._worker_done = True
        root.after(700, verify_tab_in)

    def verify_tab_in():
        check("tabbing back in stops the run",
              app.typing is False, app.typing)
        expected = ("Stopped - switch to your app first, then press %s "
                    "to continue" % app.resume_key.upper())
        check("and that ending is announced too",
              len(toasts) == 1 and toasts[0][1] == expected, str(toasts))
        check("the status still explains the stop",
              app.status_text._text == "TAB OUT", app.status_text._text)
        # the session is not thrown away - it is waiting for its own key
        check("the stop leaves the session there to be resumed",
              app._tab_stopped is True and app.session_state._text
              == "Switch to your app first",
              str((app._tab_stopped, app.session_state._text)))

        root.after(200, press_resume)

    # ---------------------------------------------------------------- #
    #  after a tab-in stop the resume key continues, the start key begins
    # ---------------------------------------------------------------- #
    def press_resume():
        # the pool is one line and the loop field still says 1 from the run
        # above - an endless loop keeps this run alive to be looked at
        app.loop_count = 0
        app.nf_loop.set(0, call_change=False)
        store = {"sent": app.stats["sent"],
                 "elapsed": app.stats["elapsed"]}
        app._resume_requested = True       # exactly what the hotkey thread sets
        root.after(800, lambda: verify_continued(store))

    def verify_continued(store):
        check("the resume key picks the stopped run back up",
              app.typing is True and app._tab_stopped is False,
              str((app.typing, app._tab_stopped)))
        check("and it carries the counters on instead of starting over",
              app.stats["sent"] > store["sent"]
              and app.stats["elapsed"] >= store["elapsed"],
              str((store, app.stats)))
        check("the session says so again",
              app.status_text._text == "TYPING"
              and app.session_state._text == "Typing",
              str((app.status_text._text, app.session_state._text)))
        # the announcement this key answered is not owed a second time
        expected = ("Stopped - switch to your app first, then press %s "
                    "to continue" % app.resume_key.upper())
        check("and the resume owes no announcement",
              toasts == [("Raze", expected)], str(toasts))

        root.after(100, tab_in_again)

    def tab_in_again():
        # the same thing the worker does, with the run genuinely under way
        store = {"sent": app.stats["sent"], "chars": app.stats["chars"]}
        app._stop_requested = False
        app._start_requested = False
        app._tab_in_stop = True
        app._worker_done = True
        root.after(700, lambda: verify_tab_in_again(store))

    def verify_tab_in_again(store):
        check("tabbing in again stops it a second time",
              app.typing is False and app._tab_stopped is True,
              str((app.typing, app._tab_stopped)))
        check("and the second stop keeps the counters too",
              app.stats["sent"] >= store["sent"] and app.stats["sent"] > 0
              and app.stats["chars"] >= store["chars"],
              str((store, app.stats)))

        root.after(200, press_start)

    def press_start():
        app._start_requested = True        # the other key, the one it names
        root.after(100, verify_fresh_start)

    def verify_fresh_start():
        # start does not continue anything: it is a new session, so the
        # counters are back at zero and the resumable state is gone
        check("the start key begins again from the top",
              app.typing is True and app.stats["sent"] == 0
              and app._tab_stopped is False,
              str((app.typing, app.stats, app._tab_stopped)))

        root.after(300, stop_it)

    def stop_it():
        del toasts[:]
        app._stop_requested = True         # F9, which the user chose
        root.after(400, verify_silent_stop)

    def verify_silent_stop():
        check("a stop of a session this way stays silent",
              app.typing is False and toasts == [],
              str((app.typing, toasts)))
        check("and leaves nothing behind to be resumed",
              app._tab_stopped is False, app._tab_stopped)

        root.after(200, loop_counter)

    # ---------------------------------------------------------------- #
    #  the loop counter on the session card
    # ---------------------------------------------------------------- #
    def loop_counter():
        check("the session card carries a loop counter",
              getattr(app, "session_loop", None) is not None,
              getattr(app, "session_loop", None))
        app.passes = 2
        app.loop_count = 0
        root.after(150, verify_infinite)

    def verify_infinite():
        check("an endless run reads the current loop and ∞",
              app.session_loop._text == "Loop 3 / \u221e",
              app.session_loop._text)
        app.loop_count = 5
        root.after(150, verify_finite)

    def verify_finite():
        check("a counted run reads current, total and how many are left",
              app.session_loop._text == "Loop 3 of 5 / 2 left",
              app.session_loop._text)
        # a run that has finished is clamped to its last loop rather than
        # counting one past the end
        app.loop_count = 1
        app.passes = 5
        root.after(150, verify_clamped)

    def verify_clamped():
        check("the counter never reads past the last loop",
              app.session_loop._text == "Loop 1 of 1",
              app.session_loop._text)
        app.passes = 0
        app.loop_count = 0
        root.after(150, held_toast)

    # ---------------------------------------------------------------- #
    #  a notification Windows refuses is held, then sent when it frees up
    # ---------------------------------------------------------------- #
    def held_toast():
        A.notify_toast = lambda *a, **k: balloons.append(a) or True
        # Windows answers the way it does while a full-screen game is up
        A.notifications_allowed = lambda: False
        del balloons[:]
        app._pending_toast = None
        app._toast_retry = 0.0
        # the routing tests above replaced _toast with a recorder; this one
        # is about the real thing, so it is called directly
        A.AutoTyper._toast(app, "Finished - 1 message sent")
        check("a screen Windows will not notify on holds the message",
              app._pending_toast == ("Raze", "Finished - 1 message sent")
              and balloons == [],
              str((app._pending_toast, balloons)))
        # the screen frees up, and the heartbeat is what sends it
        A.notifications_allowed = lambda: True
        app._toast_retry = 0.0
        root.after(300, verify_held_sent)

    def verify_held_sent():
        check("the held message goes out once the screen is free",
              len(balloons) == 1 and balloons[0][0] == "Raze"
              and balloons[0][1] == "Finished - 1 message sent",
              str(balloons))
        check("and nothing is left waiting",
              app._pending_toast is None, str(app._pending_toast))

        root.after(200, refused_fire)

    def refused_fire():
        # Windows can also refuse at the API itself rather than through the
        # state query; that has to hold the message too instead of dropping
        # an announcement on the floor
        A.notify_toast = lambda *a, **k: False
        app._pending_toast = None
        app._toast_retry = 0.0
        A.AutoTyper._fire_toast(app, "Raze", "Pool ran out")
        check("a refused send keeps the message waiting",
              app._pending_toast == ("Raze", "Pool ran out"),
              str(app._pending_toast))

        root.after(200, done)

    def done():
        try:
            root.destroy()
        except Exception:
            pass
        print("RESULT:", "PASS" if not failures else "FAIL " + str(failures))

    root.after(300, start)
    root.mainloop()


if __name__ == "__main__":
    main()
