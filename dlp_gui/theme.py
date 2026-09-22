"""Design tokens shared across every widget in the app.

Palette concept: a dark equipment-panel look — cool graphite surfaces
with a single warm amber accent, the kind of warmth you'd find on a
tape deck's VU meter or a mixing console's gain knob. This app is
fundamentally about recording/mixing/downloading media, so the accent
leans into that rather than a generic SaaS blue or a "danger" red.
"""

# ── Surfaces ─────────────────────────────────────────────────────────────
BG0 = "#15171c"   # app background
BG1 = "#1b1e24"   # recessed panels: log console, tab track
BG2 = "#20242b"   # input fields, cards
BG3 = "#2c313b"   # borders, dividers
BG4 = "#3a4049"   # stronger borders, hover surfaces

# ── Text ─────────────────────────────────────────────────────────────────
FG0 = "#f1efe9"   # primary text (warm off-white, not stark #fff)
FG1 = "#a3a8b3"   # field labels, secondary text
FG2 = "#6c7280"   # helper / muted text
FG3 = "#454b56"   # placeholder, disabled

# ── Accent ───────────────────────────────────────────────────────────────
ACCENT = "#e2a13d"        # primary actions, focus rings, "needs attention"
ACCENT_HOVER = "#efb156"
ACCENT_INK = "#211703"    # text drawn on top of an accent fill

RED = "#e2585d"           # stop / destructive only
BLUE = "#5b9bd6"          # informational (kept distinct from the accent)

# ── Log console ──────────────────────────────────────────────────────────
LOG_GREEN = "#7bdb9e"
LOG_RED = "#f2726f"
LOG_GRAY = "#b7bcc6"
LOG_OK = "#63cf8a"
LOG_FAIL = "#ee6a67"
LOG_WARN = ACCENT
