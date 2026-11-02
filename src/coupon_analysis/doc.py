"""A tiny template engine: fills a Markdown template from results.json.

    {{ rd.at1000.effects.s34.effect | signed }}   a number from results.json, formatted by a filter (see fmt.FILTERS)
    {{ fig:trends | caption text }}               a numbered figure (Figure A1 in the appendix, Figure 1 in the report)
    {{ tab:rd_effects | caption text }}           a numbered table built by tables.py
    {{ ref:trends }} / {{ aref:trends }}          "Figure A1" - in this document / in the appendix
    {{ code:rdd.run_rd }}                         the source code of a function, so the manual never drifts from the code

Because every number is looked up, a number in the text cannot disagree with the analysis.
"""
from __future__ import annotations

import importlib
import inspect
import re
import textwrap

from . import fmt, tables

DIRECTIVE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.S)
KINDS = {"fig": "Figure", "tab": "Table"}


class TemplateError(ValueError):
    pass


def scan(template: str, prefix: str) -> dict[str, str]:
    """Numbering in order of appearance: {'fig:trends': 'Figure A1', ...}."""
    counters = {"fig": 0, "tab": 0}
    out = {}
    for m in DIRECTIVE.finditer(template):
        head = m.group(1).split("|", 1)[0].strip()
        for kind in KINDS:
            if head.startswith(kind + ":"):
                counters[kind] += 1
                out[head] = f"{KINDS[kind]} {prefix}{counters[kind]}"
    return out


def _lookup(R: dict, path: str):
    cur = R
    for tok in path.split("."):
        try:
            cur = cur[int(tok)] if isinstance(cur, list) else cur[tok]
        except (KeyError, IndexError, ValueError, TypeError):
            raise TemplateError(f"Unknown results path '{path}' (failed at '{tok}'). Fix: check results.json for the key.") from None
    return cur


def _code(spec: str) -> str:
    mod, _, fn = spec.partition(".")
    obj = getattr(importlib.import_module(f"coupon_analysis.{mod}"), fn)
    return "```python\n" + textwrap.dedent(inspect.getsource(obj)).rstrip() + "\n```"


def render(template: str, R: dict, figs: dict[str, str], prefix: str, appendix_numbers: dict[str, str] | None = None) -> str:
    local = scan(template, prefix)

    def inline(text: str) -> str:
        """[[ path | filter ]] inside a caption, because a caption cannot hold {{ }}."""
        def one(m: re.Match) -> str:
            p, _, f = m.group(1).partition("|")
            return fmt.FILTERS[f.strip() or "int"](_lookup(R, p.strip()))
        return re.sub(r"\[\[\s*(.+?)\s*\]\]", one, text)

    def sub(m: re.Match) -> str:
        body = m.group(1).strip()
        head, _, tail = body.partition("|")
        head, tail = head.strip(), inline(tail.strip())
        if head.startswith("fig:"):
            key = head[4:]
            if key not in figs:
                raise TemplateError(f"Unknown figure '{key}'. Known: {sorted(figs)}")
            return f"![{local[head]}. {tail}](figures/{figs[key]})"
        if head.startswith("tab:"):
            key = head[4:]
            if key not in tables.BUILDERS:
                raise TemplateError(f"Unknown table '{key}'. Known: {sorted(tables.BUILDERS)}")
            return f"**{local[head]}.** {tail}\n{{: .tcap }}\n\n{tables.BUILDERS[key](R)}"
        if head.startswith("ref:"):
            k = head[4:]
            return local["fig:" + k] if ("fig:" + k) in local else local["tab:" + k]
        if head.startswith("aref:"):
            src = appendix_numbers or local
            k = head[5:]
            if k.endswith("_tab"):
                return src["tab:" + k[:-4]]
            return src["fig:" + k] if ("fig:" + k) in src else src["tab:" + k]
        if head.startswith("code:"):
            return _code(head[5:])
        flt = tail or "int"
        if flt not in fmt.FILTERS:
            raise TemplateError(f"Unknown filter '{flt}'. Known: {sorted(fmt.FILTERS)}")
        return fmt.FILTERS[flt](_lookup(R, head))

    return DIRECTIVE.sub(sub, template)
