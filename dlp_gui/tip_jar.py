"""The post-download tip-jar popup."""
import random
import tkinter as tk

from . import fonts, widgets
from .constants import TIP_NOTES
from .paths import BASE, QRCODE_IMAGE
from .theme import BG0, FG0, FG1


class TipJarMixin:
    """Adds `_show_tip_prompt` to the main App window."""

    def _show_tip_prompt(self):
        win = tk.Toplevel(self)
        win.title("Enjoying DLP-UI?")
        win.configure(bg=BG0)
        win.resizable(False, False)
        try:
            win.iconbitmap(str(BASE / "favicon.ico"))
        except Exception:
            pass

        tk.Label(
            win, text=random.choice(TIP_NOTES), bg=BG0, fg=FG0,
            font=fonts.body(10), wraplength=360, justify="left",
        ).pack(padx=20, pady=(20, 12))

        try:
            qr_img = tk.PhotoImage(file=str(QRCODE_IMAGE))
            win._qr_img_ref = qr_img  # keep a reference alive
            tk.Label(win, image=qr_img, bg=BG0).pack(padx=20, pady=(0, 8))
            tk.Label(
                win, text="Scan to send a tip — thank you! 💙", bg=BG0,
                fg=FG1, font=fonts.small(),
            ).pack(padx=20, pady=(0, 12))
        except Exception:
            pass

        widgets.secondary_button(
            win, "You're welcome", win.destroy,
        ).pack(pady=(0, 18), ipadx=16, ipady=5)

        win.transient(self)
        win.update_idletasks()
        x = (self.winfo_rootx()
             + (self.winfo_width() - win.winfo_width()) // 2)
        y = (self.winfo_rooty()
             + (self.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
