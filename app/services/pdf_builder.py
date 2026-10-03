"""PDF generation with correct Urdu: arabic-reshaper + python-bidi + a Naskh TTF font.

Note: ReportLab cannot do OpenType shaping, so use a NASKH-style font (Noto Naskh Arabic,
Amiri, Scheherazade). Nastaliq fonts need a HarfBuzz engine (WeasyPrint) to look right.
"""
import logging
import re
from datetime import date
from io import BytesIO
from typing import Dict, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import config
from .validators import display_value

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    _RESHAPER = arabic_reshaper.ArabicReshaper(configuration={"delete_harakat": False})
except Exception:  # library missing: PDF still builds, Urdu will not be shaped
    _RESHAPER = None
    get_display = None

log = logging.getLogger("pdf")
_FONT_CANDIDATES = [
    "NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic[wght].ttf", "Amiri-Regular.ttf",
    "Scheherazade-Regular.ttf", "NotoSansArabic-Regular.ttf",
]
_SYSTEM_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
_UR_FONT: Optional[str] = None
_registered = False


def urdu_font_name() -> Optional[str]:
    """Register the first usable Urdu-capable font. Returns None if nothing is found."""
    global _UR_FONT, _registered
    if _registered:
        return _UR_FONT
    _registered = True
    paths = [config.FONT_DIR / n for n in _FONT_CANDIDATES]
    paths += list(config.FONT_DIR.glob("*.ttf")) + [__import__("pathlib").Path(p) for p in _SYSTEM_FALLBACKS]
    for p in paths:
        try:
            if p.exists():
                pdfmetrics.registerFont(TTFont("UrduFont", str(p)))
                _UR_FONT = "UrduFont"
                log.info("Urdu font: %s", p)
                break
        except Exception as e:
            log.warning("Font %s unusable: %s", p, e)
    if not _UR_FONT:
        log.warning("No Urdu font found. Run: python download_fonts.py")
    return _UR_FONT


def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]", text or ""))


def shape(text: str) -> str:
    if not _RESHAPER or not get_display:
        return text
    return get_display(_RESHAPER.reshape(text))


def _wrap_rtl(text: str, font: str, size: float, max_w: float) -> str:
    """Wrap logical Urdu text ourselves, then shape each line (Paragraph can't wrap RTL correctly)."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and pdfmetrics.stringWidth(shape(trial), font, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return "<br/>".join(escape(shape(l)) for l in lines)


def _cell(text: str, size: float = 10, width: float = 8 * cm, bold: bool = False, align=None) -> Paragraph:
    urdu = urdu_font_name()
    if has_arabic(text) and urdu:
        style = ParagraphStyle("u", fontName=urdu, fontSize=size + 1, leading=(size + 1) * 1.6, alignment=TA_RIGHT)
        paragraph_lines = []
        for chunk in (text or "").splitlines() or [""]:
            paragraph_lines.append(_wrap_rtl(chunk, urdu, size + 1, width - 14))
        return Paragraph("<br/>".join(paragraph_lines), style)
    style = ParagraphStyle(
        "l", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, leading=size * 1.35,
        alignment=align if align is not None else TA_LEFT,
    )
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def build_pdf(form: dict, values: Dict[str, str]) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=form["title_en"], author="SpeakFill",
    )
    w_label, w_val = 4.6 * cm, 8.8 * cm
    elements = [
        _cell(form["title_en"], size=18, width=18 * cm, bold=True, align=TA_CENTER),
        Spacer(1, 4),
        _cell(form["title_ur"], size=15, width=18 * cm),
        Spacer(1, 14),
    ]
    # centre the Urdu title
    if elements[2].style.alignment == TA_RIGHT:
        elements[2].style.alignment = TA_CENTER

    rows = []
    for f in form["fields"]:
        val = display_value(f, (values.get(f["id"]) or "").strip())
        rows.append([
            _cell(f["label_en"], size=9, width=w_label, bold=True),
            _cell(val if val else "-", size=10.5, width=w_val),
            _cell(f["label_ur"], size=9, width=w_label),
        ])
    table = Table(rows, colWidths=[w_label, w_val, w_label])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#8A9A90")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF3EF")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EEF3EF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements += [table, Spacer(1, 30)]
    sig = Table(
        [[_cell("Signature: ______________________", 10), _cell(f"Date: {date.today().strftime('%d-%m-%Y')}", 10)]],
        colWidths=[9 * cm, 9 * cm],
    )
    elements += [sig, Spacer(1, 16), _cell("Generated with SpeakFill. Please verify all details before submitting.", 7.5)]
    doc.build(elements)
    return buf.getvalue()
