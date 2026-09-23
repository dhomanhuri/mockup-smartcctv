"""Comprehensive PDF report builder — see ADR-0015.

Replaces the earlier plain-CSV export (ADR-0014): a CSV has no branding,
no charts, and can't carry the "bukti gambar" (photo evidence) that
makes an HSSE report actually useful to a manager. This builds a real,
letterhead-branded PDF with the same numbers `_compute_report_summary`
feeds the Dashboard/Reports pages, a trend chart, and — for the
"detail" kind — a full violation table plus an embedded photo-evidence
gallery.

Kept dependency-light on purpose: reportlab + Pillow are pure-Python/
wheel-only (no apt-get native libs needed in the slim Python image,
unlike e.g. WeasyPrint), which matters for a container that otherwise
only needs `pip install`.
"""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from . import storage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATH = ASSETS_DIR / "pertamina-ep-logo.jpg"

# Embed a real TTF rather than reportlab's default (non-embedded)
# Helvetica: the base-14 PDF fonts aren't shipped in the file itself, so
# a viewer without good Helvetica metrics installed (common on a bare
# container/CI renderer) substitutes its own font and can visibly
# mis-space text. DejaVu Sans ships in Debian's fonts-dejavu-core
# (installed in the backend Dockerfile) and renders identically
# everywhere since it's embedded. See ADR-0015.
_DEJAVU_DIR = Path("/usr/share/fonts/truetype/dejavu")
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(_DEJAVU_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_DEJAVU_DIR / "DejaVuSans-Bold.ttf")))
except Exception:
    # Falls back to registering the DejaVuSans/-Bold names as aliases for
    # reportlab's built-in Helvetica metrics if the TTFs aren't present
    # (e.g. running this module outside the container) — degraded
    # spacing risk returns, but the module still imports and every
    # fontName="DejaVuSans*" reference below still resolves.
    pdfmetrics.registerFont(pdfmetrics.Font("DejaVuSans", "Helvetica", "WinAnsiEncoding"))
    pdfmetrics.registerFont(pdfmetrics.Font("DejaVuSans-Bold", "Helvetica-Bold", "WinAnsiEncoding"))

# Same tokens as apps/frontend/styles.css — one palette, PDF included.
INK = colors.HexColor("#171A1D")
MUTED = colors.HexColor("#61686F")
BORDER = colors.HexColor("#DEE2E6")
SURFACE_2 = colors.HexColor("#EEF0F2")
WARNING = colors.HexColor("#C4841F")  # APD
CRITICAL = colors.HexColor("#A3001A")  # Vehicle
BRAND_RED = colors.HexColor("#E4032E")
BRAND_BLUE = colors.HexColor("#0067B1")
BRAND_GREEN = colors.HexColor("#8DC63F")

CATEGORY_COLOR = {"apd": WARNING, "vehicle": CRITICAL}
CATEGORY_LABEL = {"apd": "APD Detection", "vehicle": "Vehicle Violation"}
MAX_EVIDENCE_PHOTOS = 30  # keeps a full-month detail report's page count sane

_styles = getSampleStyleSheet()
STYLE_TITLE = ParagraphStyle("VGTitle", parent=_styles["Title"], fontName="DejaVuSans-Bold",
                              fontSize=18, textColor=INK, spaceAfter=2)
STYLE_SUBTITLE = ParagraphStyle("VGSubtitle", parent=_styles["Normal"], fontName="DejaVuSans",
                                 fontSize=10, textColor=MUTED, spaceAfter=0)
STYLE_SECTION = ParagraphStyle("VGSection", parent=_styles["Heading2"], fontName="DejaVuSans-Bold",
                                fontSize=12.5, textColor=INK, spaceBefore=14, spaceAfter=6)
STYLE_BODY = ParagraphStyle("VGBody", parent=_styles["Normal"], fontName="DejaVuSans",
                             fontSize=8.5, textColor=INK, leading=11)
