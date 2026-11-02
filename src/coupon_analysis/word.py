"""Word backend: turns the rendered report (text.md) into a .docx.

The same Markdown that feeds the HTML route comes in, so every number still comes from results.json through the template
engine. Only a small Markdown subset is understood: headings, paragraphs, **bold**, *italic*, figures, tables.
Layout: A4, 2.0 cm margins, Calibri 12 throughout (body, tables, captions); an optional cover page (not counted in the
three pages) and an optional reference page. Both are flags of `build`.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import config as C
from .render import split_frontmatter

FONT = "Calibri"
SIZE = 12
INK = RGBColor(0x1B, 0x1B, 0x1B)
BODY_WIDTH_CM = 17.0
MARGIN_CM = 2.0
MARGIN_TB_CM = 2.0


class WordError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------ low-level helpers
def _set_font(style_or_run, size=SIZE, bold=None, italic=None, color=INK):
    f = style_or_run.font
    f.name = FONT
    f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    f.color.rgb = color
    rpr = style_or_run.element.get_or_add_rPr() if hasattr(style_or_run.element, "get_or_add_rPr") else style_or_run.element.rPr
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(a), FONT)


def _border(cell_or_par_pr, edge: str, size: int, color: str):
    el = OxmlElement(f"w:{edge}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), color)
    return el


def _add_runs(par, text: str, size=SIZE, base_italic=False, base_bold=False):
    """**bold** and *italic* inside a line of text."""
    for tok in re.split(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*)", text):
        if not tok:
            continue
        bold, italic = base_bold, base_italic
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            tok, bold = tok[2:-2], True
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            tok, italic = tok[1:-1], not base_italic
        run = par.add_run(tok)
        _set_font(run, size, bold=bold, italic=italic)


def _page_number_field(par):
    run = par.add_run()
    _set_font(run, SIZE)
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def _style_document(doc: Document, line: float):
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(MARGIN_CM)
    sec.top_margin = sec.bottom_margin = Cm(MARGIN_TB_CM)
    sec.footer_distance = Cm(1.1)
    normal = doc.styles["Normal"]
    _set_font(normal, SIZE)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = line
    normal.paragraph_format.widow_control = True
    h1 = doc.styles["Heading 1"]
    _set_font(h1, 14, bold=True)
    h1.paragraph_format.space_before = Pt(6)
    h1.paragraph_format.space_after = Pt(3)
    h1.paragraph_format.keep_with_next = True
    h1.paragraph_format.line_spacing = 1.0
    ppr = h1.element.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bdr.append(_border(None, "bottom", 6, "C9CED4"))
    ppr.append(bdr)
    for name in ("Heading 2", "Heading 3", "Title"):
        if name in [s.name for s in doc.styles]:
            _set_font(doc.styles[name], SIZE, bold=True)


def _set_properties(doc: Document, title: str, subject: str):
    cp = doc.core_properties
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    cp.author = C.AUTHOR
    cp.last_modified_by = C.AUTHOR
    cp.title = title
    cp.subject = subject
    cp.comments = ""
    cp.keywords = ""
    cp.category = ""
    cp.content_status = ""
    cp.created = now
    cp.modified = now
    cp.last_printed = now
    cp.revision = 1
    cp.language = "en-GB"
    cp.identifier = ""
    cp.version = ""


def _scrub_app_properties(docx_path: Path):
    """python-docx's template carries docProps/app.xml of its own; blank the fields that name a tool or a 2013 date."""
    import shutil
    import zipfile
    tmp = docx_path.with_suffix(".tmp")
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                text = data.decode("utf-8")
                text = re.sub(r"<Company>.*?</Company>|<Company\s*/>", "<Company></Company>", text, flags=re.S)
                text = re.sub(r"<Application>.*?</Application>", "<Application>Microsoft Office Word</Application>", text, flags=re.S)
                text = re.sub(r"<AppVersion>.*?</AppVersion>", "", text, flags=re.S)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, docx_path)


# ------------------------------------------------------------------------------------------ blocks
def _paragraph(doc, text, **fmt):
    p = doc.add_paragraph()
    _add_runs(p, text)
    for k, v in fmt.items():
        setattr(p.paragraph_format, k, v)
    return p


