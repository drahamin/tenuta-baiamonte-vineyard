#!/usr/bin/env python3
"""Build the branded system manual PDF and scrollable web preview pages."""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GOLD = colors.HexColor("#D3A624")
INK = colors.HexColor("#171816")
CREAM = colors.HexColor("#F5F1E7")
MUTED = colors.HexColor("#68675F")
GREEN = colors.HexColor("#576A4C")
RULE = colors.HexColor("#D8D3C5")
MANUAL_RELEASE = "1.6.0"


def register_fonts() -> None:
    root = Path("/System/Library/Fonts/Supplemental")
    fonts = {
        "ManualSans": root / "Arial.ttf",
        "ManualSans-Bold": root / "Arial Bold.ttf",
        "ManualSans-Italic": root / "Arial Italic.ttf",
        "ManualSerif": root / "Georgia.ttf",
        "ManualSerif-Bold": root / "Georgia Bold.ttf",
    }
    for name, path in fonts.items():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "ManualSans", normal="ManualSans", bold="ManualSans-Bold", italic="ManualSans-Italic",
    )
    pdfmetrics.registerFontFamily("ManualSerif", normal="ManualSerif", bold="ManualSerif-Bold")


def inline_markup(value: str) -> str:
    value = html.escape(value.strip())
    value = re.sub(r"\[([^]]+)]\(([^)]+)\)", r'<link href="\2" color="#576A4C"><u>\1</u></link>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
    return value


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "ManualBody", parent=base["BodyText"], fontName="ManualSans", fontSize=9.2,
            leading=13.1, textColor=INK, spaceAfter=5.5, splitLongWords=True,
        ),
        "h1": ParagraphStyle(
            "ManualH1", parent=base["Heading1"], fontName="ManualSerif-Bold", fontSize=20,
            leading=23, textColor=INK, spaceBefore=12, spaceAfter=8, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "ManualH2", parent=base["Heading2"], fontName="ManualSerif-Bold", fontSize=14,
            leading=17, textColor=INK, spaceBefore=9, spaceAfter=5, keepWithNext=True,
        ),
        "eyebrow": ParagraphStyle(
            "ManualEyebrow", parent=base["BodyText"], fontName="ManualSans-Bold", fontSize=7.5,
            leading=9, textColor=GOLD, spaceBefore=3, spaceAfter=3, tracking=1.1,
        ),
        "quote": ParagraphStyle(
            "ManualQuote", parent=base["BodyText"], fontName="ManualSerif", fontSize=11,
            leading=15, textColor=GREEN, leftIndent=12, rightIndent=12, borderColor=GOLD,
            borderWidth=1.5, borderPadding=(6, 8, 6, 10), spaceBefore=5, spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "ManualCode", parent=base["Code"], fontName="Courier", fontSize=7.8, leading=10.5,
            textColor=INK, backColor=colors.HexColor("#EEE8D9"), borderColor=GOLD,
            borderWidth=0.6, borderPadding=8, spaceBefore=4, spaceAfter=8,
        ),
        "table": ParagraphStyle(
            "ManualTable", parent=base["BodyText"], fontName="ManualSans", fontSize=7.6,
            leading=10, textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "ManualTableHead", parent=base["BodyText"], fontName="ManualSans-Bold", fontSize=7.6,
            leading=9.5, textColor=CREAM,
        ),
        "toc": ParagraphStyle(
            "ManualToc", parent=base["BodyText"], fontName="ManualSans", fontSize=8.5,
            leading=12, textColor=INK, leftIndent=8, spaceAfter=2,
        ),
    }


