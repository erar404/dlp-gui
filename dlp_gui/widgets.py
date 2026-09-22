"""Reusable Tkinter widgets and small style factories shared by every
tab — buttons, entries, the card/section layout used throughout
Settings, and the busy-state motion (pulse + activity bar) used
wherever a background task is running.
"""
import time
import tkinter as tk
from tkinter import ttk

from . import fonts
from .theme import (
    ACCENT, ACCENT_HOVER, ACCENT_INK, BG0, BG1, BG2, BG3, BG4, FG0, FG1, FG2,
)


def _ease_in_out(t):
    """Smoothstep — no bounce/overshoot, just a gentle accelerate then
    decelerate. Used for every hand-rolled animation in this module."""
    return t * t * (3 - 2 * t)


def _lerp_hex(c1, c2, t):
    def _to_rgb(c):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    r1, g1, b1 = _to_rgb(c1)
    r2, g2, b2 = _to_rgb(c2)
    return "#{:02x}{:02x}{:02x}".format(
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t),
    )


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


def entry(parent, default="", font=None, **kw):
    """A single-line text field with a hairline border that lights up
    amber on focus — no separate widget, Tk does this natively via
    highlightcolor once bd is 0."""
    e = tk.Entry(
        parent, bg=BG2, fg=FG0, insertbackground=FG0,
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=BG3, highlightcolor=ACCENT,
        font=font or fonts.body(), **kw,
    )
    if default:
        e.insert(0, default)
    return e


def combobox(parent, values, font=None):
    c = ttk.Combobox(
        parent, values=values, state="readonly", font=font or fonts.body())
    if values:
        c.current(0)
    return c


def checkbox(parent, text, font=None, bg=BG2):
    var = tk.BooleanVar()
    cb = tk.Checkbutton(
        parent, text=text, variable=var, bg=bg, fg=FG1,
        selectcolor=BG1, activebackground=bg, activeforeground=FG0,
        font=font or fonts.body(), anchor="w",
    )
    return cb, var


def spinbox(parent, lo, hi, default, width=5):
    s = tk.Spinbox(
        parent, from_=lo, to=hi, bg=BG2, fg=FG0,
        insertbackground=FG0, buttonbackground=BG3, relief="flat", bd=0,
        highlightthickness=1, highlightbackground=BG3, highlightcolor=ACCENT,
        font=fonts.body(), width=width)
    s.delete(0, "end")
    s.insert(0, str(default))
    return s


def field_label(parent, text, font=None, bg=BG2):
    return tk.Label(
        parent, text=text, bg=bg, fg=FG1, font=font or fonts.body())


def status_label(parent, bg=BG2):
    """A quiet, wrapping status line under a field or button."""
    lbl = tk.Label(
        parent, text="", bg=bg, fg=FG2, font=fonts.small(), anchor="w",
        justify="left")
    lbl.bind(
        "<Configure>",
        lambda e, w=lbl: w.configure(wraplength=max(1, e.width - 4)))
    return lbl


# ── Buttons ──────────────────────────────────────────────────────────────
# Three weights, used consistently everywhere: primary (the one thing
# to do on this screen), secondary (a clear, deliberate action) and
# ghost (a low-emphasis or destructive/utility action).

def primary_button(parent, text, command, font=None):
    btn = tk.Button(
        parent, text=text, bg=ACCENT, fg=ACCENT_INK, relief="flat", bd=0,
        cursor="hand2", font=font or fonts.button(), command=command,
        activebackground=ACCENT_HOVER, activeforeground=ACCENT_INK,
        highlightthickness=0)
    return btn


def secondary_button(parent, text, command, font=None):
    return tk.Button(
        parent, text=text, bg=BG2, fg=FG0, relief="flat", bd=0,
        cursor="hand2", font=font or fonts.body(), command=command,
        highlightthickness=1, highlightbackground=BG3,
        activebackground=BG3, activeforeground=FG0)


def ghost_button(parent, text, command, fg=FG1, font=None):
    return tk.Button(
        parent, text=text, bg=BG0, fg=fg, relief="flat", bd=0,
        cursor="hand2", font=font or fonts.small(), command=command,
        highlightthickness=1, highlightbackground=BG2,
        activebackground=BG2, activeforeground=FG0)


# ── Settings layout: category headers + cards ───────────────────────────

def category_header(parent, title):
    """A section divider grouping several cards under one heading —
    e.g. 'Setup' over Dependencies + Audio Tools. Real navigational
    structure (the settings list is long), not decoration."""
    wrap = tk.Frame(parent, bg=BG0)
    wrap.pack(fill="x", padx=14, pady=(20, 6))
    tk.Label(
        wrap, text=title, bg=BG0, fg=FG0, font=fonts.category(),
    ).pack(side="left")
    rule = tk.Frame(wrap, bg=BG3, height=1)
    rule.pack(side="left", fill="x", expand=True, padx=(10, 0))
    return wrap