def _caption(doc, label: str, text: str, keep_with_next=False, space_before=2):
    p = doc.add_paragraph()
    _add_runs(p, f"{label}: {text}", base_italic=True)
    pf = p.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing, pf.keep_with_next = Pt(space_before), Pt(8), 1.0, keep_with_next
    pf.keep_together = True
    return p


def _figure(doc, img: Path, label: str, caption: str):
    if not img.exists():
        raise WordError(f"Image not found: {img}. Fix: run the full pipeline so that figures/ is regenerated.")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(4), Pt(0)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.line_spacing = 1.0
    p.add_run().add_picture(str(img), width=Cm(BODY_WIDTH_CM))
    _caption(doc, label, caption)


def _table(doc, rows: list[list[str]], aligns: list[str], label: str, caption: str):
    ncol = len(rows[0])
    tbl = doc.add_table(rows=len(rows), cols=ncol)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    weights = [max(len(re.sub(r"\*", "", r[i])) for r in rows) for i in range(ncol)]
    weights = [max(w, 9) for w in weights]
    widths = [BODY_WIDTH_CM * w / sum(weights) for w in weights]
    tblpr = tbl._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    for i, row in enumerate(rows):
        tr = tbl.rows[i]
        trpr = tr._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        for j, text in enumerate(row):
            cell = tr.cells[j]
            cell.width = Cm(widths[j])
            par = cell.paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.RIGHT if aligns[j] == "r" else WD_ALIGN_PARAGRAPH.LEFT
            pf = par.paragraph_format
            pf.space_after = pf.space_before = Pt(1.5)
            pf.line_spacing = 1.0
            pf.keep_with_next = True
            _add_runs(par, text, base_bold=(i == 0))
            borders = OxmlElement("w:tcBorders")
            if i == 0:
                borders.append(_border(None, "top", 8, "1B1B1B"))
                borders.append(_border(None, "bottom", 8, "1B1B1B"))
            elif i == len(rows) - 1:
                borders.append(_border(None, "bottom", 8, "1B1B1B"))
            else:
                borders.append(_border(None, "bottom", 4, "D3D7DC"))
            cell._tc.get_or_add_tcPr().append(borders)
    # last row must not keep with next (the caption follows, and it is kept by the table before it)
    for cell in tbl.rows[-1].cells:
        cell.paragraphs[0].paragraph_format.keep_with_next = True
    _caption(doc, label, caption, space_before=3)


def _cover(doc, meta: dict[str, str]):
    def line(text, size, bold=False, before=0, after=0, color=INK):
        p = doc.add_paragraph()
        run = p.add_run(text)
        _set_font(run, size, bold=bold, color=color)
        p.paragraph_format.space_before, p.paragraph_format.space_after, p.paragraph_format.line_spacing = Pt(before), Pt(after), 1.15
        return p

    line(meta.get("titel", "Causal Impact of Coupon Interventions"), 24, bold=True, before=150, after=10)
    line(meta.get("untertitel", ""), 14, after=4, color=RGBColor(0x44, 0x44, 0x44))
    line(f"Assignment 1, {C.COURSE}", 14, after=26, color=RGBColor(0x44, 0x44, 0x44))
    date = meta.get("datum", "")
    try:
        d = dt.date.fromisoformat(date)
        date = f"{d.day} {d.strftime('%B %Y')}"
    except ValueError:
        pass
    for label, value in (("Name", meta.get("name", C.AUTHOR)), ("Student ID", meta.get("matrikel", C.STUDENT_ID)),
                         ("Course", C.COURSE), ("Lecturer", meta.get("dozent", C.LECTURER)), ("Date", date)):
        p = doc.add_paragraph()
        r1 = p.add_run(f"{label}: ")
        _set_font(r1, SIZE, bold=True)
        r2 = p.add_run(value)
        _set_font(r2, SIZE)
        p.paragraph_format.space_after = Pt(3)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _title_block(doc, meta: dict[str, str]):
    p = doc.add_paragraph()
    r = p.add_run(meta.get("titel", ""))
    _set_font(r, 18, bold=True)
    p.paragraph_format.space_after = Pt(0)
    p = doc.add_paragraph()
    r = p.add_run(f"{meta.get('name', C.AUTHOR)} · Student ID {meta.get('matrikel', C.STUDENT_ID)} · {C.COURSE}, Assignment 1")
    _set_font(r, SIZE, color=RGBColor(0x55, 0x55, 0x55))