STYLE_MUTED = ParagraphStyle("VGMuted", parent=_styles["Normal"], fontName="DejaVuSans",
                              fontSize=8, textColor=MUTED, leading=11)
STYLE_CAPTION = ParagraphStyle("VGCaption", parent=_styles["Normal"], fontName="DejaVuSans",
                                fontSize=7.5, textColor=MUTED, alignment=TA_CENTER, leading=10)
STYLE_TABLE_HEAD = ParagraphStyle("VGTableHead", parent=_styles["Normal"], fontName="DejaVuSans-Bold",
                                   fontSize=7.5, textColor=MUTED)
STYLE_TABLE_CELL = ParagraphStyle("VGTableCell", parent=_styles["Normal"], fontName="DejaVuSans",
                                   fontSize=7.5, textColor=INK, leading=9.5)


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "-"
    return dt.strftime("%d %b %Y, %H:%M")


def _fmt_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d %b %Y")


def _fmt_date_range(start_iso: str, end_iso: str) -> str:
    return f"{_fmt_date(start_iso)} – {_fmt_date(end_iso)}"


def _header_footer(kind_label: str, period_label: str):
    def _draw(canvas, doc):
        canvas.saveState()
        page_w, page_h = A4
        # Top brand strip — same 3-color gradient feel as the app header.
        canvas.setFillColor(BRAND_RED)
        canvas.rect(0, page_h - 4, page_w / 3, 4, stroke=0, fill=1)
        canvas.setFillColor(BRAND_BLUE)
        canvas.rect(page_w / 3, page_h - 4, page_w / 3, 4, stroke=0, fill=1)
        canvas.setFillColor(BRAND_GREEN)
        canvas.rect(2 * page_w / 3, page_h - 4, page_w / 3, 4, stroke=0, fill=1)
        # Footer
        canvas.setFont("DejaVuSans", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Smart CCTV AI — Pertamina EP · {kind_label} · {period_label}")
        canvas.drawRightString(page_w - 18 * mm, 10 * mm, f"Halaman {doc.page}")
        canvas.setStrokeColor(BORDER)
        canvas.line(18 * mm, 13 * mm, page_w - 18 * mm, 13 * mm)
        canvas.restoreState()
    return _draw


def _letterhead(title: str, subtitle: str) -> list:
    elements = []
    logo_cell = ""
    if LOGO_PATH.is_file():
        logo_cell = Image(str(LOGO_PATH), width=15 * mm, height=15 * mm)
    title_cell = [Paragraph(title, STYLE_TITLE), Paragraph(subtitle, STYLE_SUBTITLE)]
    head_table = Table([[logo_cell, title_cell]], colWidths=[20 * mm, None])
    head_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(head_table)
    elements.append(Spacer(1, 4 * mm))
    line_table = Table([[""]], colWidths=[170 * mm], rowHeights=[1])
    line_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, INK)]))
    elements.append(line_table)
    elements.append(Spacer(1, 4 * mm))
    return elements


