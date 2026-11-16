"""Measure the four-keycap layout and capture the tabs.

Geometry is asserted rather than eyeballed, because a keycap that quietly
runs past its own frame is invisible in a screenshot until it is not.
"""
import os
import sys

PROJ = r"C:\Users\nawaf\Documents\Default Project"
sys.path.insert(0, PROJ)
os.environ.setdefault("APPDATA", r"C:\Users\nawaf\AppData\Roaming")

import customtkinter as ctk

import AutoTyper as A

import capture_window as cw

A.reduce_motion_enabled = lambda: True
# a test must never put anything on the user's Discord profile
A.rpcmod.enabled = False
failures = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label,
                           " - " + str(detail) if detail else ""))
    if not ok:
        failures.append(label)


def main():
    A.register_fonts()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    ctk.set_widget_scaling(A.S)
    ctk.set_window_scaling(A.S)

    root = ctk.CTk()
    app = A.AutoTyper(root)
    root.attributes("-alpha", 0.0)
    # Opening the Updates tab records seen_version through _save_config, and
    # the real config decides the badge at construction - neither may happen
    # in a test, so the save is stubbed here and the badge state is forced
    # in open_updates.
    app._save_config = lambda: None
    app._set_updates_dot(False)
    root.update_idletasks()

    def measure():
        # the whole point of the fit clamp: on a screen smaller than the
        # design, the app used to run off the bottom edge with no way to
        # reach the session card or the footer
        aw, ah = A._work_area()
        # the window's own frame (borders + title bar) sits outside the
        # client area, so it has to fit too
        need_w = root.winfo_width() + A.FRAME_W
        need_h = root.winfo_height() + A.FRAME_H
        check("the window fits the work area's width",
              0 < need_w <= aw, "%s in %s" % (need_w, aw))
        check("the window fits the work area's height",
              0 < need_h <= ah, "%s in %s" % (need_h, ah))
        check("the client area is the design at the clamped scale",
              abs(root.winfo_width() - A.px(A.WIN_W)) <= 2
              and abs(root.winfo_height() - A.px(A.WIN_H)) <= 2,
              "%sx%s vs %sx%s" % (root.winfo_width(), root.winfo_height(),
                                  A.px(A.WIN_W), A.px(A.WIN_H)))
        check("the scale is the clamped one, not the raw dpi scale",
              abs(A.S - A._fit_scale(A._device_scale(), aw, ah)) < 1e-9,
              "%s (dpi %s)" % (A.S, A._device_scale()))

        # the app's own clock lives on the status line, so it reads from
        # every tab - and its box is pinned from the longest string it can
        # ever print, which is what keeps a year of uptime away from both
        # the tabs on its left and the status dot on its right
        up = getattr(app, "uptime_text", None)
        if up is None:
            check("the uptime is on the status line", False, "missing")
        else:
            root.update_idletasks()
            ux0, ux1 = up.winfo_x(), up.winfo_x() + up.winfo_width()
            dot_x = app.status_dot.winfo_x()
            tabs_right = max(x1 for _item, _x0, x1
                             in app._tab_items.values()) * A.S
            check("the uptime is on the status line without crowding it",
                  up.winfo_ismapped() and up._text.startswith("UPTIME ")
                  and ux1 <= dot_x and ux0 >= tabs_right
                  and abs(up.winfo_y() - app.status_text.winfo_y()) <= 2,
                  "text %r box %s..%s dot %s tabs %s y %s/%s"
                  % (up._text, ux0, ux1, dot_x, tabs_right,
                     up.winfo_y(), app.status_text.winfo_y()))
            # a clock people read: muted grey, not the dim one that sits
            # under the contrast line at 10 px
            check("the uptime is the readable grey, not the dim one",
                  up._color == A.MUTED, up._color)

        # colour follows meaning: the loop counter is data like every other
        # number, so it is white - amber belongs to states (Paused, Tab out)
        # and two amber words side by side read as one phrase
        loop = getattr(app, "session_loop", None)
        check("the loop counter reads as data, not a warning",
              loop is not None and loop._color == A.TEXT,
              loop._color if loop is not None else "missing")

        print("keycaps (typer)")
        for attr, expect in (("key_cap_start", "F8"),
                             ("key_cap_pause", "F6"),
                             ("key_cap_resume", "F7"),
                             ("key_cap_stop", "F9")):
            label = getattr(app, attr, None)
            check("%s is present" % attr, label is not None, label)
            if label is None:
                continue
            check("%s reads %s" % (attr, expect), label._text == expect,
                  label._text)
            lw, cw_ = label.winfo_width(), label.master.winfo_width()
            check("%s fits its frame" % attr, 0 < lw <= cw_,
                  "text %s in frame %s" % (lw, cw_))

        # the artwork has to sit on the fill it is looking at: a hover that
        # lightened the pill used to leave the rest colour painted behind the
        # text, which read as a dark box around every button label
        buttons = []

        def collect(w):
            for child in w.winfo_children():
                if isinstance(child, A.BakedButton):
                    buttons.append(child)
                collect(child)

        collect(root)
        for b in buttons:
            b._on_enter()
        root.update_idletasks()
        mismatched = [(b.label._text, b.label.cget("bg"), b.cget("fg_color"))
                      for b in buttons
                      if str(b.label.cget("bg")) != str(b.cget("fg_color"))]
        check("every hovered button paints its label on the hover fill",
              bool(buttons) and not mismatched, str(mismatched))
        for b in buttons:
            b._on_leave()
        root.update_idletasks()
        back = [(b.label._text, b.label.cget("bg"), b.cget("fg_color"))
                for b in buttons
                if str(b.label.cget("bg")) != str(b.cget("fg_color"))]
        check("leaving a button puts its label back on the rest fill",
              not back, str(back))

        root.after(200, capture_typer)

    def capture_typer():
        hwnd = int(root.wm_frame(), 16)
        cw.capture(hwnd, r"C:\Users\nawaf\AppData\Local\Temp\opencode\typer.png")
        root.after(300, open_hotkeys)

    def open_hotkeys():
        app.show("hotkeys")
        root.after(400, measure_hotkeys)

    def measure_hotkeys():
        for attr, expect in (("hotkey_view_var", "f8"),
                             ("pausekey_view_var", "f6"),
                             ("resumekey_view_var", "f7"),
                             ("stopkey_view_var", "f9")):
            var = getattr(app, attr, None)
            check("%s holds %s" % (attr, expect),
                  var is not None and var.get() == expect,
                  var.get() if var else var)

        hwnd = int(root.wm_frame(), 16)
        cw.capture(hwnd, r"C:\Users\nawaf\AppData\Local\Temp\opencode\hotkeys.png")

        # the card grew again for the fourth row; it must still sit inside
        # the tab, and it must be tall enough to hold every row
        card = app._views["hotkeys"].winfo_children()[0]
        root.update_idletasks()
        top, bot = card.winfo_y(), card.winfo_y() + card.winfo_height()
        tab_h = app._views["hotkeys"].winfo_height()
        check("the hotkeys card fits its tab", 0 <= top and bot <= tab_h,
              "card %s..%s in tab %s" % (top, bot, tab_h))
        check("the fourth row made the card taller",
              card.winfo_height() >= A.px(340),
              "%s (need %s)" % (card.winfo_height(), A.px(340)))

        root.after(200, open_history)

    def open_history():
        app.show("history")
        root.after(400, measure_history)

    def measure_history():
        # the two personal bests, pinned between the header and the day
        # list - the strip is a fixed height, so it must not resize the card
        msgs = getattr(app, "tile_best_msgs", None)
        clock = getattr(app, "tile_best_time", None)
        check("the records tiles are on the history card",
              msgs is not None and clock is not None,
              "%s / %s" % (msgs, clock))
        # a forced record has to reach its tile through the same refresh
        # the stop path calls (_save_config is stubbed above, so the
        # forced values never leave this process)
        app.best_sitting_msgs = 42
        app.best_sitting_s = 3725
        app.best_sitting_msgs_day = "2026-11-16"
        app.best_sitting_s_day = "2026-11-15"
        app._refresh_records()
        root.update_idletasks()
        check("a stored record reaches its tile",
              msgs is not None and msgs.value._text == "42"
              and clock is not None
              and clock.value._text == A._elapsed_text(3725),
              "%r / %r" % (msgs.value._text if msgs else None,
                           clock.value._text if clock else None))
        check("the day each record was set reaches its tile",
              msgs is not None and msgs.date._text == "Nov 16, 2026"
              and clock is not None
              and clock.date._text == "Nov 15, 2026",
              "%r / %r" % (msgs.date._text if msgs else None,
                           clock.date._text if clock else None))

        hwnd = int(root.wm_frame(), 16)
        cw.capture(hwnd, r"C:\Users\nawaf\AppData\Local\Temp\opencode\history.png")

        root.after(200, open_updates)

    def open_updates():
        # the badge state is forced, never read: whatever the tester's own
        # config says is irrelevant, and the first visit is made to be the
        # one that clears it
        app.seen_version = "1.18"
        app._updates_unseen = True
        app._set_updates_dot(True)
        app.show("updates")
        root.after(400, measure_updates)

    def measure_updates():
        check("the updates tab is on the bar",
              "updates" in app._tab_items, str(sorted(app._tab_items)))
        view = app._views.get("updates")
        check("the updates view builds", view is not None,
              "missing" if view is None else "built")
        rows = getattr(app, "_updates_rows", [])
        head = rows[0][1]._text if rows else None
        check("the shipped version heads the list",
              head == A.APP_VERSION, str(head))
        root.update_idletasks()
        room = app.updates_list.winfo_height() if view is not None else 0
        bottom = max((r.winfo_y() + r.winfo_height()
                      for r, _tag, _body in rows), default=0)
        check("every update row sits inside the panel",
              bool(rows) and 0 < bottom <= room,
              "rows %s bottom %s room %s" % (len(rows), bottom, room))

        # --- the badge.  The first visit is the one that marks the new
        # version seen: the dot goes, the config is told (stubbed above),
        # and that visit alone carries the banner explaining the update.
        banner = getattr(app, "_updates_banner_row", None)
        check("the first visit clears the badge",
              not app._updates_unseen and app.seen_version == A.APP_VERSION
              and not app._updates_dot.winfo_ismapped(),
              "unseen %s seen %s dot mapped %s"
              % (app._updates_unseen, app.seen_version,
                 app._updates_dot.winfo_ismapped()))
        check("the first visit carries the update banner",
              app._updates_banner and banner is not None
              and banner[1]._text == "UPDATED"
              and banner[1]._color == A.BLUE
              and banner[2]._text.startswith("Raze updated to"),
              "flag %s tag %r colour %r body %r"
              % (app._updates_banner,
                 banner[1]._text if banner else None,
                 banner[1]._color if banner else None,
                 banner[2]._text if banner else None))
        check("the banner sits above the rows",
              banner is not None and bool(rows)
              and banner[0].winfo_y() < rows[0][0].winfo_y(),
              "banner %s row %s"
              % (banner[0].winfo_y() if banner else None,
                 rows[0][0].winfo_y() if rows else None))
        # one column for every body: the banner's tag is a word and the
        # rows' are versions, and a body that starts where its own tag
        # ends reads as a table with a broken column
        starts = set()
        if banner is not None:
            starts.add(banner[2].winfo_x())
        starts.update(b.winfo_x() for _r, _t, b in rows)
        check("every body in the list starts on one x",
              len(starts) == 1, str(sorted(starts)))

        # its own place on the bar: right of every tab, left of the uptime
        # box - the one gap on the status line with room for it
        app._set_updates_dot(True)
        root.update_idletasks()
        dot = app._updates_dot
        dx0 = dot.winfo_x()
        dx1 = dx0 + dot.winfo_width()
        tabs_right = max(x1 for _i, _x0, x1 in app._tab_items.values()) * A.S
        ux0 = app.uptime_text.winfo_x()
        check("the badge dot sits between the tabs and the uptime box",
              dot.winfo_ismapped() and dx0 >= tabs_right and dx1 <= ux0,
              "dot %s..%s tabs %s uptime %s"
              % (dx0, dx1, tabs_right, ux0))

        # the badge state worth an eye: banner on the panel, dot on the bar
        hwnd = int(root.wm_frame(), 16)
        cw.capture(hwnd, r"C:\Users\nawaf\AppData\Local\Temp\opencode\updates_badge.png")

        # coming back is an ordinary visit: nothing left to explain, and
        # the bar returns to how it looks the rest of the time
        app.show("updates")
        app._set_updates_dot(False)
        root.update_idletasks()
        check("a later visit carries no banner",
              not app._updates_banner and app._updates_banner_row is None,
              "flag %s row %s" % (app._updates_banner,
                                  app._updates_banner_row))
        cw.capture(hwnd, r"C:\Users\nawaf\AppData\Local\Temp\opencode\updates.png")

        root.after(200, done)

    def done():
        try:
            root.destroy()
        except Exception:
            pass
        print("RESULT:", "PASS" if not failures else "FAIL " + str(failures))

    root.after(600, measure)
    root.mainloop()


if __name__ == "__main__":
    main()
