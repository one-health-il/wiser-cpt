"""Locate a criterion's 'Verbatim anchor' inside a source PDF and render the
relevant page(s) as PNG images with the matched text highlighted.

Anchors are messy: they stitch together non-contiguous quotes with ellipses
and '+', use smart quotes, and carry editorial notes like '(new revision)' or
a leading 'L35041:' label. So matching is best-effort and multi-fragment:

  1. Clean the anchor and split it into quote fragments.
  2. For each fragment, try the whole phrase, then progressively shorter
     prefixes and sliding windows, until PyMuPDF finds it on some page.
  3. Collect every hit's page + rectangle so the UI can render and box them.
"""
import re

import fitz  # PyMuPDF

_SMART = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "…": "...",
}


def _clean(text: str) -> str:
    text = text or ""
    for k, v in _SMART.items():
        text = text.replace(k, v)
    # drop editorial markers and leading doc-code labels (e.g. "L35041:")
    text = re.sub(r"\(\s*new revision\s*\)", " ", text, flags=re.I)
    text = re.sub(r"\b(?:NCD\s*270\.3|[LA]\d{4,6})\s*:", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fragments(anchor: str):
    """Split a cleaned anchor into quote fragments worth searching for."""
    cleaned = _clean(anchor)
    parts = re.split(r"\.\.\.|\s\+\s", cleaned)
    frags = []
    for p in parts:
        p = p.strip().strip('"\'').strip(' "\'.;:,')
        if len(p.split()) >= 3:  # ignore tiny noise fragments
            frags.append(p)
    return frags


def _candidates(fragment: str):
    """Ordered search strings for one fragment: longest first, then shorter
    prefixes, then sliding windows (to survive OCR noise at the edges)."""
    words = fragment.split()
    cands = []
    for n in range(len(words), 4, -1):       # whole -> 5-word prefix
        cands.append(" ".join(words[:n]))
    win = 8
    if len(words) > win:
        for i in range(0, len(words) - win + 1, 4):
            cands.append(" ".join(words[i:i + win]))
    seen, out = set(), []
    for c in cands:
        if c not in seen and len(c) >= 12:
            seen.add(c)
            out.append(c)
    return out


def _locate_fragment(doc, fragment):
    """Return {page_index: [rect_tuples]} for the longest candidate that hits."""
    for cand in _candidates(fragment):
        for pno in range(doc.page_count):
            rects = doc[pno].search_for(cand)
            if rects:
                return {pno: [tuple(r) for r in rects]}
    return {}


def analyze(doc_path, anchor):
    """Find every anchor fragment in the PDF.

    Returns a JSON-serialisable dict:
      n_fragments  - how many fragments we tried to match
      n_matched    - how many of them were found
      hits         - {page_index: [(x0,y0,x1,y1), ...]}
      pages        - sorted list of page indices with at least one hit
      page_count   - total pages in the document
    """
    doc = fitz.open(str(doc_path))
    frags = _fragments(anchor)
    hits, matched = {}, 0
    for frag in frags:
        loc = _locate_fragment(doc, frag)
        if loc:
            matched += 1
        for pno, rects in loc.items():
            hits.setdefault(pno, []).extend(rects)
    result = {
        "n_fragments": len(frags),
        "n_matched": matched,
        "hits": {str(k): v for k, v in hits.items()},  # str keys for caching
        "pages": sorted(hits.keys()),
        "page_count": doc.page_count,
    }
    doc.close()
    return result


def render_page(doc_path, page_index, rects=None, dpi=140,
                color=(0.99, 0.86, 0.16)):
    """Render one page as PNG bytes, drawing highlight boxes over `rects`."""
    doc = fitz.open(str(doc_path))
    page = doc[page_index]
    for r in rects or []:
        annot = page.add_highlight_annot(fitz.Rect(r))
        annot.set_colors(stroke=color)
        annot.set_opacity(0.45)
        annot.update()
    png = page.get_pixmap(dpi=dpi).tobytes("png")
    doc.close()
    return png


def page_count(doc_path):
    doc = fitz.open(str(doc_path))
    n = doc.page_count
    doc.close()
    return n
