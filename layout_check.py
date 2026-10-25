"""Measure the four-keycap layout and capture both tabs.

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
