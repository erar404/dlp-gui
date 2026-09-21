"""Reusable Tkinter widgets."""
import tkinter as tk

from .theme import FG0, FG2


class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder="", **kw):
        self._ph = placeholder
        self._real_fg = kw.pop("fg", FG0)
        super().__init__(
            parent, fg=FG2 if placeholder else self._real_fg, **kw
        )
        if placeholder:
            self.insert(0, placeholder)
            self.bind("<FocusIn>", self._in)
            self.bind("<FocusOut>", self._out)

    def _in(self, _):
        if self.get() == self._ph:
            self.delete(0, "end")
            self.config(fg=self._real_fg)

    def _out(self, _):
        if not self.get():
            self.insert(0, self._ph)
            self.config(fg=FG2)

    def value(self):
        v = self.get()
        return "" if v == self._ph else v
