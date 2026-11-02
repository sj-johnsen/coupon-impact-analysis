"""LaTeX backend: turns the rendered report (text.md) into a .tex file and compiles it to the submission PDF.

Same source as the Word route, so every number still comes from results.json through the template engine. Understood
Markdown subset: headings, paragraphs, **bold**, *italic*, inline math $...$, display math $$...$$, figures, tables.
Layout: cover page and reference page on their own pages (not counted in the three pages), justified text in between.
Compiler: tectonic (a single binary, no TeX Live needed); pages are counted with pypdf.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

from . import config as C
from .render import split_frontmatter

FONT_PT = 12
MARGIN_CM = 2.0
MAX_PAGES = 3


class LatexError(RuntimeError):
    pass


PREAMBLE = r"""\documentclass[%(pt)dpt,a4paper]{article}
\usepackage[hmargin=%(margin).1fcm,vmargin=1.8cm]{geometry}
\usepackage{newtxtext,newtxmath}
\usepackage{amsmath}
\usepackage{graphicx,booktabs,microtype,xurl}
\usepackage[labelfont=bf,labelsep=period,justification=justified,singlelinecheck=false,skip=4pt,font={normalsize}]{caption}
\usepackage[colorlinks=true,allcolors=black,pdftitle={%(title)s},pdfauthor={Simon Jensen},pdfsubject={%(subject)s}]{hyperref}
\urlstyle{same}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.4em plus 0.1em}
\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}
\setlength{\intextsep}{8pt plus 2pt minus 2pt}
\setlength{\abovedisplayskip}{4pt plus 2pt}
\setlength{\belowdisplayskip}{4pt plus 2pt}
\setlength{\abovedisplayshortskip}{2pt}
\setlength{\belowdisplayshortskip}{2pt}
\renewcommand{\topfraction}{0.9}
\renewcommand{\bottomfraction}{0.9}
\renewcommand{\textfraction}{0.1}
\renewcommand{\floatpagefraction}{0.8}
\pagestyle{plain}
\newcommand{\sect}[1]{\par\vspace{0.3em}{\large\bfseries #1}\par\nopagebreak\vspace{0.05em}}
"""

_SPECIALS = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
_UNICODE = {"−": r"\textminus{}", "α": r"$\alpha$", "τ": r"$\tau$", "–": "--", "—": "---", "×": r"$\times$"}


def _math(m: str) -> str:
    """Math content: digits with thousands commas keep the comma from taking a space (4,459 -> 4{,}459)."""
    return re.sub(r"(?<=\d),(?=\d{3})", "{,}", m).replace("%", r"\%")


def _plain(text: str) -> str:
    if "\u2014" in text:
        raise LatexError("Em dash in the report text. Fix: rewrite the sentence in text.md without a dash.")
    text = re.sub(r"(?<=\d)-(?=\d)", "\u2013", text)      # ranges: 3,000-9,999 -> en dash
    out = []
    for i, ch in enumerate(text):
        if ch == "<" and text[i + 1:i + 2].isdigit():
            out.append(r"$<$\,")                          # p <0.001 -> p < 0.001
        elif ch in _SPECIALS:
            out.append(_SPECIALS[ch])
        elif ch == "\u2013":
            out.append("--")
        else:
            out.append(_UNICODE.get(ch, ch))
    return "".join(out)


def inline(text: str) -> str:
    """Inline Markdown to LaTeX: math is kept, **bold**, *italic*, URLs, escaping of the rest."""
    parts = re.split(r"(\$[^$]+\$|\*\*.+?\*\*|\*[^*\s][^*]*?\*|https?://\S+)", text)
    out = []
    for p in parts:
        if not p:
            continue
        if p.startswith("$") and p.endswith("$") and len(p) > 2:
            out.append("$" + _math(p[1:-1]) + "$")
        elif p.startswith("**") and p.endswith("**") and len(p) > 4:
            out.append(r"\textbf{" + inline(p[2:-2]) + "}")
        elif p.startswith("*") and p.endswith("*") and len(p) > 2:
            out.append(r"\textit{" + inline(p[1:-1]) + "}")
        elif p.startswith("http"):
            url = p.rstrip(".,;")
            out.append(r"\url{" + url + "}" + p[len(url):])
        else:
            out.append(_plain(p))
    return "".join(out)


def _table(lines: list[str], label: str, caption: str) -> str:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    header, align_row, body = rows[0], rows[1], rows[2:]
    spec = "".join("r" if a.endswith(":") and not a.startswith(":") else "l" for a in align_row)
    out = [r"\begin{table}[htbp]", r"\centering", r"\caption{" + inline(caption) + "}",
           r"\begin{tabular}{@{}" + spec + r"@{}}", r"\toprule",
           " & ".join(r"\textbf{" + inline(c) + "}" for c in header) + r" \\", r"\midrule"]
    out += [" & ".join(inline(c) for c in r) + r" \\" for r in body]
    out += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(out)


def _figure(caption: str, path: str) -> str:
    caption = re.sub(r"^Figure\s+[A-Z]?\d+\.\s*", "", caption)
    return "\n".join([r"\begin{figure}[htbp]", r"\centering", r"\includegraphics[width=0.9\textwidth]{" + path + "}",
                      r"\caption{" + inline(caption) + "}", r"\end{figure}"])


def _cover(meta: dict[str, str]) -> str:
    rows = [("Name", meta["name"]), ("Student ID", meta["matrikel"]), ("Course", meta["kurs_name"]),
            ("Lecturer", meta["dozent"]), ("Date", meta["datum_text"])]
    info = "\\\\\n".join(r"\textbf{" + k + ":} " + _plain(v) for k, v in rows)
    return "\n".join([r"\thispagestyle{empty}", r"\vspace*{4cm}",
                      r"{\fontsize{24}{28}\selectfont\bfseries " + _plain(meta["titel"]) + r"\par}\vspace{0.6em}",
                      r"{\Large " + _plain(meta["untertitel"]) + r"\par}\vspace{0.4em}",
                      r"{\Large Assignment 1, " + _plain(meta["kurs_name"]) + r"\par}\vspace{2.5cm}",
                      r"\begin{flushleft}", info, r"\end{flushleft}", r"\newpage", r"\pagenumbering{arabic}"])


def _date_text(iso: str) -> str:
    import datetime as dt
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def to_tex(md_text: str, subject: str = "Assignment 1, Topics in Econometrics B") -> str:
    meta, body = split_frontmatter(md_text)
    meta = dict(meta)
    meta["kurs_name"] = "Topics in Econometrics B"
    meta["datum_text"] = _date_text(meta["datum"])
    body = body.split("\n## References", 1)
    main, refs = body[0], (body[1] if len(body) > 1 else "")

    tex = [PREAMBLE % {"pt": FONT_PT, "margin": MARGIN_CM, "title": meta["titel"].replace("%", r"\%"), "subject": subject},
           r"\begin{document}", _cover(meta)]
    blocks = [b for b in re.split(r"\n\s*\n", main.strip("\n")) if b.strip()]
    i = 0
    while i < len(blocks):
        b = blocks[i].strip()
        if b.startswith("## "):
            tex.append(r"\sect{" + inline(b[3:].strip()) + "}")
        elif b.startswith("$$"):
            tex.append(r"\begin{equation*}" + "\n" + _math(b.strip("$").strip()) + "\n" + r"\end{equation*}")
        elif b.startswith("!["):
            m = re.match(r"!\[(.*)\]\((.*?)\)", b, re.S)
            tex.append(_figure(m.group(1), m.group(2)))
        elif b.startswith("**Table"):
            m = re.match(r"\*\*Table\s+\d+\.\*\*\s*(.*?)\n\{:", b, re.S)
            if m is None:
                raise LatexError("Table block without caption line '{: .tcap }'. Fix: check the table directive in text.md.")
            i += 1
            tex.append(_table([ln for ln in blocks[i].splitlines() if ln.strip()], "Table", m.group(1).strip()))
        else:
            tex.append(inline(" ".join(b.split())))
        i += 1

    tex.append(r"\newpage")
    tex.append(r"\sect{References}")
    tex.append(r"\begingroup\setlength{\parindent}{-1.2em}\setlength{\leftskip}{1.2em}\setlength{\parskip}{0.15em}")
    for r in [r.strip() for r in re.split(r"\n\s*\n", refs) if r.strip()]:
        tex.append(inline(" ".join(r.split())) + r"\par")
    tex.append(r"\endgroup")
    tex.append(r"\end{document}")
    return "\n\n".join(tex) + "\n"


def tectonic_path() -> str:
    p = shutil.which("tectonic") or str(Path.home() / ".local" / "bin" / "tectonic")
    if not Path(p).exists():
        raise LatexError("tectonic not found. Fix: download the release binary from github.com/tectonic-typesetting/tectonic "
                         "and put it on the PATH (for example ~/.local/bin).")
    return p


def build(md_text: str, root: Path, tex_name: str, quiet: bool = True) -> tuple[Path, int]:
    """Write <tex_name>.tex next to the project files and compile it; returns (pdf path, number of pages)."""
    root = Path(root)
    tex_path = root / f"{tex_name}.tex"
    tex_path.write_text(to_tex(md_text), encoding="utf-8")
    proc = subprocess.run([tectonic_path(), "--keep-logs", str(tex_path.name)], cwd=root, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise LatexError("tectonic failed:\n" + proc.stderr[-2000:])
    pdf = tex_path.with_suffix(".pdf")
    for junk in (tex_path.with_suffix(".log"), tex_path.with_suffix(".aux"), tex_path.with_suffix(".out")):
        junk.unlink(missing_ok=True)
    return pdf, len(PdfReader(str(pdf)).pages) - 2      # body pages: cover and reference page do not count
