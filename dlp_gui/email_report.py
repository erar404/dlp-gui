"""Emails an error report to the developer via SMTP.

Credentials come from the local, gitignored dlp-ui-config.json (set
via Settings -> Error Reporting) — never hardcoded here, so they're
never committed to source control or shipped in the app.
"""
import platform
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from .constants import VERSION
from .paths import load_config

# Keep the email body (and any email client rendering it) sane even
# if the user's Output Log is huge.
MAX_LOG_CHARS = 20_000


def smtp_config_ready() -> bool:
    cfg = load_config()
    return bool(
        cfg.get("smtp_host") and cfg.get("smtp_user")
        and cfg.get("smtp_password") and cfg.get("developer_email")
    )


def send_error_report(context: dict, log_text: str, note: str = "") -> None:
    """Send an error report email. Raises on any failure (unconfigured
    SMTP, auth failure, network error, ...) — callers show that to the
    user rather than failing silently."""
    cfg = load_config()
    host = (cfg.get("smtp_host") or "").strip()
    user = (cfg.get("smtp_user") or "").strip()
    password = cfg.get("smtp_password") or ""
    to_addr = (cfg.get("developer_email") or "").strip()
    try:
        port = int(cfg.get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587

    if not (host and user and password and to_addr):
        raise RuntimeError(
            "SMTP isn't set up yet — configure it in Settings → Error "
            "Reporting first.")

    if len(log_text) > MAX_LOG_CHARS:
        log_text = (
            f"...[truncated — showing the last {MAX_LOG_CHARS:,} "
            f"characters]...\n" + log_text[-MAX_LOG_CHARS:]
        )

    subject_bit = context.get("url") or "download"
    msg = EmailMessage()
    msg["Subject"] = f"DLP-UI error report — {subject_bit}"
    msg["From"] = user
    msg["To"] = to_addr

    lines = [
        f"DLP-UI v{VERSION} error report",
        f"Sent: {datetime.now().isoformat(timespec='seconds')}",
        f"Platform: {platform.platform()}",
        "",
    ]
    for key, label in (
        ("url", "URL"),
        ("format", "Format"),
        ("quality", "Quality"),
        ("destination", "Destination"),
        ("exit_code", "Exit code"),
    ):
        value = context.get(key)
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    if note.strip():
        lines.append("")
        lines.append("Note from user:")
        lines.append(note.strip())
    lines.append("")
    lines.append("--- Output log ---")
    lines.append(log_text or "(empty)")
    msg.set_content("\n".join(lines))

    tls_context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls(context=tls_context)
        server.login(user, password)
        server.send_message(msg)