# ------------------------------------------------------------------------------------------ markdown subset
def _parse_table(lines: list[str]):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    sep = rows[1]
    aligns = ["r" if c.endswith(":") and not c.startswith(":") else "l" for c in sep]
    return [rows[0]] + rows[2:], aligns


def build(md_text: str, root: Path, out: Path, include_cover: bool | None = None, include_references: bool | None = None,
          line_spacing: float = 1.0) -> Path:
    """Write the Word report. `include_cover` and `include_references` default to config.INCLUDE_COVER / INCLUDE_REFERENCES."""
    include_cover = C.INCLUDE_COVER if include_cover is None else include_cover
    include_references = C.INCLUDE_REFERENCES if include_references is None else include_references
    meta, body = split_frontmatter(md_text)
    body, _, refs = body.partition("\n## References")
    doc = Document()
    _style_document(doc, line_spacing)
    _set_properties(doc, meta.get("titel", ""), f"Assignment 1, {C.COURSE}")
    if include_cover:
        _cover(doc, meta)
        doc.sections[0].different_first_page_header_footer = True
    else:
        _title_block(doc, meta)
    _page_number_field(doc.sections[0].footer.paragraphs[0])
    doc.sections[0].footer.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    pending_caption: tuple[str, str] | None = None
    for block in re.split(r"\n\s*\n", body.strip()):
        lines = block.strip().splitlines()
        first = lines[0]
        if first.startswith("## "):
            doc.add_heading(first[3:].strip(), level=1)
        elif first.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", first, re.S)
            label, _, cap = m.group(1).partition(". ")
            _figure(doc, root / m.group(2), label, cap)
        elif first.startswith("**Table") and any(ln.startswith("{:") for ln in lines):
            m = re.match(r"\*\*(Table \d+)\.\*\*\s*(.*)", first)
            pending_caption = (m.group(1), m.group(2))
        elif first.startswith("|"):
            rows, aligns = _parse_table(lines)
            label, cap = pending_caption or ("Table", "")
            _table(doc, rows, aligns, label, cap)
            pending_caption = None
        else:
            _paragraph(doc, " ".join(ln.strip() for ln in lines))

    if include_references and refs.strip():
        h = doc.add_heading("References", level=1)
        h.paragraph_format.page_break_before = True
        for entry in [e for e in re.split(r"\n\s*\n", refs.strip()) if e.strip()]:
            p = doc.add_paragraph()
            _add_runs(p, " ".join(entry.split()))
            pf = p.paragraph_format
            pf.left_indent, pf.first_line_indent, pf.space_after, pf.line_spacing = Cm(1.27), Cm(-1.27), Pt(8), 1.08
    out = Path(out)
    doc.save(out)
    _scrub_app_properties(out)
    return out


# ------------------------------------------------------------------------------------------ checks and export
def docx_body_text(path: Path) -> str:
    """Text of the report proper (from the first heading to the references), tables included, for the number guard."""
    doc = Document(str(path))
    parts, started = [], False
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            par = Paragraph(child, doc)
            if par.style.name == "Heading 1":
                if par.text.strip() == "References":
                    break
                started = True
            if started:
                parts.append(par.text)
        elif child.tag == qn("w:tbl") and started:
            for row in Table(child, doc).rows:
                parts.append(" ".join(c.text for c in row.cells))
    return "\n".join(parts)


def export_pdf_with_word(docx_path: Path, pdf_path: Path) -> int:
    """macOS only: let Microsoft Word save the PDF (the only reliable page count). Returns the page count."""
    script = f'''tell application "Microsoft Word"
  set d to open file name (POSIX file "{Path(docx_path).resolve()}" as text)
  save as d file name (POSIX file "{Path(pdf_path).resolve()}" as text) file format format PDF
  close d saving no
end tell'''
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
    if not Path(pdf_path).exists():
        raise WordError("Word did not write the PDF. Fix: open the .docx in Word and export it by hand.")
    from pypdf import PdfReader
    return len(PdfReader(str(pdf_path)).pages)