class Card:
    """A flat, hairline-bordered panel with a title + one-line
    description, used for every settings group. Deliberately square
    (no faked rounded corners) — reads as an equipment-panel module
    rather than the generic soft-shadow SaaS card."""

    def __init__(self, parent, title, description=None, mark="›"):
        self.frame = tk.Frame(
            parent, bg=BG2, highlightthickness=1, highlightbackground=BG3)
        self.frame.pack(fill="x", padx=14, pady=(0, 10))
        self.frame.columnconfigure(0, weight=1)

        head = tk.Frame(self.frame, bg=BG2)
        head.grid(row=0, column=0, sticky="EW", padx=14, pady=(12, 8))
        head.columnconfigure(1, weight=1)

        tk.Label(
            head, text=mark, bg=BG2, fg=ACCENT, font=fonts.section(),
        ).grid(row=0, column=0, rowspan=2 if description else 1,
               sticky="NW", padx=(0, 8))
        tk.Label(
            head, text=title, bg=BG2, fg=FG0, font=fonts.section(),
        ).grid(row=0, column=1, sticky="W")
        if description:
            desc = tk.Label(
                head, text=description, bg=BG2, fg=FG2, font=fonts.small(),
                justify="left", anchor="w")
            desc.grid(row=1, column=1, sticky="EW", pady=(2, 0))
            desc.bind(
                "<Configure>",
                lambda e, w=desc: w.configure(
                    wraplength=max(1, e.width - 4)))

        tk.Frame(self.frame, bg=BG3, height=1).grid(
            row=1, column=0, sticky="EW")

        self.body = tk.Frame(self.frame, bg=BG2)
        self.body.grid(row=2, column=0, sticky="EW", padx=14, pady=(10, 14))
        self.body.columnconfigure(0, weight=1)


# ── Busy-state motion ────────────────────────────────────────────────────
# One consistent language for "a background task is running", used at
# every download/install/update site on both pages: the triggering
# button breathes between its resting and a lifted tone, and a hairline
# activity bar beneath it sweeps — a track that's otherwise invisible,
# so it costs no layout space in the idle state it spends most of its
# life in.

# (base, peak) breathing tones per button weight — secondary/ghost
# buttons don't own the accent color, so they breathe within their own
# neutral surface instead of borrowing amber.
PULSE_TONES = {
    "primary": (ACCENT, ACCENT_HOVER),
    "secondary": (BG2, BG4),
}


def start_pulse(widget, weight="secondary", period_ms=1100):
    """Start a slow, eased breathing animation on a button's
    background — the visual signature of "this triggered a running
    task". Idempotent; safe to call again while already running."""
    if getattr(widget, "_pulsing", False):
        return
    base, peak = PULSE_TONES[weight]
    widget._pulsing = True
    widget._pulse_t0 = time.monotonic()

    def tick():
        if not getattr(widget, "_pulsing", False):
            return
        try:
            if not widget.winfo_exists():
                return
            elapsed = (time.monotonic() - widget._pulse_t0) * 1000
            phase = (elapsed % period_ms) / period_ms
            triangle = phase * 2 if phase < 0.5 else 2 - phase * 2
            widget.config(bg=_lerp_hex(base, peak, _ease_in_out(triangle)))
        except tk.TclError:
            return
        widget._pulse_after = widget.after(33, tick)

    tick()


def stop_pulse(widget, restore):
    """Stop the breathing animation and restore the button's resting
    color (its normal base/ACCENT/BG2 — whatever it should idle at)."""
    widget._pulsing = False
    after_id = getattr(widget, "_pulse_after", None)
    if after_id is not None:
        try:
            widget.after_cancel(after_id)
        except Exception:
            pass
    try:
        if widget.winfo_exists():
            widget.config(bg=restore)
    except tk.TclError:
        pass


class ActivityBar(tk.Canvas):
    """A hairline indeterminate progress sweep. Always occupies its
    layout slot (so starting/stopping it never reflows the page) but
    is only visible while running — the track color matches its
    parent, so at rest it's simply blank space."""

    HEIGHT = 3
    PERIOD_MS = 1100

    def __init__(self, parent, bg=BG2):
        super().__init__(
            parent, height=self.HEIGHT, bg=bg, highlightthickness=0, bd=0)
        self._seg = self.create_rectangle(0, 0, 0, 0, width=0, fill=ACCENT)
        self._running = False
        self._after_id = None
        self._t0 = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def _phase(self):
        elapsed = (time.monotonic() - self._t0) * 1000
        return (elapsed % self.PERIOD_MS) / self.PERIOD_MS

    def _draw(self):
        w = self.winfo_width()
        if not self._running or w <= 1:
            self.coords(self._seg, 0, 0, 0, 0)
            return
        eased = _ease_in_out(self._phase())
        seg_w = max(28, w * 0.3)
        x = eased * (w + seg_w) - seg_w
        self.coords(self._seg, max(0, x), 0, min(w, x + seg_w), self.HEIGHT)

    def start(self):
        if self._running:
            return
        self._running = True
        self._t0 = time.monotonic()
        self._tick()

    def stop(self):
        self._running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            if self.winfo_exists():
                self.coords(self._seg, 0, 0, 0, 0)
        except tk.TclError:
            pass

    def _tick(self):
        if not self._running:
            return
        try:
            if not self.winfo_exists():
                self._running = False
                return
            self._draw()
        except tk.TclError:
            self._running = False
            return
        self._after_id = self.after(16, self._tick)
