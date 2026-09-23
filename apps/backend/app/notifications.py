import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .models import Camera, Violation

logger = logging.getLogger("smart_cctv_ai.notifications")
logging.basicConfig(level=logging.INFO)

# SMTP is intentionally just a plain, swappable set of env vars — see
# ADR-0014. Whatever mail relay Pertamina EP ends up pointing this at
# (their own Outlook/M365 tenant included) works as long as it accepts
# normal SMTP submission on these settings; nothing in this file assumes
# Mailpit specifically. If a given tenant has legacy SMTP AUTH disabled
# and requires OAuth2 (Microsoft Graph API) instead, that would need a
# separate sender implementation — deliberately not built ahead of time
# since which relay/auth mode the company will actually use isn't known
# yet.
SMTP_HOST = os.getenv("SMTP_HOST", "mailpit")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
NOTIFY_EMAIL_FROM = os.getenv("NOTIFY_EMAIL_FROM", "smart-cctv-ai@pertamina-ep.local")
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO", "hse-team@pertamina-ep.local")


def _send_email(subject: str, body: str, to: str | None = None,
                 attachments: list[tuple[str, bytes, str]] | None = None) -> None:
    """Points at Mailpit (a local SMTP catcher with a web UI) for this demo
    deploy since no real corporate SMTP credentials were provided — swap the
    SMTP_* env vars to point at the real mail server and nothing else in
    this function needs to change. `attachments`, when given, is a list of
    `(filename, bytes, mime_type)` — the snapshot JPEG on a Direct Notify
    alert (ADR-0014's "bukti gambarnya"), or the PDF report on a Recurring
    Report (ADR-0015)."""
    recipient = to or NOTIFY_EMAIL_TO
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        for filename, data, mime_type in attachments:
            maintype, _, subtype = mime_type.partition("/")
            part = MIMEImage(data, _subtype=subtype, name=filename) if maintype == "image" \
                else MIMEApplication(data, _subtype=subtype, name=filename)
            part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = NOTIFY_EMAIL_FROM
    msg["To"] = recipient

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(NOTIFY_EMAIL_FROM, [recipient], msg.as_string())
        logger.info("EMAIL sent -> %s : %s", recipient, subject)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("failed to send email notification: %s", exc)


def send_notification(violation: Violation, camera: Camera, snapshot_bytes: bytes | None = None) -> None:
    """The initial alert — "Direct Notify" (ADR-0014): sent the moment a
    violation is ingested, straight to the HSSE channel (NOTIFY_EMAIL_TO),
    complete with time, location and — when the inference worker captured
    one — the photo evidence itself as an attachment. There's no per-role
    email directory in this deploy, so "the Operator inbox" and "the
    Supervisor inbox" are both, today, just NOTIFY_EMAIL_TO — see
    ADR-0011."""
    subject = f"[Smart CCTV AI][{violation.severity.upper()}] {violation.label} — {camera.name}"
    body = (
        f"Pelanggaran terdeteksi.\n\n"
        f"Jenis        : {violation.label} ({violation.category})\n"
        f"Kamera       : {camera.name} ({camera.ip_address})\n"
        f"Lokasi       : {camera.location or '-'}\n"
        f"Severity     : {violation.severity.value}\n"
        f"Waktu        : {violation.created_at}\n"
        f"Bukti gambar : {'terlampir' if snapshot_bytes else 'tidak tersedia'}\n"
        f"\n-- Smart CCTV AI, Pertamina EP"
    )
    attachments = [(f"violation-{violation.id}.jpg", snapshot_bytes, "image/jpeg")] if snapshot_bytes else None
    _send_email(subject, body, attachments=attachments)


def send_escalation(violation: Violation, camera: Camera, escalate_role: str, after_minutes: int) -> None:
    """Fired by `_periodic_escalation_check` in main.py when a violation
    has sat in 'baru' longer than its category's configured
    `escalate_after_minutes` (Pengaturan > Aturan Notifikasi). Real, sent
    for real — but routed to the same NOTIFY_EMAIL_TO as the initial
    alert, since there is no real per-role distribution list configured
    yet; the subject/body make the intended audience explicit so this is
    an honest gap, not a silently fake feature."""
    subject = f"[Smart CCTV AI][ESKALASI ke {escalate_role.upper()}] {violation.label} — {camera.name}"
    body = (
        f"Kasus belum ditindak dalam {after_minutes} menit, dieskalasi ke role {escalate_role}.\n\n"
        f"Case         : #{violation.id}\n"
        f"Jenis        : {violation.label} ({violation.category})\n"
        f"Kamera       : {camera.name} ({camera.ip_address})\n"
        f"Lokasi       : {camera.location or '-'}\n"
        f"Terdeteksi   : {violation.created_at}\n"
        f"\n-- Smart CCTV AI, Pertamina EP"
    )
    _send_email(subject, body)


def send_recurring_report(summary, frequency_days: int, recipient: str | None = None,
                           pdf_bytes: bytes | None = None) -> None:
    """"Recurring Report" (ADR-0014): a periodic HSSE summary sent
    automatically — no one has to compile it by hand. `summary` is a
    `schemas.ReportSummaryOut` (or matching object) as returned by
    `_compute_report_summary` in main.py, so the numbers here always match
    what Laporan & Analitik / the Executive Dashboard show. The email body
    stays plain text (readable in any client, no rendering surprises);
    `pdf_bytes` — the same branded Executive Report `build_report_pdf`
    produces (ADR-0015) — is attached alongside it so the recipient gets
    the chart/table version too, not just a wall of text."""
    period_label = f"{summary.start} s/d {summary.end}" if summary.start != summary.end else summary.start
    lines = [
        f"Laporan HSSE Otomatis — Smart CCTV AI ({period_label})",
        "=" * 56,
        "",
        "RINGKASAN PELANGGARAN",
        f"  Total pelanggaran        : {summary.total}",
        f"  - APD                    : {summary.apd_total}",
        f"  - Vehicle                : {summary.vehicle_total}",
        f"  Rata-rata per hari       : {summary.avg_per_day}",
        "",
        "PENANGANAN KASUS",
        f"  Dijadikan kasus          : {summary.case_total}",
        f"  Kasus selesai            : {summary.completed_count} "
        f"({summary.completion_rate:.0%})",
        f"  Rata-rata waktu respons  : "
        f"{summary.avg_response_minutes:.1f} menit" if summary.avg_response_minutes is not None
        else "  Rata-rata waktu respons  : -",
        "",
        "AREA DENGAN PELANGGARAN TERBANYAK",
    ]
    for cam in summary.by_camera[:5]:
        lines.append(f"  {cam.camera_name} ({cam.location or '-'}) — {cam.count} pelanggaran")
    lines += [
        "",
        f"Laporan ini dikirim otomatis setiap {frequency_days} hari.",
        "-- Smart CCTV AI, Pertamina EP",
    ]
    subject = f"[Smart CCTV AI] Laporan HSSE Berkala — {period_label}"
    attachments = [("laporan-hsse-berkala.pdf", pdf_bytes, "application/pdf")] if pdf_bytes else None
    _send_email(subject, "\n".join(lines), to=recipient, attachments=attachments)