def parse_table(lines: list[str], start: int, style_map: dict[str, ParagraphStyle], width: float):
    raw = []
    index = start
    while index < len(lines) and lines[index].strip().startswith("|"):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        raw.append(cells)
        index += 1
    if len(raw) > 1 and all(re.fullmatch(r":?-{3,}:?", item) for item in raw[1]):
        raw.pop(1)
    columns = max(len(row) for row in raw)
    data = []
    for row_index, row in enumerate(raw):
        row += [""] * (columns - len(row))
        text_style = style_map["table_head"] if row_index == 0 else style_map["table"]
        data.append([Paragraph(inline_markup(cell), text_style) for cell in row])
    weights = []
    for column in range(columns):
        longest = max(len(re.sub(r"[*`]", "", row[column])) for row in raw if column < len(row))
        weights.append(min(max(longest, 8), 42))
    total = sum(weights)
    column_widths = [width * weight / total for weight in weights]
    table = Table(data, colWidths=column_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), CREAM),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F4F1E9")),
        ("GRID", (0, 0), (-1, -1), 0.45, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table, index


def body_story(source: str, doc: SimpleDocTemplate) -> list:
    style_map = styles()
    lines = source.splitlines()
    story: list = [Spacer(1, doc.height - 14), PageBreak()]
    headings = [line[3:].strip() for line in lines if line.startswith("## ") and not line.startswith("## System Manual")]
    story.extend([
        Paragraph("CONTENTS", style_map["eyebrow"]),
        Paragraph("System at a glance", style_map["h1"]),
        Paragraph("This manual follows the live dashboard from everyday use through administration, recovery, and release verification.", style_map["body"]),
    ])
    midpoint = (len(headings) + 1) // 2
    toc_data = []
    for left, right in zip(headings[:midpoint], headings[midpoint:] + [""] * midpoint):
        toc_data.append([
            Paragraph(inline_markup(left), style_map["toc"]),
            Paragraph(inline_markup(right), style_map["toc"]) if right else "",
        ])
    toc = Table(toc_data, colWidths=[doc.width / 2 - 5, doc.width / 2 - 5], hAlign="LEFT")
    toc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
    story.extend([toc, PageBreak()])

    index = 0
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    list_kind = "bullet"
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            text = " ".join(item.strip() for item in paragraph_buffer)
            story.append(Paragraph(inline_markup(text), style_map["body"]))
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            items = [ListItem(Paragraph(inline_markup(item), style_map["body"]), leftIndent=8) for item in list_buffer]
            options = {"bulletType": list_kind, "leftIndent": 18, "bulletFontName": "ManualSans-Bold", "bulletFontSize": 7.5, "spaceAfter": 5}
            if list_kind == "1":
                options["start"] = "1"
            story.append(ListFlowable(items, **options))
            list_buffer.clear()

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph(); flush_list()
            if in_code:
                story.append(Preformatted("\n".join(code_lines), style_map["code"]))
                code_lines.clear()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph(); flush_list(); index += 1; continue
        if stripped.startswith("# ") or stripped == "## System Manual" or stripped.startswith("**Release covered:") or stripped.startswith("**Manual date:") or stripped.startswith("**System owner:") or stripped.startswith("**Operational authority:"):
            index += 1; continue
        if stripped.startswith("| "):
            flush_paragraph(); flush_list()
            table, index = parse_table(lines, index, style_map, doc.width)
            story.extend([table, Spacer(1, 6)])
            continue
        if stripped.startswith("## "):
            flush_paragraph(); flush_list()
            label = stripped[3:].strip()
            story.append(KeepTogether([Paragraph("OPERATING REFERENCE", style_map["eyebrow"]), Paragraph(inline_markup(label), style_map["h1"])]))
        elif stripped.startswith("### "):
            flush_paragraph(); flush_list()
            story.append(Paragraph(inline_markup(stripped[4:]), style_map["h2"]))
        elif stripped.startswith("> "):
            flush_paragraph(); flush_list()
            story.append(Paragraph(inline_markup(stripped[2:]), style_map["quote"]))
        elif re.match(r"^- ", stripped):
            flush_paragraph()
            if list_buffer and list_kind != "bullet": flush_list()
            list_kind = "bullet"; list_buffer.append(stripped[2:])
        elif re.match(r"^\d+\. ", stripped):
            flush_paragraph()
            if list_buffer and list_kind != "1": flush_list()
            list_kind = "1"; list_buffer.append(re.sub(r"^\d+\. ", "", stripped))
        elif stripped == "---":
            flush_paragraph(); flush_list(); story.append(Spacer(1, 4))
        else:
            paragraph_buffer.append(stripped)
        index += 1
    flush_paragraph(); flush_list()
    return story


def cover(canvas, doc, logo: Path) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(INK); canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(GOLD); canvas.rect(0, 0, 14 * mm, height, fill=1, stroke=0)
    canvas.setFillColor(GREEN); canvas.circle(width - 34 * mm, height - 31 * mm, 7 * mm, fill=1, stroke=0)
    if logo.exists():
        canvas.drawImage(str(logo), 31 * mm, height - 97 * mm, width=48 * mm, height=25 * mm, preserveAspectRatio=True, mask="auto")
    canvas.setFillColor(GOLD); canvas.setFont("ManualSans-Bold", 9.2); canvas.drawString(24 * mm, height - 126 * mm, "OPERATIONS · AGRONOMY · ENOLOGY · HOSPITALITY · REGISTER")
    canvas.setFillColor(CREAM); canvas.setFont("ManualSerif-Bold", 30)
    canvas.drawString(24 * mm, height - 151 * mm, "Tenuta Baiamonte")
    canvas.drawString(24 * mm, height - 170 * mm, "System Manual")
    canvas.setStrokeColor(GOLD); canvas.setLineWidth(2); canvas.line(24 * mm, height - 184 * mm, 90 * mm, height - 184 * mm)
    canvas.setFont("ManualSans", 11.5); canvas.setFillColor(CREAM)
    canvas.drawString(24 * mm, height - 199 * mm, "Operations, agronomy, enology, hospitality, register, security, and recovery.")
    canvas.setFont("ManualSans", 9.5)
    canvas.drawString(24 * mm, 74 * mm, f"Release covered {MANUAL_RELEASE}")
    canvas.drawString(24 * mm, 66 * mm, "Manual date 21 August 2026")
    canvas.drawString(24 * mm, 58 * mm, "Operational authority Vineyard Operations MariaDB")
    canvas.restoreState()


def body_page(canvas, doc) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5); canvas.line(21 * mm, height - 17 * mm, width - 21 * mm, height - 17 * mm)
    canvas.setFillColor(MUTED); canvas.setFont("ManualSans", 7.5)
    canvas.drawString(21 * mm, height - 13 * mm, f"TENUTA BAIAMONTE · SYSTEM MANUAL · RELEASE {MANUAL_RELEASE}")
    canvas.drawRightString(width - 21 * mm, 12 * mm, f"{doc.page}")
    canvas.setFillColor(GOLD); canvas.rect(0, 0, 4 * mm, height, fill=1, stroke=0)
    canvas.restoreState()


