"""Verify pause and the toast routing against a real Raze window.

Nothing reaches the desktop: the keystroke sender and the notification call
are both replaced with recorders, so the only thing ever produced is what the
real heartbeat and the real worker threads leave behind.
"""
import os
import sys

PROJ = r"C:\Users\nawaf\Documents\Default Project"
sys.path.insert(0, PROJ)
os.environ.setdefault("APPDATA", r"C:\Users\nawaf\AppData\Roaming")

import time

import customtkinter as ctk

import AutoTyper as A

A.reduce_motion_enabled = lambda: True

# the loop counter legitimately reads "Loop 3 ∞", and a cp1252 console
# cannot encode it - one raised print would break the callback chain and
# stall the whole harness
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

failures = []
typed = []          # what the worker believes it sent
toasts = []         # what _toast asked Windows to show
balloons = []       # what reached notify_balloon itself


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label,
                           " - " + str(detail) if detail else ""))
    if not ok:
        failures.append(label)


def main():
    # nothing may reach the keyboard, and nothing may reach the desktop
    A.send_enter = lambda: True
    A.notify_balloon = lambda *a, **k: False
    A.notify_clear = lambda *a, **k: True
    # the harness window is on-screen and does take focus, which is precisely
    # what the real guard is meant to refuse.  This harness is about pause and
    # the toast routing - the guard has its own coverage in selftest - so the
    # guard is answered here rather than exercised
    A.is_foreground = lambda handle: False

    def fake_type(text):
        typed.append(text)
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
        check("and that ending is announced too",
              len(toasts) == 1 and "switched back to Raze" in toasts[0][1],
              str(toasts))
        check("the status still explains the stop",
              app.status_text._text == "TAB OUT", app.status_text._text)

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
              app.session_loop._text == "Loop 3 \u221e",
              app.session_loop._text)
        app.loop_count = 5
        root.after(150, verify_finite)

    def verify_finite():
        check("a counted run reads current, total and how many are left",
              app.session_loop._text == "Loop 3 of 5 \u00b7 2 left",
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
        A.notify_balloon = lambda *a, **k: balloons.append(a) or True
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
              len(balloons) == 1 and balloons[0][1] == "Raze"
              and balloons[0][2] == "Finished - 1 message sent",
              str(balloons))
        check("and nothing is left waiting",
              app._pending_toast is None, str(app._pending_toast))

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
