"""CSV and PDF generators for analytics reports."""
from __future__ import annotations

import csv
import io
import unicodedata
from xml.sax.saxutils import escape


def _safe_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Prevent spreadsheet formula execution when a report is opened in Excel.
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        text = "'" + text
    return text


def create_csv(rows: list[list[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, dialect="excel", lineterminator="\r\n")
    for row in rows:
        writer.writerow([_safe_csv_cell(value) for value in row])
    return buffer.getvalue().encode("utf-8-sig")


def _pdf_text(value: object) -> str:
    text = "" if value is None else str(value)
    # ReportLab's built-in Helvetica uses WinAnsi. Transliterate Polish letters
    # rather than emitting missing-glyph boxes in the portable PDF report.
    text = text.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def create_pdf(title: str, sections: list[tuple[str, list[list[object]]]]) -> bytes:
    """Build a compact landscape PDF; ReportLab is loaded only on export."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=_pdf_text(title),
        author="CyberSim",
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    cell_style = ParagraphStyle(
        "AnalyticsCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    story = [Paragraph(escape(_pdf_text(title)), title_style), Spacer(1, 5 * mm)]

    for section_title, rows in sections:
        if not rows:
            continue
        wrapped_rows = []
        for row in rows:
            wrapped_rows.append([
                Paragraph(escape(_pdf_text(value)), cell_style)
                for value in row
            ])
        column_count = max(1, max(len(row) for row in rows))
        available_width = landscape(A4)[0] - document.leftMargin - document.rightMargin
        widths = [available_width / column_count] * column_count
        table = Table(wrapped_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#303846")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c0cc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f3f7")]),
        ]))
        story.append(KeepTogether([Paragraph(escape(_pdf_text(section_title)), heading_style), Spacer(1, 2 * mm)]))
        story.append(table)
        story.append(Spacer(1, 6 * mm))

    document.build(story)
    return buffer.getvalue()