# ------------------------------------------------------------------------------------------ page estimate (no Word needed)
CHAR_MM = 2.1          # conservative average character width of Calibri 12 pt, spaces included
LINE_FACTOR = 1.22     # Calibri: single line height = 1.22 x font size
MAX_FILL = 0.92        # the body may use at most this share of three pages


def _wrap_lines(text: str, width_mm: float, char_mm: float = CHAR_MM) -> int:
    per_line = max(1, int(width_mm / char_mm))
    lines, cur = 1, 0
    for word in text.split():
        n = len(word)
        if cur and cur + 1 + n > per_line:
            lines, cur = lines + 1, n
        else:
            cur = cur + (1 if cur else 0) + n
    return lines


def estimate_pages(path: Path) -> dict:
    """Estimate how the report body (heading 'Executive Summary' up to 'References') flows over A4 pages in Word.

    Height per block = wrapped lines x line height + paragraph spacing; figures at their inserted height; table rows by
    their wrapped cells. Blocks that must stay together (heading + next paragraph, figure + caption, table + caption) move to
    the next page as a whole, as Word does. Returns {'pages', 'fill' (share of three pages used), 'per_page' (share of each
    page filled), 'ok'}. Deliberately pessimistic; `ok` needs fill <= MAX_FILL and at most three pages.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(str(path))
    sec = doc.sections[0]
    usable = (sec.page_height - sec.top_margin - sec.bottom_margin) / 12700.0        # points
    width_mm = (sec.page_width - sec.left_margin - sec.right_margin) / 36000.0
    blocks: list[tuple[float, bool]] = []                                            # (height pt, keep with next)
    started = False
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            par = Paragraph(child, doc)
            heading = par.style.name == "Heading 1"
            if heading and par.text.strip() == "References":
                break
            if heading:
                started = True
            if not started:
                continue
            pf = par.paragraph_format
            style_pf = par.style.paragraph_format
            before = (pf.space_before if pf.space_before is not None else style_pf.space_before or 0) / 12700.0
            after = (pf.space_after if pf.space_after is not None else style_pf.space_after or 0) / 12700.0
            ls = pf.line_spacing or style_pf.line_spacing or 1.0
            ls = ls if isinstance(ls, float) else 1.0
            keep = bool(pf.keep_with_next if pf.keep_with_next is not None else style_pf.keep_with_next)
            drawings = child.findall(".//" + qn("wp:extent"))
            if drawings:
                h = max(int(d.get("cy")) for d in drawings) / 12700.0 + before + after
            else:
                size = 14 if heading else SIZE
                lines = _wrap_lines(par.text, width_mm - (pf.left_indent or 0) / 36000.0)
                h = lines * size * LINE_FACTOR * ls + before + after
            blocks.append((h, keep))
        elif child.tag == qn("w:tbl") and started:
            tbl = Table(child, doc)
            h = 0.0
            for row in tbl.rows:
                n = 1
                for cell in row.cells:
                    w_mm = (cell.width or 0) / 36000.0 - 3.5
                    n = max(n, _wrap_lines(cell.text, max(w_mm, 8)))
                h += n * SIZE * LINE_FACTOR + 3.0 + 1.0
            blocks.append((h, True))
    # paginate with keep-with-next chains
    chains, cur = [], 0.0
    for h, keep in blocks:
        cur += h
        if not keep:
            chains.append(cur)
            cur = 0.0
    if cur:
        chains.append(cur)
    pages, used, per_page = 1, 0.0, []
    for h in chains:
        if used + h > usable and used > 0:
            per_page.append(used / usable)
            pages, used = pages + 1, 0.0
        used += h
    per_page.append(used / usable)
    fill = sum(chains) / (3 * usable)
    return {"pages": pages, "fill": fill, "per_page": per_page, "ok": pages <= 3 and fill <= MAX_FILL}