def render_preview(pdf_path: Path, pages_dir: Path) -> int:
    renderer = shutil.which("pdftoppm")
    if not renderer:
        raise RuntimeError("pdftoppm is required to build the in-window manual preview")
    pages_dir.mkdir(parents=True, exist_ok=True)
    for old in pages_dir.glob("page-*.webp"):
        old.unlink()
    with tempfile.TemporaryDirectory(prefix="baiamonte-manual-") as temp:
        prefix = Path(temp) / "page"
        environment = {**os.environ, "HOME": temp, "XDG_CACHE_HOME": temp}
        subprocess.run([renderer, "-png", "-r", "144", str(pdf_path), str(prefix)], check=True, env=environment)
        pngs = sorted(Path(temp).glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
        for number, png in enumerate(pngs, 1):
            with Image.open(png) as image:
                image.convert("RGB").save(pages_dir / f"page-{number:02d}.webp", "WEBP", quality=88, method=6)
    return len(list(pages_dir.glob("page-*.webp")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("docs/Tenuta_Baiamonte_System_Manual.md"))
    parser.add_argument("--output", type=Path, default=Path("docs/Tenuta_Baiamonte_System_Manual.pdf"))
    parser.add_argument("--pages", type=Path, default=Path("app/static/manual-pages"))
    args = parser.parse_args()
    register_fonts()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(args.output), pagesize=A4, rightMargin=21 * mm, leftMargin=24 * mm,
        topMargin=23 * mm, bottomMargin=19 * mm, title="Tenuta Baiamonte Vineyard Operations - System Manual",
        author="Azienda Agricola Tenuta Baiamonte S.S.", subject="Operations, agronomy, enology, hospitality, data logic, security, and recovery",
    )
    story = body_story(args.source.read_text(encoding="utf-8"), doc)
    logo = Path("logo.png")
    doc.build(story, onFirstPage=lambda canvas, document: cover(canvas, document, logo), onLaterPages=body_page)
    count = render_preview(args.output, args.pages)
    print(f"Built {args.output} with {count} portrait pages")


if __name__ == "__main__":
    main()