def _kpi_table(summary) -> Table:
    rows = [
        ["Total Pelanggaran", str(summary.total), "Dijadikan Kasus", str(summary.case_total)],
        ["Pelanggaran APD", str(summary.apd_total), "Kasus Selesai",
         f"{summary.completed_count} ({summary.completion_rate:.0%})"],
        ["Pelanggaran Vehicle", str(summary.vehicle_total), "Rata-rata Waktu Respons",
         f"{summary.avg_response_minutes:.1f} menit" if summary.avg_response_minutes is not None else "-"],
        ["Rata-rata / Hari", str(summary.avg_per_day), "", ""],
    ]
    data = [[Paragraph(str(c), STYLE_TABLE_HEAD if i % 2 == 0 else STYLE_BODY) for i, c in enumerate(row)]
            for row in rows]
    t = Table(data, colWidths=[42 * mm, 30 * mm, 55 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE_2),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _trend_chart(summary) -> Drawing:
    daily = summary.daily or []
    dates = [d.date for d in daily]
    apd_vals = [d.apd for d in daily]
    veh_vals = [d.vehicle for d in daily]
    max_val = max([1] + apd_vals + veh_vals)

    drawing = Drawing(170 * mm, 65 * mm)
    chart = VerticalBarChart()
    chart.x = 15 * mm
    chart.y = 12 * mm
    chart.width = 145 * mm
    chart.height = 45 * mm
    chart.data = [apd_vals, veh_vals]
    # A date range (ADR-0017) can be anywhere from 1 to 31 days — a
    # day-of-week label stops being useful (and starts overlapping) past
    # ~10 bars, so this shows the day-of-month instead, thinning them out
    # (every 2nd/3rd/5th) as the range grows so labels never collide.
    stride = 1 if len(dates) <= 10 else (2 if len(dates) <= 16 else (3 if len(dates) <= 24 else 5))
    chart.categoryAxis.categoryNames = [
        date.fromisoformat(d).strftime("%d") if i % stride == 0 else ""
        for i, d in enumerate(dates)
    ]
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(5, ((max_val // 5) + 1) * 5)
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.bars[0].fillColor = WARNING
    chart.bars[1].fillColor = CRITICAL
    chart.barSpacing = 2
    chart.groupSpacing = 10
    drawing.add(chart)

    legend = Legend()
    legend.x = 15 * mm
    legend.y = 60 * mm
    legend.dx = 8
    legend.dy = 8
    legend.fontSize = 8
    legend.fontName = "DejaVuSans"
    legend.alignment = "right"
    legend.colorNamePairs = [(WARNING, "APD Detection"), (CRITICAL, "Vehicle Violation")]
    drawing.add(legend)
    return drawing


def _top_locations_table(summary) -> Table:
    header = ["Kamera", "Lokasi", "Kategori", "Jumlah"]
    data = [[Paragraph(h, STYLE_TABLE_HEAD) for h in header]]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    for i, c in enumerate(summary.by_camera[:10], start=1):
        color = CATEGORY_COLOR.get(c.category, MUTED)
        data.append([
            Paragraph(c.camera_name, STYLE_TABLE_CELL),
            Paragraph(c.location or "-", STYLE_TABLE_CELL),
            Paragraph(CATEGORY_LABEL.get(c.category, c.category),
                      ParagraphStyle(f"cat{i}", parent=STYLE_TABLE_CELL, textColor=color)),
            Paragraph(str(c.count), ParagraphStyle(f"cnt{i}", parent=STYLE_TABLE_CELL, fontName="DejaVuSans-Bold")),
        ])
    t = Table(data, colWidths=[45 * mm, 55 * mm, 40 * mm, 29 * mm], repeatRows=1)
    t.setStyle(TableStyle(style_cmds))
    return t


def _violation_row(v) -> list:
    return [
        Paragraph(str(v.id), STYLE_TABLE_CELL),
        Paragraph(_fmt_dt(v.created_at), STYLE_TABLE_CELL),
        Paragraph(v.camera_name or f"Kamera #{v.camera_id}", STYLE_TABLE_CELL),
        Paragraph(v.category, STYLE_TABLE_CELL),
        Paragraph(v.status.value, STYLE_TABLE_CELL),
        Paragraph("Ya" if v.is_case else "Tidak", STYLE_TABLE_CELL),
    ]


def _violations_table(violations: list) -> Table:
    header = ["ID", "Waktu", "Kamera", "Kategori", "Status", "Kasus"]
    data = [[Paragraph(h, STYLE_TABLE_HEAD) for h in header]]
    data += [_violation_row(v) for v in violations]
    t = Table(data, colWidths=[13 * mm, 34 * mm, 46 * mm, 24 * mm, 24 * mm, 17 * mm], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), SURFACE_2))
    t.setStyle(TableStyle(style_cmds))
    return t


STATUS_ID = {"baru": "Baru", "diproses": "Diproses", "selesai": "Selesai"}


def _evidence_blocks(violations_with_snapshot: list) -> list:
    """One block per violation — its metadata line immediately followed
    by its actual snapshot JPEG fetched from MinIO (ADR-0017), in the
    same most-recent-first order as the table above. Each pair is kept
    together (never split across a page break) so the photo always
    stays directly under the violation it belongs to."""
    elements = [Paragraph("Bukti Foto per Pelanggaran", STYLE_SECTION)]
    any_photo = False
    for v in violations_with_snapshot:
        data = storage.get_snapshot(v.snapshot_ref)
        if data is None:
            continue
        try:
            img = Image(BytesIO(data), width=70 * mm, height=52.5 * mm)
        except Exception:
            continue
        any_photo = True
        meta = Paragraph(
            f"<b>#{v.id}</b> · {_fmt_dt(v.created_at)} · "
            f"{v.camera_name or ('Kamera #' + str(v.camera_id))} · "
            f"{CATEGORY_LABEL.get(v.category, v.category)} · "
            f"Status: {STATUS_ID.get(v.status.value, v.status.value)}",
            STYLE_BODY,
        )
        elements.append(KeepTogether([meta, Spacer(1, 1.5 * mm), img, Spacer(1, 5 * mm)]))
    if not any_photo:
        elements.append(Paragraph("Tidak ada foto bukti pada periode ini.", STYLE_MUTED))
    return elements


def build_report_pdf(kind: str, summary, violations: list | None = None) -> bytes:
    """`kind`: "executive" (KPI + trend + top locations — a
    manager can forward this as-is) or "detail" (all of the above, plus
    the full violation table and a photo-evidence gallery). Returns raw
    PDF bytes ready for a Content-Disposition: attachment response, or
    to attach onto the Recurring Report email."""
    buffer = BytesIO()
    period_label = (
        _fmt_date_range(summary.start, summary.end) if summary.start != summary.end
        else _fmt_date(summary.start)
    )
    kind_label = "Laporan Eksekutif" if kind == "executive" else "Laporan Detail"
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=16 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Smart CCTV AI — {kind_label}",
    )

    story: list = []
    story += _letterhead(
        f"Laporan HSSE — {kind_label}",
        f"Smart CCTV AI · Pertamina EP · Periode: {period_label} · "
        f"Dibuat: {_fmt_dt(datetime.now())}",
    )

    story.append(Paragraph("Ringkasan Pelanggaran", STYLE_SECTION))
    story.append(_kpi_table(summary))

    story.append(Paragraph("Tren Pelanggaran", STYLE_SECTION))
    story.append(_trend_chart(summary))

    story.append(Paragraph("Area dengan Pelanggaran Terbanyak", STYLE_SECTION))
    story.append(_top_locations_table(summary))

    if kind == "detail" and violations is not None:
        story.append(PageBreak())
        story.append(Paragraph("Detail Seluruh Pelanggaran", STYLE_SECTION))
        story.append(Paragraph(
            f"Menampilkan {len(violations)} pelanggaran pada periode ini, diurutkan dari yang terbaru.",
            STYLE_MUTED,
        ))
        story.append(Spacer(1, 3 * mm))
        story.append(_violations_table(violations))

        with_snapshot_all = [v for v in violations if v.has_snapshot]
        with_snapshot = with_snapshot_all[:MAX_EVIDENCE_PHOTOS]
        story.append(PageBreak())
        if len(with_snapshot_all) > MAX_EVIDENCE_PHOTOS:
            story.append(Paragraph(
                f"Menampilkan foto bukti untuk {MAX_EVIDENCE_PHOTOS} dari "
                f"{len(with_snapshot_all)} pelanggaran yang punya snapshot pada periode ini "
                f"(diurutkan dari yang terbaru). Gunakan rentang tanggal lebih pendek untuk "
                f"melihat semuanya.",
                STYLE_MUTED,
            ))
            story.append(Spacer(1, 3 * mm))
        story += _evidence_blocks(with_snapshot)

    doc.build(story, onFirstPage=_header_footer(kind_label, period_label),
               onLaterPages=_header_footer(kind_label, period_label))
    return buffer.getvalue()
